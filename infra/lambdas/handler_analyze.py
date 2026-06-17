"""
Analyze Lambda — classify a business+week's reviews into a ThemeReport.

Trigger
-------
Asynchronously invoked by the ingest Lambda with payload
``{"business_id": ..., "week": ...}``.

What it does
------------
1. Load the normalized reviews for (business_id, week) from DynamoDB.
2. Run the SAME batch → route → classify → merge loop the local pipeline uses.
   The per-batch classification, JSON extraction, theme parsing and merging are
   imported directly from pipeline.analyze, and each model call still flows
   through reliability.call_model — so the cloud path inherits the model router,
   prompt caching, retries, cost ceiling and idempotency cache unchanged.
3. Persist the ThemeReport to DynamoDB.
4. Emit cost / latency / throughput / cache metrics (broken down by model).
5. Invoke the brief Lambda.

Abstention: if the review count is below cfg.min_reviews_for_brief, a
``sufficient=False`` report is written and the brief Lambda is NOT invoked —
identical semantics to the local pipeline (never manufacture a brief).
"""

from __future__ import annotations

import json
import os
import time
import uuid

import storage
import metrics
import secrets_provider as bizbrief_secrets

from pipeline.config import Config  # type: ignore
from pipeline.analyze import (  # type: ignore
    BATCH_SIZE,
    _SYSTEM_BLOCK,
    _USER_TEMPLATE,
    _extract_json_array,
    _merge_themes,
    _parse_batch_themes,
)
from pipeline.router import pick_model  # type: ignore
from reliability import call_model  # type: ignore
from reliability.logger import StructuredLogger  # type: ignore


def _invoke_brief(business_id: str, week: str) -> None:
    fn = os.environ.get("BRIEF_FUNCTION_NAME")
    if not fn:
        print("[analyze] BRIEF_FUNCTION_NAME unset — skipping chained invoke")
        return
    import boto3  # noqa: PLC0415

    boto3.client("lambda").invoke(
        FunctionName=fn,
        InvocationType="Event",
        Payload=json.dumps({"business_id": business_id, "week": week}).encode(),
    )


def handler(event: dict, context) -> dict:  # noqa: ANN001
    t0 = time.monotonic()
    # Hydrate ANTHROPIC_API_KEY from Secrets Manager if not already in the env.
    bizbrief_secrets.ensure_anthropic_key()
    business_id = event["business_id"]
    week = event["week"]
    cfg = Config()
    # Lambda has no shared filesystem; structured logs go to stdout → CloudWatch
    # Logs. StructuredLogger still emits, writing under /tmp which is ephemeral
    # but readable within the invocation.
    cfg.log_dir = "/tmp/logs"
    cfg.briefs_dir = "/tmp/briefs"
    run_id = f"sls_{uuid.uuid4().hex[:8]}"
    logger = StructuredLogger(cfg.log_dir)

    reviews = storage.get_reviews(business_id, week)
    review_count = len(reviews)
    avg_stars = (
        round(sum(int(r.get("stars", 0)) for r in reviews) / review_count, 2)
        if review_count else 0.0
    )

    # Abstain on sparse weeks — same rule as local.
    if review_count < cfg.min_reviews_for_brief:
        report = {
            "business_id": business_id, "week": week,
            "review_count": review_count, "avg_stars": avg_stars,
            "themes": [], "sufficient": False, "partial": False,
        }
        storage.put_theme_report(business_id, week, report)
        metrics.emit(stage="analyze", cost_usd=0.0,
                     latency_ms=(time.monotonic() - t0) * 1000, throughput=review_count)
        return {"statusCode": 200, "sufficient": False, "themes": 0}

    batches = [reviews[i:i + BATCH_SIZE] for i in range(0, review_count, BATCH_SIZE)]
    _run_cost = [0.0]
    all_batch_themes: list[list[dict]] = []
    batches_failed = 0
    last_model: str | None = None
    cache_read_total = 0

    for batch_idx, batch in enumerate(batches):
        valid_ids = {r["review_id"] for r in batch if "review_id" in r}
        reviews_json = json.dumps(
            [{"review_id": r.get("review_id"), "stars": r.get("stars"),
              "text": r.get("text", "")} for r in batch],
            ensure_ascii=False,
        )
        prompt = _USER_TEMPLATE.format(reviews_json=reviews_json)
        model = pick_model(batch, cfg)
        last_model = model
        try:
            result = call_model(
                prompt, cfg=cfg, stage="analyze", run_id=run_id,
                business_id=business_id, week=week,
                idempotency_key=f"analyze_{business_id}_{week}_{batch_idx}",
                model=model, system=_SYSTEM_BLOCK,
                _run_cost=_run_cost, _logger=logger,
            )
        except Exception as exc:  # noqa: BLE001 — partial-failure handling
            print(f"[analyze] batch {batch_idx} failed: {exc}")
            batches_failed += 1
            continue
        cache_read_total += getattr(result, "cache_read_tokens", 0)
        raw = _extract_json_array(result.text)
        if raw is None:
            batches_failed += 1
            continue
        all_batch_themes.append(_parse_batch_themes(raw, valid_ids, batch_idx))

    themes = _merge_themes(all_batch_themes, cfg.max_themes)
    partial = batches_failed > 0 and bool(themes)
    report = {
        "business_id": business_id, "week": week,
        "review_count": review_count, "avg_stars": avg_stars,
        "themes": themes, "sufficient": bool(themes), "partial": partial,
    }
    storage.put_theme_report(business_id, week, report)

    metrics.emit(
        stage="analyze", cost_usd=round(_run_cost[0], 6),
        latency_ms=(time.monotonic() - t0) * 1000, throughput=review_count,
        model=last_model, cache_read_tokens=cache_read_total,
    )

    if themes:
        _invoke_brief(business_id, week)

    return {"statusCode": 200, "sufficient": bool(themes),
            "themes": len(themes), "partial": partial}
