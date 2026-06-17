"""
Brief stage: prioritizes themes and produces a Brief (+ optional email draft).
All model calls go through reliability.call_model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from typing import TYPE_CHECKING

# Optional: only used by the CLI entry point for local runs. Absent in Lambda
# (no .env, python-dotenv not packaged); a missing dependency must not break the
# module import there.
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args, **_kwargs):  # no-op fallback
        return False

if TYPE_CHECKING:
    from pipeline.config import Config

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_BRIEF_PROMPT = """\
You are writing a weekly action brief for a small business owner.

ThemeReport:
{theme_report_json}

Return a JSON object with:
- "summary": 2-3 sentence plain-English overview of the week, written for the \
business owner (avoid jargon, be specific about what customers said)
- "trend": "up", "down", or "flat" (compare avg_stars to prev_avg_stars; \
"flat" if prev_avg_stars is null or the difference is within 0.1)
- "action_items": array of objects, each with:
    - "rank": integer starting at 1 (1 = highest priority)
    - "theme_id": from the ThemeReport
    - "headline": short punchy title (5-8 words)
    - "why_it_matters": 1-2 sentences explaining the business impact
    - "recommended_action": one concrete action the owner can take THIS week \
(be specific: who does what, by when)
    - "evidence_review_ids": a subset (up to 5) of the review_ids from that \
theme in the ThemeReport — real ids only, no fabrication
    - "severity": "high", "medium", or "low"
  Only include negative or mixed sentiment themes. Rank by: high severity \
first, then by count descending within each severity tier. Maximum 5 action \
items. If there are no negative or mixed themes, return an empty array.

Return ONLY valid JSON, no explanation, no markdown fences.
"""

_EMAIL_PROMPT = """\
You are writing a friendly, professional weekly email from a business to itself \
— a digest the owner reads to stay on top of customer feedback.

Brief:
{brief_json}

Write a short email draft (subject line + body, plain text, no HTML). Keep it \
under 250 words. Tone: direct, warm, actionable. Address the owner as "Hi [Name]," \
(leave the placeholder). End with "— Your BizBrief".

Return ONLY the email text, no extra explanation.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _validate_action_items(
    raw_items: list[dict], theme_report: dict
) -> list[dict]:
    """
    Sanitise the model-produced action_items list:
    - Keep only items whose theme_id exists in the ThemeReport.
    - Clamp evidence_review_ids to the valid set for that theme.
    - Re-number rank sequentially after filtering.
    - Cap at 5 items.
    """
    # Build a fast lookup of valid review_ids per theme.
    valid_review_ids: dict[str, set[str]] = {}
    for theme in theme_report.get("themes", []):
        tid = theme.get("theme_id", "")
        valid_review_ids[tid] = set(theme.get("review_ids", []))

    cleaned: list[dict] = []
    seen_theme_ids: set[str] = set()

    for item in raw_items:
        theme_id = item.get("theme_id", "")
        if theme_id not in valid_review_ids:
            # Model hallucinated a theme_id — drop it.
            continue
        if theme_id in seen_theme_ids:
            # Deduplicate (model sometimes emits duplicates).
            continue
        seen_theme_ids.add(theme_id)

        # Clamp evidence_review_ids.
        raw_eids = item.get("evidence_review_ids") or []
        valid_eids = [eid for eid in raw_eids if eid in valid_review_ids[theme_id]]
        item["evidence_review_ids"] = valid_eids[:5]

        # Normalise severity.
        severity = item.get("severity", "medium").lower()
        if severity not in _SEVERITY_ORDER:
            severity = "medium"
        item["severity"] = severity

        # Ensure required string fields have a fallback.
        item.setdefault("headline", f"Issue: {theme_id}")
        item.setdefault("why_it_matters", "")
        item.setdefault("recommended_action", "")

        cleaned.append(item)
        if len(cleaned) == 5:
            break

    # Re-number ranks 1..N.
    for i, item in enumerate(cleaned, start=1):
        item["rank"] = i

    return cleaned


