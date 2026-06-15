---
tags: [eval]
---
# Eval memory — append-only, dated

## 2026-06-15 — Phase 5: quality-vs-cost eval harness shipped

### Metric definitions

**score_classification(predicted, golden) -> dict**

Compares a generated ThemeReport against a rich golden record on three axes:

1. Theme-label precision / recall / F1 — predicted and golden theme sets are
   matched by normalised label (lowercase + collapsed whitespace, exact match).
   Standard P/R/F1 computed over the matched set.
2. Evidence overlap — for each true-positive theme pair, Jaccard similarity of
   their review_id sets (|pred_ids ∩ gold_ids| / |pred_ids ∪ gold_ids|).
   Averaged across all true positives. Penalises correct labels with wrong
   evidence citations. Zero when no themes matched.
3. Sentiment accuracy — for each TP pair, whether predicted sentiment equals
   golden sentiment (exact string). Fraction of TPs correct.

Returns: label_precision, label_recall, label_f1, evidence_overlap,
sentiment_accuracy, matched_themes, total_golden_themes.

**score_brief_quality(brief, golden) -> dict**

Compares generated Brief action_items against golden action_items using the
same label-normalisation + P/R/F1 logic (matching on "headline" or "label").
Also checks evidence_present: True iff every action item has a non-empty
evidence_review_ids list.

Returns: action_f1, evidence_present, action_count.

### Files added / modified

- eval/seam.py — score_classification + score_brief_quality stubs filled.
- eval/runner.py — run_eval(business_id, week, models, cfg, golden) → list[dict].
  Runs the analyse-stage classify loop for each model tier using call_model with
  explicit model override; tracks cost_usd + latency_ms; scores against golden.
  Gated behind BIZBRIEF_EVAL_LIVE=1 env var for the CLI entry point.
- eval/compare_table.py — render_table(rows) → (markdown, csv_text).
  Columns: Model | Cost/run ($) | Label F1 | Evidence Overlap | Sentiment Acc |
           Action F1 (optional) | Avg Latency (ms).
  Short model names (Haiku/Sonnet/Opus); None values → em dash.
- eval/golden_candidate.json — CANDIDATE golden set for B007IAE5WY / 2017-W38
  (17 reviews, Salux bath cloth). Derived by eval-engineer reading all 17 reviews
  directly from data/processed/reviews.jsonl. NOT model-generated.
  Sign-off status: **PENDING** — human must review and approve.
- tests/test_eval.py — 31 new tests; all pass against mocks.

### Golden candidate set — B007IAE5WY / 2017-W38 (PENDING sign-off)

5 themes derived from 17 reviews of Salux Nylon Japanese Bath Cloth:
1. "Effective exfoliation and skin improvement" — positive (8 reviews)
2. "Cloth is too rough or abrasive for sensitive skin" — negative (4 reviews)
3. "Product quality decline in recent orders" — negative (1 review)
4. "Good value and durability over time" — positive (4 reviews)
5. "Helps with keratosis pilaris (KP) on skin" — positive (3 reviews)

2 action items:
1. Add roughness / sensitive-skin guidance to product listing (negative signal)
2. Investigate thinning/quality decline in recent production batches (negative)

**Sign-off status: PENDING.** Human must review eval/golden_candidate.json,
correct any errors, and explicitly approve before eval scores are used as the
official consulting artifact.

### Test count
186 tests passing (155 pre-existing + 31 new eval tests).

### Gated real-run command (after golden sign-off)
    BIZBRIEF_EVAL_LIVE=1 uv run python -m eval.runner \
        --business B007IAE5WY --week 2017-W38 \
        --models claude-haiku-4-5-20251001 claude-sonnet-4-6 claude-opus-4-8 \
        --out eval/results.csv
