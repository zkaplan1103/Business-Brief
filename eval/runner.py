"""
Eval runner — runs the analyse stage through each model tier and collects
cost, latency, and quality metrics.

Design
------
- Calls pipeline.analyze._load_reviews + the batch/classify loop directly
  (the same logic as analyze.run, minus file I/O and run-record logging).
- Uses reliability.call_model with an explicit *model* override so each
  model tier is evaluated on identical inputs.
- Works entirely with mocked call_model for unit tests (no real API calls).
- Returns one result dict per model, ready for compare_table.render().

Usage (mocked, for tests):
    from unittest.mock import patch
    from reliability.call_model import ModelResult
    mock_result = ModelResult(text='[]', model='...', ...)
    with patch('reliability.call_model', return_value=mock_result):
        rows = run_eval(...)

Gated live usage (after golden sign-off):
    BIZBRIEF_EVAL_LIVE=1 uv run python -m eval.runner \
        --business B007IAE5WY --week 2017-W38
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.config import Config

from eval.seam import score_classification
from pipeline.analyze import (
    BATCH_SIZE,
    _SYSTEM_BLOCK,
    _USER_TEMPLATE,
    _extract_json_array,
    _load_reviews,
    _merge_themes,
    _parse_batch_themes,
)
from reliability import call_model
from reliability.logger import StructuredLogger

# Models available for the eval (one Anthropic SDK, three tiers)
EVAL_MODELS: list[str] = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-8",
]


def _classify_reviews_with_model(
    reviews: list[dict],
    model: str,
    cfg: "Config",
    run_id: str,
    business_id: str,
    week: str,
) -> tuple[list[dict], float, float]:
    """
    Run the analyse-stage classification loop for *reviews* using *model*.

    Returns
    -------
    themes : list[dict]
        Merged theme list (same shape as ThemeReport["themes"]).
    total_cost_usd : float
        Sum of call_model cost_usd across all batches.
    total_latency_ms : float
        Wall-clock milliseconds for the entire classification run.
    """
    logger = StructuredLogger(cfg.log_dir)
    _run_cost: list[float] = [0.0]
    all_batch_themes: list[list[dict]] = []

    batches = [
        reviews[i: i + BATCH_SIZE] for i in range(0, len(reviews), BATCH_SIZE)
    ]

    t0_wall = time.monotonic()

    for batch_idx, batch in enumerate(batches):
        valid_ids = {r["review_id"] for r in batch if "review_id" in r}
        reviews_json = json.dumps(
            [
                {
                    "review_id": r.get("review_id"),
                    "stars": r.get("stars"),
                    "text": r.get("text", ""),
                }
                for r in batch
            ],
            ensure_ascii=False,
        )
        prompt = _USER_TEMPLATE.format(reviews_json=reviews_json)
        # Use a unique idempotency key per model so each model's result is
        # cached independently and reruns are free.
        ikey = f"eval_{model}_{business_id}_{week}_{batch_idx}"

        try:
            result = call_model(
                prompt,
                cfg=cfg,
                stage="analyze",
                run_id=run_id,
                business_id=business_id,
                week=week,
                idempotency_key=ikey,
                model=model,
                system=_SYSTEM_BLOCK,
                _run_cost=_run_cost,
                _logger=logger,
            )
        except Exception:
            # Batch failed — skip it, continue to next.
            continue

        raw_themes = _extract_json_array(result.text)
        if raw_themes is None:
            continue

        parsed = _parse_batch_themes(raw_themes, valid_ids, batch_idx)
        all_batch_themes.append(parsed)

    total_latency_ms = (time.monotonic() - t0_wall) * 1000
    themes = _merge_themes(all_batch_themes, cfg.max_themes)
    return themes, round(_run_cost[0], 6), round(total_latency_ms, 1)


def run_eval(
    business_id: str,
    week: str,
    models: list[str],
    cfg: "Config",
    golden: dict | None = None,
    processed_path: str | None = None,
) -> list[dict]:
    """
    Run the classify stage through each model in *models* on the same fixture
    reviews, then score each against *golden*.

    Parameters
    ----------
    business_id, week : str
        Identify the fixture review set.
    models : list[str]
        Model IDs to evaluate (e.g. EVAL_MODELS).
    cfg : Config
        Pipeline config (paths, cost ceiling, etc.).
    golden : dict | None
        Rich golden record (eval/golden_candidate.json) used for scoring.
        If None, quality scores will be None.
    processed_path : str | None
        Override path to reviews.jsonl (useful in tests).

    Returns
    -------
    list[dict]  — one row per model:
        {
          "model": str,
          "cost_usd": float,
          "latency_ms": float,
          "label_precision": float,
          "label_recall": float,
          "label_f1": float,
          "evidence_overlap": float,
          "sentiment_accuracy": float,
          "matched_themes": int,
          "total_golden_themes": int,
          "review_count": int,
        }
    """
    if processed_path is None:
        processed_path = os.path.join("data", "processed", "reviews.jsonl")

    reviews = _load_reviews(processed_path, business_id, week)
    review_count = len(reviews)

    rows: list[dict] = []
    for model in models:
        run_id = f"eval_{model}_{uuid.uuid4().hex[:8]}"
        themes, cost_usd, latency_ms = _classify_reviews_with_model(
            reviews=reviews,
            model=model,
            cfg=cfg,
            run_id=run_id,
            business_id=business_id,
            week=week,
        )

        theme_report = {
            "business_id": business_id,
            "week": week,
            "themes": themes,
            "sufficient": True,
            "partial": False,
        }

        if golden is not None:
            scores = score_classification(theme_report, golden)
        else:
            scores = {
                "label_precision": None,
                "label_recall": None,
                "label_f1": None,
                "evidence_overlap": None,
                "sentiment_accuracy": None,
                "matched_themes": None,
                "total_golden_themes": None,
            }

        rows.append(
            {
                "model": model,
                "cost_usd": cost_usd,
                "latency_ms": latency_ms,
                "review_count": review_count,
                **scores,
            }
        )

    return rows


def load_golden_candidate(path: str | None = None) -> dict:
    """Load the candidate golden record from eval/golden_candidate.json."""
    if path is None:
        path = os.path.join(
            os.path.dirname(__file__), "golden_candidate.json"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    from eval.compare_table import render_table
    from pipeline.config import Config

    parser = argparse.ArgumentParser(
        description="Run quality-vs-cost eval across Haiku / Sonnet / Opus."
    )
    parser.add_argument("--business", default="B007IAE5WY")
    parser.add_argument("--week", default="2017-W38")
    parser.add_argument(
        "--models",
        nargs="+",
        default=EVAL_MODELS,
        help="Model IDs to evaluate (default: all three tiers)",
    )
    parser.add_argument(
        "--golden",
        default=None,
        help="Path to golden_candidate.json (default: eval/golden_candidate.json)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write CSV to this path in addition to printing the markdown table",
    )
    args = parser.parse_args()

    cfg = Config()

    if not os.environ.get("BIZBRIEF_EVAL_LIVE"):
        print(
            "ERROR: real API calls are gated.\n"
            "Set BIZBRIEF_EVAL_LIVE=1 to confirm you have human sign-off on the\n"
            "golden answer key and explicit approval to spend API budget."
        )
        raise SystemExit(1)

    golden = load_golden_candidate(args.golden)
    if "CANDIDATE" in golden.get("note", ""):
        print(
            "WARNING: golden_candidate.json has not been signed off.\n"
            "Scores against an unsigned key are for development only and\n"
            "must NOT be used as the final consulting artifact.\n"
        )

    rows = run_eval(
        business_id=args.business,
        week=args.week,
        models=args.models,
        cfg=cfg,
        golden=golden,
    )

    md, csv_text = render_table(rows)
    print(md)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(csv_text)
        print(f"\nCSV written to {args.out}")


if __name__ == "__main__":
    main()