def _parse_brief_json(text: str, theme_report: dict) -> dict:
    """
    Parse the model's JSON response into a validated brief payload.
    Returns a dict with keys: summary, trend, action_items.
    Falls back gracefully on parse errors.
    """
    # Strip any accidental markdown fences.
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop first and last fence lines.
        inner_lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        stripped = "\n".join(inner_lines).strip()

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        # Last-resort: try to find a JSON object in the text.
        start = stripped.find("{")
        end = stripped.rfind("}") + 1
        if start != -1 and end > start:
            try:
                payload = json.loads(stripped[start:end])
            except json.JSONDecodeError:
                payload = {}
        else:
            payload = {}

    summary = str(payload.get("summary") or "No summary available.")
    trend_raw = str(payload.get("trend") or "flat").lower()
    trend = trend_raw if trend_raw in ("up", "down", "flat") else "flat"
    raw_items = payload.get("action_items") or []
    if not isinstance(raw_items, list):
        raw_items = []

    action_items = _validate_action_items(raw_items, theme_report)

    return {"summary": summary, "trend": trend, "action_items": action_items}


# ---------------------------------------------------------------------------
# Main stage function
# ---------------------------------------------------------------------------


def run(
    business_id: str,
    week: str,
    cfg: "Config",
    run_id: str,
    theme_report: dict,
) -> dict:
    """
    Produce a Brief dict from a ThemeReport.

    Steps:
    1. If insufficient data → return an abstaining Brief with no model call.
    2. Call the model once for summary + trend + action_items (idempotent).
    3. Optionally call the model a second time for an email draft (idempotent).
       Email draft is suppressed for partial runs.
    4. Write Brief JSON to data/briefs/<business_id>/<week>.brief.json.
    5. Return the Brief dict.
    """
    from reliability import call_model

    # Shared mutable cost accumulator for this run.
    run_cost: list[float] = [0.0]

    business_name: str = theme_report.get("business_name") or business_id
    sufficient: bool = bool(theme_report.get("sufficient", True))
    partial: bool = bool(theme_report.get("partial", False))

    # ------------------------------------------------------------------
    # 1. Insufficient-data path — no model call needed.
    # ------------------------------------------------------------------
    if not sufficient:
        review_count = theme_report.get("review_count", 0)
        min_needed = cfg.min_reviews_for_brief
        summary = (
            f"Not enough reviews this week to produce a meaningful brief "
            f"({review_count} received; {min_needed} required). "
            f"Check back next week once more feedback has come in."
        )
        brief: dict = {
            "business_id": business_id,
            "business_name": business_name,
            "week": week,
            "summary": summary,
            "trend": "flat",
            "action_items": [],
            "email_draft": None,
            "partial": partial,
            "generated_by": cfg.gen_model,
        }
        _write_brief(brief, cfg.briefs_dir)
        return brief

    # ------------------------------------------------------------------
    # 2. Build and call the brief prompt.
    # ------------------------------------------------------------------
    theme_report_json = json.dumps(theme_report, indent=2, ensure_ascii=False)
    brief_prompt = _BRIEF_PROMPT.format(theme_report_json=theme_report_json)

    result = call_model(
        brief_prompt,
        cfg=cfg,
        stage="brief",
        run_id=run_id,
        business_id=business_id,
        week=week,
        idempotency_key=f"brief_{business_id}_{week}",
        _run_cost=run_cost,
    )

    parsed = _parse_brief_json(result.text, theme_report)

    brief = {
        "business_id": business_id,
        "business_name": business_name,
        "week": week,
        "summary": parsed["summary"],
        "trend": parsed["trend"],
        "action_items": parsed["action_items"],
        "email_draft": None,  # filled in below if applicable
        "partial": partial,
        "generated_by": result.model,
    }

    # ------------------------------------------------------------------
    # 3. Email draft — only for complete (non-partial) runs.
    #    Never auto-send; always draft-only per CONTRACTS §5.
    # ------------------------------------------------------------------
    generate_email = getattr(cfg, "email_draft", True)
    if generate_email and not partial:
        brief_json = json.dumps(brief, indent=2, ensure_ascii=False)
        email_prompt = _EMAIL_PROMPT.format(brief_json=brief_json)

        email_result = call_model(
            email_prompt,
            cfg=cfg,
            stage="brief",
            run_id=run_id,
            business_id=business_id,
            week=week,
            idempotency_key=f"emaildraft_{business_id}_{week}",
            _run_cost=run_cost,
        )
        brief["email_draft"] = email_result.text.strip() or None

    # ------------------------------------------------------------------
    # 4. Persist to disk.
    # ------------------------------------------------------------------
    _write_brief(brief, cfg.briefs_dir)

    return brief


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------


