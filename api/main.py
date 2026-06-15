"""
FastAPI seam — serves Brief, ThemeReport, ScheduleSettings, and RunRecords
from data/briefs/, data/schedule/, and data/logs/runs.jsonl.

All routes read from disk; no in-memory state. The UI can swap between
this API and static JSON import with no component changes.

Security controls (see api/security.py for implementation details):
  - Per-IP sliding-window rate limiting (reads: 60/min, writes: 10/min).
  - Request-body size cap: 10 KB max (rejects with 413 before parsing).
  - Hardened input validation: business_id and week validated against strict
    patterns before being used in filesystem paths.
  - Path-traversal defence: realpath check on all data-directory joins.
  - API-key auth on all mutating routes (X-API-Key header, env BIZBRIEF_API_KEY).
  - Cost-amplification guard dependency (pre-wired for future trigger routes).
  - Generic exception handler: secrets never appear in response bodies.

RT-001 FIX — XFF spoofing (definitive):
  Uvicorn CLI reads FORWARDED_ALLOW_IPS from the environment in
  uvicorn.config.Config.__init__ BEFORE importing this module.  Setting
  os.environ["FORWARDED_ALLOW_IPS"] here is therefore ineffective — uvicorn
  has already constructed ProxyHeadersMiddleware(trusted_hosts="127.0.0.1")
  and scope["client"] is rewritten before our app ever sees the request.

  The correct fix is to start uvicorn PROGRAMMATICALLY via api/run.py which
  passes forwarded_allow_ips=[] directly to uvicorn.run().  This ensures
  uvicorn never trusts X-Forwarded-For regardless of environment state.

  ALWAYS start the server with:
      uv run python -m api.run

  StripProxyHeadersMiddleware (wired below) provides defense-in-depth: it
  strips XFF/X-Real-IP from scope["headers"] so no downstream code can read
  attacker-controlled proxy headers even in unexpected deployment scenarios.
  See api/run.py and .env.example for details.
"""

from __future__ import annotations

import json
import logging
import os

from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

from pipeline.config import Config
from api.security import (
    MaxBodySizeMiddleware,
    RateLimitMiddleware,
    StripProxyHeadersMiddleware,
    check_cost_guard,           # Apply as Depends(check_cost_guard) to any route
                                # that triggers model calls (pipeline.brief, analyze,
                                # etc.).  Without this dependency, the cost guard is
                                # imported but provides ZERO protection (RT-010).
                                # Example for a future trigger route:
                                #   @app.post("/api/run", dependencies=[
                                #       Depends(require_api_key),
                                #       Depends(check_cost_guard),   # <-- required
                                #   ])
    generic_exception_handler,
    init_cost_guard,
    init_auth_lockout,
    init_security,
    require_api_key,
    safe_path_join,
    startup_secret_checks,
    validate_business_id,
    validate_week,
    validation_exception_handler,
)

logger = logging.getLogger("bizbrief.api")

cfg = Config()

from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(application: FastAPI):
    startup_secret_checks()
    init_security(cfg)   # wires cfg into _client_ip, cost guard, and auth lockout
    logger.info("BizBrief API started")
    yield
    logger.info("BizBrief API shutting down")


app = FastAPI(
    title="BizBrief API",
    version="0.1.0",
    lifespan=_lifespan,
    # Disable automatic debug detail in error responses
    docs_url="/docs",
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# Middleware — order matters: outer layers execute first on request,
# last on response.  MaxBodySize must run before RateLimit so oversized
# bodies are rejected before they count against the rate-limit window.
#
# StripProxyHeadersMiddleware is added LAST (added last = outermost layer in
# Starlette's LIFO wrapping) so it executes FIRST on every incoming request.
# It removes XFF/X-Real-IP headers before any other middleware reads them,
# providing defense-in-depth against RT-001 at the application level.
# The primary fix is the FORWARDED_ALLOW_IPS="" env var set above, which
# prevents uvicorn itself from rewriting scope["client"]; this middleware is a
# belt-and-suspenders guard for any path where the env var is not effective.
# ---------------------------------------------------------------------------

app.add_middleware(RateLimitMiddleware, cfg=cfg)
app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "PUT"],
    allow_headers=["*"],
)
# RT-001 FIX (defense-in-depth layer): strip XFF/X-Real-IP headers from all
# requests when trusted_proxy=False.  Added last so it executes first.
# The primary fix is api/run.py passing forwarded_allow_ips=[] to uvicorn.run()
# so uvicorn never rewrites scope["client"] from an XFF header in the first place.
# This middleware is belt-and-suspenders: it removes XFF from scope["headers"]
# so no downstream handler can consume the header either.
app.add_middleware(StripProxyHeadersMiddleware, cfg=cfg)

