"""
Tests for the Phase 5 quality-vs-cost eval harness.

All tests run against mocked call_model — no real API calls are made.

Coverage:
  - score_classification: 1.0 F1 on identical themes
  - score_classification: 0.0 F1 on no overlap
  - score_classification: correct partial F1
  - score_classification: evidence overlap (Jaccard) for matched themes
  - score_classification: sentiment accuracy for matched themes
  - score_brief_quality:  correct F1 on action items
  - score_brief_quality:  evidence_present = False when review_ids empty
  - score_brief_quality:  evidence_present = True when all items have ids
  - run_eval:             one row per model; columns present; uses mocked call
  - compare_table:        markdown table renders with correct headers
  - compare_table:        CSV has a header row and one data row per model
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from eval.compare_table import render_table
from eval.seam import score_brief_quality, score_classification
from pipeline.config import Config
from reliability.call_model import ModelResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GOLDEN = {
    "business_id": "B007IAE5WY",
    "week": "2017-W38",
    "note": "CANDIDATE",
    "themes": [
        {
            "label": "Effective exfoliation and skin improvement",
            "sentiment": "positive",
            "review_ids": ["r1", "r2", "r3"],
        },
        {
            "label": "Cloth is too rough for sensitive skin",
            "sentiment": "negative",
            "review_ids": ["r4", "r5"],
        },
    ],
    "action_items": [
        {"label": "Add roughness guidance in product listing"},
        {"label": "Investigate quality thinning in recent batches"},
    ],
}


def _make_theme_report(themes: list[dict]) -> dict:
    return {
        "business_id": "B007IAE5WY",
        "week": "2017-W38",
        "themes": themes,
        "sufficient": True,
        "partial": False,
    }


# ---------------------------------------------------------------------------
# score_classification — label F1
# ---------------------------------------------------------------------------

class TestScoreClassificationF1(unittest.TestCase):

    def test_identical_themes_returns_1_0(self):
        """Exact match on both labels → precision=recall=F1=1.0."""
        predicted = _make_theme_report([
            {
                "label": "Effective exfoliation and skin improvement",
                "sentiment": "positive",
                "review_ids": ["r1", "r2", "r3"],
            },
            {
                "label": "Cloth is too rough for sensitive skin",
                "sentiment": "negative",
                "review_ids": ["r4", "r5"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["label_f1"], 1.0)
        self.assertAlmostEqual(result["label_precision"], 1.0)
        self.assertAlmostEqual(result["label_recall"], 1.0)

    def test_no_overlap_returns_0_0(self):
        """Completely different labels → F1 = 0.0."""
        predicted = _make_theme_report([
            {
                "label": "Completely unrelated theme about shipping",
                "sentiment": "negative",
                "review_ids": ["r99"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["label_f1"], 0.0)
        self.assertEqual(result["matched_themes"], 0)

    def test_partial_overlap_correct_f1(self):
        """One of two golden themes matched → F1 = 2*(0.5*1.0)/(0.5+1.0) = 2/3."""
        # Predict only the first golden theme (recall=0.5, precision=1.0 → F1~0.667)
        predicted = _make_theme_report([
            {
                "label": "Effective exfoliation and skin improvement",
                "sentiment": "positive",
                "review_ids": ["r1"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertEqual(result["matched_themes"], 1)
        self.assertEqual(result["total_golden_themes"], 2)
        self.assertAlmostEqual(result["label_precision"], 1.0)
        self.assertAlmostEqual(result["label_recall"], 0.5)
        expected_f1 = 2 * 1.0 * 0.5 / (1.0 + 0.5)
        self.assertAlmostEqual(result["label_f1"], expected_f1, places=4)

    def test_case_insensitive_match(self):
        """Labels differing only in case should still match."""
        predicted = _make_theme_report([
            {
                "label": "EFFECTIVE EXFOLIATION AND SKIN IMPROVEMENT",
                "sentiment": "positive",
                "review_ids": ["r1"],
            },
            {
                "label": "Cloth Is Too Rough For Sensitive Skin",
                "sentiment": "negative",
                "review_ids": ["r4"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["label_f1"], 1.0)

    def test_whitespace_normalisation(self):
        """Extra internal whitespace in labels should be normalised."""
        predicted = _make_theme_report([
            {
                "label": "Effective  exfoliation  and  skin  improvement",
                "sentiment": "positive",
                "review_ids": ["r1"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertEqual(result["matched_themes"], 1)

    def test_empty_predicted_themes(self):
        """No predicted themes → precision=0, recall=0, F1=0."""
        predicted = _make_theme_report([])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["label_f1"], 0.0)
        self.assertEqual(result["matched_themes"], 0)

    def test_extra_predicted_themes_lower_precision(self):
        """One extra predicted theme that doesn't match → precision < 1."""
        predicted = _make_theme_report([
            {
                "label": "Effective exfoliation and skin improvement",
                "sentiment": "positive",
                "review_ids": ["r1"],
            },
            {
                "label": "Cloth is too rough for sensitive skin",
                "sentiment": "negative",
                "review_ids": ["r4"],
            },
            {
                "label": "Random invented theme not in golden",
                "sentiment": "mixed",
                "review_ids": ["r99"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertEqual(result["matched_themes"], 2)
        self.assertAlmostEqual(result["label_recall"], 1.0)
        # precision = 2/3
        self.assertAlmostEqual(result["label_precision"], 2 / 3, places=4)


# ---------------------------------------------------------------------------
# score_classification — evidence overlap
# ---------------------------------------------------------------------------

class TestScoreClassificationEvidence(unittest.TestCase):

    def test_perfect_evidence_overlap(self):
        """Same review_ids → evidence_overlap = 1.0."""
        predicted = _make_theme_report([
            {
                "label": "Effective exfoliation and skin improvement",
                "sentiment": "positive",
                "review_ids": ["r1", "r2", "r3"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["evidence_overlap"], 1.0)

    def test_no_evidence_overlap(self):
        """Disjoint review_ids → Jaccard = 0.0."""
        predicted = _make_theme_report([
            {
                "label": "Effective exfoliation and skin improvement",
                "sentiment": "positive",
                "review_ids": ["r99", "r100"],  # wrong ids
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["evidence_overlap"], 0.0)

    def test_partial_evidence_overlap(self):
        """Partial id overlap → Jaccard = |intersection| / |union|."""
        # Golden has {r1, r2, r3}; predicted has {r1, r2, r99}
        # intersection={r1,r2}, union={r1,r2,r3,r99} → Jaccard = 2/4 = 0.5
        predicted = _make_theme_report([
            {
                "label": "Effective exfoliation and skin improvement",
                "sentiment": "positive",
                "review_ids": ["r1", "r2", "r99"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["evidence_overlap"], 0.5)

    def test_evidence_overlap_zero_when_no_match(self):
        """No matched themes → evidence_overlap = 0.0 (not NaN)."""
        predicted = _make_theme_report([
            {
                "label": "Completely unrelated theme",
                "sentiment": "negative",
                "review_ids": ["r99"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["evidence_overlap"], 0.0)


# ---------------------------------------------------------------------------
# score_classification — sentiment accuracy
# ---------------------------------------------------------------------------

class TestScoreClassificationSentiment(unittest.TestCase):

    def test_correct_sentiment(self):
        """Both matched themes have correct sentiment → accuracy = 1.0."""
        predicted = _make_theme_report([
            {
                "label": "Effective exfoliation and skin improvement",
                "sentiment": "positive",
                "review_ids": ["r1"],
            },
            {
                "label": "Cloth is too rough for sensitive skin",
                "sentiment": "negative",
                "review_ids": ["r4"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["sentiment_accuracy"], 1.0)

    def test_wrong_sentiment(self):
        """Both matched themes have wrong sentiment → accuracy = 0.0."""
        predicted = _make_theme_report([
            {
                "label": "Effective exfoliation and skin improvement",
                "sentiment": "negative",  # wrong
                "review_ids": ["r1"],
            },
            {
                "label": "Cloth is too rough for sensitive skin",
                "sentiment": "positive",  # wrong
                "review_ids": ["r4"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["sentiment_accuracy"], 0.0)

    def test_partial_sentiment(self):
        """One correct, one wrong sentiment → accuracy = 0.5."""
        predicted = _make_theme_report([
            {
                "label": "Effective exfoliation and skin improvement",
                "sentiment": "positive",  # correct
                "review_ids": ["r1"],
            },
            {
                "label": "Cloth is too rough for sensitive skin",
                "sentiment": "positive",  # wrong (should be negative)
                "review_ids": ["r4"],
            },
        ])
        result = score_classification(predicted, _GOLDEN)
        self.assertAlmostEqual(result["sentiment_accuracy"], 0.5)


# ---------------------------------------------------------------------------
# score_brief_quality
# ---------------------------------------------------------------------------

class TestScoreBriefQuality(unittest.TestCase):

    _GOLDEN_WITH_ACTIONS = {
        "action_items": [
            {"label": "Add roughness guidance in product listing"},
            {"label": "Investigate quality thinning in recent batches"},
        ]
    }

    def _make_brief(self, items: list[dict]) -> dict:
        return {
            "business_id": "B007IAE5WY",
            "week": "2017-W38",
            "action_items": items,
        }

    def test_perfect_action_match(self):
        brief = self._make_brief([
            {
                "headline": "Add roughness guidance in product listing",
                "evidence_review_ids": ["r1"],
            },
            {
                "headline": "Investigate quality thinning in recent batches",
                "evidence_review_ids": ["r2"],
            },
        ])
        result = score_brief_quality(brief, self._GOLDEN_WITH_ACTIONS)
        self.assertAlmostEqual(result["action_f1"], 1.0)
        self.assertTrue(result["evidence_present"])
        self.assertEqual(result["action_count"], 2)

    def test_missing_evidence_detected(self):
        """An action item with empty evidence_review_ids fails evidence_present."""
        brief = self._make_brief([
            {
                "headline": "Add roughness guidance in product listing",
                "evidence_review_ids": [],  # empty — no citation
            },
        ])
        result = score_brief_quality(brief, self._GOLDEN_WITH_ACTIONS)
        self.assertFalse(result["evidence_present"])

    def test_evidence_present_all_cited(self):
        brief = self._make_brief([
            {
                "headline": "Add roughness guidance in product listing",
                "evidence_review_ids": ["r1", "r2"],
            },
        ])
        result = score_brief_quality(brief, self._GOLDEN_WITH_ACTIONS)
        self.assertTrue(result["evidence_present"])

    def test_no_action_items(self):
        brief = self._make_brief([])
        result = score_brief_quality(brief, self._GOLDEN_WITH_ACTIONS)
        self.assertAlmostEqual(result["action_f1"], 0.0)
        self.assertFalse(result["evidence_present"])
        self.assertEqual(result["action_count"], 0)

    def test_partial_action_overlap(self):
        """One of two golden actions matched."""
        brief = self._make_brief([
            {
                "headline": "Add roughness guidance in product listing",
                "evidence_review_ids": ["r1"],
            },
        ])
        result = score_brief_quality(brief, self._GOLDEN_WITH_ACTIONS)
        # precision=1.0, recall=0.5 → F1 = 2/3
        expected_f1 = 2 * 1.0 * 0.5 / (1.0 + 0.5)
        self.assertAlmostEqual(result["action_f1"], expected_f1, places=4)


# ---------------------------------------------------------------------------
# run_eval — runner
# ---------------------------------------------------------------------------

class TestRunEval(unittest.TestCase):
    """runner.run_eval() produces one row per model with the expected keys."""

    def setUp(self):
        # Minimal fixture reviews written to a temp file
        self.tmpdir = tempfile.mkdtemp()
        reviews = [
            {
                "review_id": "r1",
                "business_id": "BTEST",
                "business_name": "Test Biz",
                "stars": 5.0,
                "text": "Great exfoliation product, skin feels smooth and clean.",
                "date": "2017-09-20",
                "week": "2017-W38",
            },
            {
                "review_id": "r2",
                "business_id": "BTEST",
                "business_name": "Test Biz",
                "stars": 2.0,
                "text": "Too rough for my sensitive skin, very abrasive.",
                "date": "2017-09-20",
                "week": "2017-W38",
            },
        ]
        self.reviews_path = os.path.join(self.tmpdir, "reviews.jsonl")
        with open(self.reviews_path, "w") as f:
            for r in reviews:
                f.write(json.dumps(r) + "\n")

        self.cfg = Config(
            briefs_dir=os.path.join(self.tmpdir, "briefs"),
            log_dir=os.path.join(self.tmpdir, "logs"),
        )
        os.makedirs(self.cfg.briefs_dir, exist_ok=True)
        os.makedirs(self.cfg.log_dir, exist_ok=True)

        self.golden = {
            "business_id": "BTEST",
            "week": "2017-W38",
            "themes": [
                {
                    "label": "Effective exfoliation and skin improvement",
                    "sentiment": "positive",
                    "review_ids": ["r1"],
                },
                {
                    "label": "Cloth is too rough for sensitive skin",
                    "sentiment": "negative",
                    "review_ids": ["r2"],
                },
            ],
            "action_items": [],
        }

        # Model response — a valid JSON array of themes
        self._mock_themes = json.dumps([
            {
                "label": "Effective exfoliation and skin improvement",
                "sentiment": "positive",
                "review_ids": ["r1"],
                "sample_quotes": ["Great exfoliation product"],
            },
            {
                "label": "Cloth is too rough for sensitive skin",
                "sentiment": "negative",
                "review_ids": ["r2"],
                "sample_quotes": ["Too rough for my sensitive skin"],
            },
        ])

    def _make_mock_result(self, model: str) -> ModelResult:
        return ModelResult(
            text=self._mock_themes,
            model=model,
            input_tokens=500,
            output_tokens=100,
            cost_usd=0.001,
            cached=False,
        )

    def test_one_row_per_model(self):
        """runner produces exactly one result row per requested model."""
        from eval.runner import run_eval

        models = [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-6",
            "claude-opus-4-8",
        ]

        def _mock_call(prompt, *, cfg, stage, run_id, business_id="",
                       week="", idempotency_key=None, model=None,
                       system=None, _run_cost=None, _logger=None):
            effective = model or cfg.gen_model
            if _run_cost is not None:
                _run_cost[0] += 0.001
            return self._make_mock_result(effective)

        with patch("eval.runner.call_model", side_effect=_mock_call):
            rows = run_eval(
                business_id="BTEST",
                week="2017-W38",
                models=models,
                cfg=self.cfg,
                golden=self.golden,
                processed_path=self.reviews_path,
            )

        self.assertEqual(len(rows), 3)
        returned_models = [r["model"] for r in rows]
        self.assertEqual(returned_models, models)

    def test_row_has_required_keys(self):
        """Each row must have cost_usd, latency_ms, label_f1, review_count."""
        from eval.runner import run_eval

        required_keys = {
            "model", "cost_usd", "latency_ms", "review_count",
            "label_precision", "label_recall", "label_f1",
            "evidence_overlap", "sentiment_accuracy",
            "matched_themes", "total_golden_themes",
        }

        def _mock_call(prompt, *, cfg, stage, run_id, business_id="",
                       week="", idempotency_key=None, model=None,
                       system=None, _run_cost=None, _logger=None):
            effective = model or cfg.gen_model
            if _run_cost is not None:
                _run_cost[0] += 0.001
            return self._make_mock_result(effective)

        with patch("eval.runner.call_model", side_effect=_mock_call):
            rows = run_eval(
                business_id="BTEST",
                week="2017-W38",
                models=["claude-haiku-4-5-20251001"],
                cfg=self.cfg,
                golden=self.golden,
                processed_path=self.reviews_path,
            )

        self.assertTrue(required_keys.issubset(rows[0].keys()))

    def test_perfect_mock_scores_1_0(self):
        """With mocked responses that match golden, label_f1 should be 1.0."""
        from eval.runner import run_eval

        def _mock_call(prompt, *, cfg, stage, run_id, business_id="",
                       week="", idempotency_key=None, model=None,
                       system=None, _run_cost=None, _logger=None):
            effective = model or cfg.gen_model
            if _run_cost is not None:
                _run_cost[0] += 0.001
            return self._make_mock_result(effective)

        with patch("eval.runner.call_model", side_effect=_mock_call):
            rows = run_eval(
                business_id="BTEST",
                week="2017-W38",
                models=["claude-haiku-4-5-20251001"],
                cfg=self.cfg,
                golden=self.golden,
                processed_path=self.reviews_path,
            )

        self.assertAlmostEqual(rows[0]["label_f1"], 1.0)

    def test_no_golden_scores_are_none(self):
        """When golden=None, all quality scores are None (not errors)."""
        from eval.runner import run_eval

        def _mock_call(prompt, *, cfg, stage, run_id, business_id="",
                       week="", idempotency_key=None, model=None,
                       system=None, _run_cost=None, _logger=None):
            effective = model or cfg.gen_model
            if _run_cost is not None:
                _run_cost[0] += 0.001
            return self._make_mock_result(effective)

        with patch("eval.runner.call_model", side_effect=_mock_call):
            rows = run_eval(
                business_id="BTEST",
                week="2017-W38",
                models=["claude-haiku-4-5-20251001"],
                cfg=self.cfg,
                golden=None,
                processed_path=self.reviews_path,
            )

        self.assertIsNone(rows[0]["label_f1"])
        self.assertIsNone(rows[0]["cost_usd"] if False else rows[0]["label_f1"])


# ---------------------------------------------------------------------------
# compare_table
# ---------------------------------------------------------------------------

class TestCompareTable(unittest.TestCase):

    _SAMPLE_ROWS = [
        {
            "model": "claude-haiku-4-5-20251001",
            "cost_usd": 0.000123,
            "latency_ms": 450.0,
            "label_precision": 0.8,
            "label_recall": 0.6,
            "label_f1": 0.6857,
            "evidence_overlap": 0.75,
            "sentiment_accuracy": 0.9,
            "matched_themes": 4,
            "total_golden_themes": 5,
            "review_count": 17,
        },
        {
            "model": "claude-sonnet-4-6",
            "cost_usd": 0.000456,
            "latency_ms": 820.0,
            "label_precision": 0.9,
            "label_recall": 0.8,
            "label_f1": 0.8421,
            "evidence_overlap": 0.85,
            "sentiment_accuracy": 1.0,
            "matched_themes": 5,
            "total_golden_themes": 5,
            "review_count": 17,
        },
        {
            "model": "claude-opus-4-8",
            "cost_usd": 0.002100,
            "latency_ms": 2100.0,
            "label_precision": 1.0,
            "label_recall": 1.0,
            "label_f1": 1.0,
            "evidence_overlap": 0.92,
            "sentiment_accuracy": 1.0,
            "matched_themes": 5,
            "total_golden_themes": 5,
            "review_count": 17,
        },
    ]

    def test_markdown_has_header_row(self):
        md, _ = render_table(self._SAMPLE_ROWS)
        # First line must be the header
        header_line = md.split("\n")[0]
        self.assertIn("Model", header_line)
        self.assertIn("Label F1", header_line)
        self.assertIn("Cost/run", header_line)
        self.assertIn("Avg Latency", header_line)

    def test_markdown_has_separator_row(self):
        md, _ = render_table(self._SAMPLE_ROWS)
        lines = md.split("\n")
        # Second line is the separator row (dashes)
        sep_line = lines[1]
        self.assertIn("---", sep_line)

    def test_markdown_has_one_row_per_model(self):
        md, _ = render_table(self._SAMPLE_ROWS)
        lines = md.split("\n")
        # header + separator + 3 data rows = 5 lines
        self.assertEqual(len(lines), 5)

    def test_markdown_shows_short_model_names(self):
        md, _ = render_table(self._SAMPLE_ROWS)
        self.assertIn("Haiku", md)
        self.assertIn("Sonnet", md)
        self.assertIn("Opus", md)
        # Full model IDs should not appear verbatim
        self.assertNotIn("claude-haiku-4-5-20251001", md)

    def test_csv_has_header(self):
        _, csv_text = render_table(self._SAMPLE_ROWS)
        first_line = csv_text.split("\n")[0]
        self.assertIn("Model", first_line)
        self.assertIn("Label F1", first_line)

    def test_csv_has_three_data_rows(self):
        _, csv_text = render_table(self._SAMPLE_ROWS)
        lines = [l for l in csv_text.split("\n") if l.strip()]
        # header + 3 data rows = 4 lines
        self.assertEqual(len(lines), 4)

    def test_none_values_render_as_dash(self):
        rows = [
            {
                "model": "claude-haiku-4-5-20251001",
                "cost_usd": 0.001,
                "latency_ms": 300.0,
                "label_f1": None,
                "label_precision": None,
                "label_recall": None,
                "evidence_overlap": None,
                "sentiment_accuracy": None,
                "matched_themes": None,
                "total_golden_themes": None,
                "review_count": 5,
            }
        ]
        md, _ = render_table(rows)
        self.assertIn("—", md)

    def test_empty_rows_returns_no_results_message(self):
        md, csv_text = render_table([])
        self.assertIn("no results", md)
        self.assertEqual(csv_text, "")


if __name__ == "__main__":
    unittest.main()