def _write_brief(brief: dict, briefs_dir: str) -> str:
    """Write brief to data/briefs/<business_id>/<week>.brief.json. Returns path."""
    business_id = brief["business_id"]
    week = brief["week"]
    out_dir = os.path.join(briefs_dir, business_id)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{week}.brief.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(brief, fh, indent=2, ensure_ascii=False)
    return out_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run the BizBrief pipeline")
    parser.add_argument("--business", required=True, help="Business ID (ASIN)")
    parser.add_argument("--week", required=True, help="ISO week, e.g. 2024-W31")
    parser.add_argument(
        "--skip-ingest", action="store_true",
        help="Skip the ingest step (use existing data/processed/reviews.jsonl)"
    )
    args = parser.parse_args()

    business_id: str = args.business
    week: str = args.week

    from pipeline.config import Config
    import pipeline.ingest as ingest_stage
    import pipeline.analyze as analyze_stage

    cfg = Config()
    run_id = str(uuid.uuid4())

    # -- Ingest --
    if args.skip_ingest:
        print(f"[ingest] Skipping — using existing data/processed/reviews.jsonl", flush=True)
    else:
        print(f"[ingest] Fetching reviews for {business_id!r} …", flush=True)
        try:
            review_count = ingest_stage.run(business_id, week, cfg)
            print(f"[ingest] {review_count:,} reviews written.", flush=True)
        except Exception as exc:
            print(f"[ingest] FAILED: {exc}", file=sys.stderr)
            sys.exit(1)

    # -- Analyze --
    print(f"[analyze] Classifying themes for {business_id!r} / {week!r} …", flush=True)
    try:
        theme_report = analyze_stage.run(business_id, week, cfg, run_id)
        print(
            f"[analyze] {len(theme_report.get('themes', []))} themes identified "
            f"(sufficient={theme_report.get('sufficient')}, "
            f"partial={theme_report.get('partial')}).",
            flush=True,
        )
    except Exception as exc:
        print(f"[analyze] FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    # -- Brief --
    print(f"[brief] Generating action brief …", flush=True)
    try:
        brief = run(business_id, week, cfg, run_id, theme_report)
    except Exception as exc:
        print(f"[brief] FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    # -- Output --
    out_path = os.path.join(
        cfg.briefs_dir, business_id, f"{week}.brief.json"
    )
    print()
    print("=" * 60)
    print(f"Business : {brief['business_name']}")
    print(f"Week     : {brief['week']}")
    print(f"Trend    : {brief['trend']}")
    print(f"Partial  : {brief['partial']}")
    print()
    print("Summary:")
    print(brief["summary"])
    print()
    if brief["action_items"]:
        print(f"Action items ({len(brief['action_items'])}):")
        for item in brief["action_items"]:
            print(
                f"  {item['rank']}. [{item['severity'].upper()}] "
                f"{item['headline']} (theme: {item['theme_id']})"
            )
    else:
        print("No action items (insufficient data or no negative/mixed themes).")
    print()
    if brief["email_draft"]:
        print("Email draft generated.")
    print(f"Output   : {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
