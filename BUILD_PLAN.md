# Tideline — Build Plan (for Claude Code)

> **Tideline** turns a flood of customer reviews into a clear weekly read. A
> multi-step agent ingests a business's reviews, classifies recurring themes and
> complaints, produces a **prioritized action brief** for the owner (with an
> optional drafted email), presents it in a polished business-facing dashboard,
> and can run on a recurring schedule. Built on the Yelp Open Dataset (or Amazon
> Reviews). Designed to be built fast by a small team of Claude Code subagents.

Read this with `CLAUDE.md` (rules, loaded every session), `docs/CONTRACTS.md`
(interfaces every agent builds against), `docs/DESIGN.md` (UI brief), and
`docs/STYLE.md` (the frozen art direction). This kit is deliberately **UI-weighted**
(§2) and **automation-aware** (§6).

*(Name is a placeholder you can change with one find-and-replace on "Tideline".)*

---

## 1. Goal & scope

Demo-grade, not production. Definition of done:

1. Pick a business and a week.
2. The pipeline reads that business's reviews, classifies sentiment + themes, and clusters recurring complaints/praise.
3. It produces a **prioritized action brief**: top issues ranked by impact, each with a recommended action and the review evidence behind it.
4. It optionally **drafts** an owner-facing email (draft-only by default — see §6/compliance).
5. A business owner can **see all of this at a glance** in a dashboard that looks designed, not generated.
6. The owner can **set a schedule** (weekly/biweekly, which day, auto-send vs. draft-only) so the brief recurs on its own.
7. Automated runs are **reliable and observable**: retries with backoff, a per-run cost ceiling, idempotent reruns, partial-failure handling, and structured logs.
8. A clean eval seam exists (classification + brief quality) — not filled.

Out of scope for v1: auth, multi-business accounts, live scraping, model training,
hosted/multi-tenant scheduling, real email delivery, and production reliability
infra (distributed queues, alerting). Those are labeled as productionization.

**Grounding rule (carried from the RAG project):** the brief never invents a
complaint. Every brief item traces to real reviews and shows its evidence. An
owner must be able to click a recommendation and see the reviews that justify it.

---

## 2. The scale tweak: UI is the senior role

The analysis only creates value if a non-technical owner can absorb it in fifteen
seconds. A correct brief in an ugly dashboard is a failed product. So:

