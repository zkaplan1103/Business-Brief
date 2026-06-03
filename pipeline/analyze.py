"""
Analysis stage: classifies reviews into themes and produces a ThemeReport.
All model calls go through reliability.call_model — never the SDK directly.

Reads:  data/processed/reviews.jsonl  (filtered to business_id + week)
Writes: data/briefs/<business_id>/<week>.themes.json
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from dotenv import load_dotenv

load_dotenv()  # picks up ANTHROPIC_API_KEY from .env at project root

from reliability import BudgetExceeded, call_model
from reliability.logger import RunRecord, StructuredLogger

if TYPE_CHECKING:
    from pipeline.config import Config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_SIZE = 20  # reviews per model call — safe within token limits

_PROMPT_TEMPLATE = """\
You are analyzing customer reviews for a business. Identify the main themes across these reviews.

Reviews (JSON array):
{reviews_json}

Return a JSON array of theme objects. Each object MUST have exactly these fields:
- "label": short descriptive label, 5-10 words
- "sentiment": exactly one of "positive", "negative", or "mixed"
- "review_ids": list of review_id strings from the input that belong to this theme
- "sample_quotes": list of up to 3 direct quotes from the reviews, each 25 words or fewer

Rules:
- Every review_id you list MUST appear in the input above.
- A review_id may appear in more than one theme if it discusses multiple topics.
- If there are no clear themes, return an empty array [].
- Do NOT include any explanation, markdown, or text outside the JSON.

