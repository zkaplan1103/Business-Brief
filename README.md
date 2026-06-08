# Tideline

> Turns a flood of customer reviews into a clear weekly action brief for small-business owners.

**[Dashboard screenshot — add after running the UI]**

Tideline ingests Amazon product reviews, classifies recurring themes with Claude, and produces a **prioritized weekly action brief**: top issues ranked by impact, each with a concrete recommended action and the review evidence behind it. A business owner can read the full picture in 15 seconds. Briefs run on a recurring schedule, all through a reliability layer that handles retries, cost caps, idempotent reruns, and structured logs.

---

## Quick start

```bash
# 1. Install
uv sync
cd web && npm install && cd ..

# 2. Add API key
cp .env.example .env
# edit .env → ANTHROPIC_API_KEY=sk-ant-...

# 3. Ingest data + prepare demo businesses
uv run python -m pipeline.ingest
uv run python -m pipeline.prepare_demo --business B007IAE5WY --target-week 2022-W40
uv run python -m pipeline.prepare_demo --business B012Q9NGE4 --target-week 2021-W30

# 4. Run the pipeline (generates brief JSON)
uv run python -m pipeline.brief --business B007IAE5WY --week 2022-W40 --skip-ingest
uv run python -m pipeline.brief --business B012Q9NGE4 --week 2021-W30 --skip-ingest

# 5. Start the API + UI (two terminals)
uv run uvicorn api.main:app --reload     # → http://localhost:8000
cd web && npm run dev                    # → http://localhost:5173

# 6. Smoke tests
make smoke
```

---

## Demo businesses

| ASIN | Product | Reviews | Week |
|---|---|---|---|
| `B007IAE5WY` | Salux Nylon Exfoliating Cloth | 17 | 2022-W40 |
| `B012Q9NGE4` | Moroccan Argan Oil Shampoo | 10 | 2021-W30 |

---

## Project layout

```
pipeline/
  ingest.py        download + normalize reviews → data/processed/reviews.jsonl
  analyze.py       classify themes via Claude → ThemeReport JSON
  brief.py         prioritize + write action brief → Brief JSON
  config.py        Config dataclass (all tunables)
  prepare_demo.py  aggregate sparse reviews into a single demo week

reliability/
  call_model.py    ALL model calls go through here (backoff, cost cap, idempotency, logging)
  logger.py        StructuredLogger → data/logs/<date>.jsonl + runs.jsonl + dead-letter/

scheduler/
  run.py           run_once() + APScheduler daily job + circuit breaker

api/
  main.py          FastAPI: /api/businesses · /api/brief · /api/schedule · /api/runs

web/
  src/
    App.tsx        root — loads API data, falls back to fixtures
    api.ts         typed fetch client
    types.ts       contract types (mirrors CONTRACTS.md)
    fixtures.ts    demo fixtures for offline development
    components/    Header · BriefPanel · ThemeChart · TrendIndicator ·
                   EmailDraft · SchedulePanel · RunStatus · EmptyState

eval/
  seam.py          compare() + load_golden() — interface wired, metrics stub
  golden.json      human-labelled golden weeks for the two demo businesses

data/              git-ignored
  processed/       reviews.jsonl (normalized)
  briefs/          <business>/<week>.themes.json + <week>.brief.json (idempotency cache)
  schedule/        <business>.json (ScheduleSettings)
  logs/            <date>.jsonl + runs.jsonl + dead-letter/

docs/
  CONTRACTS.md     frozen interfaces (Review · ThemeReport · Brief · Config · ScheduleSettings)
  DESIGN.md        UI brief (audience, required screens, quality bar)
  STYLE.md         frozen art direction (Warm Premium Hospitality — Cormorant Garamond / Figtree)
  memory/          per-agent decision log
```

---

## Operational design

| Concern | How it's handled |
|---|---|
| **Cost** | Every model call goes through `reliability.call_model`. Per-run cost ceiling (default $1.00) aborts the run if exceeded. |
| **Retries** | Exponential backoff with jitter on retryable errors only (429, 5xx, timeout). Never retries 400/auth — paying to fail. |
| **Idempotency** | A completed `(business, week)` brief is cached in `data/briefs/`. Reruns read from cache — no re-charge. |
| **Partial failure** | If some classification batches fail after retries, the brief is produced from what succeeded and marked `partial`. A partial run never auto-sends email. |
| **Circuit breaker** | After `circuit_breaker_threshold` (default 5) consecutive scheduler failures, the scheduler stops and logs `CircuitOpen` rather than hammering a down API. |
| **Logs** | Structured JSONL per attempt (`data/logs/<date>.jsonl`). One `RunRecord` per scheduled job. Failed runs also written to `data/logs/dead-letter/`. |

---

## Data source

Amazon Reviews 2023 (McAuley Lab) — `McAuley-Lab/Amazon-Reviews-2023` on Hugging Face.
Subset used: `All_Beauty`. Raw data streams via `huggingface_hub` into the local HF cache (`~/.cache/huggingface/`) — never written to `data/raw/` or committed to git.

License: see the [dataset card](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023) for terms.

---

## Running the scheduler

```bash
uv run python -m scheduler.run
# Runs daily at 06:00 local time.
# Reads data/schedule/<business_id>.json for each business.
# Set cadence via the Schedule panel in the UI, or write the JSON directly.
```

---

## Eval seam

```bash
# After generating briefs, run the eval compare against golden labels:
uv run python -m eval.seam

# Output (demo):
#   B007IAE5WY / 2022-W40: themes=7/3, top_match=True, overlap=0.36 — full run
#   B012Q9NGE4 / 2021-W30: themes=7/3, top_match=True, overlap=0.39 — full run
```

`eval/golden.json` holds human-labelled expected top themes. `eval/seam.py` wires `load_golden()` and `compare()` — precision/recall metrics are left as stubs for a future harness (`score_classification`, `score_brief_quality`).