# ---------------------------------------------------------------------------
# Exception handlers — generic messages, no secrets in output
# ---------------------------------------------------------------------------

# RT-007: RequestValidationError (422) must be handled before the generic
# Exception handler, otherwise FastAPI's default 422 handler echoes the raw
# "input" field from the request body in its response.
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _brief_dir(business_id: str) -> str:
    """Return the validated, realpath-checked brief directory for business_id."""
    # business_id already validated by caller via validate_business_id()
    base = os.path.realpath(cfg.briefs_dir)
    return safe_path_join(base, business_id)


def _brief_path(business_id: str, week: str) -> str:
    """Return the safe path to a .brief.json file."""
    bdir = _brief_dir(business_id)
    return safe_path_join(bdir, f"{week}.brief.json")


def _themes_path(business_id: str, week: str) -> str:
    """Return the safe path to a .themes.json file."""
    bdir = _brief_dir(business_id)
    return safe_path_join(bdir, f"{week}.themes.json")


def _schedule_path(business_id: str) -> str:
    """Return the safe path to a schedule JSON file."""
    base = os.path.realpath(cfg.schedule_dir)
    return safe_path_join(base, f"{business_id}.json")


def _runs_path() -> str:
    return os.path.join(cfg.log_dir, "runs.jsonl")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/businesses")
def list_businesses() -> list[dict]:
    """
    Return all businesses that have at least one generated brief, along with
    the list of weeks available for each.
    """
    briefs_dir = cfg.briefs_dir
    if not os.path.isdir(briefs_dir):
        return []

    result = []
    for raw_business_id in sorted(os.listdir(briefs_dir)):
        # Only surface directories whose names are valid business_ids.
        # This avoids exposing hidden dirs (.call_cache, etc.) and prevents
        # enumeration of traversal-crafted names.
        if not _BUSINESS_ID_RE_PATTERN.match(raw_business_id):
            continue
        biz_dir = os.path.join(briefs_dir, raw_business_id)
        if not os.path.isdir(biz_dir):
            continue
        weeks = sorted(
            f.replace(".brief.json", "")
            for f in os.listdir(biz_dir)
            if f.endswith(".brief.json")
        )
        if not weeks:
            continue
        # Try to get business_name from the most recent brief.
        name = raw_business_id
        try:
            latest = _read_json(os.path.join(biz_dir, f"{weeks[-1]}.brief.json"))
            name = latest.get("business_name", raw_business_id)
        except Exception:
            pass
        result.append({"business_id": raw_business_id, "business_name": name, "weeks": weeks})

    return result


import re as _re
_BUSINESS_ID_RE_PATTERN = _re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@app.get("/api/brief")
def get_brief(business_id: str, week: str) -> dict:
    """Return the Brief + ThemeReport for a given business/week."""
    # Validate BEFORE constructing any path
    validate_business_id(business_id)
    validate_week(week)

    bp = _brief_path(business_id, week)
    tp = _themes_path(business_id, week)

    if not os.path.exists(bp):
        raise HTTPException(
            status_code=404,
            detail=f"No brief found for {business_id!r} / {week!r}. Run the pipeline first.",
        )

    brief = _read_json(bp)
    theme_report = _read_json(tp) if os.path.exists(tp) else {}
    return {"brief": brief, "themeReport": theme_report}


