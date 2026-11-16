"""
Edge cases for the serverless handlers, run against mock AWS (moto).

Each test pins one failure mode a real deploy would hit: URL-encoded S3 keys,
duplicate S3 deliveries, bad uploads, bad keys, a Secrets Manager outage, retry
timing against the Lambda timeout, and the cost ceiling tripping mid-run.
The Anthropic client is always faked, so nothing here touches the network.
"""

from __future__ import annotations

import json
import time
import uuid
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from tests.test_serverless_storage import RAW_BUCKET, aws  # noqa: F401 — fixture

import handler_ingest  # noqa: E402 — importable once test_serverless_storage set sys.path

HAIKU = "claude-haiku-4-5-20251001"


def _response(text: str, input_tokens: int = 100) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=input_tokens, output_tokens=10,
                           cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return resp


def _themes_for(**kwargs) -> str:
    """Fake analyze reply: one negative theme over every review in the batch."""
    import re
    ids = re.findall(r'"review_id": "([^"]+)"', kwargs["messages"][0]["content"])
    return json.dumps([{"label": "Slow service", "sentiment": "negative",
                        "review_ids": ids, "sample_quotes": ["Slow."]}])


def _upload(key: str, body: bytes) -> dict:
    """Put an object in the mock raw bucket and return its S3 event."""
    import boto3
    etag = boto3.client("s3").put_object(Bucket=RAW_BUCKET, Key=key, Body=body)["ETag"]
    return {"Records": [{"s3": {"bucket": {"name": RAW_BUCKET},
                                "object": {"key": key, "eTag": etag.strip('"')}}}]}


def _jsonl(n: int) -> bytes:
    return "\n".join(json.dumps({"review_id": f"r{i}", "rating": 2, "text": f"Slow {i}"})
                     for i in range(n)).encode()


@pytest.fixture
def invoked(aws, monkeypatch):  # noqa: F811
    """Record handler_ingest's chained analyze invokes instead of sending them."""
    import handler_ingest
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(handler_ingest, "_invoke_analyze", lambda b, w: calls.append((b, w)))
    return calls


def test_url_encoded_key_is_decoded(invoked):
    biz = f"blue_door_{uuid.uuid4().hex[:6]}"
    event = _upload(f"uploads/{biz}/2026-W01.jsonl", _jsonl(3))
    # S3 sends keys URL-encoded. "_" as %5F must still find the object.
    event["Records"][0]["s3"]["object"]["key"] = f"uploads/{biz.replace('_', '%5F')}/2026-W01.jsonl"
    out = handler_ingest.handler(event, None)
    assert out["ingested"][0]["reviews"] == 3
    assert invoked == [(biz, "2026-W01")]


def test_plus_in_key_decodes_to_space_and_is_rejected(invoked):
    event = {"Records": [{"s3": {"bucket": {"name": RAW_BUCKET},
                                 "object": {"key": "uploads/my+shop/2026-W01.jsonl"}}}]}
    out = handler_ingest.handler(event, None)
    assert "my shop" in out["ingested"][0]["key"]
    assert "rejected" in out["ingested"][0]
    assert invoked == []


def test_duplicate_delivery_makes_one_model_call(invoked, monkeypatch):
    import handler_analyze
    monkeypatch.setattr(handler_ingest, "_invoke_analyze",
                        lambda b, w: handler_analyze.handler({"business_id": b, "week": w}, None))
    client = MagicMock()
    client.messages.create.side_effect = lambda **kw: _response(_themes_for(**kw))
    event = _upload(f"uploads/dup_{uuid.uuid4().hex[:6]}/2026-W01.jsonl", _jsonl(3))

    with patch("reliability.call_model.anthropic.Anthropic", return_value=client):
        first = handler_ingest.handler(event, None)
        second = handler_ingest.handler(event, None)

    assert "reviews" in first["ingested"][0]
    assert second["ingested"][0]["duplicate"] is True
    assert client.messages.create.call_count == 1


@pytest.mark.parametrize("body", [
    b"",                                   # empty
    b"\n\n",                               # only blank lines
    b'{"review_id": "r1", "text": "ok"\n',  # malformed JSON
    b'{"review_id": "r1", "text": "caf\xe9"}',  # Latin-1, not UTF-8
    b"[1, 2, 3]",                          # JSON, but not an object
    b'{"review_id": "r1", "rating": "five", "text": "ok"}',  # bad rating
], ids=["empty", "blank", "malformed", "non_utf8", "not_object", "bad_rating"])
def test_bad_upload_is_rejected_without_analyze(invoked, body):
    event = _upload(f"uploads/bad_{uuid.uuid4().hex[:6]}/2026-W01.jsonl", body)
    out = handler_ingest.handler(event, None)
    assert "rejected" in out["ingested"][0]
    assert invoked == []


def test_oversized_upload_is_rejected_before_parsing(invoked):
    import storage
    event = _upload("uploads/huge/2026-W01.jsonl", b" " * (storage.MAX_UPLOAD_BYTES + 1))
    out = handler_ingest.handler(event, None)
    assert "limit" in out["ingested"][0]["rejected"]
    assert invoked == []


