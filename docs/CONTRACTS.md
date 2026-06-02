# CONTRACTS.md — frozen interfaces

Freeze in Phase 0. Builders code against these types + a fixture, which is what
lets the four agents run in parallel. Changing a contract = edit here first, log
it in `docs/memory/00-decisions.md`, notify affected agents. (UI styling lives in
`docs/STYLE.md`; this file is data + interface shapes only.)

Signatures are illustrative Python/TS; keep names exact.

---

## 1. Review schema  (produced by `data-engineer`, consumed by `analysis-engineer`)

`data/raw/... → data/processed/reviews.jsonl`, one object per line:

```python
class Review(TypedDict):
    review_id: str
    business_id: str
    business_name: str
    stars: float          # 1.0–5.0
    text: str             # cleaned plain text
    date: str             # ISO date
    week: str             # ISO week bucket, e.g. "2024-W31" (precomputed for grouping)
```

Rules: normalized, deduped, one business resolvable by `business_id`; `week` is
precomputed so downstream never parses dates. Keep `review_id` stable for citations.

---

## 2. ThemeReport schema  (produced by `analysis-engineer`, consumed by `brief-engineer` AND `ui-engineer`)

```python
class Theme(TypedDict):
    theme_id: str
    label: str               # short human label, e.g. "Slow service at peak hours"
    sentiment: str           # "positive" | "negative" | "mixed"
    review_ids: list[str]    # evidence: which reviews belong to this theme
    count: int
    sample_quotes: list[str] # up to 3 SHORT (<=25-word) snippets

class ThemeReport(TypedDict):
    business_id: str
    week: str
    review_count: int
    avg_stars: float
    prev_avg_stars: float | None   # for trend; None if no prior week
    themes: list[Theme]
    sufficient: bool         # False => too few reviews to be meaningful this week
    partial: bool            # True => produced from a subset of batches (some failed); see RunRecord
```

