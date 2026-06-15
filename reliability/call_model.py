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
    __slots__ = (
        "text",
        "model",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "cached",
        "cache_creation_tokens",
        "cache_read_tokens",
    )

    def __init__(
        self,
        text: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        cached: bool = False,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ):
        self.text = text
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_usd = cost_usd
        self.cached = cached
        self.cache_creation_tokens = cache_creation_tokens
        self.cache_read_tokens = cache_read_tokens


# Approximate token costs (USD per 1M tokens) — update when pricing changes.
# Tuple layout: (input_rate, output_rate, cached_input_rate)
# Sources: https://www.anthropic.com/pricing (retrieved 2026-06-14)
#   Haiku:  $0.80 input / $4.00 output / $0.08 cached-input per 1M tokens
#   Sonnet: $3.00 input / $15.00 output / $0.30 cached-input per 1M tokens
#   Opus:   $15.00 input / $75.00 output / $1.50 cached-input per 1M tokens
_COST_TABLE: dict[str, tuple[float, float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00, 0.08),
    "claude-sonnet-4-6": (3.00, 15.00, 0.30),
    "claude-opus-4-8": (15.00, 75.00, 1.50),
}

_RETRYABLE_HTTP = {429, 500, 502, 503, 504}


# Cache-write tokens are billed at 1.25x the base input rate (5-minute TTL).
_CACHE_WRITE_MULTIPLIER = 1.25


def _estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """Compute cost in USD.

    The Anthropic API reports three DISJOINT input-token buckets — they do not
    overlap, so each is billed at its own rate and NONE is a subset of another:

      input_tokens          full base input rate (uncached prompt + messages)
      cache_creation_tokens 1.25x base rate (tokens written to the prompt cache)
      cached_read_tokens    0.10x base rate (tokens served from the prompt cache)
    """
    rates = _COST_TABLE.get(model, (3.00, 15.00, 0.30))
    in_rate, out_rate, cached_rate = rates
    return (
        input_tokens * in_rate
        + cache_creation_tokens * in_rate * _CACHE_WRITE_MULTIPLIER
        + cached_read_tokens * cached_rate
        + output_tokens * out_rate
    ) / 1_000_000


def _prompt_cache_savings(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
) -> dict:
    """
    Compute prompt-cache savings for a completed model call.

    Returns a dict with:
      - cost_without_cache: what this call would have cost with no caching
      - cost_with_cache:    what was actually charged
      - saved_usd:          the difference (always >= 0)

    Note: this measures PROMPT-CACHE savings only.  Idempotency-cache skips
    (outcome="skipped_cache") mean the call was never made at all — zero cost —
    and are a completely different mechanism.  Both appear in the logs; only
    prompt-cache skips appear here.
    """
    rates = _COST_TABLE.get(model, (3.00, 15.00, 0.30))
    in_rate, out_rate, _ = rates
    # Hypothetical no-cache cost: every input token (uncached + the tokens that
    # were instead written-to / read-from cache) billed at the full input rate.
    # The three buckets are disjoint, so the no-cache prompt size is their sum.
    total_input = input_tokens + cache_read_tokens + cache_creation_tokens
    cost_without_cache = (total_input * in_rate + output_tokens * out_rate) / 1_000_000
    # Actual cost (cache-write premium + cache-read discount).
    cost_with_cache = _estimate_cost(
        model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens
    )
    return {
        "cost_without_cache": cost_without_cache,
        "cost_with_cache": cost_with_cache,
        "saved_usd": max(0.0, cost_without_cache - cost_with_cache),
        "cache_creation_tokens": cache_creation_tokens,
        "cache_read_tokens": cache_read_tokens,
    }


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
    model: str | None = None,
    system: list[dict] | None = None,
    _run_cost: list[float] | None = None,
    _logger: "StructuredLogger | None" = None,
) -> ModelResult:
    """
    Call the model with full reliability guarantees.

    Parameters
    ----------
    model:
        Optional per-call model override (e.g. "claude-haiku-4-5-20251001").
        When provided, this model is used instead of ``cfg.gen_model``.
        All callers that don't pass *model* continue to use ``cfg.gen_model``
        unchanged — full backward compatibility.

    system:
        Optional system prompt passed as the ``system`` field to the
        Anthropic messages API.  Provide a list of content blocks so that
        callers can attach ``cache_control`` to individual blocks, e.g.::

            system=[{
                "type": "text",
                "text": "<long static instructions>",
                "cache_control": {"type": "ephemeral"},
            }]

        When ``system`` is None (default) the API call is made without a
        system prompt, preserving full backward compatibility.

    _run_cost:
        A mutable single-element list shared across a run so cost accumulates
        across calls.  Pass the same list for every call in a run.
    """
    if _logger is None:
        _logger = StructuredLogger(cfg.log_dir)
    if _run_cost is None:
        _run_cost = [0.0]

    # Resolve the model to use: explicit override > cfg.gen_model fallback.
    effective_model = model if model is not None else cfg.gen_model

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
            create_kwargs: dict = {
                "model": effective_model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system is not None:
                create_kwargs["system"] = system
            response = client.messages.create(**create_kwargs)
            latency_ms = int((time.monotonic() - t0) * 1000)
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            # Prompt-cache token counts — present only when cache_control blocks
            # are used.  Use int() conversion with a fallback so that both real
            # SDK responses (which set these to an int or None) and test mocks
            # (which may return MagicMock for unknown attributes) are handled
            # safely.
            _raw_creation = getattr(response.usage, "cache_creation_input_tokens", None)
            _raw_read = getattr(response.usage, "cache_read_input_tokens", None)
            cache_creation_tokens = int(_raw_creation) if isinstance(_raw_creation, int) else 0
            cache_read_tokens = int(_raw_read) if isinstance(_raw_read, int) else 0
            cost = _estimate_cost(
                effective_model,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_creation_tokens,
            )

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
                        model=effective_model,
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
                model=effective_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                cached=False,
                cache_creation_tokens=cache_creation_tokens,
                cache_read_tokens=cache_read_tokens,
            )

            log_event = LogEvent(
                ts=datetime.now(timezone.utc).isoformat(),
                run_id=run_id,
                business_id=business_id,
                week=week,
                stage=stage,
                model=effective_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                outcome="ok",
                error_class=None,
            )
            if cache_creation_tokens or cache_read_tokens:
                log_event["cache_creation_tokens"] = cache_creation_tokens
                log_event["cache_read_tokens"] = cache_read_tokens
                savings = _prompt_cache_savings(
                    effective_model,
                    input_tokens,
                    output_tokens,
                    cache_read_tokens,
                    cache_creation_tokens,
                )
                log_event["prompt_cache_saved_usd"] = savings["saved_usd"]
            _logger.emit(log_event)

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
        except anthropic.AuthenticationError:
            # Never retry auth failures — paying to fail.
            _logger.emit(
                LogEvent(
                    ts=datetime.now(timezone.utc).isoformat(),
                    run_id=run_id,
                    business_id=business_id,
                    week=week,
                    stage=stage,
                    model=effective_model,
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
                model=effective_model,
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