Return ONLY valid JSON (a bare array), no code fences, no explanation."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_reviews(processed_path: str, business_id: str, week: str) -> list[dict]:
    """Read reviews.jsonl and return only those matching business_id + week."""
    reviews: list[dict] = []
    if not os.path.exists(processed_path):
        return reviews
    with open(processed_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("business_id") == business_id and obj.get("week") == week:
                reviews.append(obj)
    return reviews


def _extract_json_array(text: str) -> list | None:
    """
    Parse a JSON array from model output.
    Strips optional code fences (```json ... ```) before parsing.
    Returns None on any parse failure.
    """
    # Strip optional markdown code fences.
    stripped = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # Find the outermost array.
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None


def _truncate_quote(text: str, max_words: int = 25) -> str:
    """Return text truncated to max_words words, appending '…' if cut."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


def _make_theme_id(label: str, idx: int) -> str:
    """Produce a stable slug from label + ordinal index."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40]
    return f"theme_{idx:02d}_{slug}"


def _parse_batch_themes(
    raw_themes: list,
    valid_ids: set[str],
    batch_idx: int,
) -> list[dict]:
    """
    Validate and normalise theme objects returned by the model for one batch.
    Skips malformed objects; silently drops review_ids not present in the batch.
    """
    out: list[dict] = []
    for raw in raw_themes:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label", "")).strip()
        sentiment = str(raw.get("sentiment", "mixed")).strip().lower()
        if sentiment not in {"positive", "negative", "mixed"}:
            sentiment = "mixed"
        review_ids = [
            rid
            for rid in raw.get("review_ids", [])
            if isinstance(rid, str) and rid in valid_ids
        ]
        if not review_ids:
            # Theme with zero valid evidence — skip it.
            continue
        raw_quotes = raw.get("sample_quotes", [])
        sample_quotes = [
            _truncate_quote(str(q))
            for q in raw_quotes
            if isinstance(q, str) and q.strip()
        ][:3]
        out.append(
            {
                "label": label,
                "sentiment": sentiment,
                "review_ids": review_ids,
                "sample_quotes": sample_quotes,
            }
        )
    return out


def _merge_themes(all_batch_themes: list[list[dict]], max_themes: int) -> list[dict]:
    """
    Merge theme lists from multiple batches.

    Strategy: exact label match (case-insensitive) → merge review_ids and
    extend sample_quotes (deduplicated, capped at 3). After merging, assign
    stable theme_ids and rank by count descending, capped at max_themes.
    """
    merged: dict[str, dict] = {}  # normalised_label -> merged theme
    for batch in all_batch_themes:
        for theme in batch:
            key = theme["label"].lower().strip()
            if key in merged:
                existing = merged[key]
                # Merge review_ids (deduplicate, preserve order).
                seen = set(existing["review_ids"])
                for rid in theme["review_ids"]:
                    if rid not in seen:
                        existing["review_ids"].append(rid)
                        seen.add(rid)
                # Extend quotes up to 3.
                existing_q_set = set(existing["sample_quotes"])
                for q in theme["sample_quotes"]:
                    if q not in existing_q_set and len(existing["sample_quotes"]) < 3:
                        existing["sample_quotes"].append(q)
                        existing_q_set.add(q)
            else:
                merged[key] = {
                    "label": theme["label"],
                    "sentiment": theme["sentiment"],
                    "review_ids": list(theme["review_ids"]),
                    "sample_quotes": list(theme["sample_quotes"]),
                }

    # Sort by count descending, cap at max_themes.
    sorted_themes = sorted(
        merged.values(), key=lambda t: len(t["review_ids"]), reverse=True
    )[:max_themes]

    # Assign final theme_ids and counts.
    result: list[dict] = []
    for idx, t in enumerate(sorted_themes, start=1):
        result.append(
            {
                "theme_id": _make_theme_id(t["label"], idx),
                "label": t["label"],
                "sentiment": t["sentiment"],
                "review_ids": t["review_ids"],
                "count": len(t["review_ids"]),
                "sample_quotes": t["sample_quotes"],
            }
        )
    return result


def _prev_avg_stars(
    business_id: str, week: str, briefs_dir: str
) -> float | None:
    """
    Look for the themes file from the immediately preceding ISO week.
    Returns avg_stars from that file if found, otherwise None.
    """
    try:
        # Parse week like "2024-W31"
        match = re.match(r"^(\d{4})-W(\d{1,2})$", week)
        if not match:
            return None
        year, wnum = int(match.group(1)), int(match.group(2))
        if wnum > 1:
            prev_week = f"{year}-W{wnum - 1:02d}"
        else:
            prev_week = f"{year - 1}-W52"
        prev_path = os.path.join(
            briefs_dir, business_id, f"{prev_week}.themes.json"
        )
        if not os.path.exists(prev_path):
            return None
        with open(prev_path, encoding="utf-8") as f:
            prev_report = json.load(f)
        val = prev_report.get("avg_stars")
        return float(val) if val is not None else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    business_id: str,
    week: str,
    cfg: "Config",
    run_id: str,
) -> dict:
    """
    Classify reviews for (business_id, week) into themes.

    Returns a ThemeReport dict (see CONTRACTS.md §2) and writes it to
    data/briefs/<business_id>/<week>.themes.json.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    logger = StructuredLogger(cfg.log_dir)
    _run_cost: list[float] = [0.0]

    # ------------------------------------------------------------------
    # 1. Load reviews
    # ------------------------------------------------------------------
    processed_path = os.path.join("data", "processed", "reviews.jsonl")
    reviews = _load_reviews(processed_path, business_id, week)
    review_count = len(reviews)

    avg_stars: float = 0.0
    if review_count:
        avg_stars = round(
            sum(r.get("stars", 0.0) for r in reviews) / review_count, 2
        )

    prev_avg = _prev_avg_stars(business_id, week, cfg.briefs_dir)

    # ------------------------------------------------------------------
    # 2. Insufficient-data short-circuit
    # ------------------------------------------------------------------
    if review_count < cfg.min_reviews_for_brief:
        report: dict = {
            "business_id": business_id,
            "week": week,
            "review_count": review_count,
            "avg_stars": avg_stars,
            "prev_avg_stars": prev_avg,
            "themes": [],
            "sufficient": False,
            "partial": False,
        }
        _write_report(report, business_id, week, cfg.briefs_dir)
        _write_run_record(
            logger,
            run_id=run_id,
            business_id=business_id,
            week=week,
            status="success",
            started_at=started_at,
            total_cost_usd=0.0,
            batches_total=0,
            batches_failed=0,
            note=f"Insufficient reviews ({review_count} < {cfg.min_reviews_for_brief}); no brief produced.",
        )
        return report

    # ------------------------------------------------------------------
    # 3. Batch and classify
    # ------------------------------------------------------------------
    batches = [
        reviews[i : i + BATCH_SIZE] for i in range(0, review_count, BATCH_SIZE)
    ]
    batches_total = len(batches)
    batches_failed = 0
    partial = False
    all_batch_themes: list[list[dict]] = []

    for batch_idx, batch in enumerate(batches):
        valid_ids = {r["review_id"] for r in batch if "review_id" in r}
        reviews_json = json.dumps(
            [
                {
                    "review_id": r.get("review_id"),
                    "stars": r.get("stars"),
                    "text": r.get("text", ""),
                }
                for r in batch
            ],
            ensure_ascii=False,
        )
        prompt = _PROMPT_TEMPLATE.format(reviews_json=reviews_json)
        ikey = f"analyze_{business_id}_{week}_{batch_idx}"

        try:
            result = call_model(
                prompt,
                cfg=cfg,
                stage="analyze",
                run_id=run_id,
                business_id=business_id,
                week=week,
                idempotency_key=ikey,
                _run_cost=_run_cost,
                _logger=logger,
            )
        except BudgetExceeded:
            # Budget exhausted — mark remaining batches as failed and stop.
            batches_failed += batches_total - batch_idx
            partial = True
            break
        except Exception:
            # Batch failed after all retries; log already emitted by call_model.
            batches_failed += 1
            partial = True
            continue

        # Parse the model's JSON response defensively.
        raw_themes = _extract_json_array(result.text)
        if raw_themes is None:
            # Unparseable response — treat as a soft batch failure.
            batches_failed += 1
            partial = True
            continue

        parsed = _parse_batch_themes(raw_themes, valid_ids, batch_idx)
        all_batch_themes.append(parsed)

    # ------------------------------------------------------------------
    # 4. Merge themes across batches
    # ------------------------------------------------------------------
    themes = _merge_themes(all_batch_themes, cfg.max_themes)

    # ------------------------------------------------------------------
    # 5. Assemble and write ThemeReport
    # ------------------------------------------------------------------
    status = "success"
    note: str | None = None
    if batches_failed > 0:
        status = "partial" if all_batch_themes else "failed"
        note = (
            f"{batches_failed}/{batches_total} batches failed; "
            f"brief produced from {batches_total - batches_failed}"
        )

    report = {
        "business_id": business_id,
        "week": week,
        "review_count": review_count,
        "avg_stars": avg_stars,
        "prev_avg_stars": prev_avg,
        "themes": themes,
        "sufficient": True,
        "partial": partial,
    }

    _write_report(report, business_id, week, cfg.briefs_dir)
    _write_run_record(
        logger,
        run_id=run_id,
        business_id=business_id,
        week=week,
        status=status,
        started_at=started_at,
        total_cost_usd=round(_run_cost[0], 6),
        batches_total=batches_total,
        batches_failed=batches_failed,
        note=note,
    )

    return report


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _write_report(
    report: dict, business_id: str, week: str, briefs_dir: str
) -> None:
    out_dir = os.path.join(briefs_dir, business_id)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{week}.themes.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def _write_run_record(
    logger: StructuredLogger,
    *,
    run_id: str,
    business_id: str,
    week: str,
    status: str,
    started_at: str,
    total_cost_usd: float,
    batches_total: int,
    batches_failed: int,
    note: str | None,
) -> None:
    logger.write_run_record(
        RunRecord(
            run_id=run_id,
            business_id=business_id,
            week=week,
            status=status,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            total_cost_usd=total_cost_usd,
            batches_total=batches_total,
            batches_failed=batches_failed,
            note=note,
        )
    )


# ---------------------------------------------------------------------------
# Entry-point guard
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("analyze stage ready — run via pipeline.brief")