Rules: `sufficient` is False below `Config.min_reviews_for_brief`; downstream must
handle it (abstain, don't fabricate). `partial` is True when some classification
batches failed after retries but enough succeeded to proceed. `review_ids` real
and traceable. Quotes short.

---

## 3. Brief schema  (produced by `brief-engineer`, consumed by `ui-engineer`)

```python
class ActionItem(TypedDict):
    rank: int                # 1 = highest priority
    theme_id: str            # links back to the ThemeReport theme
    headline: str
    why_it_matters: str
    recommended_action: str  # concrete, doable this week
    evidence_review_ids: list[str]
    severity: str            # "high" | "medium" | "low"

class Brief(TypedDict):
    business_id: str
    business_name: str
    week: str
    summary: str             # 2–3 sentence owner-facing overview
    trend: str               # "up" | "down" | "flat"
    action_items: list[ActionItem]   # ranked; empty + summary explains if insufficient
    email_draft: str | None  # optional owner-facing email; None if not generated
    partial: bool            # carried from ThemeReport; UI shows a "based on partial data" flag
    generated_by: str        # model id, for the eval/report
```

Rules: items ranked by impact = severity × frequency. Every item's
`evidence_review_ids` must exist in the ThemeReport. If `sufficient` is False,
`action_items` is empty and `summary` says why.

---

## 4. Config  (orchestrator, Phase 0)

```python
@dataclass
class Config:
    # generation
    gen_backend: str = "anthropic"
    gen_model: str = "claude-haiku-4-5"   # swap to a sonnet model for the final cut
    min_reviews_for_brief: int = 5        # below => ThemeReport.sufficient = False
    max_themes: int = 8
    briefs_dir: str = "data/briefs"
    # reliability (see §7)
    max_retries: int = 4
    backoff_base_s: float = 1.0           # exponential base; jittered
    retry_on = (429, 500, 502, 503, 504, "timeout")   # retryable ONLY; never 400/auth
    run_cost_ceiling_usd: float = 1.00    # hard per-run cap; abort if exceeded
    circuit_breaker_threshold: int = 5    # consecutive failures => scheduler stops
    log_dir: str = "data/logs"
```

---

## 5. ScheduleSettings schema  (read/written by UI, consumed by scheduler + brief-engineer)

```python
class ScheduleSettings(TypedDict):
    business_id: str
    cadence: str         # "weekly" | "biweekly" | "off"
    day_of_week: str     # "mon".."sun"
    email_mode: str      # "auto_send" | "draft_only"
```

Stored as JSON (`data/schedule/<business_id>.json`). The scheduler reads it to
decide when to run; `brief-engineer` honors `email_mode`. Demo-grade: a local
scheduler, not hosted multi-tenant infra.

> **Compliance note (`auto_send`):** the moment this actually emails real people it
> stops being a pure demo and pulls in consent/anti-spam obligations (CAN-SPAM /
> CASL / GDPR depending on recipients): a lawful basis to email, a real unsubscribe
> path, accurate sender identity, and not mailing addresses harvested from review
> data without permission. For v1, **default to `draft_only` and have the pipeline
> never actually send** — generate the draft, a human sends. A failed/partial run
> must never auto-send. Treat real auto-send as a productionization step needing a
> consent model first. (Especially apt given this project's privacy lineage.)

---

## 6. API seam  (orchestrator, Phase 2; UI builds against fixtures until then)

```
GET  /api/businesses                  -> [{business_id, business_name, weeks: [..]}]
GET  /api/brief?business_id=&week=     -> { brief: Brief, themeReport: ThemeReport }
GET  /api/schedule?business_id=        -> ScheduleSettings
PUT  /api/schedule                     -> ScheduleSettings
GET  /api/runs?business_id=            -> [RunRecord]   (for the UI run-status surface)
```

If skipping FastAPI for speed: emit/read the same JSON shapes under `data/` and
have the UI import them. The UI must not care which.

---

## 7. Reliability & logging  (built & frozen in Phase 0; every model call uses it)

**The wrapper — all model calls go through this:**

```python
class ModelResult(TypedDict):
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cached: bool             # True => served from idempotency cache, no API call

def call_model(prompt: str, *, cfg: Config, stage: str, run_id: str,
               idempotency_key: str | None = None) -> ModelResult: ...
# Behavior (owned here, not in callers):
#  - retry retryable errors only (cfg.retry_on) with exponential backoff + jitter, up to cfg.max_retries
#  - enforce cfg.run_cost_ceiling_usd across the run; raise BudgetExceeded if exceeded
#  - if idempotency_key hits the cache (data/briefs or a call cache), return cached result, no API call
#  - emit a LogEvent for every attempt (ok/retry/fail/skipped_cache)

class BudgetExceeded(Exception): ...
class CircuitOpen(Exception): ...   # raised by the scheduler-side breaker
```

**Structured logging shapes:**

```python
class LogEvent(TypedDict):
    ts: str                  # ISO timestamp
    run_id: str
    business_id: str
    week: str
    stage: str               # "ingest" | "analyze" | "brief" | "schedule"
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int | None
    outcome: str             # "ok" | "retry" | "fail" | "skipped_cache"
    error_class: str | None  # e.g. "RateLimit", "Timeout", "BudgetExceeded"

class RunRecord(TypedDict):
    run_id: str
    business_id: str
    week: str
    status: str              # "success" | "partial" | "failed"
    started_at: str
    finished_at: str
    total_cost_usd: float
    batches_total: int
    batches_failed: int
    note: str | None         # e.g. "3/50 batches failed; brief produced from 47"
```

Rules: `LogEvent`s append to `data/logs/<date>.jsonl`. One `RunRecord` per
scheduled run. `status="failed"` runs also get written to `data/logs/dead-letter/`
for later retry. The UI's run-status surface reads `RunRecord`s.

---

## 8. Eval seam  (Phase 3 stub; future harness implements)

```python
class GoldenWeek(TypedDict):
    business_id: str
    week: str
    expected_top_theme_labels: list[str]

def load_golden(path: str) -> list[GoldenWeek]: ...
# eval/ exists with this signature documented; metrics NOT implemented here.
```
