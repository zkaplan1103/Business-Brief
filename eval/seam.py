"""Eval seam — interface documented, metrics NOT implemented. Phase 3."""

import json
from typing import TypedDict


class GoldenWeek(TypedDict):
    business_id: str
    week: str
    expected_top_theme_labels: list[str]


def load_golden(path: str) -> list[GoldenWeek]:
    with open(path) as f:
        return json.load(f)
