"""
Tests for GET /api/metrics.

All tests use temporary directories and fixture JSONL files — no real API calls,
no real Anthropic SDK, no network.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


def _make_event(**kwargs) -> dict:
    """Build a minimal LogEvent dict; caller overrides fields."""
    base = {
        "ts": "2026-06-14T10:00:00+00:00",
        "run_id": "run-001",
        "business_id": "demo",
        "week": "2026-W24",
        "stage": "analyze",
        "model": "claude-haiku-4-5-20251001",
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": 0.000080,
        "latency_ms": 400,
        "outcome": "ok",
        "error_class": None,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "prompt_cache_saved_usd": 0.0,
    }
    base.update(kwargs)
    return base


def _write_events(log_dir: str, filename: str, events: list[dict]) -> None:
    """Write events as JSONL to log_dir/filename."""
    path = os.path.join(log_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


class TestMetricsEmptyLogs(unittest.TestCase):
    """GET /api/metrics returns a zeroed structure when logs are empty."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        from pipeline.config import Config
        cfg = Config(log_dir=self._tmpdir)

        with patch("api.main.cfg", cfg):
            from api.main import app
            self.client = TestClient(app, raise_server_exceptions=True)

    def test_empty_log_dir_returns_zero_structure(self):
        with patch("api.main.cfg.log_dir", self._tmpdir):
            resp = self.client.get("/api/metrics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_cost_usd"], 0.0)
        self.assertEqual(data["total_calls"], 0)
        self.assertEqual(data["idempotency_skips"], 0)
        self.assertEqual(data["days_covered"], 0)
        self.assertEqual(data["by_model"], {})
        self.assertEqual(data["by_stage"], {})
        self.assertIn("generated_at", data)
        rm = data["routing_mix"]
        self.assertEqual(rm["haiku_pct"], 0.0)
        self.assertEqual(rm["sonnet_pct"], 0.0)
        self.assertEqual(rm["opus_pct"], 0.0)

    def test_runs_jsonl_is_excluded(self):
        """runs.jsonl must never be parsed as a log-event file."""
        run_record = {
            "run_id": "r1",
            "business_id": "demo",
            "week": "2026-W24",
            "status": "success",
            "started_at": "2026-06-14T10:00:00Z",
            "finished_at": "2026-06-14T10:01:00Z",
            "total_cost_usd": 0.05,
            "batches_total": 10,
            "batches_failed": 0,
            "note": None,
        }
        path = os.path.join(self._tmpdir, "runs.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps(run_record) + "\n")

        with patch("api.main.cfg.log_dir", self._tmpdir):
            resp = self.client.get("/api/metrics")
        data = resp.json()
        # runs.jsonl entries must NOT be counted
        self.assertEqual(data["total_calls"], 0)
        self.assertEqual(data["total_cost_usd"], 0.0)


class TestMetricsAggregation(unittest.TestCase):
    """Correct aggregation by model and stage."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def _client_with_log_dir(self):
        tmpdir = self._tmpdir
        from pipeline.config import Config
        cfg = Config(log_dir=tmpdir)
        with patch("api.main.cfg", cfg):
            from api.main import app
            return TestClient(app, raise_server_exceptions=True), cfg

    def test_aggregates_by_model(self):
        events = [
            _make_event(model="claude-haiku-4-5-20251001", cost_usd=0.001, latency_ms=300),
            _make_event(model="claude-haiku-4-5-20251001", cost_usd=0.002, latency_ms=500),
            _make_event(model="claude-sonnet-4-6",         cost_usd=0.010, latency_ms=800),
        ]
        _write_events(self._tmpdir, "2026-06-14.jsonl", events)
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        data = resp.json()

        self.assertEqual(data["total_calls"], 3)
        self.assertAlmostEqual(data["total_cost_usd"], 0.013, places=6)

        haiku = data["by_model"]["claude-haiku-4-5-20251001"]
        self.assertEqual(haiku["calls"], 2)
        self.assertAlmostEqual(haiku["total_cost_usd"], 0.003, places=6)
        self.assertAlmostEqual(haiku["avg_latency_ms"], 400.0, places=1)
        self.assertAlmostEqual(haiku["p95_latency_ms"], 500.0, places=1)

        sonnet = data["by_model"]["claude-sonnet-4-6"]
        self.assertEqual(sonnet["calls"], 1)
        self.assertAlmostEqual(sonnet["total_cost_usd"], 0.010, places=6)

    def test_aggregates_by_stage(self):
        events = [
            _make_event(stage="analyze", cost_usd=0.001, latency_ms=400),
            _make_event(stage="brief",   cost_usd=0.005, latency_ms=600),
            _make_event(stage="analyze", cost_usd=0.002, latency_ms=200),
        ]
        _write_events(self._tmpdir, "2026-06-14.jsonl", events)
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        data = resp.json()

        analyze = data["by_stage"]["analyze"]
        self.assertEqual(analyze["calls"], 2)
        self.assertAlmostEqual(analyze["total_cost_usd"], 0.003, places=6)
        self.assertAlmostEqual(analyze["avg_latency_ms"], 300.0, places=1)

        brief = data["by_stage"]["brief"]
        self.assertEqual(brief["calls"], 1)
        self.assertAlmostEqual(brief["total_cost_usd"], 0.005, places=6)

    def test_days_covered(self):
        _write_events(self._tmpdir, "2026-06-13.jsonl", [_make_event()])
        _write_events(self._tmpdir, "2026-06-14.jsonl", [_make_event()])
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        data = resp.json()
        self.assertEqual(data["days_covered"], 2)

    def test_token_totals(self):
        events = [
            _make_event(input_tokens=100, output_tokens=50,
                        cache_read_tokens=30, cache_creation_tokens=0,
                        prompt_cache_saved_usd=0.001),
            _make_event(input_tokens=200, output_tokens=80,
                        cache_read_tokens=0, cache_creation_tokens=150,
                        prompt_cache_saved_usd=0.0),
        ]
        _write_events(self._tmpdir, "2026-06-14.jsonl", events)
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        data = resp.json()

        m = data["by_model"]["claude-haiku-4-5-20251001"]
        self.assertEqual(m["total_input_tokens"], 300)
        self.assertEqual(m["total_output_tokens"], 130)
        self.assertEqual(m["cache_read_tokens"], 30)
        self.assertEqual(m["cache_creation_tokens"], 150)
        self.assertAlmostEqual(m["prompt_cache_saved_usd"], 0.001, places=6)


class TestMetricsRoutingMix(unittest.TestCase):
    """routing_mix percentages reflect model tier counts and always sum to ~100."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def _client_with_log_dir(self):
        tmpdir = self._tmpdir
        from pipeline.config import Config
        cfg = Config(log_dir=tmpdir)
        with patch("api.main.cfg", cfg):
            from api.main import app
            return TestClient(app, raise_server_exceptions=True), cfg

    def test_routing_mix_sums_to_100(self):
        events = [
            _make_event(model="claude-haiku-4-5-20251001"),  # 2 haiku
            _make_event(model="claude-haiku-4-5-20251001"),
            _make_event(model="claude-sonnet-4-6"),           # 1 sonnet
            _make_event(model="claude-opus-4-8"),             # 1 opus
        ]
        _write_events(self._tmpdir, "2026-06-14.jsonl", events)
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        data = resp.json()

        rm = data["routing_mix"]
        total_pct = rm["haiku_pct"] + rm["sonnet_pct"] + rm["opus_pct"]
        # Allow ±0.5 for rounding
        self.assertAlmostEqual(total_pct, 100.0, delta=0.5)

    def test_routing_mix_all_haiku(self):
        events = [_make_event(model="claude-haiku-4-5-20251001") for _ in range(4)]
        _write_events(self._tmpdir, "2026-06-14.jsonl", events)
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        data = resp.json()

        rm = data["routing_mix"]
        self.assertEqual(rm["haiku_pct"], 100.0)
        self.assertEqual(rm["sonnet_pct"], 0.0)
        self.assertEqual(rm["opus_pct"], 0.0)

    def test_routing_mix_correct_fractions(self):
        # 3 haiku out of 4 total = 75%
        events = [
            _make_event(model="claude-haiku-4-5-20251001"),
            _make_event(model="claude-haiku-4-5-20251001"),
            _make_event(model="claude-haiku-4-5-20251001"),
            _make_event(model="claude-sonnet-4-6"),
        ]
        _write_events(self._tmpdir, "2026-06-14.jsonl", events)
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        data = resp.json()

        rm = data["routing_mix"]
        self.assertEqual(rm["haiku_pct"], 75.0)
        self.assertEqual(rm["sonnet_pct"], 25.0)
        self.assertEqual(rm["opus_pct"], 0.0)


class TestMetricsIdempotencySkips(unittest.TestCase):
    """skipped_cache entries are counted as idempotency_skips, not in cost/latency."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def _client_with_log_dir(self):
        tmpdir = self._tmpdir
        from pipeline.config import Config
        cfg = Config(log_dir=tmpdir)
        with patch("api.main.cfg", cfg):
            from api.main import app
            return TestClient(app, raise_server_exceptions=True), cfg

    def test_skipped_cache_counted_as_idempotency_skips(self):
        events = [
            _make_event(outcome="ok",            cost_usd=0.001, latency_ms=400),
            _make_event(outcome="skipped_cache", cost_usd=0.0,   latency_ms=None),
            _make_event(outcome="skipped_cache", cost_usd=0.0,   latency_ms=None),
        ]
        _write_events(self._tmpdir, "2026-06-14.jsonl", events)
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        data = resp.json()

        self.assertEqual(data["idempotency_skips"], 2)
        self.assertEqual(data["total_calls"], 1)  # only the "ok" call
        self.assertAlmostEqual(data["total_cost_usd"], 0.001, places=6)

    def test_skipped_cache_excluded_from_latency(self):
        """Latency stats must only reflect real (non-skipped) calls."""
        events = [
            _make_event(outcome="ok",            cost_usd=0.001, latency_ms=300),
            _make_event(outcome="ok",            cost_usd=0.001, latency_ms=700),
            _make_event(outcome="skipped_cache", cost_usd=0.0,   latency_ms=None),
        ]
        _write_events(self._tmpdir, "2026-06-14.jsonl", events)
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        data = resp.json()

        m = data["by_model"]["claude-haiku-4-5-20251001"]
        self.assertAlmostEqual(m["avg_latency_ms"], 500.0, places=1)  # (300+700)/2
        self.assertAlmostEqual(m["p95_latency_ms"], 700.0, places=1)


class TestMetricsP95Latency(unittest.TestCase):
    """p95 latency is computed correctly."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def _client_with_log_dir(self):
        tmpdir = self._tmpdir
        from pipeline.config import Config
        cfg = Config(log_dir=tmpdir)
        with patch("api.main.cfg", cfg):
            from api.main import app
            return TestClient(app, raise_server_exceptions=True), cfg

    def test_p95_single_event(self):
        _write_events(self._tmpdir, "2026-06-14.jsonl", [_make_event(latency_ms=500)])
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        m = resp.json()["by_model"]["claude-haiku-4-5-20251001"]
        self.assertEqual(m["p95_latency_ms"], 500.0)

    def test_p95_multiple_events(self):
        # 20 events: latencies 100..2000 step 100; p95 = the 19th value = 1900
        events = [_make_event(latency_ms=i * 100) for i in range(1, 21)]
        _write_events(self._tmpdir, "2026-06-14.jsonl", events)
        client, cfg = self._client_with_log_dir()

        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        m = resp.json()["by_model"]["claude-haiku-4-5-20251001"]
        # ceil(0.95 * 20) - 1 = ceil(19) - 1 = 19 - 1 = 18 → sorted[18] = 1900
        self.assertEqual(m["p95_latency_ms"], 1900.0)


class TestMetricsAllowlists(unittest.TestCase):
    """
    RT-011: unknown model/stage strings must NOT appear as top-level keys in
    by_model / by_stage — they must be folded into an 'other' bucket.
    """

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def _client_with_log_dir(self, extra_cfg=None):
        tmpdir = self._tmpdir
        from pipeline.config import Config
        kw = dict(log_dir=tmpdir)
        if extra_cfg:
            kw.update(extra_cfg)
        cfg = Config(**kw)
        with patch("api.main.cfg", cfg):
            from api.main import app
            return TestClient(app, raise_server_exceptions=True), cfg

    def test_unknown_model_key_not_reflected_in_by_model(self):
        """
        A log event with model='attacker_model_name' must NOT produce a key
        'attacker_model_name' in by_model.  Instead it is counted in 'other'.
        """
        events = [
            _make_event(model="claude-haiku-4-5-20251001", cost_usd=0.001),
            _make_event(model="attacker_model_name",        cost_usd=0.002),
            _make_event(model="model_/../data/config",      cost_usd=0.003),
        ]
        path = os.path.join(self._tmpdir, "2026-06-14.jsonl")
        with open(path, "w") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        client, cfg = self._client_with_log_dir()
        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Known model present
        self.assertIn("claude-haiku-4-5-20251001", data["by_model"])
        # Attacker-controlled strings must NOT be top-level keys
        self.assertNotIn("attacker_model_name", data["by_model"])
        self.assertNotIn("model_/../data/config", data["by_model"])
        # Both unknown events folded into "other"
        self.assertIn("other", data["by_model"])
        self.assertEqual(data["by_model"]["other"]["calls"], 2)

    def test_unknown_stage_key_not_reflected_in_by_stage(self):
        """
        A log event with stage='secret_stage_ANTHROPIC_KEY' must NOT produce
        that string as a key in by_stage.  It must appear under 'other'.
        """
        events = [
            _make_event(stage="analyze",                  cost_usd=0.001),
            _make_event(stage="secret_stage_ANTHROPIC_KEY", cost_usd=0.002),
            _make_event(stage="../../etc/passwd",          cost_usd=0.003),
        ]
        path = os.path.join(self._tmpdir, "2026-06-14.jsonl")
        with open(path, "w") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        client, cfg = self._client_with_log_dir()
        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Known stage present
        self.assertIn("analyze", data["by_stage"])
        # Attacker-controlled strings must NOT be top-level keys
        self.assertNotIn("secret_stage_ANTHROPIC_KEY", data["by_stage"])
        self.assertNotIn("../../etc/passwd", data["by_stage"])
        # Both unknown events folded into "other"
        self.assertIn("other", data["by_stage"])
        self.assertEqual(data["by_stage"]["other"]["calls"], 2)

    def test_total_calls_includes_other_bucket_events(self):
        """
        Events in the 'other' bucket must still be counted in total_calls and
        total_cost_usd — we are just sanitising the response key, not dropping data.
        """
        events = [
            _make_event(model="claude-haiku-4-5-20251001", cost_usd=0.001),
            _make_event(model="unknown_future_model",       cost_usd=0.010),
        ]
        path = os.path.join(self._tmpdir, "2026-06-14.jsonl")
        with open(path, "w") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        client, cfg = self._client_with_log_dir()
        with patch("api.main.cfg.log_dir", cfg.log_dir):
            resp = client.get("/api/metrics")
        data = resp.json()

        self.assertEqual(data["total_calls"], 2)
        self.assertAlmostEqual(data["total_cost_usd"], 0.011, places=6)


class TestMetricsLineCap(unittest.TestCase):
    """
    RT-012: total lines processed across all files is capped at
    Config.metrics_max_lines.  When the cap is hit, 'truncated': true is set.
    """

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def _get_client(self):
        from pipeline.config import Config
        cfg = Config(log_dir=self._tmpdir)
        with patch("api.main.cfg", cfg):
            from api.main import app
            return TestClient(app, raise_server_exceptions=True), cfg

    def test_normal_response_not_truncated(self):
        """With fewer lines than the cap, truncated must be False."""
        events = [_make_event() for _ in range(10)]
        path = os.path.join(self._tmpdir, "2026-06-14.jsonl")
        with open(path, "w") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        client, cfg = self._get_client()
        # Patch both log_dir and metrics_max_lines on the module-level cfg
        with patch("api.main.cfg.log_dir", cfg.log_dir), \
             patch("api.main.cfg.metrics_max_lines", 100):
            resp = client.get("/api/metrics")
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(data["truncated"], "Expected truncated=False when under cap")
        self.assertEqual(data["total_calls"], 10)

    def test_large_log_file_triggers_truncated_flag(self):
        """
        Writing more lines than metrics_max_lines must result in truncated=True
        and at most metrics_max_lines lines processed.
        """
        cap = 100
        total_events = 300  # 3x the cap

        events = [_make_event(cost_usd=0.001) for _ in range(total_events)]
        path = os.path.join(self._tmpdir, "2026-06-14.jsonl")
        with open(path, "w") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        client, cfg = self._get_client()
        with patch("api.main.cfg.log_dir", cfg.log_dir), \
             patch("api.main.cfg.metrics_max_lines", cap):
            resp = client.get("/api/metrics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertTrue(data["truncated"], "Expected truncated=True when line cap is hit")
        # Must have processed at most `cap` lines
        self.assertLessEqual(
            data["total_calls"], cap,
            f"Expected at most {cap} calls when cap={cap}, got {data['total_calls']}"
        )

    def test_truncation_stops_at_cap_across_multiple_files(self):
        """
        The line cap applies across all files in one request, not per-file.
        With cap=50 and two files of 40 lines each, total_calls must be <= 50.
        """
        cap = 50
        for date in ("2026-06-13", "2026-06-14"):
            events = [_make_event(cost_usd=0.001) for _ in range(40)]
            path = os.path.join(self._tmpdir, f"{date}.jsonl")
            with open(path, "w") as f:
                for ev in events:
                    f.write(json.dumps(ev) + "\n")

        client, cfg = self._get_client()
        with patch("api.main.cfg.log_dir", cfg.log_dir), \
             patch("api.main.cfg.metrics_max_lines", cap):
            resp = client.get("/api/metrics")
        data = resp.json()

        self.assertTrue(data["truncated"], "Expected truncated=True when two files exceed cap")
        self.assertLessEqual(
            data["total_calls"], cap,
            f"Expected at most {cap} total calls across both files"
        )


if __name__ == "__main__":
    unittest.main()
