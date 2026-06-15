# BizBrief — Cost-Engineering Upgrade Plan

> Evolves the existing Claude review-analysis pipeline into a showcase of **cost
> engineering**: a model router (Haiku ↔ Sonnet ↔ Opus), prompt caching, a live
> cost/latency/throughput dashboard, and a quality-vs-cost eval — fronted by a
> genuinely red-teamed security layer. A separate, later phase adds the AWS
> serverless ingest path (S3 → Lambda → DynamoDB).
>
> Status: **approved, not yet started.** Read with `CLAUDE.md`, `BUILD_PLAN.md`,
> `docs/CONTRACTS.md`. This plan does not change frozen contracts unless a phase
> says so explicitly (and then it edits CONTRACTS.md first + logs in
> `docs/memory/00-decisions.md`).

---

## Why this upgrade

The reliability spine already exists — `reliability/call_model.py` tracks
per-call tokens, cost, and latency; enforces a per-run cost ceiling; caches for
idempotency; and logs structured JSONL. This upgrade **surfaces and extends**
that instrumentation into a named, salary-moving skill: inference-cost
engineering, with a written cost-benefit case study as the artifact.

Two résumé stories, sequenced:
- **Cost-engineering half** (Phases 0–6) — AI Engineer / AI consulting signal.
- **Serverless half** (Phase 7+) — AWS serverless event-pipeline signal.

They share almost no code; the cost half ships first as a standalone artifact.

---

## Guiding constraints (every phase)

- **API spend is gated.** Build and test against mocked model responses first.
  Before any real Claude calls, quote a rough cost and wait for explicit go.
  The `run_cost_ceiling_usd = $1.00` per-run ceiling is the hard backstop.
- **Route between Claude tiers only** — Haiku ↔ Sonnet ↔ Opus (one Anthropic
  SDK). NOT Nova/Gemma/Bedrock; cross-provider routing is a separate, larger
  effort and is out of scope here.
- **Security is demo-grade but real, and in-process** — rate limiting, input
  validation, payload caps, cost-amplification guard, auth on mutating routes,
  secret hygiene. No Redis/WAF/cloud infra.
- **Security gates every endpoint.** A baseline pass secures the existing
  surface first; thereafter no new endpoint is "done" until `security-engineer`
  has hardened it and `red-team` has failed to break it.

### Who does what

| Only the human (Zack) | Claude (me) |
|---|---|
| Approve each batch of real Claude calls (I quote cost first) | All code, tests, refactors, docs drafts |
| Set the "is Haiku good enough" quality floor | Run everything against mocks |
| Sign off the eval golden answer key (~30 min) | Build router, caching, metrics, eval harness, security |
| Final case-study wording (your voice) | Run the red-team / security iteration |
| (Phase 7+) Create AWS account + IAM + credentials | (Phase 7+) All Lambda/S3/DynamoDB code |

---

## Phase 0 — Restructure `.claude/` + subagent roster

**Problem being fixed:** agent `.md` files are loose in `.claude/`, but Claude
Code only discovers subagents in `.claude/agents/`. They also still say
"Tideline" and reference stale memory paths.

- **0.1** Create `.claude/agents/`; move agent definitions into it. Move frozen
  project docs that currently sit in `.claude/` (`BUILD_PLAN.md`, `CONTRACTS.md`,
  `DESIGN.md`, `STYLE.md`, `INDEX.md`, `00-decisions.md`, `README.md`) to where
  `CLAUDE.md` already says they live (`docs/` and `docs/memory/`). Resolve any
  duplicates against the canonical `docs/` copies.
- **0.2** Refresh the three build agents (`data-engineer`, `analysis-engineer`,
  `brief-engineer`): de-"Tideline", fix memory paths, add awareness of the new
  router/caching/metrics work. Park `ui-engineer` (this round's UI work is one
  additive tab, not a from-scratch build).
- **0.3** Add new agents:

  | Agent | Role | Model | Writes app code? |
  |---|---|---|---|
  | `cost-engineer` | Router, prompt caching, `/api/metrics`, cost math | sonnet | yes |
  | `eval-engineer` | Quality-vs-cost eval harness + table | sonnet | yes |
  | `security-engineer` ⭐ | Rate limiting, validation, payload caps, cost-amplification guard, auth on mutating routes, secret hygiene | sonnet | yes |
  | `red-team` ⭐ | Adversary. Floods endpoints, malformed/oversized payloads, cost-amplification, prompt injection via review text. Files findings; does NOT patch. | sonnet | **no** (read + run only) |

  The red-team agent deliberately lacks Write access to app code, so it can't
  "fix" a finding by weakening the check — it reports, `security-engineer` fixes,
  repeat until red-team is out of breaks.

**Spend:** none. **Human touchpoint:** none (review agent files if you wish).

---

## Phase 1 — Security baseline (the existing surface, before new endpoints)

`security-engineer` hardens what's already exposed, then `red-team` attacks,
then fix-loop until it holds.

Known starting issues:
- `PUT /api/schedule` (`api/main.py`) is **unauthenticated and unrate-limited** —
  writes arbitrary JSON to `data/schedule/`.
