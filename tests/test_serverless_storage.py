"""
Integration tests for the serverless storage adapter against mock AWS (moto).

These exercise the real S3 + DynamoDB code paths in infra/lambdas/storage.py —
including the Decimal normalization that a live deploy depends on — without any
AWS account. Skipped automatically if the `local-aws` extras (moto/boto3) are
not installed:  uv sync --group local-aws
"""

from __future__ import annotations

import os
import sys

import pytest

moto = pytest.importorskip("moto", reason="install the local-aws group: uv sync --group local-aws")
pytest.importorskip("boto3")

# Make the Lambda storage module importable (same path Lambda uses).
_INFRA_LAMBDAS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "infra", "lambdas")
)
if _INFRA_LAMBDAS not in sys.path:
    sys.path.insert(0, _INFRA_LAMBDAS)

# Fake region/creds so boto3 + moto initialize without a real profile.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

TABLE = "bizbrief-test"
RAW_BUCKET = "bizbrief-raw-test"
BRIEFS_BUCKET = "bizbrief-briefs-test"


@pytest.fixture
def aws(monkeypatch):
    """Spin up mock S3 + DynamoDB with the template's schema; yield storage."""
    from moto import mock_aws

    monkeypatch.setenv("BIZBRIEF_TABLE", TABLE)
    monkeypatch.setenv("BIZBRIEF_RAW_BUCKET", RAW_BUCKET)
    monkeypatch.setenv("BIZBRIEF_BRIEFS_BUCKET", BRIEFS_BUCKET)

    with mock_aws():
        import boto3

        boto3.client("s3").create_bucket(Bucket=RAW_BUCKET)
        boto3.client("s3").create_bucket(Bucket=BRIEFS_BUCKET)
        boto3.client("dynamodb").create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
        )
        import storage
        yield storage


def test_put_and_get_reviews_roundtrip(aws):
    storage = aws
    reviews = [
        {"review_id": "r1", "stars": 5, "text": "great"},
        {"review_id": "r2", "stars": 3, "text": "ok"},
    ]
    written = storage.put_reviews("B007IAE5WY", "2017-W38", reviews)
    assert written == 2

    got = storage.get_reviews("B007IAE5WY", "2017-W38")
    assert len(got) == 2
    ids = {r["review_id"] for r in got}
    assert ids == {"r1", "r2"}


def test_get_reviews_returns_native_numbers_not_decimal(aws):
    """The Decimal->int/float normalization is what makes downstream json.dumps
    and the router's arithmetic work on real DynamoDB. Guard it explicitly."""
    from decimal import Decimal

    storage = aws
    storage.put_reviews("B0X", "2020-W01", [{"review_id": "r1", "stars": 4, "text": "x"}])
    got = storage.get_reviews("B0X", "2020-W01")
    stars = got[0]["stars"]
    assert not isinstance(stars, Decimal)
    assert isinstance(stars, int)
    assert stars == 4

    # And the result must be JSON-serializable (the exact thing that broke).
    import json
    json.dumps(got)


def test_theme_report_roundtrip(aws):
    storage = aws
    report = {
        "business_id": "B0X", "week": "2020-W01",
        "themes": [{"label": "T", "sentiment": "positive", "review_ids": ["r1"]}],
        "sufficient": True,
    }
    storage.put_theme_report("B0X", "2020-W01", report)
    got = storage.get_theme_report("B0X", "2020-W01")
    assert got["themes"][0]["label"] == "T"


def test_brief_roundtrip_writes_to_s3(aws):
    import boto3

    storage = aws
    brief = {"business_id": "B0X", "week": "2020-W01", "summary": "s", "action_items": []}
    storage.put_brief("B0X", "2020-W01", brief)

    # In DynamoDB
    assert storage.get_brief("B0X", "2020-W01")["summary"] == "s"
    # And rendered to the briefs bucket
    obj = boto3.client("s3").get_object(Bucket=BRIEFS_BUCKET, Key="B0X/2020-W01.brief.json")
    assert b"summary" in obj["Body"].read()


def test_parse_upload_key_via_read_s3_jsonl(aws):
    """read_s3_jsonl streams a real object out of mock S3 line by line."""
    import boto3
    import json

    rows = [{"review_id": "r1", "stars": 5, "text": "a"}, {"review_id": "r2", "stars": 2, "text": "b"}]
    body = "\n".join(json.dumps(r) for r in rows).encode()
    key = "uploads/B0X/2020-W01.jsonl"
    boto3.client("s3").put_object(Bucket=RAW_BUCKET, Key=key, Body=body)

    out = list(storage.read_s3_jsonl(RAW_BUCKET, key)) if (storage := aws) else []
    assert len(out) == 2
    assert out[0]["review_id"] == "r1"
