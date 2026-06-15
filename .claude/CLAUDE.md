# CLAUDE.md — Tideline

Turns a business's reviews into a weekly prioritized action brief, shown in a
polished business-facing dashboard, runnable on a recurring schedule. Demo-grade.
Plan: `BUILD_PLAN.md`. Interfaces: `docs/CONTRACTS.md`. Design brief: `docs/DESIGN.md`.
Art direction (frozen Phase 0): `docs/STYLE.md`.

## Golden rules
- **Honor `docs/CONTRACTS.md`, `docs/DESIGN.md`, and `docs/STYLE.md`.** All frozen in Phase 0. To change one, edit it first and log it in `docs/memory/00-decisions.md`.
- **Evidence over invention.** Every brief item traces to real reviews and lists their ids. Never surface a complaint the reviews don't support. Too few reviews for a meaningful week → say so; don't manufacture a brief.
- **UI is the senior role.** The dashboard executes the frozen `docs/STYLE.md` and must look intentionally designed, not generic SaaS. A correct brief in an ugly UI is a failed deliverable.
- **Art direction is decided in Phase 0, not at build time.** The UI agent executes STYLE.md; it does not pick fonts/colors itself.
- **All model calls go through `reliability.call_model`.** Never call the model API directly from a pipeline stage. The wrapper owns retries/backoff, the cost ceiling, idempotency caching, and structured logging. Direct calls bypass cost caps and logging.
- **Email defaults to draft-only; never auto-send in v1.** Real sending triggers consent/anti-spam obligations (CAN-SPAM/CASL/GDPR) and needs a consent model first — see CONTRACTS §5 compliance note. A failed/partial run must never send. Generate drafts; a human sends.
- **Respect data licenses.** Verify the dataset's terms. Raw data stays in `data/raw/` (git-ignored); cite the source in the README.

## Project layout
```
pipeline/         ingest.py  analyze.py  brief.py  config.py
reliability/      call_model wrapper (retry/backoff/cost-cap/idempotency) + structured logger
scheduler/        local scheduler running the pipeline on cadence (reads ScheduleSettings)
api/              FastAPI seam serving briefs + schedule (or generated JSON)
web/              React + Tailwind + Vite dashboard (brief, viz, schedule panel, run-status)
data/raw/         downloaded corpora (git-ignored)
data/briefs/      generated brief + theme JSON; also the idempotency cache (git-ignored)
data/schedule/    per-business ScheduleSettings JSON (git-ignored)
data/logs/        structured JSONL logs + run manifests + dead-letter/ (git-ignored)
eval/             eval seam only (future)
docs/             CONTRACTS.md, DESIGN.md, STYLE.md, memory/
tests/            unit + `make smoke`
```

## Commands
- Install: `uv sync` (pipeline) and `cd web && npm install`
- Run pipeline: `uv run python -m pipeline.brief --business <id> --week <YYYY-Www>`
- Serve API: `uv run python -m api.run` (do NOT use `uvicorn api.main:app` CLI directly — see api/run.py)
- Run scheduler: `uv run python -m scheduler.run`
- Run UI: `cd web && npm run dev`
- Smoke: `make smoke` (busy business, sparse week, forced-failure case)

## Defaults (overridable via Config)
- Classification: Claude (`haiku` dev / `sonnet` final), batched. Brief output: JSON in `data/briefs/`.
- Reliability: exp backoff + jitter on retryable errors only; per-run cost ceiling; idempotent reruns; structured JSONL logs.
- UI: React + Tailwind + Vite + Motion.

## Working style (token discipline)
- Delegate heavy/isolated work to subagents; bring back only their final report.
- Recon with `Explore` (Haiku, read-only). Build with Sonnet.
- Never load full review files or the dataset into context — sample, query counts, batch classification.
- Cache classification to `data/briefs/`; reruns are cache hits, not re-charges.
- `/clear` between phases; `/compact` before auto-compact; `/rewind` on a wrong turn.

## Memory protocol
Before a task: read `docs/memory/INDEX.md`, then ONLY your tagged file(s).
After: append a dated entry to your tagged file + one line to `docs/memory/00-decisions.md`.

## Definition of done
Pick business + week → classify themes from real reviews → prioritized brief with evidence → optional draft email → a dashboard an owner reads in 15 seconds (executing STYLE.md) → recurring schedule (cadence/day/email-mode) → reliable automation (backoff, cost ceiling, idempotency, partial-failure, structured logs) → abstains on sparse weeks → eval seam exists (unfilled) → README leads with a dashboard screenshot.
