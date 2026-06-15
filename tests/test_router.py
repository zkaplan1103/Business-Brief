"""
Tests for the Phase-2 model router.

All tests run without a real Anthropic API key — the SDK client is mocked
wherever call_model would try to use it.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from pipeline.config import Config
from pipeline.router import pick_model, score_batch_complexity
from reliability.call_model import _estimate_cost, call_model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_review(text: str, stars: float, review_id: str = "r1") -> dict:
    return {"review_id": review_id, "text": text, "stars": stars}


def _short_uniform_batch() -> list[dict]:
    """Simple batch: short texts, identical 5-star ratings, low vocab diversity."""
    return [
        _make_review("Great product. Love it.", 5.0, "r1"),
        _make_review("Great product. Love it.", 5.0, "r2"),
        _make_review("Great product. Love it.", 5.0, "r3"),
    ]


def _long_mixed_batch() -> list[dict]:
    """Complex batch: long texts, high star variance, rich vocabulary.

    Designed to score clearly above the Haiku threshold so the invariant
    ``simple_score < complex_score`` holds.  The actual tier (Sonnet vs Opus)
    depends on the default thresholds; the Opus-routing test uses
    ``_opus_batch()`` which is deliberately engineered to exceed 0.65.
    """
    long_positive = (
        "This is an absolutely extraordinary product that exceeded every single one of "
        "my expectations in terms of quality, durability, performance, aesthetics, and "
        "value for money. The craftsmanship is impeccable and the attention to detail "
        "is remarkable. I have recommended it to numerous colleagues and family members "
        "and they have all been equally impressed by its outstanding characteristics. "
        "The packaging was environmentally conscious which I greatly appreciated. "
        "Customer service was exemplary and responsive. Would purchase again without hesitation."
    )
    long_negative = (
        "I am profoundly disappointed with this purchase. The product arrived damaged "
        "and the materials feel cheap and flimsy compared to the photographs displayed "
        "online. The functionality is severely compromised and the instructions provided "
        "were confusing and incomplete. After multiple attempts to contact customer support "
        "I received only automated responses that failed to address my specific concerns. "
        "The return process has been unnecessarily complicated and time-consuming. "
        "This represents extremely poor value and I strongly caution other consumers."
    )
    return [
        _make_review(long_positive, 5.0, "r1"),
        _make_review(long_negative, 1.0, "r2"),
        _make_review(long_positive[:200] + " fairly decent overall experience.", 3.0, "r3"),
        _make_review(long_negative[:200] + " mixed feelings about the purchase.", 2.0, "r4"),
    ]


def _opus_batch() -> list[dict]:
    """Batch that reliably scores above the Sonnet threshold (0.65) at default settings.

    Design:
      - 4 reviews, each ~480 unique words (no word shared between reviews).
      - avg token estimate = 480 * 1.3 = 624 → length_score capped at 1.0.
      - stars = [5, 1, 4, 2] → std-dev ≈ 1.58 → variance_score ≈ 0.79.
      - All words are globally unique across the batch → richness = 1.0.
      - Expected composite: 0.40*1.0 + 0.35*0.79 + 0.25*1.0 ≈ 0.93.

    We generate the vocabulary using a numeric encoding so words never repeat
    across reviews without relying on a dictionary.
    """
    def make_long_unique_text(prefix: str, n_words: int = 480) -> str:
        """Return n_words tokens, each globally unique via prefix+index."""
        return " ".join(f"{prefix}{i:04d}" for i in range(n_words))

    return [
        _make_review(make_long_unique_text("alpha"), 5.0, "r1"),
        _make_review(make_long_unique_text("beta"),  1.0, "r2"),
        _make_review(make_long_unique_text("gamma"), 4.0, "r3"),
        _make_review(make_long_unique_text("delta"), 2.0, "r4"),
    ]


def _mock_response(text: str = '[]', input_tokens: int = 100, output_tokens: int = 50):
    """Build a minimal mock that looks like an Anthropic Messages response."""
    mock = MagicMock()
    mock.content = [MagicMock(text=text)]
    mock.usage.input_tokens = input_tokens
    mock.usage.output_tokens = output_tokens
    return mock


# ---------------------------------------------------------------------------
# 1. score_batch_complexity — range and boundary tests
# ---------------------------------------------------------------------------

class TestScoreBatchComplexity(unittest.TestCase):

    def test_score_is_in_range_for_short_uniform(self):
        score = score_batch_complexity(_short_uniform_batch())
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_score_is_in_range_for_long_mixed(self):
        score = score_batch_complexity(_long_mixed_batch())
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_empty_batch_returns_zero(self):
        self.assertEqual(score_batch_complexity([]), 0.0)

    def test_single_review_no_crash(self):
        score = score_batch_complexity([_make_review("Nice.", 4.0)])
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_missing_text_key_handled_gracefully(self):
        batch = [{"review_id": "r1", "stars": 3.0}]
        score = score_batch_complexity(batch)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_missing_stars_key_handled_gracefully(self):
        batch = [{"review_id": "r1", "text": "Good product."}]
        score = score_batch_complexity(batch)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_short_uniform_scores_below_long_mixed(self):
        simple = score_batch_complexity(_short_uniform_batch())
        complex_ = score_batch_complexity(_long_mixed_batch())
        self.assertLess(simple, complex_,
            "Simple batch must score lower than complex batch")


# ---------------------------------------------------------------------------
# 2. pick_model — routing logic
# ---------------------------------------------------------------------------

class TestPickModel(unittest.TestCase):

    def _cfg(self, **overrides) -> Config:
        cfg = Config(
            router_enabled=True,
            router_haiku_threshold=0.35,
            router_sonnet_threshold=0.65,
        )
        for k, v in overrides.items():
            setattr(cfg, k, v)
        return cfg

    def test_simple_batch_picks_haiku(self):
        cfg = self._cfg()
        model = pick_model(_short_uniform_batch(), cfg)
        self.assertEqual(model, "claude-haiku-4-5-20251001",
            "Short uniform batch should route to Haiku")

    def test_complex_batch_picks_opus(self):
        cfg = self._cfg()
        model = pick_model(_opus_batch(), cfg)
        self.assertEqual(model, "claude-opus-4-8",
            "Very long mixed-sentiment batch should route to Opus")

    def test_router_disabled_returns_gen_model(self):
        cfg = self._cfg(router_enabled=False, gen_model="claude-sonnet-4-6")
        # Even a maximally complex batch should return gen_model when disabled.
        model = pick_model(_long_mixed_batch(), cfg)
        self.assertEqual(model, "claude-sonnet-4-6")

    def test_router_disabled_simple_batch_also_returns_gen_model(self):
        cfg = self._cfg(router_enabled=False, gen_model="claude-sonnet-4-6")
        model = pick_model(_short_uniform_batch(), cfg)
        self.assertEqual(model, "claude-sonnet-4-6")

    def test_custom_thresholds_force_haiku(self):
        # Raise both thresholds so everything routes to Haiku.
        cfg = self._cfg(router_haiku_threshold=0.99, router_sonnet_threshold=1.0)
        model = pick_model(_long_mixed_batch(), cfg)
        self.assertEqual(model, "claude-haiku-4-5-20251001")

    def test_custom_thresholds_force_opus(self):
        # Lower both thresholds so everything routes to Opus.
        cfg = self._cfg(router_haiku_threshold=0.0, router_sonnet_threshold=0.0)
        model = pick_model(_long_mixed_batch(), cfg)
        self.assertEqual(model, "claude-opus-4-8")

    def test_sonnet_band(self):
        # Create a batch that scores between haiku and sonnet thresholds.
        # Medium-length texts, moderate star variance.
        medium_batch = [
            _make_review("The product is decent. Works as advertised. Good value.", 4.0, "r1"),
            _make_review("Somewhat disappointed with the quality. Expected better.", 2.0, "r2"),
            _make_review("Arrived on time. Packaging was good. Product is fine.", 3.0, "r3"),
        ]
        cfg = self._cfg(router_haiku_threshold=0.35, router_sonnet_threshold=0.65)
        score = score_batch_complexity(medium_batch)
        # If it lands in the Sonnet band, verify pick_model agrees.
        if cfg.router_haiku_threshold < score <= cfg.router_sonnet_threshold:
            self.assertEqual(pick_model(medium_batch, cfg), "claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# 3. call_model — model override flows through and is logged
# ---------------------------------------------------------------------------

class TestCallModelOverride(unittest.TestCase):

    def _make_cfg(self) -> Config:
        return Config(
            gen_model="claude-sonnet-4-6",
            max_retries=0,
            backoff_base_s=0.0,
        )

    @patch("reliability.call_model.anthropic.Anthropic")
    def test_override_model_is_used_in_api_call(self, mock_anthropic_cls):
        """When model override is passed, the SDK is called with that model."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_response('["ok"]')

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_cfg()
            cfg.log_dir = tmpdir
            cfg.briefs_dir = tmpdir

            result = call_model(
                "test prompt",
                cfg=cfg,
                stage="analyze",
                run_id="run-1",
                model="claude-haiku-4-5-20251001",
            )

        # The SDK must have been called with the overridden model, not gen_model.
        call_kwargs = mock_client.messages.create.call_args
        self.assertEqual(call_kwargs.kwargs["model"], "claude-haiku-4-5-20251001")

    @patch("reliability.call_model.anthropic.Anthropic")
    def test_override_model_is_reflected_in_result(self, mock_anthropic_cls):
        """ModelResult.model must match the override, not cfg.gen_model."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_response('["ok"]')

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_cfg()
            cfg.log_dir = tmpdir
            cfg.briefs_dir = tmpdir

            result = call_model(
                "test prompt",
                cfg=cfg,
                stage="analyze",
                run_id="run-1",
                model="claude-haiku-4-5-20251001",
            )

        self.assertEqual(result.model, "claude-haiku-4-5-20251001")

    @patch("reliability.call_model.anthropic.Anthropic")
    def test_override_model_is_logged(self, mock_anthropic_cls):
        """The LogEvent written to disk must record the overridden model."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_response('["ok"]')

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_cfg()
            cfg.log_dir = tmpdir
            cfg.briefs_dir = tmpdir

            call_model(
                "test prompt",
                cfg=cfg,
                stage="analyze",
                run_id="run-log-1",
                model="claude-haiku-4-5-20251001",
            )

            # Find the JSONL log file and check the model field.
            log_files = [f for f in os.listdir(tmpdir) if f.endswith(".jsonl")]
            self.assertTrue(log_files, "No log file written")
            logged_models = []
            with open(os.path.join(tmpdir, log_files[0])) as f:
                for line in f:
                    event = json.loads(line)
                    if event.get("run_id") == "run-log-1":
                        logged_models.append(event.get("model"))

        self.assertIn("claude-haiku-4-5-20251001", logged_models,
            "Logged model must be the override, not cfg.gen_model")
        self.assertNotIn("claude-sonnet-4-6", logged_models,
            "cfg.gen_model must NOT appear in the log when overridden")

    @patch("reliability.call_model.anthropic.Anthropic")
    def test_no_override_uses_gen_model(self, mock_anthropic_cls):
        """Callers that don't pass model= continue to use cfg.gen_model."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_response()

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_cfg()
            cfg.log_dir = tmpdir
            cfg.briefs_dir = tmpdir

            result = call_model(
                "test prompt",
                cfg=cfg,
                stage="analyze",
                run_id="run-2",
                # No model= keyword arg — backward compat.
            )

        call_kwargs = mock_client.messages.create.call_args
        self.assertEqual(call_kwargs.kwargs["model"], "claude-sonnet-4-6")
        self.assertEqual(result.model, "claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# 4. Cost math — cached-input pricing
# ---------------------------------------------------------------------------

class TestEstimateCost(unittest.TestCase):

    def test_no_cached_tokens_matches_standard_pricing(self):
        # Haiku: 1000 input + 500 output, no cache
        # cost = (1000 * 0.80 + 500 * 4.00) / 1_000_000 = 0.0028
        cost = _estimate_cost("claude-haiku-4-5-20251001", 1000, 500)
        self.assertAlmostEqual(cost, 0.0028, places=6)

    def test_cached_tokens_reduce_cost(self):
        # Buckets are disjoint: 200 fresh input + 800 served from cache + 500 output.
        # cost = (200 * 0.80 + 800 * 0.08 + 500 * 4.00) / 1_000_000
        #      = (160 + 64 + 2000) / 1_000_000 = 0.002224
        cost_with_cache = _estimate_cost(
            "claude-haiku-4-5-20251001", 200, 500, cached_read_tokens=800
        )
        # No-cache baseline: the same 1000-token prefix billed entirely as input.
        cost_no_cache = _estimate_cost("claude-haiku-4-5-20251001", 1000, 500)
        self.assertLess(cost_with_cache, cost_no_cache,
            "Reading a prefix from cache must cost less than fresh input")
        self.assertAlmostEqual(cost_with_cache, 0.002224, places=6)

    def test_all_cached_tokens(self):
        # Cache hit with no fresh input: 0 input + 1000 served from cache + 500 output.
        # cost = (0 * 0.80 + 1000 * 0.08 + 500 * 4.00) / 1_000_000 = 0.002080
        cost = _estimate_cost(
            "claude-haiku-4-5-20251001", 0, 500, cached_read_tokens=1000
        )
        self.assertAlmostEqual(cost, 0.002080, places=6)

    def test_sonnet_cached_pricing(self):
        # Sonnet: 500 fresh input + 500 served from cache + 200 output.
        # cost = (500 * 3.00 + 500 * 0.30 + 200 * 15.00) / 1_000_000
        #      = (1500 + 150 + 3000) / 1_000_000 = 0.004650
        cost = _estimate_cost(
            "claude-sonnet-4-6", 500, 200, cached_read_tokens=500
        )
        self.assertAlmostEqual(cost, 0.004650, places=6)

    def test_cache_creation_premium(self):
        # Cache-write tokens are billed at 1.25x the input rate.
        # Haiku: 0 input + 1000 creation + 500 output.
        # cost = (1000 * 0.80 * 1.25 + 500 * 4.00) / 1_000_000
        #      = (1000 + 2000) / 1_000_000 = 0.003000
        cost = _estimate_cost(
            "claude-haiku-4-5-20251001", 0, 500, cache_creation_tokens=1000
        )
        self.assertAlmostEqual(cost, 0.003000, places=6)

    def test_unknown_model_falls_back_to_sonnet_rates(self):
        # Unknown model → falls back to (3.00, 15.00, 0.30) sonnet defaults.
        cost = _estimate_cost("claude-unknown-model", 1000, 500)
        expected = _estimate_cost("claude-sonnet-4-6", 1000, 500)
        self.assertAlmostEqual(cost, expected, places=6)

    def test_disjoint_buckets_sum_independently(self):
        # input, cache_read, and cache_creation are independent buckets that
        # each contribute at their own rate — none is subtracted from another.
        cost = _estimate_cost(
            "claude-haiku-4-5-20251001", 100, 200,
            cached_read_tokens=300, cache_creation_tokens=400,
        )
        expected = (
            100 * 0.80
            + 400 * 0.80 * 1.25
            + 300 * 0.08
            + 200 * 4.00
        ) / 1_000_000
        self.assertAlmostEqual(cost, expected, places=6)


# ---------------------------------------------------------------------------
# 5. Config — router fields present with correct defaults
# ---------------------------------------------------------------------------

class TestConfigRouterFields(unittest.TestCase):

    def test_router_enabled_default_true(self):
        cfg = Config()
        self.assertTrue(cfg.router_enabled)

    def test_haiku_threshold_default(self):
        cfg = Config()
        self.assertAlmostEqual(cfg.router_haiku_threshold, 0.35)

    def test_sonnet_threshold_default(self):
        cfg = Config()
        self.assertAlmostEqual(cfg.router_sonnet_threshold, 0.65)

    def test_thresholds_ordered(self):
        cfg = Config()
        self.assertLess(cfg.router_haiku_threshold, cfg.router_sonnet_threshold)


if __name__ == "__main__":
    unittest.main()
