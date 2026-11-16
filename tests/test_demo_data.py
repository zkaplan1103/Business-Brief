"""
The static demo's bundled JSON must stay in step with its generator and with the
contract shapes the dashboard reads (docs/CONTRACTS.md sections 2, 3, 5, 6, 7).
"""

import json
from pathlib import Path

from scripts.make_demo_data import OUT, build

THEME_REPORT_KEYS = {"business_id", "week", "review_count", "avg_stars", "prev_avg_stars",
                     "themes", "sufficient", "partial"}
THEME_KEYS = {"theme_id", "label", "sentiment", "review_ids", "count", "sample_quotes"}
BRIEF_KEYS = {"business_id", "business_name", "week", "summary", "trend", "action_items",
              "email_draft", "partial", "generated_by"}
ACTION_KEYS = {"rank", "theme_id", "headline", "why_it_matters", "recommended_action",
               "evidence_review_ids", "severity"}
RUN_KEYS = {"run_id", "business_id", "week", "status", "started_at", "finished_at",
            "total_cost_usd", "batches_total", "batches_failed", "note"}


def test_committed_json_matches_generator():
    assert json.loads(Path(OUT).read_text()) == build(), "rerun scripts/make_demo_data.py"


def test_demo_data_follows_contracts():
    data = build()
    assert len(data["businesses"]) >= 3
    for biz in data["businesses"]:
        bid = biz["business_id"]
        assert set(data["schedules"][bid]) == {"business_id", "cadence", "day_of_week", "email_mode"}
        assert all(set(r) == RUN_KEYS for r in data["runs"][bid])
        for week in biz["weeks"]:
            entry = data["briefs"][bid][week]
            report, brief = entry["themeReport"], entry["brief"]
            assert set(report) == THEME_REPORT_KEYS and set(brief) == BRIEF_KEYS
            assert brief["trend"] in {"up", "down", "flat"}
            ids = {rid for t in report["themes"] for rid in t["review_ids"]}
            for t in report["themes"]:
                assert set(t) == THEME_KEYS
                assert t["sentiment"] in {"positive", "negative", "mixed"}
                assert t["count"] == len(t["review_ids"]) and len(t["sample_quotes"]) <= 3
            if not report["sufficient"]:
                assert brief["action_items"] == []
            for rank, item in enumerate(brief["action_items"], start=1):
                assert set(item) == ACTION_KEYS and item["rank"] == rank
                assert item["severity"] in {"high", "medium", "low"}
                assert set(item["evidence_review_ids"]) <= ids   # evidence is traceable
            if brief["partial"]:
                assert brief["email_draft"] is None              # partial runs never draft email
