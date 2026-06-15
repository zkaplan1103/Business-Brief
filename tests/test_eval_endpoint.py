"""
Tests for GET /api/eval — the static quality-vs-cost eval artifact endpoint.

No network, no model calls: the endpoint reads eval/results.json (or returns
{"available": false} when absent) so the dashboard Eval tab can render or fall
back to its bundled fixture.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


class TestEvalEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=True)

    def test_returns_results_when_present(self):
        # The repo ships eval/results.json, so the live endpoint returns it.
        resp = self.client.get("/api/eval")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["available"])
        self.assertIn("rows", data)
        labels = {r["label"] for r in data["rows"]}
        self.assertEqual(labels, {"Haiku", "Sonnet", "Opus"})

    def test_rows_have_required_score_fields(self):
        data = self.client.get("/api/eval").json()
        for row in data["rows"]:
            for key in ("cost_usd", "label_f1", "evidence_overlap",
                        "sentiment_accuracy", "matched_themes", "total_golden_themes"):
                self.assertIn(key, row)

    def test_missing_artifact_returns_unavailable_not_error(self):
        # Point cwd at an empty dir so eval/results.json does not exist.
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                resp = self.client.get("/api/eval")
            finally:
                os.chdir(cwd)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"available": False})

    def test_malformed_artifact_returns_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "eval"))
            with open(os.path.join(tmp, "eval", "results.json"), "w") as f:
                f.write("{not valid json")
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                resp = self.client.get("/api/eval")
            finally:
                os.chdir(cwd)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["available"])


if __name__ == "__main__":
    unittest.main()
