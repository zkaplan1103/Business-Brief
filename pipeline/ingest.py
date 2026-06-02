"""
Ingest stage: loads raw Yelp/Amazon review files from data/raw/ and emits
normalized Review objects to data/processed/reviews.jsonl.

Implemented by the data-engineer in Phase 1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.config import Config


def run(business_id: str, week: str, cfg: "Config") -> int:
    """Return count of reviews written. Stub — Phase 1."""
    raise NotImplementedError("ingest stage not yet implemented")
