# 06-security.md — Security Engineer memory

---

## 2026-06-14 — Phase 1 security baseline (initial hardening pass)

### Controls added

| Control | File | Config knob(s) |
|---|---|---|
| Per-IP sliding-window rate limiter | `api/security.py` (`RateLimitMiddleware`) | `rate_limit_reads_per_min` (default 60), `rate_limit_writes_per_min` (default 10) |
| Request-body size cap | `api/security.py` (`MaxBodySizeMiddleware`) | `max_request_body_bytes` (default 10 240 bytes) |
| Path-traversal defence | `api/security.py` (`validate_business_id`, `validate_week`, `safe_path_join`) | `^[A-Za-z0-9_-]{1,64}$` for business_id; `^\d{4}-W\d{2}$` for week; `realpath` containment check |
| API-key auth on mutating routes | `api/security.py` (`require_api_key` Depends) | `BIZBRIEF_API_KEY` env var; 503 if unset, 401 if wrong |
| Extra-fields rejection on PUT /api/schedule | `api/main.py` | N/A — hardcoded allow-list |
| Per-IP + global cost-amplification guard | `api/security.py` (`CostGuard`, `check_cost_guard` Depends) | `cost_guard_per_ip_max` (5), `cost_guard_per_ip_window_s` (60), `cost_guard_global_max` (20), `cost_guard_global_window_s` (60) |
| Generic exception handler | `api/security.py` (`generic_exception_handler`) | N/A |
| Startup secret checks | `api/security.py` (`startup_secret_checks`) | N/A |
| Secret hygiene: .env git-ignored | `.gitignore` (confirmed present, `.env` in ignore list) | N/A |
| New Config knobs | `pipeline/config.py` | See table above |

### Threat model covered

- **Path traversal** — any `business_id` or `week` containing `..`, `/`, special chars, or exceeding 64 chars is rejected 400 before any `os.path.join`. Additionally `os.path.realpath` containment is checked on every constructed path.
- **Unauthenticated writes** — `PUT /api/schedule` (and any future write route using `Depends(require_api_key)`) requires a valid `X-API-Key` header matching `BIZBRIEF_API_KEY` env var. Key is compared with `hmac.compare_digest` (constant-time).
- **Request flooding** — per-IP sliding windows for reads and writes; 429 + `Retry-After` header.
- **Oversized payloads** — pure-ASGI body cap; Content-Length fast-path + streaming enforcement; returns 413 before FastAPI parses JSON.
- **Cost amplification** — `CostGuard` provides a per-IP and global sliding-window guard ready to be applied via `Depends(check_cost_guard)` to any model-triggering route. Currently wired as a ready dependency; no routes trigger model calls yet.
- **Secret leakage** — generic exception handler returns `{"detail":"An internal error occurred"}` with no stack trace or env vars. Startup check warns (but never logs values) if keys are missing.
- **Extra-field injection in schedule writes** — PUT /api/schedule rejects any key outside the known-good set with 400; writes only the validated clean dict to disk.

### Config knobs (summary)

All added to `pipeline/config.py` `Config` dataclass:

```
rate_limit_reads_per_min   = 60
rate_limit_writes_per_min  = 10
max_request_body_bytes     = 10_240
cost_guard_per_ip_max      = 5
cost_guard_per_ip_window_s = 60
cost_guard_global_max      = 20
cost_guard_global_window_s = 60
```

All can be overridden by constructing `Config(rate_limit_reads_per_min=N, ...)` — no hard-coding.

### Tests

`tests/test_security.py` — 55 tests, all passing. Covers:
- Path traversal on business_id (8 bad values × 3 routes) and week (6 bad values)
- Auth (no key → 401, wrong key → 401, key never in response)
- Oversized body → 413; under-limit body not rejected
- Write rate limit: 11th request → 429; first 10 pass
- Read rate limit: 6th request with limit=5 → 429; 61st with limit=60 → 429
- Secret hygiene: ANTHROPIC_API_KEY and BIZBRIEF_API_KEY absent from all response bodies
- Happy path: GET /api/brief with real data → 200; authenticated PUT → 200 + persisted to disk
- Extra fields on PUT → 400; traversal business_id on PUT → 400
- Direct unit tests for `validate_business_id`, `validate_week`, `safe_path_join`

### Residual risks (explicitly out of scope for Phase 1)