@app.get("/api/schedule")
def get_schedule(business_id: str) -> dict:
    """Return ScheduleSettings for a business, or a default off schedule."""
    validate_business_id(business_id)

    path = _schedule_path(business_id)
    if os.path.exists(path):
        return _read_json(path)
    # Return a sensible default rather than 404.
    return {
        "business_id": business_id,
        "cadence": "off",
        "day_of_week": "mon",
        "email_mode": "draft_only",
    }


@app.put("/api/schedule", dependencies=[Depends(require_api_key)])
def put_schedule(settings: dict) -> dict:
    """
    Persist ScheduleSettings for a business.
    Requires X-API-Key header (env: BIZBRIEF_API_KEY).
    Body must be <= 10 KB (enforced by MaxBodySizeMiddleware before this runs).
    """
    # --- Required fields ---
    business_id = settings.get("business_id", "")
    if not business_id:
        raise HTTPException(status_code=400, detail="business_id is required")

    # Validate business_id before ANYTHING touches the filesystem
    validate_business_id(business_id)

    required = {"business_id", "cadence", "day_of_week", "email_mode"}
    missing = required - set(settings.keys())
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {sorted(missing)}")

    # Reject unexpected fields (no extra keys pass through to disk)
    extra = set(settings.keys()) - required
    if extra:
        raise HTTPException(status_code=400, detail=f"Unexpected fields: {sorted(extra)}")

    valid_cadence = {"weekly", "biweekly", "off"}
    valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    valid_modes = {"auto_send", "draft_only"}

    if settings["cadence"] not in valid_cadence:
        raise HTTPException(status_code=400, detail=f"cadence must be one of {sorted(valid_cadence)}")
    if settings["day_of_week"] not in valid_days:
        raise HTTPException(status_code=400, detail=f"day_of_week must be one of {sorted(valid_days)}")
    if settings["email_mode"] not in valid_modes:
        raise HTTPException(status_code=400, detail=f"email_mode must be one of {sorted(valid_modes)}")

    os.makedirs(cfg.schedule_dir, exist_ok=True)
    path = _schedule_path(business_id)

    # RT-008: cap total number of schedule files to prevent disk-fill attacks.
    # Count only .json files; skip the target file itself (an update is fine).
    if not os.path.exists(path):
        existing = sum(
            1 for f in os.listdir(cfg.schedule_dir) if f.endswith(".json")
        )
        if existing >= cfg.max_schedule_entries:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Schedule entry limit reached ({cfg.max_schedule_entries}). "
                    "Contact the administrator."
                ),
            )

    with open(path, "w") as f:
        # Write only the known-good fields, never raw settings dict
        clean: dict = {
            "business_id": settings["business_id"],
            "cadence": settings["cadence"],
            "day_of_week": settings["day_of_week"],
            "email_mode": settings["email_mode"],
        }
        json.dump(clean, f, indent=2)

    return clean


