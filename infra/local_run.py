"""
Local end-to-end runner for the serverless pipeline — NO real AWS account.

Spins up in-process mocks of S3 + DynamoDB (moto), creates the same resources
the SAM template would, drops a real review file into the mock raw bucket, and
runs the exact Lambda handlers ingest -> analyze -> brief in sequence against
those mocks. The analyze stage calls Claude through reliability.call_model, so
this needs ANTHROPIC_API_KEY (it costs the same cents a local pipeline run does;
reruns hit the idempotency cache and are free).

The handlers' chained Lambda invokes (ANALYZE_FUNCTION_NAME / BRIEF_FUNCTION_NAME)
are deliberately left UNSET so each handler skips its boto3 lambda.invoke() call;
this script orchestrates the chain itself, which is what lets the whole thing run
in one process against the mocks.

Usage:
    uv run --group local-aws python infra/local_run.py \
        --business B007IAE5WY --week 2015-W28

    # or via the Makefile:
    cd infra && make local-e2e
"""

from __future__ import annotations

import argparse
import json
import os
import sys

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
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        # Allow loading from .env like the rest of the project does.
        try:
            from dotenv import load_dotenv

            load_dotenv(os.path.join(_REPO, ".env"))
        except Exception:
            pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY not set (needed by the analyze stage).")

    from moto import mock_aws

    with mock_aws():
        _create_resources()
        import boto3
        import storage  # the handlers' storage adapter, now hitting moto

        # --- seed: write a real review file into the mock raw bucket ---
        rows = _load_seed_rows(args.business, args.week)
        if not rows:
            sys.exit(
                f"No reviews for {args.business} / {args.week} in data/processed/.\n"
                "Pick a business+week present in that file."
            )
        key = f"uploads/{args.business}/{args.week}.jsonl"
        body = "\n".join(json.dumps(r) for r in rows).encode("utf-8")
        boto3.client("s3").put_object(Bucket=RAW_BUCKET, Key=key, Body=body)
        print(f"[seed] wrote {len(rows)} reviews to s3://{RAW_BUCKET}/{key}\n")

        # --- stage 1: ingest (S3 event -> DynamoDB) ---
        import handler_ingest

        s3_event = {
            "Records": [
                {"s3": {"bucket": {"name": RAW_BUCKET}, "object": {"key": key}}}
            ]
        }
        ingest_out = handler_ingest.handler(s3_event, None)
        print(f"[ingest]  {json.dumps(ingest_out)}")
        print(f"[ingest]  DynamoDB now holds {len(storage.get_reviews(args.business, args.week))} reviews\n")

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
        print("\n[done] full ingest -> analyze -> brief ran end-to-end on mock AWS.")


if __name__ == "__main__":
    main()
