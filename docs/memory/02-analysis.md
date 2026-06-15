---
tags: [analysis, cost]
---
# Analysis / Cost-Engineer log (append-only, dated)

## 2026-06-14 — Phase 2: Model router

### Routing signals and weights

`score_batch_complexity(batch)` returns a float in [0.0, 1.0] from three signals:

| Signal | How computed | Normalisation cap | Weight |
|---|---|---|---|
| avg_token_len | `len(text.split()) * 1.3` per review, averaged | 600 tokens | 0.40 |
| star_variance | std-dev of stars field across batch | 2.0 | 0.35 |
| vocab_richness | unique words / total words (all reviews pooled) | 1.0 (inherent) | 0.25 |

Length dominates (most predictive of token cost). Variance is second (mixed sentiment = genuinely harder classification). Richness is a tiebreaker.

### Tier selection (Config-driven thresholds)

```
score ≤ router_haiku_threshold (0.35)   → claude-haiku-4-5-20251001
score ≤ router_sonnet_threshold (0.65)  → claude-sonnet-4-6
score >  router_sonnet_threshold        → claude-opus-4-8
```

Defaults chosen so that short, uniform reviews (e.g. "Great product. Love it." × 3,
all 5-star) score ~0.10 → Haiku; and very long heterogeneous batches with diverse
vocabulary and mixed stars score ~0.93 → Opus. Typical mixed-length realistic
batches land in the Sonnet band (~0.40–0.55).

### Tuning guidance

- Raise `router_haiku_threshold` to route more batches to Haiku (cheaper; monitor quality).
- Lower `router_sonnet_threshold` to reduce Opus spend (accept some quality loss on edge cases).
- Set `router_enabled=False` to disable routing entirely and use `gen_model` for all batches.
- The token-length cap (600) and star-variance cap (2.0) are internal constants in
  `pipeline/router.py`; adjust them if your review corpus has a different typical length.

### Cost table update (call_model.py)

`_COST_TABLE` now stores `(input_rate, output_rate, cached_input_rate)` tuples.
Cached-input rates sourced from anthropic.com/pricing (2026-06-14):
- Haiku: $0.80/$4.00/$0.08 per 1M tokens
- Sonnet: $3.00/$15.00/$0.30 per 1M tokens
- Opus: $15.00/$75.00/$1.50 per 1M tokens

`_estimate_cost` now accepts `cached_input_tokens` to compute the reduced rate for
tokens served from Anthropic's prompt cache. Non-cached input = total_input - cached_input.
This is a no-op for Phase 2 (cached_input_tokens defaults to 0); Phase 3 will populate it.

### Logging

`call_model` now accepts a `model` keyword override. When provided, `effective_model`
replaces `cfg.gen_model` in every LogEvent and in the ModelResult. Callers that don't
pass `model=` continue to use `cfg.gen_model` unchanged. The `model` field in every
LogEvent therefore always reflects the actual tier used — no inference needed from
cost or token counts.

### Files changed

- `pipeline/config.py` — added `router_enabled`, `router_haiku_threshold`, `router_sonnet_threshold`
- `pipeline/router.py` — new file: `score_batch_complexity`, `pick_model`
- `pipeline/analyze.py` — imports router; calls `pick_model(batch, cfg)` before each `call_model` call
- `reliability/call_model.py` — added `model` override param; updated `_COST_TABLE` to 3-tuple; updated `_estimate_cost` to accept `cached_input_tokens`
- `tests/test_router.py` — new file: 28 tests (score range, routing logic, override flows through, cost math, config defaults)

---

## 2026-06-14 — Phase 3: Prompt caching

### Caching approach

The analysis prompt was split into two parts:

| Part | Where | Changes each call? | Cached? |
|---|---|---|---|
| `SYSTEM_PROMPT` | `system` field, content block | No | Yes — `cache_control: {type: ephemeral}` |
| `_USER_TEMPLATE` | `messages[0].content` (user role) | Yes (reviews JSON) | No |

`SYSTEM_PROMPT` contains the full task instructions: role description, field definitions, output format spec, rules, good/bad label examples, and a quality bar section. The dynamic user message contains only the reviews JSON array and the bare instruction to return JSON.

### Token count / threshold

Anthropic requires ≥1024 tokens for a cache block to activate. The current `SYSTEM_PROMPT` is approximately 720 words / ~960 tokens (word count × 1.3 tok/word heuristic). If the live run shows the cache does not activate (`cache_creation_input_tokens = 0`), expand the system prompt further (e.g. add more examples or an extended field glossary).

Measured approach: after the gated live run, check `cache_creation_input_tokens` in the first call's log event — if it equals `input_tokens` (or close to it), caching activated; on subsequent calls `cache_read_input_tokens` will be nonzero.

### How savings appear in logs

Two distinct mechanisms are now surfaced:

