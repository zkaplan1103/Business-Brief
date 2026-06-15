"""
Brief Lambda — turn a ThemeReport into a prioritized action Brief.

Trigger
-------
Asynchronously invoked by the analyze Lambda with payload
``{"business_id": ..., "week": ...}``.

What it does
------------
1. Load the ThemeReport for (business_id, week) from DynamoDB.
2. Call the existing pipeline.brief.run() — which prioritizes themes, drafts the
   summary / trend / action items, and (for non-partial runs) the optional draft
   email — through reliability.call_model, inheriting the router, caching,
   retries, cost ceiling and idempotency cache.  Email stays DRAFT-ONLY; nothing
   is ever auto-sent (CONTRACTS §5).
3. Persist the Brief to DynamoDB and render <business_id>/<week>.brief.json to
   the briefs S3 bucket, which the dashboard reads.
4. Emit cost / latency metrics to CloudWatch.

This is the terminal stage; it invokes nothing downstream.
"""

from __future__ import annotations

import time
import uuid

import storage
import metrics

from pipeline.config import Config  # type: ignore
import pipeline.brief as brief_stage  # type: ignore


def handler(event: dict, context) -> dict:  # noqa: ANN001
    t0 = time.monotonic()
    business_id = event["business_id"]
    week = event["week"]

    theme_report = storage.get_theme_report(business_id, week)
    if theme_report is None:
        # Nothing to brief on — analyze either abstained or hasn't run.
        return {"statusCode": 404, "error": "no theme report for business+week"}

    cfg = Config()
    cfg.briefs_dir = "/tmp/briefs"   # ephemeral; the canonical copy goes to S3
    cfg.log_dir = "/tmp/logs"
    run_id = f"sls_{uuid.uuid4().hex[:8]}"

    brief = brief_stage.run(business_id, week, cfg, run_id, theme_report)

    storage.put_brief(business_id, week, brief)

    metrics.emit(
        stage="brief", cost_usd=float(brief.get("_cost_usd", 0.0)),
        latency_ms=(time.monotonic() - t0) * 1000, throughput=1,
    )

    return {
        "statusCode": 200,
        "business_id": business_id,
        "week": week,
        "action_items": len(brief.get("action_items", [])),
        "sufficient": bool(theme_report.get("sufficient", True)),
    }
