"""
Storage adapter for the serverless deployment.

In the local/CLI build, the pipeline reads reviews from
``data/processed/reviews.jsonl`` and writes briefs to ``data/briefs/``.  In the
serverless deployment those two roles are played by S3 (object store for raw
uploads and rendered briefs) and DynamoDB (queryable review + theme records).

This module is the single seam between the pipeline's file-based world and AWS.
It is written so that:

  * It imports cleanly WITHOUT boto3 installed (so the rest of the repo, tests,
    and `sam build` introspection don't require an AWS SDK in the base env).
    boto3 is only imported lazily inside the functions that touch AWS.
  * Every public function has the same shape it would have in production — a
    reviewer can read it and see exactly which AWS calls would fire.

DynamoDB single-table design
-----------------------------
Table: ``bizbrief`` (name overridable via env ``BIZBRIEF_TABLE``).

  PK (partition)              SK (sort)                 item shape
  --------------------------  ------------------------  ---------------------------
  BIZ#<business_id>           REVIEW#<week>#<review_id> one normalized Review
  BIZ#<business_id>           THEMES#<week>             one ThemeReport
  BIZ#<business_id>           BRIEF#<week>              one Brief

Access patterns this satisfies in a single query each:
  - "all reviews for a business in a week"  → PK=BIZ#x, SK begins_with REVIEW#<week>#
  - "the theme report for a business+week"  → PK=BIZ#x, SK=THEMES#<week>
  - "the brief for a business+week"         → PK=BIZ#x, SK=BRIEF#<week>

S3 layout
---------
Bucket: ``BIZBRIEF_RAW_BUCKET`` (raw uploads, the event source) and
``BIZBRIEF_BRIEFS_BUCKET`` (rendered brief JSON the dashboard reads).

  s3://<raw>/uploads/<business_id>/<week>.jsonl      ← triggers ingest Lambda
  s3://<briefs>/<business_id>/<week>.brief.json      ← written by brief Lambda
"""

from __future__ import annotations

import json
import os
import re
from typing import Iterator


# ---------------------------------------------------------------------------
# Environment / configuration
# ---------------------------------------------------------------------------

def table_name() -> str:
    return os.environ.get("BIZBRIEF_TABLE", "bizbrief")


def raw_bucket() -> str:
    return os.environ.get("BIZBRIEF_RAW_BUCKET", "bizbrief-raw")


def briefs_bucket() -> str:
    return os.environ.get("BIZBRIEF_BRIEFS_BUCKET", "bizbrief-briefs")


# Lazy boto3 — imported only when an AWS call is actually made.  Keeps this
# module importable in environments without the SDK (tests, local tooling).
def _dynamo_table():
    import boto3  # noqa: PLC0415 — intentional lazy import

    return boto3.resource("dynamodb").Table(table_name())


def _s3():
    import boto3  # noqa: PLC0415

    return boto3.client("s3")