| Mechanism | Log field | Notes |
|---|---|---|
| Idempotency cache (call never made) | `outcome = "skipped_cache"` | Zero cost; the entire call is a no-op |
| Prompt cache hit (call made, discount applied) | `outcome = "ok"` + `cache_read_tokens > 0` + `prompt_cache_saved_usd > N` | Real API call, but static prefix served at cached_input rate |

`prompt_cache_saved_usd` = `cost_without_cache - cost_with_cache` (never negative). It is only written to the log event when `cache_creation_tokens > 0` or `cache_read_tokens > 0`.

### call_model changes

- New optional `system: list[dict] | None` parameter. When provided, passed as `system=` to `client.messages.create()`. Backward compatible — callers that omit it see no change.
- `ModelResult` gains `cache_creation_tokens: int = 0` and `cache_read_tokens: int = 0` slots.
- `response.usage.cache_creation_input_tokens` and `response.usage.cache_read_input_tokens` are read with `isinstance(v, int)` guard — safe against old SDK versions and MagicMock test fixtures.
- `_prompt_cache_savings(model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)` helper returns `{cost_without_cache, cost_with_cache, saved_usd, cache_read_tokens, cache_creation_tokens}`.
- `LogEvent` gains three optional fields: `cache_creation_tokens`, `cache_read_tokens`, `prompt_cache_saved_usd`.

### Cost math (unchanged rates, new application)

Cache-read tokens are billed at the third element of each `_COST_TABLE` tuple:
- Haiku: $0.08/M (vs $0.80/M standard = 10x discount)
- Sonnet: $0.30/M (vs $3.00/M = 10x discount)
- Opus: $1.50/M (vs $15.00/M = 10x discount)

Cache creation is billed at the standard input rate (same as a cold call). Savings only materialise on the second and subsequent calls within an Anthropic cache window (~5 minutes default).

### Files changed

- `pipeline/analyze.py` — `_PROMPT_TEMPLATE` removed; `SYSTEM_PROMPT`, `_USER_TEMPLATE`, `_SYSTEM_BLOCK` added; `run()` passes `system=_SYSTEM_BLOCK` to `call_model`
- `reliability/call_model.py` — `system` param added; cache token reading; `ModelResult` extended; `_prompt_cache_savings` helper added; `LogEvent` emission conditionally includes cache fields
- `reliability/logger.py` — `LogEvent` gains `cache_creation_tokens`, `cache_read_tokens`, `prompt_cache_saved_usd`
- `tests/test_prompt_cache.py` — new file: 31 tests

---

## 2026-06-15 — Phase 4: /api/metrics + Cost tab

### Aggregation logic

`GET /api/metrics` reads all `data/logs/*.jsonl` except `runs.jsonl`.

- `outcome="skipped_cache"` entries are excluded from cost/latency tallies and counted as `idempotency_skips` (these are idempotency-cache hits — zero cost, no latency, not prompt-cache events).
- All other outcomes (ok, retry, fail) are counted. `retry` and `fail` entries still have cost=0 in practice (call_model only logs cost on success), so they don't skew totals but they do inflate `total_calls`.
- `routing_mix` classifies model names by substring: "haiku" → Haiku tier, "sonnet" → Sonnet tier, "opus" → Opus tier.
- `days_covered` counts distinct JSONL filenames (format `YYYY-MM-DD.jsonl`).
- p95 latency: `sorted[ceil(0.95 * N) - 1]`.
- Returns a fully zeroed structure (no 404) when the log directory has no event files.

### Response shape

```json
{
  "total_cost_usd": 0.0,
  "total_calls": 0,
  "by_model": { "<model_id>": { "calls", "total_cost_usd", "avg_latency_ms", "p95_latency_ms",
                                 "total_input_tokens", "total_output_tokens",
                                 "cache_read_tokens", "cache_creation_tokens", "prompt_cache_saved_usd" } },
  "by_stage": { "<stage>": { "calls", "total_cost_usd", "avg_latency_ms" } },
  "routing_mix": { "haiku_pct", "sonnet_pct", "opus_pct" },
  "idempotency_skips": 0,
  "days_covered": 0,
  "generated_at": "<ISO timestamp>"
}
```

### React Cost tab

New `CostTab.tsx` component: stat cards (total cost, idempotency saves, prompt cache savings), routing-mix donut (Recharts PieChart), cost-by-model + latency-by-model bar charts, per-stage cost breakdown, prompt cache info box.

Tab is always visible — it does not depend on `themeReport.sufficient`. The `App.tsx` renders `<CostTab />` before the sufficiency gate.

### Files changed

- `api/main.py` — added `GET /api/metrics` (read-only, no auth)
- `web/src/types.ts` — added `ModelMetrics`, `StageMetrics`, `RoutingMix`, `MetricsData`
- `web/src/api.ts` — added `api.metrics()`
- `web/src/components/CostTab.tsx` — new file
- `web/src/components/Header.tsx` — added `cost` tab to `TABS` array
- `web/src/App.tsx` — imported `CostTab`; added `cost` to `Tab` type; renders `<CostTab />` for active `cost` tab
- `tests/test_metrics.py` — new file: 13 tests