- **IP spoofing via X-Forwarded-For** — the rate limiter trusts the first value of `X-Forwarded-For`. In a real deployment behind a load balancer the trusted proxy IP set should be pinned. In demo (direct `uvicorn`), no proxy is present so this is acceptable.
- **Rate-limit state is in-memory** — resets on process restart. Multi-worker deployments (e.g. `uvicorn --workers 4`) do not share state. Demo runs single-process; this is acceptable and documented.
- **Week pattern allows semantically invalid values** (e.g. `2024-W99`) — the pattern validates format only, not ISO calendar correctness. Semantically invalid values will produce 404 (no file exists) rather than 400. This is safe (no traversal risk) but could be tightened.
- **API key is a static shared secret** — sufficient for demo; production would want per-client rotating keys or JWT.
- **No brute-force lockout on API key** — wrong-key attempts count against the write rate limit (10/min per IP) but there is no account lockout.
- **`GET /api/businesses` enumerates business IDs** — only exposes IDs present in `data/briefs/` (not user-supplied). Filtered to valid `_BUSINESS_ID_RE_PATTERN`. Acceptable for demo; production might require auth.

---

## 2026-06-14 — Red-team findings remediation (RT-001, RT-005, RT-007, RT-008, RT-010)

### RT-001 — XFF spoofing fixed

`_client_ip()` rewritten to ignore `X-Forwarded-For` when `Config.trusted_proxy=False` (the safe default). Only `request.client.host` is used. `trusted_proxy=True` is an explicit opt-in. The "residual risk" noted above is now closed.

### RT-005 — Auth-failure lockout added

`_AuthFailureLockout` class in `api/security.py`. Config knobs added to `pipeline/config.py`:

```
auth_lockout_attempts  = 5    # failures before ban
auth_lockout_window_s  = 60   # failure window (seconds)
auth_lockout_ban_s     = 300  # ban duration (seconds)
```

`require_api_key` now checks the ban before inspecting the key, records failures on wrong key, and clears the counter on success.

### RT-007 — 422 input echo suppressed

`validation_exception_handler` added to `api/security.py`; registered on `RequestValidationError` (imported from `fastapi.exceptions`) in `api/main.py` ahead of the generic handler. Returns `{"detail": "Invalid request"}` with HTTP 422.

### RT-008 — Schedule file cap added

`PUT /api/schedule` counts `.json` files in `data/schedule/` before creating a new entry. Cap: `Config.max_schedule_entries` (default 100). Returns 429 if reached. Updates to existing entries skip the count. Config knob added to `pipeline/config.py`:

```
max_schedule_entries = 100
```

### RT-010 — CostGuard usage documented

Prominent comment block added to `check_cost_guard` import in `api/main.py` with a concrete `Depends(check_cost_guard)` example for Phase 2 trigger routes.

### New config knobs (pipeline/config.py)

```
trusted_proxy          = False   # RT-001: safe default, ignores XFF
auth_lockout_attempts  = 5       # RT-005
auth_lockout_window_s  = 60      # RT-005
auth_lockout_ban_s     = 300     # RT-005
max_schedule_entries   = 100     # RT-008
```

### Tests

68 total (was 58 before), all passing. 10 new tests:
- `TestXFFIgnored` (2) — RT-001 regression
- `TestAuthFailureLockout` (3) — RT-005 regression
- `TestValidationErrorNoEcho` (3) — RT-007 regression
- `TestScheduleFileCap` (2) — RT-008 regression

### Residual risks after this pass (open red-team findings)

- RT-002 (LOW) — rate-limit state resets on restart. Known/acceptable.
- RT-003 (LOW) — week pattern accepts semantically invalid values (2024-W99 → 404). Safe, known/acceptable.
- RT-004 (LOW) — `GET /api/businesses` enumerates IDs without auth. Demo-acceptable.
- RT-006 (LOW) — `GET /api/schedule` returns 200 with defaults for unknown biz. As designed.
- RT-009 (LOW) — `server: uvicorn` header. Demo-acceptable.

---

## 2026-06-15 — Phase 4 security gate: GET /api/metrics

### Checks performed