- No rate limiting, request-size caps, or cost-amplification guard anywhere.

Builds:
- Per-IP rate limiting (token bucket; stricter on mutating routes).
- Request-size / payload caps.
- Hardened input validation across all routes.
- **Cost-amplification guard** — per-IP and global — because endpoints can
  trigger model calls, so request floods spend real money. (Ties rate limiting
  directly to the cost story.)
- Secret hygiene: confirm `.env` is git-ignored, never logged, never in an
  error response.

**Spend:** none (red-team uses local/mocked traffic). **Human touchpoint:**
review the red-team findings report (good artifact; you may weigh in on severity).

---

## Phase 2 — Model router (Haiku ↔ Sonnet ↔ Opus)

- Add a per-call `model` override to `reliability/call_model.py` (today it always
  uses `cfg.gen_model`).
- Complexity scorer per batch (review length, star variance, vocabulary signals)
  → picks a tier.
- Wire into `pipeline/analyze.py`; log which model handled each batch so the
  dashboard can show the routing mix.
- Tested against mocks first.

**Spend:** one gated live run to confirm. **Human touchpoint:** the **quality
floor** — I show side-by-side Haiku/Sonnet outputs; you decide what's good enough.

---

## Phase 3 — Prompt caching

- Add `cache_control` to the static prompt prefix in `pipeline/analyze.py`.
- Read cached-token fields from `response.usage`; fold into cost math; log them
  distinctly from idempotency-cache skips (prompt-cache savings ≠ call-skips —
  showing both signals understanding).

**Spend:** one gated live run for real cache-hit numbers. **Human touchpoint:** none.

---

## Phase 4 — Cost / latency / throughput dashboard

- `cost-engineer` adds `/api/metrics` aggregating existing `data/logs/` JSONL by
  model/stage: cost, avg latency, throughput, routing mix, cache savings.
- New dashboard tab with charts.
- **Gate:** `security-engineer` rate-limits + validates the new endpoint;
  `red-team` attacks it before it's "done."

**Spend:** none. **Human touchpoint:** none beyond viewing the result.

---

## Phase 5 — Quality-vs-cost eval

- `eval-engineer` builds the harness: same fixture reviews through
  Haiku/Sonnet/Opus → theme-overlap score vs. golden set → cost-vs-quality table.

**Spend:** one gated live run across three models. **Human touchpoint (the big
one):** **sign off the golden answer key** (~30 min on ~20 reviews) so the eval
isn't circular.

---

## Phase 6 — Case study + docs

- Draft the written cost-benefit case study: "X reviews/day, $Y/1k reviews, Z%
  reduction from routing + caching vs. naive single-model," + the A/B quality
  table + the red-team findings summary as a security artifact.
- Update README.

**Spend:** none. **Human touchpoint:** final wording in your voice.

---

## Phase 7+ — Serverless ingest (SEPARATE PROJECT, sequenced after Phase 6)

Starts only once the cost half is shipped. Distinct résumé signal (AWS serverless
event pipeline), distinct skill set, external dependency.

- **Human, first:** create AWS account, IAM users, credentials. I cannot and will
  not create cloud accounts or hold cloud keys.
- Rewrite `pipeline/ingest.py`: from "stream a local HF JSONL" to "Lambda
  triggered on S3 upload → writes to DynamoDB."
- DynamoDB key/access-pattern design.
- Read-adapter so `pipeline/analyze.py` can read from DynamoDB instead of local
  `data/processed/reviews.jsonl`.
- SAM/CDK or Terraform deploy; CloudWatch wiring; IAM debugging.

This is a 2–4+ day rewrite that touches the data spine; it does not improve the
cost story. Planned here for completeness; decided as its own go after Phase 6.

**Status (2026-06-15): BUILT, NOT DEPLOYED.** The full serverless layer lives in
`infra/` — AWS SAM `template.yaml` (3 Lambdas, S3 event trigger, DynamoDB
single-table, SQS dead-letter, least-privilege IAM, live CloudWatch dashboard),
working handlers that import the existing `pipeline/` + `reliability/` modules
(so the router, caching, retries, cost ceiling and idempotency carry over
unchanged), an S3+DynamoDB storage adapter, and a CloudWatch metric emitter.
It is intentionally **not** `sam deploy`'d (deploying incurs AWS + Anthropic
charges). The AWS-independent surface (key design, event parsing, metric
shaping, normalization) is covered by `tests/test_serverless.py` (19 tests).
Deploy instructions + architecture diagram: `infra/README.md`.

---

## Sequencing summary

```
Phase 0  restructure .claude/ + agents        [no spend, no touchpoint]
Phase 1  security baseline + red-team loop     [no spend, review findings]
Phase 2  model router                          [gated run, quality-floor call]
Phase 3  prompt caching                        [gated run]
Phase 4  cost dashboard (security-gated)       [no spend]
Phase 5  quality-vs-cost eval                  [gated run, golden-set sign-off]
Phase 6  case study + docs                     [no spend, your voice]
── ship cost half ──
Phase 7+ serverless ingest (S3/Lambda/DynamoDB) [AWS setup is yours]
```