- The **ui-engineer** is the elevated role. It gets a design brief (`docs/DESIGN.md`),
  executes a frozen art direction (`docs/STYLE.md`), and works in **React + Tailwind**
  (which also plays to the builder's existing stack).
- The pipeline agents (data, analysis, brief) stay **lean** — plumbing that feeds the UI.

**Proportionality decisions, stated out loud:**
- *4 subagents* — each is a genuinely independent workstream with a clean interface (Review → ThemeReport → Brief → UI). Earns its place.
- *UI elevated, not split* — no separate design-system agent; one strong UI agent honoring DESIGN.md + STYLE.md is right-sized for a 3–5 day build.
- *Analysis kept as one agent* — sentiment + themes + clustering are one pipeline over one dataset.
- *Scheduling and reliability get NO agent* — they're cross-cutting plumbing/utilities, not workstreams. Built by the orchestrator (scaffold + integration).
- *Eval is a seam, not an agent.*
- *Worktree isolation kept* for the four parallel builders.

---

## 3. Component architecture

```
 Yelp/Amazon   ┌────────────┐  reviews.jsonl   ┌──────────────┐  ThemeReport
   dataset ───▶│  ingest +  │ ───────────────▶ │  classify +  │ ──────────────┐
               │  normalize │  (Review schema) │  cluster     │               │
               └────────────┘                  └──────────────┘               ▼
                                                                      ┌──────────────┐
   ┌──────────────────────────┐  ◀──────────────────────────────────│  prioritize  │
   │  React dashboard (UI)     │   ThemeReport + Brief (JSON/API)     │  + draft     │
   │  trends · themes · brief  │                                      └──────────────┘
   │  · evidence · email       │        ┌───────────┐  runs pipeline on cadence
   │  · schedule settings      │◀──────▶│ scheduler │  (reads ScheduleSettings)
   └──────────────────────────┘ Schedule└───────────┘
                                 Settings        │
   every model call routed through ──────────────┘
   reliability/ : retry+backoff · cost ceiling · idempotency · structured logs
```

The **reliability module** is a shared wrapper every model call goes through; the
**scheduler** is a thin layer that reads `ScheduleSettings` and runs the headless
pipeline on cadence. Neither is new core logic — both are plumbing.

Default stack:

| Layer | Default | Why |
|---|---|---|
| Pipeline | Python 3.11 + `uv` | data + analysis + brief |
| Classification | Claude (`haiku` dev / `sonnet` final), batched | fast to build, no labeled-data training; matches the résumé Claude story |
| Reliability | shared `reliability/` wrapper (backoff, cost cap, logging, idempotency) | safe unattended automation |
| Brief output | JSON in `data/briefs/<business>/<week>.json` | decouples pipeline from UI; also the idempotency cache |
| Serving | thin FastAPI (or static JSON import) | lets the UI dev work independently |
| Scheduler | local APScheduler (or documented cron) | recurring brief; demo-grade |
| **UI** | **React + Tailwind + Vite, Motion** | business-facing; see `docs/DESIGN.md` + `docs/STYLE.md` |

All config-switchable — see `Config` in `docs/CONTRACTS.md`.

---

## 4. The agent roster

The **main session orchestrates** (Phase 0 + integration) and delegates heavy
isolated work to subagents so only their final reports return to main context.
Recon on Haiku, building on Sonnet.

| Agent | File | Model | Does | Tag |
|---|---|---|---|---|
| `Explore` (built-in) | — | haiku | read-only recon: inspect dataset schema before bulk load | — |
| `data-engineer` | `.claude/agents/data-engineer.md` | sonnet | load + normalize reviews → `reviews.jsonl` | `data` |
| `analysis-engineer` | `.claude/agents/analysis-engineer.md` | sonnet | sentiment + themes + clustering → `ThemeReport` | `analysis` |
| `brief-engineer` | `.claude/agents/brief-engineer.md` | sonnet | prioritize + write brief + draft email → `Brief` | `brief` |
| `ui-engineer` ⭐ | `.claude/agents/ui-engineer.md` | sonnet | the dashboard, against DESIGN.md + STYLE.md | `ui` |

⭐ = elevated role.

---

## 5. Phases

### Phase 0 — Scaffold + contracts + art direction + reliability core + data (orchestrator, serial)
1. `uv init`, scaffold React app, `.gitignore` (`data/raw/`, `data/briefs/`, `data/schedule/`, `data/logs/`, `node_modules/`, `.venv/`).
2. Freeze `docs/CONTRACTS.md` and `docs/DESIGN.md`.
3. **Art-direction pass (inline):** reason from DESIGN.md, propose 2–3 directions, commit to one, fill in and **freeze `docs/STYLE.md`** (concrete fonts, palette hex, tokens, motion). Surface it for redirect before any screens exist.
4. **Build the reliability core** (`reliability/`): the `call_model` wrapper (retry+backoff+jitter, retryable-only, max-retries cap, per-run cost ceiling, idempotency cache, structured logging) and the logger, against the shapes in CONTRACTS §7. Freeze its interface so Phase-1 agents route every model call through it.
5. `Explore` (Haiku) inspects the Yelp dataset schema before any bulk load (§7-data).
6. Acquire data into `data/raw/`; record source + license in `docs/memory/00-decisions.md`.

Nothing parallel starts until CONTRACTS, DESIGN, STYLE, and the reliability interface are frozen and data is verified.

> **Architect note (for the architect-agent project):** Phase 0 front-loads the
> *irreversible-if-wrong* decisions. RAG → data contracts. UI-primary → a frozen
> STYLE.md. Automated → a reliability/observability contract. Condition-table rows:
> **UI is a primary surface → Phase-0 art-direction + STYLE.md**; **runs unattended /
> calls a paid API on a schedule → Phase-0 reliability core + logging contract.**

### Phase 1 — Parallel build (4 subagents, worktree-isolated)
Dispatch all four against their contracts + fixtures + the frozen reliability wrapper. Each returns a SHORT report.
- `data-engineer` → `reviews.jsonl` + loader
- `analysis-engineer` → `ThemeReport` (model calls via `reliability.call_model`; batch-level partial-failure handling)
- `brief-engineer` → `Brief` + email draft (via the wrapper; draft-only)
- `ui-engineer` → dashboard (fixtures for Brief/ThemeReport/ScheduleSettings; plus a small run-status surface so failures are visible)

### Phase 2 — Integration (orchestrator, serial)
1. Merge worktrees; swap stubs for real implementations; wire the FastAPI seam (or generated-JSON import).
2. Add the **scheduler**: reads `ScheduleSettings`, runs the headless pipeline on cadence, all through the reliability wrapper. Verify idempotency (a rerun of a completed week is a cache hit, not a re-charge), the circuit breaker (stops after N consecutive failures), and graceful degradation (a failed/partial run never auto-sends — falls back to draft + flag).
3. Generate real briefs for 2–3 sample businesses; run `make smoke` (busy business, sparse week, AND a forced-failure case to prove backoff + logging + dead-letter work).
4. Fix the seams; `/rewind` over stacking corrections.

### Phase 3 — Eval seam + docs (orchestrator)
1. Wire the **eval seam only** (held-out reviews → "did the brief's top issues match a human's"); empty `eval/` package.
2. Write `README.md` for a non-technical reader, **leading with a dashboard screenshot/gif**, and include a short "operational design" note (cost ceiling, backoff, idempotency, logs) — that's the production-minded signal.

---

## 6. Reliability & observability (the automation layer)

Because the scheduler runs unattended and calls a paid API, operational failure is
a first-class concern. Organized by the three goals: **spend less, perform reliably,
log everything.** Demo-grade but genuinely implemented; heavier infra is labeled
productionization.

**Spend less**
- Every model call goes through `reliability.call_model`. Retries use **exponential backoff with jitter**, and **only on retryable errors** (429, 5xx, timeout) — never retry 400/auth (paying to fail).
- **Hard caps**: `max_retries`, and a per-run **cost ceiling** (`run_cost_ceiling_usd`) that aborts the run if exceeded. (Also set Claude Code's own cost cap in settings.json for the dev loop.)
- **Idempotency / caching**: a completed (business, week) is cached in `data/briefs/`; reruns read the cache instead of re-calling the model.
- **Batching**: classification runs in batches so a failure re-runs one batch, not the corpus.

**Perform reliably**
- **Circuit breaker**: after `circuit_breaker_threshold` consecutive failures the scheduler stops and surfaces the problem instead of hammering a down API.
- **Partial-failure handling**: if some analysis batches fail after retries, produce the brief from what succeeded and mark the run `partial`, rather than failing the whole week.
- **Graceful degradation (auto-send)**: a failed or partial run must **not** send a broken/empty email — it falls back to draft + flag for review. Ties to the compliance default (§ CONTRACTS).

**Log everything**
- **Structured JSONL logs** (`data/logs/`): per attempt — ts, run_id, business, week, stage, model, tokens, cost, latency, outcome, error_class. (Shapes in CONTRACTS §7.)
- **Run manifest** per scheduled job: status (success/partial/failed), totals, note — so a human sees history without re-running.
- **Dead-letter record**: failed runs written durably (`data/logs/dead-letter/`) for later retry, not lost.

This lives as a shared `reliability/` module + a logging contract — a cross-cutting
utility (like the contracts), not its own subagent.

---

## 7. Data sources (verify before bulk download)

| Dataset | What | Use | Note |
|---|---|---|---|
| Yelp Open Dataset | real local-business reviews with stars, text, dates, business_id | source reviews; native "small business + weekly" fit | **Check current license terms before use.** |
| Amazon Reviews 2023 (McAuley Lab) | product reviews with ratings, text, timestamps | alternative source | Hugging Face: `McAuley-Lab/Amazon-Reviews-2023`. Reframe "business" as "product." |

Keep raw data out of git; cite source + license in the README.

---

## 8. Tag-based memory

`docs/memory/INDEX.md` maps tags → files. Before a task: read INDEX + your tagged
file only. After: append a dated entry to your tagged file + one line to
`00-decisions.md`. Keeps context bounded.

---

## 9. Kickoff (paste into Claude Code at the repo root)

```
Read CLAUDE.md, BUILD_PLAN.md, docs/CONTRACTS.md, docs/DESIGN.md, and docs/STYLE.md
in full. Execute Phase 0 yourself, serially: scaffold + freeze CONTRACTS + DESIGN
+ do the art-direction pass to fill and freeze STYLE.md + build and freeze the
reliability core (reliability/) + acquire data. Surface the art direction you chose
so I can redirect it before any screens exist. Do NOT start Phase 1 until CONTRACTS,
DESIGN, STYLE, and the reliability interface are frozen and data is verified.
Report back and wait for my go.
```

Then:

```
Dispatch Phase 1: spawn data-engineer, analysis-engineer, brief-engineer, and
ui-engineer in parallel via the Task tool, each in a worktree against its contract,
its fixture, and the frozen reliability wrapper (all model calls go through it).
Give the ui-engineer the extra care — it's the senior role. Collect only final
reports, then do Phase 2 integration (incl. scheduler + the forced-failure smoke
test) and run `make smoke`.
```

---

## 10. Version note

Per-agent `memory:` scopes need Claude Code ≥ v2.1.33; `isolation: worktree` is
recent too. On an older build, drop those frontmatter lines and run the builders
sequentially. Check `claude --version`.
