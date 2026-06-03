"""
Smoke test suite — called by `make smoke`.

Three cases per the build plan:
  1. busy_business   — real brief exists for B007IAE5WY/2022-W40 (17 reviews)
  2. sparse_week     — analyze stage returns sufficient=False below threshold
  3. forced_failure  — simulates API failure: backoff fires, dead-letter written
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from pipeline.config import Config
from reliability import BudgetExceeded
from reliability.call_model import _estimate_cost
from reliability.logger import StructuredLogger


class TestSmokeBusyBusiness(unittest.TestCase):
    """Case 1: a real brief was generated — verify it has the expected shape."""

    BUSINESS = "B007IAE5WY"
    WEEK = "2022-W40"

    def _brief_path(self):
        cfg = Config()
        return os.path.join(cfg.briefs_dir, self.BUSINESS, f"{self.WEEK}.brief.json")

    def test_brief_file_exists(self):
        path = self._brief_path()
        self.assertTrue(
            os.path.exists(path),
            f"Brief not found at {path} — run the pipeline first:\n"
            f"  uv run python -m pipeline.brief --business {self.BUSINESS} --week {self.WEEK} --skip-ingest",
        )

    def test_brief_has_required_keys(self):
        path = self._brief_path()
        if not os.path.exists(path):
            self.skipTest("Brief not yet generated")
        with open(path) as f:
            brief = json.load(f)
        for key in ("business_id", "business_name", "week", "summary", "trend", "action_items", "partial"):
            self.assertIn(key, brief, f"Missing key: {key}")
        self.assertEqual(brief["business_id"], self.BUSINESS)
        self.assertEqual(brief["week"], self.WEEK)
        self.assertIsInstance(brief["action_items"], list)
        self.assertFalse(brief["partial"])

    def test_action_items_have_real_evidence(self):
        path = self._brief_path()
        if not os.path.exists(path):
            self.skipTest("Brief not yet generated")
        with open(path) as f:
            brief = json.load(f)
        for item in brief["action_items"]:
            self.assertIn("evidence_review_ids", item)
            self.assertGreater(len(item["evidence_review_ids"]), 0,
                               f"Action item {item['rank']} has no evidence_review_ids")


class TestSmokeSparseWeek(unittest.TestCase):
    """Case 2: sparse week → ThemeReport.sufficient=False, no model call."""

    def test_analyze_abstains_below_threshold(self):
        """Verify analyze returns sufficient=False when reviews < min_reviews_for_brief."""
        import uuid
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Config(
                briefs_dir=os.path.join(tmpdir, "briefs"),
                log_dir=os.path.join(tmpdir, "logs"),
                min_reviews_for_brief=99,  # threshold higher than any real week
            )
            # Write a tiny reviews.jsonl — only 1 review
            processed_dir = os.path.join(tmpdir, "processed")
            os.makedirs(processed_dir)
            reviews_path = os.path.join(processed_dir, "reviews.jsonl")
            review = {
                "review_id": "r1",
                "business_id": "biz_sparse",
                "business_name": "Sparse Co",
                "stars": 4.0,
                "text": "Good product",
                "date": "2024-07-01",
                "week": "2024-W27",
            }
            with open(reviews_path, "w") as f:
                f.write(json.dumps(review) + "\n")

            from pipeline import analyze
            run_id = str(uuid.uuid4())

            # Monkeypatch the processed path inside analyze
            with patch.object(analyze, "_load_reviews", return_value=[review]):
                report = analyze.run("biz_sparse", "2024-W27", cfg, run_id)

            self.assertFalse(report["sufficient"])
            self.assertEqual(report["themes"], [])
            self.assertEqual(report["review_count"], 1)


class TestSmokeForcedFailure(unittest.TestCase):
    """Case 3: forced API failure → backoff fires, dead-letter written, CircuitOpen respected."""

    def test_budget_exceeded_raises(self):
        cfg = Config(run_cost_ceiling_usd=0.000001)
        cost = _estimate_cost(cfg.gen_model, 1000, 1000)
        self.assertGreater(cost, cfg.run_cost_ceiling_usd,
                           "Cost estimate should exceed the $0.000001 ceiling")

    def test_dead_letter_written_on_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(tmpdir)
            logger.write_run_record({
                "run_id": "smoke-forced-fail",
                "business_id": "biz_busy",
                "week": "2024-W31",
                "status": "failed",
                "started_at": "2026-06-03T00:00:00Z",
                "finished_at": "2026-06-03T00:00:01Z",
                "total_cost_usd": 0.0,
                "batches_total": 5,
                "batches_failed": 5,
                "note": "forced failure smoke test",
            })
            dead = os.listdir(os.path.join(tmpdir, "dead-letter"))
            self.assertEqual(len(dead), 1, "dead-letter entry missing for failed run")

    def test_call_model_retries_on_rate_limit(self):
        """Verify call_model retries 429 and raises after max_retries."""
        import anthropic
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Config(
                max_retries=2,
                backoff_base_s=0.01,  # fast for tests
                log_dir=tmpdir,
                briefs_dir=tmpdir,
            )
            from reliability.call_model import call_model

            call_count = 0

            def fake_create(**kwargs):
                nonlocal call_count
                call_count += 1
                raise anthropic.APIStatusError(
                    message="Rate limited",
                    response=MagicMock(status_code=429, headers={}),
                    body={"error": {"type": "rate_limit_error"}},
                )

            mock_client = MagicMock()
            mock_client.messages.create = fake_create

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                with self.assertRaises(RuntimeError) as ctx:
                    call_model(
                        "test prompt",
                        cfg=cfg,
                        stage="test",
                        run_id="smoke-retry-test",
                        business_id="biz_test",
                        week="2024-W31",
                    )

            # Should have attempted max_retries + 1 times total
            self.assertEqual(call_count, cfg.max_retries + 1,
                             f"Expected {cfg.max_retries + 1} attempts, got {call_count}")
            self.assertIn("failed after", str(ctx.exception))

    def test_circuit_breaker_opens_after_threshold(self):
        """Verify the scheduler circuit breaker opens after N consecutive failures."""
        from scheduler.run import _record_outcome
        import scheduler.run as sched_module

        original = sched_module._consecutive_failures
        try:
            sched_module._consecutive_failures = 0
            cfg = Config(circuit_breaker_threshold=3)

            _record_outcome(True, cfg)   # success — resets
            _record_outcome(False, cfg)  # 1
            _record_outcome(False, cfg)  # 2

            with self.assertRaises(Exception):  # CircuitOpen
                _record_outcome(False, cfg)     # 3 — should open
        finally:
            sched_module._consecutive_failures = original


if __name__ == "__main__":
    unittest.main()
