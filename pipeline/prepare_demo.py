"""
Demo helper: aggregates all reviews for a given business_id into a single
target week in data/processed/reviews.jsonl (overwriting that week's entries).

This is needed because the Amazon All_Beauty dataset spreads reviews thinly
(typically 1 per ASIN per week), so no single (business_id, week) pair has
enough reviews without aggregation.

Usage:
    uv run python -m pipeline.prepare_demo --business B007IAE5WY --target-week 2022-W40
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def prepare(business_id: str, target_week: str) -> int:
    """
    Re-tag all reviews for business_id with target_week, then rewrite
    data/processed/reviews.jsonl replacing the old entries for that business.

    Returns count of reviews re-tagged.
    """
    src = Path("data/processed/reviews.jsonl")
    if not src.exists():
        raise FileNotFoundError(f"{src} not found — run pipeline.ingest first")

    other_lines: list[str] = []
    business_lines: list[str] = []

    with src.open(encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            r = json.loads(raw)
            if r.get("business_id") == business_id:
                # Re-tag to target week
                r["week"] = target_week
                business_lines.append(json.dumps(r, ensure_ascii=False))
            else:
                other_lines.append(raw)

    # Write: all other reviews first, then the re-tagged business reviews
    with src.open("w", encoding="utf-8") as f:
        for line in other_lines:
            f.write(line + "\n")
        for line in business_lines:
            f.write(line + "\n")

    print(f"Re-tagged {len(business_lines)} reviews for {business_id!r} → week {target_week!r}")
    return len(business_lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate demo reviews into a single week")
    parser.add_argument("--business", required=True, help="business_id (ASIN)")
    parser.add_argument("--target-week", required=True, help="Target ISO week, e.g. 2022-W40")
    args = parser.parse_args()
    prepare(args.business, args.target_week)
