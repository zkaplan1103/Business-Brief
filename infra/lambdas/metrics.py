"""
CloudWatch custom-metric emitter for the serverless deployment.

The local build aggregates cost / latency / throughput by scanning JSONL logs
in ``/api/metrics``.  In the serverless world there is no shared filesystem, so
each Lambda publishes the same three signals as CloudWatch custom metrics under
the ``BizBrief`` namespace.  A CloudWatch dashboard (see template.yaml) then
renders them live — this is what the résumé bullet's "live CloudWatch dashboard
tracking cost, latency, and throughput" refers to.

Dimensions
----------
Every metric is published with a ``Stage`` dimension (ingest | analyze | brief)
and a ``Model`` dimension where a model was called (haiku | sonnet | opus), so
the dashboard can break cost down by model exactly like the local CostTab does.

Metrics
-------
  CostUsd        (Unit: None / dollars)  per-invocation model spend
  LatencyMs      (Unit: Milliseconds)    wall-clock for the stage
  Throughput     (Unit: Count)           reviews processed in the invocation
  CacheReadTokens(Unit: Count)           prompt-cache tokens served (savings signal)

boto3 is imported lazily so this module stays importable without the SDK.
When BIZBRIEF_METRICS_DISABLED=1 (used by `sam local` and tests) emission is a
no-op that just returns the payload it WOULD have sent — handy for assertions.
"""

from __future__ import annotations

import os

NAMESPACE = "BizBrief"

# Short model label for the Model dimension (keeps dashboard legends readable).
_MODEL_LABEL = {
    "claude-haiku-4-5-20251001": "haiku",
    "claude-sonnet-4-6": "sonnet",
    "claude-opus-4-8": "opus",
}


def model_label(model: str | None) -> str:
    if not model:
        return "none"
    return _MODEL_LABEL.get(model, "other")


def _cloudwatch():
    import boto3  # noqa: PLC0415 — lazy

    return boto3.client("cloudwatch")


def build_metric_data(
    *,
    stage: str,
    cost_usd: float,
    latency_ms: float,
    throughput: int,
    model: str | None = None,
    cache_read_tokens: int = 0,
) -> list[dict]:
    """Build the MetricData payload for a single stage invocation.

    Pure function — no AWS call — so it can be unit-tested and reused by the
    no-op path.  Returns the list passed verbatim to put_metric_data.
    """
    dimensions = [{"Name": "Stage", "Value": stage}]
    if model is not None:
        dimensions.append({"Name": "Model", "Value": model_label(model)})

    data = [
        {"MetricName": "CostUsd", "Value": float(cost_usd), "Unit": "None",
         "Dimensions": dimensions},
        {"MetricName": "LatencyMs", "Value": float(latency_ms), "Unit": "Milliseconds",
         "Dimensions": dimensions},
        {"MetricName": "Throughput", "Value": int(throughput), "Unit": "Count",
         "Dimensions": dimensions},
    ]
    if cache_read_tokens:
        data.append(
            {"MetricName": "CacheReadTokens", "Value": int(cache_read_tokens),
             "Unit": "Count", "Dimensions": dimensions}
        )
    return data


def emit(
    *,
    stage: str,
    cost_usd: float,
    latency_ms: float,
    throughput: int,
    model: str | None = None,
    cache_read_tokens: int = 0,
) -> list[dict]:
    """Publish stage metrics to CloudWatch. Returns the payload sent.

    On any AWS error this logs and swallows — telemetry must never fail the
    pipeline run (a brief that succeeded should not be marked failed because a
    metric PUT timed out).
    """
    payload = build_metric_data(
        stage=stage, cost_usd=cost_usd, latency_ms=latency_ms,
        throughput=throughput, model=model, cache_read_tokens=cache_read_tokens,
    )
    if os.environ.get("BIZBRIEF_METRICS_DISABLED") == "1":
        return payload
    try:
        _cloudwatch().put_metric_data(Namespace=NAMESPACE, MetricData=payload)
    except Exception as exc:  # noqa: BLE001 — telemetry is best-effort
        print(f"[metrics] put_metric_data failed (non-fatal): {exc}")
    return payload
