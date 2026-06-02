# Tideline

> Turns a flood of customer reviews into a clear weekly action brief for small-business owners.

**[Dashboard screenshot — added after Phase 1]**

Tideline ingests a business's Yelp reviews, classifies recurring themes, and produces a prioritized weekly brief: top issues ranked by impact, each with a concrete recommended action and the review evidence behind it. It presents the brief in a polished business-facing dashboard and runs on a recurring schedule.

## Quick start

```bash
# Python pipeline
uv sync

# UI
cd web && npm install && npm run dev

# Run pipeline (after adding API key to .env and downloading dataset)
uv run python -m pipeline.brief --business <id> --week <YYYY-Www>

# Serve API
uv run uvicorn api.main:app --reload

# Run scheduler
uv run python -m scheduler.run

# Smoke tests
make smoke
```

## Setup

1. Copy `.env.example` to `.env` and add your `ANTHROPIC_API_KEY`.
2. Download the [Yelp Open Dataset](https://www.yelp.com/dataset) and place files in `data/raw/yelp/`.
3. `uv sync && cd web && npm install`

## Operational design

- **Cost ceiling:** every model call goes through `reliability.call_model`, which enforces a per-run cost ceiling (default $1.00) and aborts if exceeded.
- **Backoff:** retries use exponential backoff with jitter, on retryable errors only (429, 5xx, timeout) — never on 400/auth.
- **Idempotency:** a completed `(business, week)` is cached; reruns are cache hits, not re-charges.
- **Partial failure:** if some classification batches fail, the brief is produced from what succeeded and marked `partial`. A partial run never auto-sends.
- **Logs:** structured JSONL in `data/logs/`; failed runs written to `data/logs/dead-letter/`.

## Project layout

```
pipeline/      ingest · analyze · brief · config
reliability/   call_model wrapper (retry/backoff/cost-cap/idempotency) + logger
scheduler/     local APScheduler running the pipeline on cadence
api/           FastAPI seam (briefs · schedule · runs)
web/           React + Tailwind + Vite dashboard
data/          raw/ · briefs/ · schedule/ · logs/  (all git-ignored)
eval/          eval seam (Phase 3 stub)
docs/          CONTRACTS.md · DESIGN.md · STYLE.md · memory/
tests/         unit tests + smoke suite
```

## Data source

Yelp Open Dataset — see [yelp.com/dataset](https://www.yelp.com/dataset) for license terms.
Raw data is git-ignored; never committed.
