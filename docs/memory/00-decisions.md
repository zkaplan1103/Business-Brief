---
tags: [decisions]
---
# Decision log (append-only, dated)

Format: `YYYY-MM-DD — <decision> — <why>`

- 2026-06-01 — UI is the elevated/senior role with its own design brief — product is business-facing; value depends on 15-second legibility.
- 2026-06-01 — UI NOT split into design-system + app agents — over-engineering for a 3–5 day solo build; one strong UI agent is right-sized.
- 2026-06-01 — Analysis kept as a single agent (sentiment + themes + clustering) — one pipeline over one dataset.
- 2026-06-01 — Brief is evidence-grounded; abstains on sparse weeks (sufficient=False) — never invent complaints.
- 2026-06-01 — Pipeline emits Brief/ThemeReport JSON; UI reads via API or static import — decouples UI for fixture-driven polish.
- 2026-06-02 — Added a recurring schedule (settings UI + local scheduler) — "weekly" is in the name; recurrence is structural. Scoped demo-grade (real settings + local runner), NOT hosted infra.
- 2026-06-02 — Scheduling got NO subagent — plumbing on the headless pipeline, not a workstream.
- 2026-06-02 — Split art direction into a frozen docs/STYLE.md produced in a Phase-0 pass; UI agent EXECUTES it — decisions belong in Phase 0 (reviewable), execution in Phase 1. (Architect rule: UI-primary → front-load STYLE.md.)
- 2026-06-02 — Email defaults to draft_only; pipeline never auto-sends in v1 — real sending triggers consent/anti-spam obligations and needs a consent model. Compliance note in CONTRACTS §5.
- 2026-06-02 — Added a reliability/observability layer (shared reliability/ wrapper + logging contract): exp backoff + jitter on retryable errors only, per-run cost ceiling, idempotent reruns, circuit breaker, partial-failure handling, structured JSONL logs + run manifests + dead-letter — unattended scheduled runs calling a paid API make operational failure first-class. Goals: spend less, perform reliably, log everything. Got NO subagent — cross-cutting utility built in Phase 0, like the contracts. (Architect rule: runs-unattended → front-load reliability core + logging contract.)
- 2026-06-02 — Project named "Tideline" (placeholder; one find-and-replace to change).
- 2026-06-02 — Art direction committed: "Warm Premium Hospitality" — Cormorant Garamond display / Figtree body / DM Mono; terracotta brand (#C0694A), forest-green accent (#2C5F4A), warm ivory bg (#FAF8F4). Frozen in docs/STYLE.md. Chosen because primary users are food/retail/service owners; hospitality register builds trust faster than cold utilitarian.
- 2026-06-02 — Yelp dataset: requires manual registration at yelp.com/dataset; cannot download programmatically. Phase 1 paused until owner downloads and places in data/raw/yelp/. Amazon Reviews 2023 (Hugging Face) is programmatic fallback. Decision on which dataset to use deferred to owner.
- 2026-06-02 — ANTHROPIC_API_KEY stored in .env (git-ignored); .env.example committed as template.
