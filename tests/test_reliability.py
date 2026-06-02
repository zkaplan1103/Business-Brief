"""Unit tests for the reliability wrapper."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from pipeline.config import Config
from reliability.logger import StructuredLogger


class TestStructuredLogger(unittest.TestCase):
    def test_emit_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(tmpdir)
            logger.emit(
                {
                    "ts": "2026-06-02T00:00:00Z",
                    "run_id": "test-run",
                    "business_id": "biz1",
                    "week": "2026-W22",
                    "stage": "test",
                    "outcome": "ok",
                }
            )
            logs = [f for f in os.listdir(tmpdir) if f.endswith(".jsonl")]
            self.assertEqual(len(logs), 1)

    def test_failed_run_writes_dead_letter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(tmpdir)
            logger.write_run_record(
                {
                    "run_id": "dead-run",
                    "business_id": "biz1",
                    "week": "2026-W22",
                    "status": "failed",
                    "started_at": "2026-06-02T00:00:00Z",
                    "finished_at": "2026-06-02T00:01:00Z",
                    "total_cost_usd": 0.0,
                    "batches_total": 1,
                    "batches_failed": 1,
                    "note": "test failure",
                }
            )
            dead = os.listdir(os.path.join(tmpdir, "dead-letter"))
            self.assertEqual(len(dead), 1)


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = Config()
        self.assertEqual(cfg.max_retries, 4)
        self.assertAlmostEqual(cfg.run_cost_ceiling_usd, 1.00)
        self.assertIn(429, cfg.retry_on)
        self.assertNotIn(400, cfg.retry_on)
        self.assertNotIn(401, cfg.retry_on)


if __name__ == "__main__":
    unittest.main()
