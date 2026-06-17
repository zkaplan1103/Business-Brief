# BizBrief — Setup Guide

End-to-end instructions to run BizBrief locally, plus notes on the production
hardening already built in and the optional AWS serverless deployment.

Everything below is verified against the actual code on `main` — entry points,
env vars, and CLI flags are copied from the repo, not assumed.

---

## 0. What you're setting up

BizBrief has three runnable pieces:

| Piece | Command | Purpose |
|---|---|---|
| **Pipeline** | `uv run python -m pipeline.brief …` | Ingest reviews → classify themes → write a brief (calls Claude) |
| **API** | `uv run python -m api.run` | FastAPI serving briefs, metrics, eval, schedule (port 8000) |
| **Dashboard** | `cd web && npm run dev` | React UI (port 5173, proxies `/api` → 8000) |

There's also an optional **scheduler** (recurring runs) and an optional
**serverless** deployment (`infra/`, AWS SAM) — both covered at the end.

---

## 1. Prerequisites

| Tool | Min version | Why | Install |
|---|---|---|---|
| **Python** | 3.11+ | pipeline / API runtime | `brew install python@3.11` |
| **uv** | recent | Python dep + venv manager | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Node.js** | 20+ (22 tested) | dashboard build | `brew install node` |
| **npm** | ships with Node | dashboard deps | — |
| **An Anthropic API key** | — | the pipeline calls Claude | https://console.anthropic.com → API Keys |

Optional, only for the serverless half (Section 8):

| Tool | Why | Install |
|---|---|---|
| **AWS SAM CLI** | build/deploy the Lambda stack | `brew install aws-sam-cli` |
| **AWS CLI** | credentials + S3 upload | `brew install awscli` |
| **Docker** | `sam local invoke` | https://docker.com |

Check what you already have:

```bash
python3 --version && uv --version && node --version && npm --version
```

---

## 2. Clone & install

```bash
git clone https://github.com/zkaplan1103/Business-Brief.git
cd Business-Brief

# Installs Python deps (creates .venv) AND web deps in one shot:
make install
# Equivalent to:
#   uv sync
#   cd web && npm install
```

`uv sync` reads `pyproject.toml` + `uv.lock` and creates `.venv/` automatically.
You do **not** need to manually activate the venv — `uv run` handles it.

---

## 3. Configure secrets (`.env`)

```bash
cp .env.example .env
```

Then edit `.env`. Three variables matter:

```bash
# 1. REQUIRED — your Anthropic key. The pipeline won't run without it.
ANTHROPIC_API_KEY=sk-ant-...

# 2. REQUIRED FOR WRITES — shared secret guarding PUT /api/schedule.
#    Generate a strong value:
#      python3 -c "import secrets; print(secrets.token_urlsafe(32))"
BIZBRIEF_API_KEY=<paste the generated value>

# 3. LEAVE EMPTY — proxy-trust control. Empty is the secure default.
#    (See Section 7 for why this matters.)
FORWARDED_ALLOW_IPS=
```

`.env` is git-ignored and never committed. The repo only ships `.env.example`.

> If `BIZBRIEF_API_KEY` is unset, the API still serves all **read** endpoints,
> but every **write** (`PUT /api/schedule`) returns `503` by design — writes are
> locked until a key exists.

---

## 4. Generate demo data + briefs

BizBrief reads the **Amazon Reviews 2023** dataset (`All_Beauty` subset) from
Hugging Face. Raw data streams to the local HF cache — never committed to git.

```bash
# 4a. Download + normalize reviews → data/processed/reviews.jsonl
uv run python -m pipeline.ingest

# 4b. Aggregate a product's reviews into one demo week
#     (the dataset is sparse: ~1 review per product per real week)
uv run python -m pipeline.prepare_demo --business B007IAE5WY --target-week 2022-W40
uv run python -m pipeline.prepare_demo --business B012Q9NGE4 --target-week 2021-W30

# 4c. Run the full pipeline → writes the brief JSON (THIS CALLS CLAUDE — costs cents)
uv run python -m pipeline.brief --business B007IAE5WY --week 2022-W40 --skip-ingest
uv run python -m pipeline.brief --business B012Q9NGE4 --week 2021-W30 --skip-ingest
```

**Demo businesses** (ASINs that work out of the box):

| ASIN | Product | Week |
|---|---|---|
| `B007IAE5WY` | Salux Nylon Exfoliating Cloth | `2022-W40` |
| `B012Q9NGE4` | Moroccan Argan Oil Shampoo | `2021-W30` |

> **How the UI finds a business:** the dashboard only lists businesses that have
> a generated brief in `data/briefs/<business_id>/`. If a business doesn't show
> up, you haven't run step **4c** for it yet.

> **Cost control:** every model call goes through `reliability.call_model`,
> which enforces a per-run cost ceiling (default $1.00) and caches completed
> `(business, week)` briefs. Re-running step 4c for the same week is a cache hit
> — free, no re-charge.

---

## 5. Run the app (two terminals)

**Terminal 1 — API:**

```bash
uv run python -m api.run          # → http://localhost:8000
```

> ⚠️ **Always start the API with `python -m api.run`** — NOT `uvicorn api.main:app`.
> `api/run.py` passes `forwarded_allow_ips=[]` to uvicorn, which is the only
> reliable way to keep the per-IP rate-limiting and auth defenses intact
> (see Section 7). The bare uvicorn CLI trusts `X-Forwarded-For` and silently
> defeats them.

