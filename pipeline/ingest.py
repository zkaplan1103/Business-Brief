"""
Ingest stage: downloads the Amazon Reviews 2023 dataset (All_Beauty subset)
via Hugging Face and emits normalized Review objects to data/processed/reviews.jsonl.

The dataset's loading script is no longer supported by datasets>=4.x, so we
download the raw JSONL directly via huggingface_hub and stream-parse it —
this avoids loading the full 327 MB file into memory at once.

Usage:
    uv run python -m pipeline.ingest
    uv run python -m pipeline.ingest --business <asin> --week <YYYY-Www>
"""

from __future__ import annotations

import json
import re
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from pipeline.config import Config


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATASET_REPO = "McAuley-Lab/Amazon-Reviews-2023"
REVIEW_FILE  = "raw/review_categories/All_Beauty.jsonl"
META_FILE    = "raw/meta_categories/meta_All_Beauty.jsonl"
MAX_REVIEWS  = 5_000


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def _clean_text(raw: str | None) -> str:
    """Strip null bytes, collapse whitespace, trim."""
    if not raw:
        return ""
    text = raw.replace("\x00", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _ms_to_date_week(timestamp_ms: int | float) -> tuple[str, str]:
    """Convert a millisecond epoch timestamp to (ISO date, ISO week string)."""
    dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    date_str = dt.date().isoformat()          # YYYY-MM-DD
    iso_cal  = dt.isocalendar()
    week_str = f"{iso_cal[0]}-W{iso_cal[1]:02d}"
    return date_str, week_str


# ---------------------------------------------------------------------------
# Streaming JSONL reader
# ---------------------------------------------------------------------------

def _stream_jsonl(path: str) -> Iterator[dict]:
    """Yield parsed JSON objects from a JSONL file, skipping malformed lines."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                pass


# ---------------------------------------------------------------------------
# Core ingest function
# ---------------------------------------------------------------------------

def run(business_id: str | None, week: str | None, cfg: "Config") -> int:
    """
    Download/cache the Amazon Reviews 2023 All_Beauty JSONL from HF Hub,
    normalize to the Review schema, optionally filter by business_id,
    and write to data/processed/reviews.jsonl.

    Returns the count of reviews written.
    """
    from huggingface_hub import hf_hub_download  # type: ignore

    # ------------------------------------------------------------------
    # 1. Download (or use cached) raw JSONL files
    # ------------------------------------------------------------------
    print("Downloading/caching All_Beauty reviews JSONL from Hugging Face …", flush=True)
    review_path = hf_hub_download(
        repo_id=DATASET_REPO,
        filename=REVIEW_FILE,
        repo_type="dataset",
    )
    print(f"  Reviews file: {review_path}", flush=True)

    # Metadata is optional — product titles
    title_lookup: dict[str, str] = {}
    print("Downloading/caching All_Beauty metadata JSONL …", flush=True)
    try:
        meta_path = hf_hub_download(
            repo_id=DATASET_REPO,
            filename=META_FILE,
            repo_type="dataset",
        )
        print(f"  Metadata file: {meta_path}", flush=True)
        for row in _stream_jsonl(meta_path):
            asin  = row.get("parent_asin") or row.get("asin") or ""
            title = row.get("title") or ""
            if asin and title:
                title_lookup[asin] = _clean_text(title)
        print(f"  Loaded {len(title_lookup):,} product titles.", flush=True)
    except Exception as exc:
        print(f"  Warning: could not load metadata ({exc}); falling back to ASIN as name.", flush=True)

    # ------------------------------------------------------------------
    # 2. Stream reviews, filter, normalize, write
    # ------------------------------------------------------------------
    out_dir  = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "reviews.jsonl"

    written = 0
    print(f"Writing normalized reviews to {out_path} …", flush=True)

    with out_path.open("w", encoding="utf-8") as fh:
        for i, row in enumerate(_stream_jsonl(review_path)):
            if written >= MAX_REVIEWS:
                break

            asin: str        = row.get("asin") or ""
            parent_asin: str = row.get("parent_asin") or asin

            # Optional filter
            if business_id and asin != business_id and parent_asin != business_id:
                continue

            # review_id
            review_id: str = row.get("review_id") or f"{asin}_{i}"

            # stars
            try:
                stars = float(row.get("rating", 0.0))
            except (TypeError, ValueError):
                stars = 0.0

            # text
            text = _clean_text(row.get("text") or "")

            # date + week from timestamp (milliseconds)
            ts = row.get("timestamp")
            if ts is not None:
                try:
                    date_str, week_str = _ms_to_date_week(int(ts))
                except (TypeError, ValueError):
                    date_str, week_str = "", ""
            else:
                date_str, week_str = "", ""

            # business_name: parent_asin title > asin title > asin
            business_name = (
                title_lookup.get(parent_asin)
                or title_lookup.get(asin)
                or asin
            )

            review: dict = {
                "review_id":     review_id,
                "business_id":   asin,
                "business_name": business_name,
                "stars":         stars,
                "text":          text,
                "date":          date_str,
                "week":          week_str,
            }

            fh.write(json.dumps(review, ensure_ascii=False) + "\n")
            written += 1

    print(f"Wrote {written:,} reviews to {out_path}", flush=True)
    return written


# ---------------------------------------------------------------------------
# __main__ entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tideline ingest: Amazon Reviews 2023 All_Beauty → reviews.jsonl"
    )
    parser.add_argument(
        "--business", default=None,
        help="Filter to a single ASIN (business_id). Omit to take the first 5000 reviews."
    )
    parser.add_argument(
        "--week", default=None,
        help="ISO week string (passed through for API compatibility; not used in ingest)."
    )
    args = parser.parse_args()

    from pipeline.config import Config
    cfg = Config()

    count = run(args.business, args.week, cfg)

    # Sample 3 lines
    out_path = Path("data/processed/reviews.jsonl")
    print("\n--- Sample (3 lines) ---")
    with out_path.open(encoding="utf-8") as fh:
        for j, line in enumerate(fh):
            if j >= 3:
                break
            print(json.dumps(json.loads(line), indent=2, ensure_ascii=False))

    # Summary
    print("\n--- Summary ---")
    weeks: dict[str, int] = {}
    biz_ids: set[str]     = set()
    with out_path.open(encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            w   = obj.get("week", "")
            weeks[w] = weeks.get(w, 0) + 1
            biz_ids.add(obj.get("business_id", ""))

    print(f"Total reviews written : {count:,}")
    print(f"Unique business_ids   : {len(biz_ids):,}  (first 10: {sorted(biz_ids)[:10]})")
    print(f"Unique weeks          : {len(weeks):,}  (first 10: {sorted(weeks.keys())[:10]})")
    sys.exit(0)
