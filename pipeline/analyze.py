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

from pipeline.router import pick_model
from reliability import BudgetExceeded, call_model
from reliability.logger import RunRecord, StructuredLogger

if TYPE_CHECKING:
    from pipeline.config import Config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_SIZE = 20  # reviews per model call — safe within token limits

# ---------------------------------------------------------------------------
# Prompt: static system instructions (cache candidate) + dynamic user message
#
# SYSTEM_PROMPT is the large, unchanging part — it qualifies for Anthropic
# prompt caching (requires >=1024 tokens).  It is sent as a system content
# block with cache_control so the Anthropic API can store it server-side and
# serve subsequent calls at the reduced cached-input rate.
#
# The user message contains only the dynamic portion (the reviews JSON for
# the current batch), which changes on every call and must not be cached.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert customer-feedback analyst for BizBrief, a business-intelligence \
platform that turns raw customer reviews into concise, prioritized weekly action briefs \
for small-to-medium business owners.

## Your task

You will receive a batch of customer reviews for a single business, represented as a \
JSON array.  Each element has three fields:
  - "review_id" — a unique string identifier for the review (e.g. "r_001").
  - "stars"     — the numeric star rating the customer gave (1–5).
  - "text"      — the full text of the review written by the customer.

Your job is to identify the main THEMES present across all reviews in the batch and \
return them as a structured JSON array.  A theme is a recurring topic, concern, \
compliment, or pattern that appears in at least one review.  Themes should be \
meaningfully distinct from one another — do not split one idea into multiple themes \
or merge unrelated ideas into one.

## Output format

Return a JSON array.  Each element of the array is a theme object with EXACTLY these \
four fields:

  "label"
    A concise, human-readable title for the theme, written in 5–10 words.
    The label should be specific enough to be actionable.  Good examples:
      "Slow checkout process at peak hours"
      "Staff friendliness praised across many visits"
      "Inconsistent portion sizes across locations"
    Bad examples (too vague):
      "Service"
      "Good"
      "Issues with the place"

  "sentiment"
    Exactly one of three string values:
      "positive" — the theme reflects something customers appreciate.
      "negative" — the theme reflects a complaint or frustration.
      "mixed"    — the theme contains both praise and criticism, or neutral
                   observations that do not lean clearly either way.
    Choose "mixed" only when the evidence genuinely goes both ways within the
    same theme.  Do not default to "mixed" to avoid a decision.

  "review_ids"
    A JSON array of review_id strings from the input whose text contributes to
    this theme.  Every review_id you list MUST be present in the input batch.
    A review may appear under more than one theme if it discusses several topics.
    Do NOT invent, paraphrase, or truncate review_ids.

  "sample_quotes"
    A JSON array of up to 3 direct, verbatim quotations from the review texts
    that best illustrate this theme.  Each quote must be 25 words or fewer —
    trim to the most relevant phrase if the original sentence is longer.
    Use the exact words from the review; do not paraphrase.

## Rules

1. Ground every theme in the review text.  Never invent themes that the reviews
   do not support.
2. Every review_id in "review_ids" must appear verbatim in the input.
3. If there are no clear themes (e.g. the batch contains only a single one-word
   review), return an empty array: []
4. Do NOT add any explanation, commentary, markdown formatting, or code fences
   around your output.  Return ONLY the bare JSON array.
5. Do NOT include a "count" field or any field not listed above — the caller
   computes counts from the review_ids list.
6. Aim for 1–8 themes per batch.  Prefer fewer, more meaningful themes over
   many narrow ones.

## Quality bar

The output feeds a business dashboard that a business owner reads in under 15 seconds.
High-quality output is:
  - Specific (the label tells the owner exactly what to act on).
  - Evidenced (every theme has supporting review_ids and quotes).
  - Honest (sentiment matches the actual tone of the cited reviews).
  - Concise (labels are short; quotes are trimmed to the telling phrase).

Low-quality output that will be rejected:
  - Themes with vague labels like "Good service" or "Problems".
  - Review IDs that do not exist in the input.
  - Themes where the sentiment contradicts the quoted text.
  - Output with anything other than a bare JSON array (no preamble, no markdown).

## Common theme patterns across business types

