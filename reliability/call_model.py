"""
call_model — the single entry point for ALL model API calls in BizBrief.

Owns: retry/backoff/jitter (retryable errors only), per-run cost ceiling,
idempotency cache (file-based), and structured logging.

NEVER call the Anthropic SDK directly from a pipeline stage — always go through
call_model so cost caps and logging are enforced.
"""

import hashlib
import json
import os
import random
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import anthropic
import httpx

if TYPE_CHECKING:
    from pipeline.config import Config
    from reliability.logger import StructuredLogger

from reliability.logger import LogEvent, StructuredLogger


class BudgetExceeded(Exception):
    """Raised when the per-run cost ceiling is hit."""


class CircuitOpen(Exception):
    """Raised by the scheduler-side breaker after N consecutive failures."""


class ModelResult:
    __slots__ = ("text", "model", "input_tokens", "output_tokens", "cost_usd", "cached")

    def __init__(
        self,
        text: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        cached: bool = False,
    ):
        self.text = text
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_usd = cost_usd
        self.cached = cached


# Approximate token costs (USD per 1M tokens) — update when pricing changes.
_COST_TABLE: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8": (15.00, 75.00),
}

_RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = _COST_TABLE.get(model, (3.00, 15.00))
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def _cache_path(idempotency_key: str, briefs_dir: str) -> str:
    slug = hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]
    cache_dir = os.path.join(briefs_dir, ".call_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{slug}.json")


def _load_cache(key: str, briefs_dir: str) -> ModelResult | None:
    path = _cache_path(key, briefs_dir)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        d = json.load(f)
    return ModelResult(
        text=d["text"],
        model=d["model"],
        input_tokens=d["input_tokens"],
        output_tokens=d["output_tokens"],
        cost_usd=d["cost_usd"],
        cached=True,
    )


def _save_cache(key: str, result: ModelResult, briefs_dir: str) -> None:
    path = _cache_path(key, briefs_dir)
    with open(path, "w") as f:
        json.dump(
            {
                "text": result.text,
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
            },
            f,
        )


def call_model(
    prompt: str,
    *,
    cfg: "Config",
    stage: str,
    run_id: str,
    business_id: str = "",
    week: str = "",
    idempotency_key: str | None = None,
    _run_cost: list[float] | None = None,
    _logger: "StructuredLogger | None" = None,
) -> ModelResult:
    """
    Call the model with full reliability guarantees.

    _run_cost is a mutable single-element list shared across a run so cost
    accumulates across calls. Pass the same list for every call in a run.
    """
    if _logger is None:
        _logger = StructuredLogger(cfg.log_dir)
    if _run_cost is None:
        _run_cost = [0.0]

    # Check idempotency cache first.
    if idempotency_key:
        cached = _load_cache(idempotency_key, cfg.briefs_dir)
        if cached:
            _logger.emit(
                LogEvent(
                    ts=datetime.now(timezone.utc).isoformat(),
                    run_id=run_id,
                    business_id=business_id,
                    week=week,
                    stage=stage,
                    model=cached.model,
                    input_tokens=cached.input_tokens,
                    output_tokens=cached.output_tokens,
                    cost_usd=0.0,
                    latency_ms=0,
                    outcome="skipped_cache",
                    error_class=None,
                )
            )
            return cached

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    last_exc: Exception | None = None
    for attempt in range(cfg.max_retries + 1):
        t0 = time.monotonic()
        try:
            response = client.messages.create(
                model=cfg.gen_model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost = _estimate_cost(cfg.gen_model, input_tokens, output_tokens)

            # Enforce cost ceiling.
            _run_cost[0] += cost
            if _run_cost[0] > cfg.run_cost_ceiling_usd:
                _logger.emit(
                    LogEvent(
                        ts=datetime.now(timezone.utc).isoformat(),
                        run_id=run_id,
                        business_id=business_id,
                        week=week,
                        stage=stage,
                        model=cfg.gen_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost,
                        latency_ms=latency_ms,
                        outcome="fail",
                        error_class="BudgetExceeded",
                    )
                )
                raise BudgetExceeded(
                    f"Run cost ${_run_cost[0]:.4f} exceeds ceiling "
                    f"${cfg.run_cost_ceiling_usd:.2f}"
                )

            text = response.content[0].text
            result = ModelResult(
                text=text,
                model=cfg.gen_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                cached=False,
            )

            _logger.emit(
                LogEvent(
                    ts=datetime.now(timezone.utc).isoformat(),
                    run_id=run_id,
                    business_id=business_id,
                    week=week,
                    stage=stage,
                    model=cfg.gen_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    outcome="ok",
                    error_class=None,
                )
            )

            if idempotency_key:
                _save_cache(idempotency_key, result, cfg.briefs_dir)

            return result

        except BudgetExceeded:
            raise

        except anthropic.APIStatusError as exc:
            status = exc.status_code
            retryable = status in _RETRYABLE_HTTP and status in cfg.retry_on
            error_class = f"HTTP{status}"
        except (httpx.TimeoutException, anthropic.APITimeoutError):
            retryable = "timeout" in cfg.retry_on
            error_class = "Timeout"
        except anthropic.AuthenticationError as exc:
            # Never retry auth failures — paying to fail.
            _logger.emit(
                LogEvent(
                    ts=datetime.now(timezone.utc).isoformat(),
                    run_id=run_id,
                    business_id=business_id,
                    week=week,
                    stage=stage,
                    model=cfg.gen_model,
                    input_tokens=None,
                    output_tokens=None,
                    cost_usd=None,
                    latency_ms=None,
                    outcome="fail",
                    error_class="AuthenticationError",
                )
            )
            raise
        except Exception as exc:
            retryable = False
            error_class = type(exc).__name__
            last_exc = exc

        latency_ms = int((time.monotonic() - t0) * 1000)
        is_final = attempt >= cfg.max_retries or not retryable
        outcome = "fail" if is_final else "retry"

        _logger.emit(
            LogEvent(
                ts=datetime.now(timezone.utc).isoformat(),
                run_id=run_id,
                business_id=business_id,
                week=week,
                stage=stage,
                model=cfg.gen_model,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                latency_ms=latency_ms,
                outcome=outcome,
                error_class=error_class,
            )
        )

        if is_final:
            break

        # Exponential backoff with full jitter.
        delay = cfg.backoff_base_s * (2**attempt)
        jitter = random.uniform(0, delay)
        time.sleep(jitter)

    raise RuntimeError(
        f"call_model failed after {cfg.max_retries + 1} attempts "
        f"(last error_class={error_class})"
    ) from last_exc
