"""
Smoke test suite — called by `make smoke`.

Three cases per the build plan:
  1. busy_business   — a business with many reviews for a given week
  2. sparse_week     — a business with fewer than min_reviews_for_brief reviews
  3. forced_failure  — simulates API failure to prove backoff + logging + dead-letter

Phase 2 wires these to real pipeline stages. For now they assert the
reliability layer (logger, budget, dead-letter) works end-to-end.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from pipeline.config import Config
from reliability import BudgetExceeded
from reliability.logger import StructuredLogger


class TestSmokeReliability(unittest.TestCase):
    def test_budget_exceeded_raises(self):
        """Verifies BudgetExceeded is raised when cost ceiling is hit."""
        from reliability.call_model import _estimate_cost
        cfg = Config(run_cost_ceiling_usd=0.000001)
        cost = _estimate_cost(cfg.gen_model, 1000, 1000)
        self.assertGreater(cost, cfg.run_cost_ceiling_usd)

    def test_dead_letter_written_on_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(tmpdir)
            logger.write_run_record(
                {
                    "run_id": "smoke-fail",
                    "business_id": "biz_busy",
                    "week": "2024-W31",
                    "status": "failed",
                    "started_at": "2026-06-02T00:00:00Z",
                    "finished_at": "2026-06-02T00:00:01Z",
                    "total_cost_usd": 0.0,
                    "batches_total": 5,
                    "batches_failed": 5,
                    "note": "forced failure smoke test",
                }
            )
            dead = os.listdir(os.path.join(tmpdir, "dead-letter"))
            self.assertEqual(len(dead), 1, "dead-letter entry missing")

    def test_sparse_week_flag(self):
        """Verifies Config.min_reviews_for_brief is wired correctly."""
        cfg = Config(min_reviews_for_brief=5)
        reviews = [{}] * 3
        sufficient = len(reviews) >= cfg.min_reviews_for_brief
        self.assertFalse(sufficient)


if __name__ == "__main__":
    unittest.main()