@pytest.mark.parametrize("key", [
    "uploads/biz/latest.jsonl",            # week not YYYY-Www
    "uploads/biz/2026-W01.csv",            # wrong suffix
    "uploads/a/b/2026-W01.jsonl",          # extra segment
    "uploads/../2026-W01.jsonl",           # traversal-looking id
    "other/biz/2026-W01.jsonl",            # wrong prefix
])
def test_unexpected_key_is_rejected(invoked, key):
    event = {"Records": [{"s3": {"bucket": {"name": RAW_BUCKET}, "object": {"key": key}}}]}
    out = handler_ingest.handler(event, None)
    assert "rejected" in out["ingested"][0]
    assert invoked == []


def test_secrets_manager_failure_is_clear_and_fast(monkeypatch):
    import boto3
    from botocore.exceptions import ConnectTimeoutError
    import secrets_provider

    seen = {}

    def fake_client(service, config=None):
        seen["config"] = config
        c = MagicMock()
        c.get_secret_value.side_effect = ConnectTimeoutError(endpoint_url="https://sm")
        return c

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:x")
    monkeypatch.setattr(secrets_provider, "_hydrated", False)
    monkeypatch.setattr(boto3, "client", fake_client)

    with pytest.raises(RuntimeError, match="Could not read the Anthropic API key"):
        secrets_provider.ensure_anthropic_key()
    assert seen["config"].connect_timeout <= 5 and seen["config"].read_timeout <= 5
    # A failed fetch is not cached as done, so the next invocation tries again.
    assert secrets_provider._hydrated is False


def test_retries_and_backoff_stop_at_the_deadline(tmp_path):
    from pipeline.config import Config
    from reliability.call_model import call_model

    cfg = Config(log_dir=str(tmp_path), briefs_dir=str(tmp_path),
                 max_retries=4, backoff_base_s=30.0)
    cfg.deadline = time.monotonic() + 2.0
    timeouts, slept = [], []

    def rate_limited(**kwargs):
        timeouts.append(kwargs["timeout"])
        raise anthropic.APIStatusError(message="Rate limited",
                                       response=MagicMock(status_code=429, headers={}),
                                       body=None)

    client = MagicMock()
    client.messages.create.side_effect = rate_limited
    with patch("reliability.call_model.anthropic.Anthropic", return_value=client) as ctor, \
         patch("reliability.call_model.time.sleep", side_effect=slept.append):
        with pytest.raises(RuntimeError):
            call_model("p", cfg=cfg, stage="analyze", run_id="t")

    assert ctor.call_args.kwargs["max_retries"] == 0   # the SDK must not retry on its own
    assert all(t <= 2.0 for t in timeouts)             # no request outlives the deadline
    assert sum(slept) < 2.0                            # no backoff sleeps past it


def test_cost_ceiling_mid_run_stops_and_marks_partial(aws, monkeypatch):  # noqa: F811
    import handler_analyze
    storage = aws
    biz = f"ceiling_{uuid.uuid4().hex[:6]}"
    storage.put_reviews(biz, "2026-W01", [
        {"review_id": f"r{i}", "stars": 2, "text": f"Slow {i}"} for i in range(45)
    ])  # 3 batches of up to 20
    monkeypatch.setattr(handler_analyze, "pick_model", lambda batch, cfg: HAIKU)
    # 700k Haiku input tokens is $0.56, so the second call crosses the $1 ceiling.
    client = MagicMock()
    client.messages.create.side_effect = lambda **kw: _response(_themes_for(**kw), 700_000)
    context = MagicMock(get_remaining_time_in_millis=lambda: 300_000)

    with patch("reliability.call_model.anthropic.Anthropic", return_value=client):
        out = handler_analyze.handler({"business_id": biz, "week": "2026-W01"}, context)

    assert client.messages.create.call_count == 2     # batch 3 never called
    assert out["status"] == "partial" and out["partial"] is True
    assert storage.get_theme_report(biz, "2026-W01")["partial"] is True


def test_brief_cost_ceiling_returns_instead_of_retrying(aws):  # noqa: F811
    import handler_brief
    storage = aws
    biz = f"briefcap_{uuid.uuid4().hex[:6]}"
    storage.put_theme_report(biz, "2026-W01", {
        "business_id": biz, "week": "2026-W01", "review_count": 3, "avg_stars": 2.0,
        "prev_avg_stars": None, "sufficient": True, "partial": False,
        "themes": [{"theme_id": "t1", "label": "Slow", "sentiment": "negative",
                    "review_ids": ["r1"], "count": 1, "sample_quotes": []}],
    })
    client = MagicMock()
    client.messages.create.return_value = _response("{}", 2_000_000)  # $1.60 on Haiku

    with patch("reliability.call_model.anthropic.Anthropic", return_value=client):
        out = handler_brief.handler({"business_id": biz, "week": "2026-W01"}, None)

    assert out["status"] == "failed"
    assert storage.get_brief(biz, "2026-W01") is None