@app.get("/api/metrics")
def get_metrics() -> dict:
    """
    Aggregate the most recent cfg.metrics_max_days data/logs/<date>.jsonl files
    (excluding runs.jsonl) and return cost, latency, throughput, routing mix, and
    cache-savings metrics.

    Security notes:
    - Rate-limited at cfg.rate_limit_reads_per_min (60/min) by RateLimitMiddleware —
      no separate cost guard needed (no model calls triggered).
    - File set is capped to cfg.metrics_max_days (default 30) most-recent log files
      to bound disk I/O and response size (read-amplification DoS defence).
    - log_dir is sourced exclusively from Config (not from user input) — no path
      traversal risk at this endpoint.
    - error_class values from LogEvent ("BudgetExceeded", "HTTP429", "Timeout",
      type(exc).__name__, etc.) are deliberately NOT included in the response —
      only numeric aggregates (cost, latency, tokens) and the model/stage names
      are returned, so no internal exception class names reach the client.
    - Read-only; no side effects.
    - Returns a zeroed structure if no event files exist.
    """
    import glob
    import math
    from datetime import datetime, timezone

    log_dir = cfg.log_dir
    pattern = os.path.join(log_dir, "*.jsonl")

    # Collect all .jsonl files except runs.jsonl, then limit to the most
    # recent cfg.metrics_max_days files.  Filenames are YYYY-MM-DD.jsonl so
    # lexicographic sort == chronological sort.
    all_files = sorted(
        p for p in glob.glob(pattern)
        if not p.endswith("runs.jsonl")
    )
    # Take only the tail (most-recent N days) to bound disk I/O and response size.
    jsonl_files = all_files[-cfg.metrics_max_days:] if cfg.metrics_max_days > 0 else []

    # Accumulators keyed by model (only allowlisted model names are top-level keys;
    # RT-011: unknown model strings go into "other" to prevent schema injection)
    by_model: dict[str, dict] = {}
    # Accumulators keyed by stage (same allowlist policy as by_model)
    by_stage: dict[str, dict] = {}

    total_cost_usd = 0.0
    total_calls = 0
    idempotency_skips = 0

    # RT-012: track total lines parsed across all files to bound latency
    lines_parsed = 0
    truncated = False

    # Track distinct dates covered
    dates_seen: set[str] = set()

    # RT-011: fetch allowlists from Config so they can be adjusted without code changes
    allowed_models: frozenset = cfg.allowed_models
    allowed_stages: frozenset = cfg.allowed_stages

    def _model_entry() -> dict:
        return {
            "calls": 0,
            "total_cost_usd": 0.0,
            "latencies_ms": [],
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "prompt_cache_saved_usd": 0.0,
        }

    def _stage_entry() -> dict:
        return {"calls": 0, "total_cost_usd": 0.0, "latencies_ms": []}

    for fpath in jsonl_files:
        if truncated:
            break

        # Infer date from filename (YYYY-MM-DD.jsonl)
        basename = os.path.basename(fpath)
        date_str = basename.replace(".jsonl", "")
        dates_seen.add(date_str)

        try:
            with open(fpath, encoding="utf-8") as f:
                for raw in f:
                    # RT-012: enforce total-line budget across all files
                    if lines_parsed >= cfg.metrics_max_lines:
                        truncated = True
                        break

                    raw = raw.strip()
                    if not raw:
                        continue
                    lines_parsed += 1
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    outcome = ev.get("outcome", "")

                    # Count idempotency skips separately; exclude from cost/latency
                    if outcome == "skipped_cache":
                        idempotency_skips += 1
                        continue

                    # Only count "ok" events toward cost & latency
                    # (retries and fails are already counted within the ok outcome
                    # by call_model — but we include all non-skip outcomes so partial
                    # failures are visible in the model/stage totals)
                    raw_model = ev.get("model") or "unknown"
                    raw_stage = ev.get("stage") or "unknown"
                    # RT-011: map unrecognised model/stage strings to "other" so
                    # attacker-controlled strings never appear as top-level JSON keys
                    model = raw_model if raw_model in allowed_models else "other"
                    stage = raw_stage if raw_stage in allowed_stages else "other"
                    cost = ev.get("cost_usd") or 0.0
                    latency = ev.get("latency_ms")

                    total_cost_usd += cost
                    total_calls += 1

                    # By-model
                    if model not in by_model:
                        by_model[model] = _model_entry()
                    me = by_model[model]
                    me["calls"] += 1
                    me["total_cost_usd"] += cost
                    if latency is not None:
                        me["latencies_ms"].append(latency)
                    me["total_input_tokens"] += ev.get("input_tokens") or 0
                    me["total_output_tokens"] += ev.get("output_tokens") or 0
                    me["cache_read_tokens"] += ev.get("cache_read_tokens") or 0
                    me["cache_creation_tokens"] += ev.get("cache_creation_tokens") or 0
                    me["prompt_cache_saved_usd"] += ev.get("prompt_cache_saved_usd") or 0.0

                    # By-stage
                    if stage not in by_stage:
                        by_stage[stage] = _stage_entry()
                    se = by_stage[stage]
                    se["calls"] += 1
                    se["total_cost_usd"] += cost
                    if latency is not None:
                        se["latencies_ms"].append(latency)

        except OSError:
            continue

    def _avg(lst: list) -> float:
        return sum(lst) / len(lst) if lst else 0.0

    def _p95(lst: list) -> float:
        if not lst:
            return 0.0
        sorted_lst = sorted(lst)
        idx = math.ceil(0.95 * len(sorted_lst)) - 1
        return float(sorted_lst[max(0, idx)])

    # Build by_model response shape (remove internal latency list)
    by_model_out: dict = {}
    for model_name, me in by_model.items():
        lats = me["latencies_ms"]
        by_model_out[model_name] = {
            "calls": me["calls"],
            "total_cost_usd": round(me["total_cost_usd"], 8),
            "avg_latency_ms": round(_avg(lats), 2),
            "p95_latency_ms": round(_p95(lats), 2),
            "total_input_tokens": me["total_input_tokens"],
            "total_output_tokens": me["total_output_tokens"],
            "cache_read_tokens": me["cache_read_tokens"],
            "cache_creation_tokens": me["cache_creation_tokens"],
            "prompt_cache_saved_usd": round(me["prompt_cache_saved_usd"], 8),
        }

    # Build by_stage response shape
    by_stage_out: dict = {}
    for stage_name, se in by_stage.items():
        lats = se["latencies_ms"]
        by_stage_out[stage_name] = {
            "calls": se["calls"],
            "total_cost_usd": round(se["total_cost_usd"], 8),
            "avg_latency_ms": round(_avg(lats), 2),
        }

    # Routing mix: classify models into haiku / sonnet / opus tiers
    haiku_calls = sum(
        me["calls"] for m, me in by_model.items()
        if "haiku" in m.lower()
    )
    sonnet_calls = sum(
        me["calls"] for m, me in by_model.items()
        if "sonnet" in m.lower()
    )
    opus_calls = sum(
        me["calls"] for m, me in by_model.items()
        if "opus" in m.lower()
    )
    denom = total_calls or 1
    routing_mix = {
        "haiku_pct": round((haiku_calls / denom) * 100, 1),
        "sonnet_pct": round((sonnet_calls / denom) * 100, 1),
        "opus_pct": round((opus_calls / denom) * 100, 1),
    }

    return {
        "total_cost_usd": round(total_cost_usd, 8),
        "total_calls": total_calls,
        "by_model": by_model_out,
        "by_stage": by_stage_out,
        "routing_mix": routing_mix,
        "idempotency_skips": idempotency_skips,
        "days_covered": len(dates_seen),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # RT-012: set when metrics_max_lines was hit; callers should treat data as partial
        "truncated": truncated,
    }


@app.get("/api/runs")
def get_runs(business_id: str) -> list[dict]:
    """Return all RunRecords for a business, newest first."""
    validate_business_id(business_id)

    path = _runs_path()
    if not os.path.exists(path):
        return []

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("business_id") == business_id:
                records.append(rec)

    # Newest first
    records.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return records


@app.get("/api/eval")
def get_eval() -> dict:
    """
    Return the signed-off quality-vs-cost eval results (eval/results.json).

    This is a STATIC consulting artifact, not live telemetry: it captures the
    one scored run across Haiku/Sonnet/Opus against the human-signed-off golden
    set, including the first-run costs (later reruns hit the idempotency cache
    at $0).  The dashboard's Eval tab renders it.

    Security notes:
    - Rate-limited at cfg.rate_limit_reads_per_min by RateLimitMiddleware.
    - Reads one fixed, repo-controlled path (eval/results.json) — no user input,
      so no path-traversal surface.
    - Read-only; returns {"available": false} (not an error) when the artifact
      is absent, so the UI can fall back to its bundled fixture cleanly.
    """
    path = os.path.join("eval", "results.json")
    if not os.path.exists(path):
        return {"available": False}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"available": False}
    data["available"] = True
    return data
