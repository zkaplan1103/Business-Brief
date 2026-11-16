"""
Local end-to-end runner for the serverless pipeline — NO real AWS account.

Spins up in-process mocks of S3 + DynamoDB (moto), creates the same resources
the SAM template would, drops a real review file into the mock raw bucket, and
runs the exact Lambda handlers ingest -> analyze -> brief in sequence against
those mocks. It also redelivers the same S3 event and checks ingest skips it.

Two modes:
  * live: with ANTHROPIC_API_KEY set, analyze + brief call Claude through
    reliability.call_model on real reviews from data/processed/ (costs the same
    cents a local pipeline run does; reruns hit the idempotency cache).
  * offline: with no key, or with --offline, a stub stands in for the Anthropic
    client and the upload is the committed fictional file
    infra/events/sample_upload.jsonl. No network, no cost. This is what CI runs.

The handlers' chained Lambda invokes (ANALYZE_FUNCTION_NAME / BRIEF_FUNCTION_NAME)
are deliberately left UNSET so each handler skips its boto3 lambda.invoke() call;
this script orchestrates the chain itself, which is what lets the whole thing run
in one process against the mocks.

Usage:
    uv run --group local-aws python infra/local_run.py \
        --business B007IAE5WY --week 2015-W28
    uv run --group local-aws python infra/local_run.py --offline

    # or via the Makefile:
    cd infra && make local-e2e
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from unittest.mock import MagicMock, patch

# --- make the Lambda code + repo importable, exactly as Lambda's path would ---
_INFRA = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_INFRA)
sys.path.insert(0, os.path.join(_INFRA, "lambdas"))   # handlers + storage + metrics
sys.path.insert(0, _REPO)                              # pipeline/ + reliability/

# Mock resource names (must match what the handlers read from env).
TABLE = "bizbrief-local"
RAW_BUCKET = "bizbrief-raw-local"
BRIEFS_BUCKET = "bizbrief-briefs-local"

# Region + fake creds so boto3/moto are happy without a real profile.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

# Point the handlers/storage at the mock resources.
os.environ["BIZBRIEF_TABLE"] = TABLE
os.environ["BIZBRIEF_RAW_BUCKET"] = RAW_BUCKET
os.environ["BIZBRIEF_BRIEFS_BUCKET"] = BRIEFS_BUCKET
# CloudWatch emitter -> no-op (we have no mock CloudWatch and don't need one).
os.environ["BIZBRIEF_METRICS_DISABLED"] = "1"
# Leave ANALYZE_FUNCTION_NAME / BRIEF_FUNCTION_NAME UNSET so handlers skip the
# real lambda.invoke() chain — we orchestrate it below instead.
os.environ.pop("ANALYZE_FUNCTION_NAME", None)
os.environ.pop("BRIEF_FUNCTION_NAME", None)


def _load_seed_rows(business_id: str, week: str) -> list[dict]:
    """Read real normalized reviews for (business_id, week) from the local
    processed file to use as the raw S3 upload contents."""
    path = os.path.join(_REPO, "data", "processed", "reviews.jsonl")
    if not os.path.exists(path):
        sys.exit(
            f"ERROR: {path} not found.\n"
            "Run `uv run python -m pipeline.ingest` first to create it."
        )
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("business_id") == business_id and r.get("week") == week:
                rows.append(r)
    return rows


SAMPLE_UPLOAD = os.path.join(_INFRA, "events", "sample_upload.jsonl")
SAMPLE_BUSINESS, SAMPLE_WEEK = "sample-cafe", "2026-W01"


def _stub_create(**kwargs):
    """Offline stand-in for client.messages.create. Answers the three prompt
    kinds the pipeline sends with valid, minimal JSON built from the prompt."""
    prompt = kwargs["messages"][0]["content"]
    if kwargs.get("system"):  # analyze batch
        ids = re.findall(r'"review_id": "([^"]+)"', prompt)
        text = json.dumps([{"label": "Long weekend wait times", "sentiment": "negative",
                            "review_ids": ids, "sample_quotes": ["The line barely moved."]}])
    elif prompt.startswith("You are writing a weekly action brief"):
        theme_id = re.search(r'"theme_id": "([^"]+)"', prompt).group(1)
        text = json.dumps({"summary": "Offline stub brief.", "trend": "flat", "action_items": [{
            "rank": 1, "theme_id": theme_id, "headline": "Add weekend counter staff",
            "why_it_matters": "Waits drive low ratings.",
            "recommended_action": "Add one person Saturday 8 to 11am.",
            "evidence_review_ids": [], "severity": "high"}]})
    else:  # email draft
        text = "Subject: Weekly brief\n\nHi [Name], offline stub.\n\n— Your BizBrief"
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=100, output_tokens=50,
                           cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return resp


def _create_resources():
    """Create the mock S3 buckets + DynamoDB table matching template.yaml."""
    import boto3

    s3 = boto3.client("s3")
    s3.create_bucket(Bucket=RAW_BUCKET)
    s3.create_bucket(Bucket=BRIEFS_BUCKET)

    dynamodb = boto3.client("dynamodb")
    dynamodb.create_table(
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--business", default="B007IAE5WY")
    parser.add_argument("--week", default="2015-W28")
    parser.add_argument("--offline", action="store_true",
                        help="stub the model and use the committed sample upload")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        # Allow loading from .env like the rest of the project does.
        try:
            from dotenv import load_dotenv

            load_dotenv(os.path.join(_REPO, ".env"))
        except Exception:
            pass
    offline = args.offline or not os.environ.get("ANTHROPIC_API_KEY")

    from moto import mock_aws

    stub = MagicMock()
    stub.return_value.messages.create.side_effect = _stub_create
    model_patch = patch("reliability.call_model.anthropic.Anthropic", stub)
    if offline:
        print("[offline] stub model, fictional sample upload, no API calls\n")
        args.business, args.week = SAMPLE_BUSINESS, SAMPLE_WEEK
        model_patch.start()

    with mock_aws():
        _create_resources()
        import boto3
        import storage  # the handlers' storage adapter, now hitting moto

        # --- seed: write a real review file into the mock raw bucket ---
        if offline:
            with open(SAMPLE_UPLOAD, encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
        else:
            rows = _load_seed_rows(args.business, args.week)
        if not rows:
            sys.exit(
                f"No reviews for {args.business} / {args.week} in data/processed/.\n"
                "Pick a business+week present in that file."
            )
        key = f"uploads/{args.business}/{args.week}.jsonl"
        body = "\n".join(json.dumps(r) for r in rows).encode("utf-8")
        etag = boto3.client("s3").put_object(Bucket=RAW_BUCKET, Key=key, Body=body)["ETag"]
        print(f"[seed] wrote {len(rows)} reviews to s3://{RAW_BUCKET}/{key}\n")

        # --- stage 1: ingest (S3 event -> DynamoDB) ---
        import handler_ingest

        s3_event = {
            "Records": [
                {"s3": {"bucket": {"name": RAW_BUCKET},
                        "object": {"key": key, "eTag": etag.strip('"')}}}
            ]
        }
        ingest_out = handler_ingest.handler(s3_event, None)
        print(f"[ingest]  {json.dumps(ingest_out)}")
        print(f"[ingest]  DynamoDB now holds {len(storage.get_reviews(args.business, args.week))} reviews")
        # S3 delivers at least once. A repeat of the same event must not rerun analyze.
        again = handler_ingest.handler(s3_event, None)
        if not again["ingested"][0].get("duplicate"):
            sys.exit(f"FAIL: duplicate delivery was not skipped: {again}")
        print("[ingest]  duplicate delivery skipped\n")

        # --- stage 2: analyze (DynamoDB reviews -> ThemeReport) [calls Claude] ---
        import handler_analyze

        analyze_out = handler_analyze.handler(
            {"business_id": args.business, "week": args.week}, None
        )
        print(f"[analyze] {json.dumps(analyze_out)}")
        report = storage.get_theme_report(args.business, args.week)
        if report:
            print(f"[analyze] themes: {[t['label'] for t in report.get('themes', [])]}\n")

        if not analyze_out.get("sufficient"):
            print("[done] analyze abstained (sparse week) — no brief produced.")
            return

        # --- stage 3: brief (ThemeReport -> Brief -> DynamoDB + briefs bucket) ---
        import handler_brief

        brief_out = handler_brief.handler(
            {"business_id": args.business, "week": args.week}, None
        )
        print(f"[brief]   {json.dumps(brief_out)}")

        # --- verify: the rendered brief landed in the mock briefs bucket ---
        brief_key = f"{args.business}/{args.week}.brief.json"
        obj = boto3.client("s3").get_object(Bucket=BRIEFS_BUCKET, Key=brief_key)
        brief = json.loads(obj["Body"].read())
        print(f"\n[verify] s3://{BRIEFS_BUCKET}/{brief_key}")
        print(f"[verify] summary: {brief.get('summary', '')[:120]}...")
        print(f"[verify] action items: {len(brief.get('action_items', []))}")
        if not brief.get("action_items"):
            sys.exit("FAIL: brief has no action items")
        print("\n[done] full ingest -> analyze -> brief ran end-to-end on mock AWS.")


if __name__ == "__main__":
    main()