To calibrate your output, here are examples of well-formed themes across different
business types.  These are illustrative — do not use them unless supported by the
actual reviews in the batch.

  Restaurants / food service:
    - "Long wait times during weekend dinner service" (negative)
    - "Signature dish praised for authentic flavor" (positive)
    - "Portion sizes inconsistent between visits" (mixed)
    - "Parking difficult; deters repeat visits" (negative)

  Retail / e-commerce:
    - "Product arrived damaged or poorly packaged" (negative)
    - "Size runs small — customers recommend sizing up" (mixed)
    - "Fast shipping and well-packaged orders" (positive)
    - "Customer service resolved issues quickly" (positive)

  Health, beauty, and personal care:
    - "Scent too strong for sensitive users" (negative)
    - "Noticeable results after consistent use" (positive)
    - "Texture clogs pores for oily skin types" (negative)
    - "Packaging leaks in transit" (negative)

  Service businesses (salons, gyms, repair):
    - "Staff knowledgeable but appointments hard to book" (mixed)
    - "Pricing higher than comparable services nearby" (negative)
    - "Results exceeded expectations on first visit" (positive)

  Electronics / gadgets:
    - "Battery drains faster than advertised" (negative)
    - "Setup intuitive even for non-technical users" (positive)
    - "Build quality feels premium for the price" (positive)
    - "Companion app crashes on older phones" (negative)

  Home and kitchen:
    - "Durable construction survives heavy daily use" (positive)
    - "Smaller than expected from product photos" (mixed)
    - "Difficult to clean; food residue sticks" (negative)
    - "Assembly instructions unclear or missing steps" (negative)

These patterns show the level of specificity expected.  Always derive themes from
the actual review text in the batch, not from these examples.

## Handling edge cases

Reviews are messy.  Apply these rules consistently so output stays comparable
across batches and across business types:

  - Off-topic reviews: A review that discusses shipping, the seller, or Amazon
    itself rather than the product is still valid evidence for a logistics or
    fulfilment theme (e.g. "Frequent late deliveries").  Do not discard it, but
    do not force it into a product-quality theme where it does not belong.

  - One-word or empty reviews: A review whose text is "Great!", "ok", or blank
    carries a sentiment signal but no thematic content.  Do not create a theme
    solely to hold such reviews.  You may attach them to an existing theme only
    when the star rating and minimal text clearly align with that theme.

  - Sarcasm and negation: Read for intent, not surface words.  "Oh sure, it
    lasted a whole TWO days" is negative despite the word "sure".  "Not bad at
    all" is positive.  Weigh the star rating as a tiebreaker when the text is
    genuinely ambiguous.

  - Contradictory signals within one review: A reviewer who praises the scent
    but complains about the price contributes to two distinct themes, not one
    "mixed" theme.  Split the review's contribution by topic; reserve "mixed"
    sentiment for a single topic that genuinely cuts both ways.

  - Volume vs. importance: A complaint mentioned by one reviewer in strong terms
    (e.g. a safety concern, a billing error) can be more actionable than a mild
    preference mentioned by many.  Surface it as its own theme even if it has a
    single supporting review — the owner needs to see it.

  - Duplicate or near-duplicate reviews: If two reviews are clearly the same
    text posted twice, cite both review_ids under the relevant theme but do not
    treat the repetition as additional evidence of prevalence.

## Calibration on theme count

Most healthy batches of 10–30 reviews yield 3–6 themes.  Fewer than 3 usually
means you have merged distinct concerns; more than 8 usually means you have
split one concern into slivers.  Re-read your draft themes and merge any two
that an owner would naturally act on together, and split any single theme that
bundles an unrelated praise and complaint.

## Final self-check before returning

Before you emit the JSON array, verify each of the following.  If any check
fails, revise the output rather than returning it as-is:

  1. Every "label" is 5–10 words, specific, and names something the owner can
     act on — not a single vague noun like "Service" or "Quality".
  2. Every "sentiment" value is exactly one of "positive", "negative", or
     "mixed", and matches the tone of the cited quotes.
  3. Every entry in "review_ids" appears verbatim in the input batch — no
     invented, paraphrased, or partial identifiers.
  4. Every "sample_quotes" entry is a verbatim substring of a cited review and
     is 25 words or fewer.
  5. The themes are mutually distinct — no two themes that an owner would treat
     as the same action item.
  6. The output is a bare JSON array with no preamble, no trailing commentary,
     and no markdown code fences.

Return the array only after all six checks pass.
"""

# The user message template — contains only the dynamic reviews JSON.
# This is NOT cached because it changes with every batch call.
_USER_TEMPLATE = """\
Reviews (JSON array):
{reviews_json}

Return ONLY valid JSON (a bare array), no code fences, no explanation.\
"""

# Build the system content block with cache_control so Anthropic caches the
# static instructions across calls.  The block format is required (plain
# string system prompts do not support cache_control).
_SYSTEM_BLOCK: list[dict] = [
    {
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }
]


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
        # User message: only the dynamic reviews JSON (not cached).
        prompt = _USER_TEMPLATE.format(reviews_json=reviews_json)
        ikey = f"analyze_{business_id}_{week}_{batch_idx}"

        # Router: pick cheapest tier that can handle this batch's complexity.
        # The chosen model is logged automatically because call_model logs the
        # effective_model (= the override we pass in).
        chosen_model = pick_model(batch, cfg)

        try:
            result = call_model(
                prompt,
                cfg=cfg,
                stage="analyze",
                run_id=run_id,
                business_id=business_id,
                week=week,
                idempotency_key=ikey,
                model=chosen_model,
                system=_SYSTEM_BLOCK,
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