**Terminal 2 — Dashboard:**

```bash
cd web && npm run dev             # → http://localhost:5173
```

Open **http://localhost:5173**. Vite proxies all `/api/*` calls to
`localhost:8000`, so both must be running.

**Tabs:**
- **Overview / Charts / Actions** — the owner-facing brief (needs a brief generated in step 4c)
- **Cost** — live cost/latency/routing metrics (needs the API running; reads `data/logs/`)
- **Eval** — quality-vs-cost comparison (works even without the API — falls back to a bundled fixture)

---

## 6. Verify it works

```bash
# Full test suite (210 tests, no network/model calls — all mocked)
uv run pytest -q

# End-to-end smoke: busy business, sparse week (abstains), forced-failure case
make smoke

# Quick API health check (API must be running)
curl -s http://localhost:8000/api/businesses | head
```

---

## 7. Production hardening (already built in)

These are live in the code — you don't implement them, but you should know they
exist and how to configure them. All limits are in `pipeline/config.py`.

| Control | Default | Where to change |
|---|---|---|
| Per-IP rate limit (reads) | 60/min | `Config.rate_limit_reads_per_min` |
| Per-IP rate limit (writes) | 10/min | `Config.rate_limit_writes_per_min` |
| Request body cap | 10 KB | `Config.max_request_body_bytes` |
| Auth-failure lockout | 5 tries → 300 s ban | `Config.auth_lockout_*` |
| Per-run model cost ceiling | $1.00 | `Config.run_cost_ceiling_usd` |
| Metrics read cap | 30 days / 50k lines | `Config.metrics_max_*` |

**Auth on writes:** `PUT /api/schedule` requires an `X-API-Key` header matching
`BIZBRIEF_API_KEY`. Example:

```bash
curl -X PUT http://localhost:8000/api/schedule \
  -H "X-API-Key: $BIZBRIEF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"business_id":"B007IAE5WY","cadence":"weekly","day_of_week":"mon","email_mode":"draft_only"}'
```

**Why `FORWARDED_ALLOW_IPS` must stay empty:** uvicorn's default trusts
`X-Forwarded-For` from localhost, which would let any local client spoof its IP
and bypass rate-limiting + lockout. Starting via `api/run.py` neutralizes this
regardless of the env var — but don't set the var to `127.0.0.1` unless you
genuinely sit behind a trusted reverse proxy you control.

---

## 8. Optional: recurring schedule

Runs the pipeline automatically on a cadence (reads `data/schedule/<id>.json`,
which the Settings panel in the UI writes):

```bash
uv run python -m scheduler.run
# Fires daily at 06:00 local time; each business's day_of_week setting decides
# whether it actually runs that day. Has a circuit breaker (stops after 5
# consecutive failures rather than hammering a down API).
```

---

## 9. Optional: AWS serverless deployment (`infra/`)

> **Status: deployable, not deployed.** This is complete, tested SAM + handler
> code. Deploying it incurs AWS + Anthropic charges. You do NOT need this to run
> BizBrief locally — it's a separate, résumé-grade serverless variant.

**Run a handler locally (no AWS account, needs Docker + SAM CLI):**

```bash
cd infra
make validate         # lint the SAM template
make local-analyze    # invoke the analyze Lambda against a sample event
```

**Deploy to a real AWS account (incurs charges):**

```bash
cd infra
make deploy           # sam build && sam deploy --guided
                      # prompts for stack name, region, and AnthropicApiKey

# Then trigger the pipeline by uploading a file to the raw bucket:
aws s3 cp <file>.jsonl s3://<RawBucketName-from-outputs>/uploads/<business>/<week>.jsonl

# Tear down:
make delete
```

Architecture, DynamoDB design, and the full walkthrough live in
[`infra/README.md`](infra/README.md).

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Dashboard shows no businesses | No brief generated yet | Run Section 4c for that business |
| Cost tab: "Metrics unavailable" | API not running | Start `uv run python -m api.run` (Cost tab has no fixture) |
| `PUT /api/schedule` → 503 | `BIZBRIEF_API_KEY` unset | Set it in `.env`, restart API |
| `PUT /api/schedule` → 401 | Wrong/missing `X-API-Key` header | Send the header matching `.env` |
| Pipeline errors on auth | `ANTHROPIC_API_KEY` missing/invalid | Check `.env` |
| `make smoke` model errors | No API key, or hit cost ceiling | Set key; raise `run_cost_ceiling_usd` if needed |
| Port 8000/5173 in use | Another process | Kill it, or change the port |

---

## Quick reference — the whole thing from scratch

```bash
# one-time
git clone https://github.com/zkaplan1103/Business-Brief.git && cd Business-Brief
make install
cp .env.example .env            # then add ANTHROPIC_API_KEY + BIZBRIEF_API_KEY

# data + briefs
uv run python -m pipeline.ingest
uv run python -m pipeline.prepare_demo --business B007IAE5WY --target-week 2022-W40
uv run python -m pipeline.brief --business B007IAE5WY --week 2022-W40 --skip-ingest

# run (two terminals)
uv run python -m api.run        # terminal 1 → :8000
cd web && npm run dev           # terminal 2 → :5173
```