| Concern | Finding | Action taken |
|---|---|---|
| Rate limiting | `RateLimitMiddleware` is app-wide middleware; all routes including `/api/metrics` are covered at 60 GET/min per IP. No exemptions exist. | None needed. Verified by new test `test_metrics_rate_limited`. |
| Log content leakage — `error_class` | Field values (`"BudgetExceeded"`, `"HTTP429"`, `"Timeout"`, `type(exc).__name__`) never appear in the response. The endpoint only extracts `model`, `stage`, `cost_usd`, `latency_ms`, and token counts from each event — `error_class` is never read into the output. | Added explicit comment in docstring; regression test `test_metrics_error_class_not_in_response` verifies no `error_class` value leaks. |
| Log content leakage — `model`/`stage` keys | These are used as dictionary keys in the response, not path components or eval input. Benign. | No action. |
| Log content leakage — API keys | `StructuredLogger.emit` never logs key values (confirmed in `reliability/call_model.py` — keys only appear in `os.environ.get` calls, never in `LogEvent` fields). | Regression test `test_metrics_secrets_not_in_response` verifies keys absent from response. |
| Path safety — `log_dir` | `cfg.log_dir` defaults to `"data/logs"` (a compile-time constant). It is never derived from query parameters, headers, or request body — zero user influence. `glob.glob` over a Config-controlled directory is safe. | Confirmed. Comment added to docstring. |
| Response size (read-amplification DoS) | `glob.glob` with no limit: one HTTP request could scan hundreds of dated log files and return megabytes of JSON. | **Fixed.** Added `Config.metrics_max_days = 30` knob. `get_metrics` now sorts files lexicographically (YYYY-MM-DD.jsonl = chronological) and takes only the last N. Regression test `test_metrics_max_days_cap_limits_files_read` verifies 2 of 5 oldest files excluded when `metrics_max_days=3`. |
| Cost-amplification guard | Endpoint is read-only; triggers zero model calls. `check_cost_guard` dependency not needed. Rate-limit middleware is sufficient. | Confirmed. Comment in docstring. |

### New Config knob

```python
# pipeline/config.py
metrics_max_days: int = 30   # scan at most this many recent .jsonl log files
```

### Tests added (7 new, in `tests/test_security.py` class `TestMetricsEndpoint`)

| Test | What it verifies |
|---|---|
| `test_metrics_returns_200_with_empty_logs` | Empty log dir → 200 with zeroed structure |
| `test_metrics_rate_limited` | 6th GET with limit=5 → 429; first 5 pass |
| `test_metrics_max_days_cap_limits_files_read` | With `metrics_max_days=3` and 5 files, only 3 newest counted |
| `test_metrics_error_class_not_in_response` | `BudgetExceeded`, `HTTP500` never in response body |
| `test_metrics_malformed_jsonl_lines_skipped` | Corrupt lines skipped; valid lines still counted; no 500 |
| `test_metrics_secrets_not_in_response` | `ANTHROPIC_API_KEY` and `BIZBRIEF_API_KEY` absent from response |
| `test_metrics_idempotency_skips_counted_separately` | `skipped_cache` → idempotency_skips, not total_calls/cost |

### Test count: 149 (was 142)

---

## 2026-06-15 — RT-011 and RT-012 fixes: metrics allowlists + per-request line cap

### RT-011 — Model/stage key allowlists

`get_metrics()` in `api/main.py` now maps unrecognised `model` and `stage` log-event values to an `"other"` bucket instead of using them verbatim as top-level JSON keys. This prevents attacker-controlled strings written into `.jsonl` log files from appearing in the API response.

**Config knobs added to `pipeline/config.py`:**

```python
allowed_models: frozenset = frozenset({
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-8",
})
allowed_stages: frozenset = frozenset({
    "analyze", "brief", "ingest", "compare_sonnet",
})
```

Events whose `model` or `stage` is not in the frozenset are counted in `by_model["other"]` / `by_stage["other"]`. Totals (`total_calls`, `total_cost_usd`) still include "other" events — we sanitise the key, not the count.

New model IDs are added to `Config.allowed_models`; no code change needed.

### RT-012 — Per-request total line cap

`get_metrics()` now tracks `lines_parsed` across all files in one request. Once `cfg.metrics_max_lines` is reached, the file loop breaks and the response includes `"truncated": true`.

**Config knob added:**

```python
metrics_max_lines: int = 50_000   # stop reading after this many lines across all files
```

The response shape gains a new field: `"truncated": bool` (always present). Callers that rely on completeness must check this flag.

### Tests added (6 new, all in `tests/test_metrics.py`)

| Class | Test | What it verifies |
|---|---|---|
| `TestMetricsAllowlists` | `test_unknown_model_key_not_reflected_in_by_model` | Unknown model → not a key in `by_model`, counted in `"other"` |
| `TestMetricsAllowlists` | `test_unknown_stage_key_not_reflected_in_by_stage` | Unknown stage → not a key in `by_stage`, counted in `"other"` |
| `TestMetricsAllowlists` | `test_total_calls_includes_other_bucket_events` | "other" bucket events still counted in `total_calls`/`total_cost_usd` |
| `TestMetricsLineCap` | `test_normal_response_not_truncated` | Under-cap file → `truncated=False` |
| `TestMetricsLineCap` | `test_large_log_file_triggers_truncated_flag` | 3× cap lines → `truncated=True`, `total_calls <= cap` |
| `TestMetricsLineCap` | `test_truncation_stops_at_cap_across_multiple_files` | Cap enforced across 2 files (not per-file) |

### Test count: 155 (was 149)
