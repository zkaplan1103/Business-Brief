"""
Tests for the serverless (Phase 7) layer.

These cover the AWS-independent surface — key design, event parsing, metric
payload shaping, and row normalization — so the infra/ code is exercised by CI
without needing boto3, Docker, or an AWS account.  The boto3-touching functions
(put_reviews, get_reviews, etc.) are intentionally not unit-tested here; they
are integration-tested against DynamoDB Local / moto in the deploy workflow.
"""

import os
import sys

import pytest

# Make the Lambda handlers importable the same way Lambda does (handlers sit at
# the package root alongside the vendored pipeline/ + reliability/).
_INFRA_LAMBDAS = os.path.join(os.path.dirname(__file__), "..", "infra", "lambdas")
sys.path.insert(0, os.path.abspath(_INFRA_LAMBDAS))

# Metric emission must be a no-op in tests (no CloudWatch).
os.environ.setdefault("BIZBRIEF_METRICS_DISABLED", "1")

import storage          # noqa: E402
import metrics          # noqa: E402


# ---------------------------------------------------------------------------
# storage — key helpers
# ---------------------------------------------------------------------------

class TestStorageKeys:
    def test_biz_pk(self):
        assert storage.biz_pk("B007IAE5WY") == "BIZ#B007IAE5WY"

    def test_review_sk(self):
        assert storage.review_sk("2017-W38", "r_1") == "REVIEW#2017-W38#r_1"

    def test_review_sk_prefix_matches_sk(self):
        sk = storage.review_sk("2017-W38", "r_1")
        assert sk.startswith(storage.review_sk_prefix("2017-W38"))

    def test_themes_and_brief_sk_distinct(self):
        assert storage.themes_sk("2017-W38") == "THEMES#2017-W38"
        assert storage.brief_sk("2017-W38") == "BRIEF#2017-W38"
        assert storage.themes_sk("2017-W38") != storage.brief_sk("2017-W38")


# ---------------------------------------------------------------------------
# storage — S3 upload-key parsing
# ---------------------------------------------------------------------------

class TestParseUploadKey:
    def test_valid_key(self):
        assert storage.parse_upload_key("uploads/B007IAE5WY/2017-W38.jsonl") == (
            "B007IAE5WY", "2017-W38"
        )

    @pytest.mark.parametrize("bad", [
        "B007IAE5WY/2017-W38.jsonl",          # missing uploads/ prefix
        "uploads/2017-W38.jsonl",             # missing business segment
        "uploads/B007IAE5WY/2017-W38.csv",    # wrong suffix
        "uploads//2017-W38.jsonl",            # empty business id
        "uploads/B007IAE5WY/.jsonl",          # empty week
    ])
    def test_malformed_key_raises(self, bad):
        with pytest.raises(ValueError):
            storage.parse_upload_key(bad)


# ---------------------------------------------------------------------------
# metrics — payload shaping
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_model_label_known(self):
        assert metrics.model_label("claude-haiku-4-5-20251001") == "haiku"
        assert metrics.model_label("claude-sonnet-4-6") == "sonnet"
        assert metrics.model_label("claude-opus-4-8") == "opus"

    def test_model_label_unknown_and_none(self):
        assert metrics.model_label("claude-future-9") == "other"
        assert metrics.model_label(None) == "none"

    def test_build_metric_data_core_three(self):
        md = metrics.build_metric_data(
            stage="analyze", cost_usd=0.0045, latency_ms=210.0, throughput=17,
        )
        names = [m["MetricName"] for m in md]
        assert names == ["CostUsd", "LatencyMs", "Throughput"]
        # No Model dimension when model is None.
        for m in md:
            assert all(d["Name"] != "Model" for d in m["Dimensions"])

    def test_build_metric_data_includes_model_and_cache(self):
        md = metrics.build_metric_data(
            stage="analyze", cost_usd=0.02, latency_ms=400.0, throughput=17,
            model="claude-sonnet-4-6", cache_read_tokens=2274,
        )
        names = [m["MetricName"] for m in md]
        assert "CacheReadTokens" in names
        # Every metric carries the Model dimension.
        for m in md:
            assert {"Name": "Model", "Value": "sonnet"} in m["Dimensions"]

    def test_cache_metric_omitted_when_zero(self):
        md = metrics.build_metric_data(
            stage="analyze", cost_usd=0.02, latency_ms=400.0, throughput=17,
            model="claude-sonnet-4-6", cache_read_tokens=0,
        )
        assert "CacheReadTokens" not in [m["MetricName"] for m in md]

    def test_emit_noop_returns_payload(self):
        # BIZBRIEF_METRICS_DISABLED=1 → no AWS call, returns what it would send.
        payload = metrics.emit(
            stage="ingest", cost_usd=0.0, latency_ms=5.0, throughput=17,
        )
        assert isinstance(payload, list) and len(payload) == 3


# ---------------------------------------------------------------------------
# handler_ingest — row normalization (reuses pipeline cleaning logic)
# ---------------------------------------------------------------------------

class TestIngestNormalization:
    def setup_method(self):
        import handler_ingest
        self.h = handler_ingest

    def test_normalizes_valid_row(self):
        row = self.h._normalize_row(
            {"review_id": "r_1", "rating": 5, "text": "Great product!"},
            "B007IAE5WY", "2017-W38",
        )
        assert row["review_id"] == "r_1"
        assert row["business_id"] == "B007IAE5WY"
        assert row["week"] == "2017-W38"
        assert row["stars"] == 5

    def test_skips_row_without_text(self):
        assert self.h._normalize_row(
            {"review_id": "r_1", "rating": 5, "text": ""},
            "B007IAE5WY", "2017-W38",
        ) is None

    def test_skips_row_without_id(self):
        assert self.h._normalize_row(
            {"rating": 5, "text": "Great!"}, "B007IAE5WY", "2017-W38",
        ) is None
