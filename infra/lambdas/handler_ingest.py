"""
Ingest Lambda — the event-driven entry point of the serverless pipeline.

Trigger
-------
S3 ``ObjectCreated`` event on the raw bucket for keys matching
``uploads/<business_id>/<week>.jsonl``.  Configured as the function's event
source in template.yaml, so dropping a file into S3 fires this automatically —
this is the "event-driven serverless" spine.

What it does
------------
1. Parse (business_id, week) from the S3 key.
2. Stream the uploaded JSONL from S3 and normalize each row into the Review
   schema using the SAME cleaning logic as the local pipeline
   (pipeline.ingest._clean_text / _ms_to_date_week) — one source of truth for
   normalization, no divergence between local and cloud.
3. Batch-write the normalized reviews to DynamoDB.
4. Emit throughput / latency metrics to CloudWatch.
5. Asynchronously invoke the analyze Lambda for (business_id, week).

Bad input (a key outside uploads/<business_id>/<week>.jsonl, or an empty,
malformed, non-UTF-8 or oversized file) is rejected with one structured log line
and no model calls. Retrying it would not help. A repeat delivery of the same
object (same ETag) is skipped, so analyze runs once per upload.

Any other error (S3 or DynamoDB unavailable) propagates so Lambda retries and,
after the configured attempts, routes the event to the SQS dead-letter queue
defined in template.yaml — the cloud analogue of the local data/logs/dead-letter/.
"""

from __future__ import annotations

import json
import os
import time
from urllib.parse import unquote_plus

import storage
import metrics

# Reuse the local pipeline's normalization so cloud and local agree byte-for-byte.
from pipeline.ingest import _clean_text, _ms_to_date_week  # type: ignore


def _normalize_row(raw: dict, business_id: str, week: str) -> dict | None:
    """Map one raw Amazon-review row to the Review schema (CONTRACTS §1).

    Returns None for rows that should be skipped (missing text or id).
    Raises ValueError for a row that is not a JSON object.
    """
    if not isinstance(raw, dict):
        raise ValueError("line is not a JSON object")
    text = _clean_text(raw.get("text"))
    review_id = raw.get("review_id") or raw.get("id")
    if not text or not review_id:
        return None
    return {
        "review_id": str(review_id),
        "business_id": business_id,
        "week": week,
        "stars": int(raw.get("rating", raw.get("stars", 0)) or 0),
        "text": text,
        "ts": raw.get("timestamp"),
    }


def _invoke_analyze(business_id: str, week: str) -> None:
    """Fire-and-forget invoke of the analyze Lambda (Event invocation type)."""
    fn = os.environ.get("ANALYZE_FUNCTION_NAME")
    if not fn:
        print("[ingest] ANALYZE_FUNCTION_NAME unset — skipping chained invoke")
        return
    import boto3  # noqa: PLC0415

    boto3.client("lambda").invoke(
        FunctionName=fn,
        InvocationType="Event",
        Payload=json.dumps({"business_id": business_id, "week": week}).encode(),
    )


def handler(event: dict, context) -> dict:  # noqa: ANN001 — Lambda context
    """Lambda entry point. `event` is an S3 notification with one+ records."""
    t0 = time.monotonic()
    total = 0
    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        # S3 URL-encodes keys in event payloads ("a b" arrives as "a+b").
        key = unquote_plus(record["s3"]["object"]["key"])
        try:
            business_id, week = storage.parse_upload_key(key)
            reviews = [
                norm for raw in storage.read_s3_jsonl(bucket, key)
                if (norm := _normalize_row(raw, business_id, week)) is not None
            ]
            if not reviews:
                raise ValueError("no usable reviews in upload")
        except (ValueError, TypeError) as exc:
            print(json.dumps({"stage": "ingest", "outcome": "rejected",
                              "key": key, "reason": str(exc)}))
            results.append({"key": key, "rejected": str(exc)})
            continue

        written = storage.put_reviews(business_id, week, reviews)
        total += written
        etag = record["s3"]["object"].get("eTag", "")
        if not storage.claim_upload(business_id, week, etag):
            print(json.dumps({"stage": "ingest", "outcome": "skipped_duplicate", "key": key}))
            results.append({"key": key, "duplicate": True})
            continue
        _invoke_analyze(business_id, week)
        results.append({"business_id": business_id, "week": week, "reviews": written})

    latency_ms = (time.monotonic() - t0) * 1000
    metrics.emit(stage="ingest", cost_usd=0.0, latency_ms=latency_ms, throughput=total)

    return {"statusCode": 200, "ingested": results}