def _undecimalize(obj):
    """Recursively convert DynamoDB Decimal values to native int/float.

    boto3's DynamoDB resource returns all numbers as decimal.Decimal, which is
    not JSON-serializable and breaks downstream json.dumps / arithmetic. Convert
    at the read boundary so handlers always get plain Python numbers.
    """
    from decimal import Decimal  # noqa: PLC0415

    if isinstance(obj, list):
        return [_undecimalize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _undecimalize(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        # Whole numbers -> int, otherwise float (mirrors the source review data).
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


# ---------------------------------------------------------------------------
# Key helpers (pure — unit-testable without AWS)
# ---------------------------------------------------------------------------

def biz_pk(business_id: str) -> str:
    return f"BIZ#{business_id}"


def review_sk(week: str, review_id: str) -> str:
    return f"REVIEW#{week}#{review_id}"


def review_sk_prefix(week: str) -> str:
    return f"REVIEW#{week}#"


def themes_sk(week: str) -> str:
    return f"THEMES#{week}"


def brief_sk(week: str) -> str:
    return f"BRIEF#{week}"


# ---------------------------------------------------------------------------
# S3 — raw uploads (read side of the ingest trigger)
# ---------------------------------------------------------------------------

# Largest upload ingest will read. A week of reviews for one business is a few
# hundred KB at most; anything bigger is a mistake or abuse, and every review
# read here turns into model spend downstream.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def read_s3_jsonl(bucket: str, key: str, max_bytes: int = MAX_UPLOAD_BYTES) -> Iterator[dict]:
    """Stream a JSONL object from S3, yielding one parsed dict per line.

    Streams via the StreamingBody iterator rather than .read() so a large
    upload does not have to be held in memory at once — the same discipline as
    the local _stream_jsonl in pipeline/ingest.py.

    Raises ValueError for an object over ``max_bytes``, a line that is not
    UTF-8, or a line that is not valid JSON (UnicodeDecodeError and
    JSONDecodeError are both ValueErrors).
    """
    obj = _s3().get_object(Bucket=bucket, Key=key)
    if obj["ContentLength"] > max_bytes:
        raise ValueError(f"upload is {obj['ContentLength']} bytes, limit is {max_bytes}")
    buffer = b""
    for chunk in obj["Body"].iter_chunks(chunk_size=65536):
        buffer += chunk
        *lines, buffer = buffer.split(b"\n")
        for line in lines:
            line = line.strip()
            if line:
                yield json.loads(line.decode("utf-8"))
    if buffer.strip():
        yield json.loads(buffer.decode("utf-8"))


# Same shapes the API accepts (api/security.py), so a key can't smuggle path
# segments or odd characters into DynamoDB keys or the briefs bucket.
_UPLOAD_KEY_RE = re.compile(r"^uploads/([A-Za-z0-9_-]{1,64})/(\d{4}-W\d{2})\.jsonl$")


def parse_upload_key(key: str) -> tuple[str, str]:
    """Extract (business_id, week) from an upload key.

    Expected key shape: ``uploads/<business_id>/<week>.jsonl`` with
    ``<week>`` like ``2024-W31``. Raises ValueError on anything else.
    """
    m = _UPLOAD_KEY_RE.match(key)
    if not m:
        raise ValueError(f"unexpected upload key shape: {key!r}")
    return m.group(1), m.group(2)


def claim_upload(business_id: str, week: str, etag: str) -> bool:
    """Record that this exact upload (by ETag) was ingested.

    Returns False when it was already claimed, i.e. S3 delivered the same
    event twice. The conditional put makes this safe under concurrent deliveries.
    """
    from botocore.exceptions import ClientError  # noqa: PLC0415

    try:
        _dynamo_table().put_item(
            Item={"PK": biz_pk(business_id), "SK": f"UPLOAD#{week}#{etag}"},
            ConditionExpression="attribute_not_exists(PK)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    return True


# ---------------------------------------------------------------------------
# DynamoDB — reviews
# ---------------------------------------------------------------------------

def put_reviews(business_id: str, week: str, reviews: list[dict]) -> int:
    """Batch-write normalized reviews for one business+week. Returns count."""
    table = _dynamo_table()
    with table.batch_writer(overwrite_by_pkeys=["PK", "SK"]) as batch:
        for r in reviews:
            review_id = r["review_id"]
            batch.put_item(
                Item={
                    "PK": biz_pk(business_id),
                    "SK": review_sk(week, review_id),
                    "business_id": business_id,
                    "week": week,
                    **r,
                }
            )
    return len(reviews)


def get_reviews(business_id: str, week: str) -> list[dict]:
    """Query all reviews for a business+week (single partition, SK prefix)."""
    from boto3.dynamodb.conditions import Key  # noqa: PLC0415

    table = _dynamo_table()
    items: list[dict] = []
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(biz_pk(business_id))
        & Key("SK").begins_with(review_sk_prefix(week)),
    }
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return _undecimalize(items)


# ---------------------------------------------------------------------------
# DynamoDB — theme reports and briefs
# ---------------------------------------------------------------------------

def put_theme_report(business_id: str, week: str, report: dict) -> None:
    _dynamo_table().put_item(
        Item={
            "PK": biz_pk(business_id),
            "SK": themes_sk(week),
            "business_id": business_id,
            "week": week,
            "report": json.dumps(report),
        }
    )


def get_theme_report(business_id: str, week: str) -> dict | None:
    resp = _dynamo_table().get_item(
        Key={"PK": biz_pk(business_id), "SK": themes_sk(week)}
    )
    item = resp.get("Item")
    return json.loads(item["report"]) if item else None


def put_brief(business_id: str, week: str, brief: dict) -> None:
    """Persist the brief to DynamoDB AND render the JSON to the briefs bucket."""
    _dynamo_table().put_item(
        Item={
            "PK": biz_pk(business_id),
            "SK": brief_sk(week),
            "business_id": business_id,
            "week": week,
            "brief": json.dumps(brief),
        }
    )
    _s3().put_object(
        Bucket=briefs_bucket(),
        Key=f"{business_id}/{week}.brief.json",
        Body=json.dumps(brief, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def get_brief(business_id: str, week: str) -> dict | None:
    resp = _dynamo_table().get_item(
        Key={"PK": biz_pk(business_id), "SK": brief_sk(week)}
    )
    item = resp.get("Item")
    return json.loads(item["brief"]) if item else None
