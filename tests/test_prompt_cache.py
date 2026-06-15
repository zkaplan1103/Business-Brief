"""
tests/test_prompt_cache.py — Phase 3: prompt caching

All tests use mocked Anthropic responses — no real API calls.

Coverage:
- call_model passes system param to SDK when provided
- ModelResult has cache_creation_tokens and cache_read_tokens fields
- Cache-read tokens use the cached_input rate (cheaper)
- Cache-creation tokens use the standard input rate
- LogEvent includes both cache token fields and prompt_cache_saved_usd
- With zero cache tokens, cost calculation is unchanged from Phase 2
- _prompt_cache_savings returns correct savings dict
- analyze.py uses _SYSTEM_BLOCK with cache_control
- analyze.py passes system= to call_model
"""
from __future__ import annotations

import json
import os
import tempfile
import types
from unittest.mock import MagicMock, patch

import pytest

from pipeline.config import Config
from reliability.call_model import (
    ModelResult,
    _COST_TABLE,
    _estimate_cost,
    _prompt_cache_savings,
    call_model,
)
from reliability.logger import LogEvent, StructuredLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmpdir: str) -> Config:
    cfg = Config()
    cfg.briefs_dir = os.path.join(tmpdir, "briefs")
    cfg.log_dir = os.path.join(tmpdir, "logs")
    cfg.max_retries = 0
    cfg.run_cost_ceiling_usd = 10.0
    os.makedirs(cfg.briefs_dir, exist_ok=True)
    os.makedirs(cfg.log_dir, exist_ok=True)
    return cfg


def _make_usage(
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> MagicMock:
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_creation_input_tokens = cache_creation_input_tokens
    usage.cache_read_input_tokens = cache_read_input_tokens
    return usage


def _make_response(text: str = '[]', **usage_kwargs) -> MagicMock:
    response = MagicMock()
    response.usage = _make_usage(**usage_kwargs)
    block = MagicMock()
    block.text = text
    response.content = [block]
    return response


def _captured_events(tmpdir: str) -> list[dict]:
    """Read all LogEvents emitted during a test run."""
    log_dir = os.path.join(tmpdir, "logs")
    events = []
    if not os.path.exists(log_dir):
        return events
    for fname in os.listdir(log_dir):
        if fname.endswith(".jsonl") and fname != "runs.jsonl":
            with open(os.path.join(log_dir, fname)) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
    return events


# ---------------------------------------------------------------------------
# ModelResult field tests
# ---------------------------------------------------------------------------

class TestModelResultFields:
    def test_has_cache_creation_tokens_field(self):
        r = ModelResult(
            text="x", model="claude-haiku-4-5-20251001",
            input_tokens=10, output_tokens=5, cost_usd=0.001,
        )
        assert hasattr(r, "cache_creation_tokens")
        assert r.cache_creation_tokens == 0

    def test_has_cache_read_tokens_field(self):
        r = ModelResult(
            text="x", model="claude-haiku-4-5-20251001",
            input_tokens=10, output_tokens=5, cost_usd=0.001,
        )
        assert hasattr(r, "cache_read_tokens")
        assert r.cache_read_tokens == 0

    def test_cache_tokens_set_correctly(self):
        r = ModelResult(
            text="x", model="claude-sonnet-4-6",
            input_tokens=200, output_tokens=30, cost_usd=0.0005,
            cache_creation_tokens=150, cache_read_tokens=80,
        )
        assert r.cache_creation_tokens == 150
        assert r.cache_read_tokens == 80

    def test_backward_compatible_no_cache_args(self):
        """Constructing ModelResult without cache args must still work."""
        r = ModelResult(
            text="x", model="claude-haiku-4-5-20251001",
            input_tokens=10, output_tokens=5, cost_usd=0.001,
            cached=True,
        )
        assert r.cached is True
        assert r.cache_creation_tokens == 0
        assert r.cache_read_tokens == 0


# ---------------------------------------------------------------------------
# _estimate_cost tests (cache token pricing)
# ---------------------------------------------------------------------------

class TestEstimateCostWithCache:
    def test_zero_cache_tokens_unchanged(self):
        """With no caching, cost must equal the Phase 2 formula."""
        model = "claude-haiku-4-5-20251001"
        in_rate, out_rate, _ = _COST_TABLE[model]
        expected = (100 * in_rate + 50 * out_rate) / 1_000_000
        assert _estimate_cost(model, 100, 50, 0) == pytest.approx(expected)

    def test_cache_read_tokens_cheaper_than_input(self):
        """Reading a prefix from cache is cheaper than paying full input rate.

        The API reports input_tokens, cache_read_tokens and cache_creation_tokens
        as DISJOINT buckets.  A 1000-token prefix served from cache (input_tokens
        small) must cost less than the same 1000 tokens billed as fresh input.
        """
        model = "claude-sonnet-4-6"
        in_rate, out_rate, cached_rate = _COST_TABLE[model]
        assert cached_rate < in_rate, "cached rate must be less than input rate"

        # Cache-read call: 5 fresh input tokens + 1000 served from cache.
        cost_cached = _estimate_cost(model, 5, 50, cached_read_tokens=1000)
        # Same prefix with no cache: all 1005 tokens billed at full input rate.
        cost_no_cache = _estimate_cost(model, 1005, 50, cached_read_tokens=0)
        assert cost_cached < cost_no_cache

    def test_cache_creation_tokens_billed_at_premium(self):
        """
        Cache-creation tokens are billed at 1.25x the base input rate.
        A call that writes a prefix to cache costs MORE than the same prefix
        billed as plain input (the write surcharge), recouped on later reads.
        """
        model = "claude-sonnet-4-6"
        in_rate, _, _ = _COST_TABLE[model]
        # 5 fresh input tokens + 1000 written to cache (creation).
        cost_with_write = _estimate_cost(
            model, 5, 50, cached_read_tokens=0, cache_creation_tokens=1000
        )
        # Same 1005 tokens billed as plain input, no cache write.
        cost_plain = _estimate_cost(model, 1005, 50, cached_read_tokens=0)
        # The 1000 creation tokens carry a 0.25x surcharge over plain input.
        assert cost_with_write > cost_plain
        expected = (
            5 * in_rate
            + 1000 * in_rate * 1.25
            + 50 * _COST_TABLE[model][1]
        ) / 1_000_000
        assert cost_with_write == pytest.approx(expected)

    def test_partial_cache_read(self):
        """Fresh input billed at full rate; cached prefix at the discount rate."""
        model = "claude-haiku-4-5-20251001"
        in_rate, out_rate, cached_rate = _COST_TABLE[model]
        input_tokens = 300   # fresh (uncached) input
        output_tokens = 100
        cache_read = 700     # served from cache (disjoint from input_tokens)

        expected = (
            input_tokens * in_rate
            + cache_read * cached_rate
            + output_tokens * out_rate
        ) / 1_000_000
        assert _estimate_cost(
            model, input_tokens, output_tokens, cached_read_tokens=cache_read
        ) == pytest.approx(expected)

    def test_all_three_tiers_have_cached_rate(self):
        for model in ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"]:
            rates = _COST_TABLE[model]
            assert len(rates) == 3, f"{model} must have 3-tuple in _COST_TABLE"
            assert rates[2] > 0, f"{model} cached rate must be positive"
            assert rates[2] < rates[0], f"{model} cached rate must be less than input rate"


# ---------------------------------------------------------------------------
# _prompt_cache_savings helper tests
# ---------------------------------------------------------------------------

class TestPromptCacheSavings:
    def test_zero_cache_read_means_zero_savings(self):
        result = _prompt_cache_savings(
            "claude-haiku-4-5-20251001", 100, 50,
            cache_read_tokens=0, cache_creation_tokens=0,
        )
        assert result["saved_usd"] == pytest.approx(0.0)
        assert result["cost_without_cache"] == pytest.approx(result["cost_with_cache"])

    def test_positive_savings_when_cache_read(self):
        result = _prompt_cache_savings(
            "claude-sonnet-4-6", 1000, 100,
            cache_read_tokens=800, cache_creation_tokens=0,
        )
        assert result["saved_usd"] > 0
        assert result["cost_with_cache"] < result["cost_without_cache"]

    def test_savings_not_negative(self):
        """saved_usd is always >= 0 even if rounding causes tiny negative."""
        result = _prompt_cache_savings(
            "claude-haiku-4-5-20251001", 10, 10,
            cache_read_tokens=0, cache_creation_tokens=5,
        )
        assert result["saved_usd"] >= 0.0

    def test_returns_cache_token_counts(self):
        result = _prompt_cache_savings(
            "claude-sonnet-4-6", 500, 50,
            cache_read_tokens=300, cache_creation_tokens=200,
        )
        assert result["cache_read_tokens"] == 300
        assert result["cache_creation_tokens"] == 200

    def test_savings_magnitude_correct(self):
        """Manual spot-check for Sonnet on a realistic cache-read call.

        Buckets are disjoint: 500 fresh input + 1500 served from cache.  The
        no-cache baseline bills all 2000 at the input rate.
        """
        model = "claude-sonnet-4-6"
        in_rate, out_rate, cached_rate = _COST_TABLE[model]
        input_tokens = 500     # fresh input on the read call
        output_tokens = 100
        cache_read = 1500      # prefix served from cache
        total_input = input_tokens + cache_read
        # Expected without cache: all 2000 input tokens at full rate.
        cost_without = (total_input * in_rate + output_tokens * out_rate) / 1_000_000
        # Expected with cache: fresh input full rate + cached prefix discount.
        cost_with = (
            input_tokens * in_rate
            + cache_read * cached_rate
            + output_tokens * out_rate
        ) / 1_000_000
        result = _prompt_cache_savings(
            model, input_tokens, output_tokens,
            cache_read_tokens=cache_read, cache_creation_tokens=0,
        )
        assert result["cost_without_cache"] == pytest.approx(cost_without)
        assert result["cost_with_cache"] == pytest.approx(cost_with)
        assert result["saved_usd"] == pytest.approx(cost_without - cost_with)


# ---------------------------------------------------------------------------
# call_model + system param tests
# ---------------------------------------------------------------------------

class TestCallModelSystemParam:
    def test_system_passed_to_sdk_when_provided(self):
        """When system= is given, client.messages.create receives system=."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            mock_response = _make_response(text='[]')

            captured: dict = {}

            def fake_create(**kwargs):
                captured.update(kwargs)
                return mock_response

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = fake_create

            system_block = [{"type": "text", "text": "instructions", "cache_control": {"type": "ephemeral"}}]

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                call_model(
                    "user message",
                    cfg=cfg,
                    stage="test",
                    run_id="r1",
                    system=system_block,
                )

            assert "system" in captured
            assert captured["system"] == system_block

    def test_no_system_key_when_not_provided(self):
        """When system= is omitted, client.messages.create must NOT receive system=."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            mock_response = _make_response(text='[]')
            captured: dict = {}

            def fake_create(**kwargs):
                captured.update(kwargs)
                return mock_response

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = fake_create

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                call_model(
                    "user message",
                    cfg=cfg,
                    stage="test",
                    run_id="r1",
                )

            assert "system" not in captured

    def test_result_has_cache_tokens_from_response(self):
        """ModelResult receives cache token counts from response.usage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            mock_response = _make_response(
                text='[]',
                input_tokens=1200,
                output_tokens=80,
                cache_creation_input_tokens=1100,
                cache_read_input_tokens=0,
            )
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                result = call_model(
                    "user message",
                    cfg=cfg,
                    stage="test",
                    run_id="r1",
                )

            assert result.cache_creation_tokens == 1100
            assert result.cache_read_tokens == 0

    def test_result_has_cache_read_tokens(self):
        """Subsequent call with cache_read_input_tokens set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            mock_response = _make_response(
                text='[]',
                input_tokens=1200,
                output_tokens=80,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=1100,
            )
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                result = call_model(
                    "user message",
                    cfg=cfg,
                    stage="test",
                    run_id="r1",
                )

            assert result.cache_creation_tokens == 0
            assert result.cache_read_tokens == 1100

    def test_cost_reduced_by_cache_read_tokens(self):
        """Cost computed from response must reflect cache_read discount.

        On a real cache hit the API reports a SMALL input_tokens (just the fresh
        user message) plus a large cache_read_tokens for the served prefix.  The
        no-cache baseline is the same prefix billed entirely as fresh input.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            model = "claude-sonnet-4-6"
            cfg.gen_model = model
            input_tokens = 300    # fresh input on a cache hit
            output_tokens = 80
            cache_read = 1200     # prefix served from cache (disjoint)

            mock_response = _make_response(
                text='[]',
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_input_tokens=cache_read,
            )
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                result = call_model(
                    "user message",
                    cfg=cfg,
                    stage="test",
                    run_id="r1",
                )

            expected_cost = _estimate_cost(
                model, input_tokens, output_tokens, cached_read_tokens=cache_read
            )
            assert result.cost_usd == pytest.approx(expected_cost)

            # Cheaper than billing the whole prefix (input + cache_read) as fresh input.
            no_cache_cost = _estimate_cost(
                model, input_tokens + cache_read, output_tokens, cached_read_tokens=0
            )
            assert result.cost_usd < no_cache_cost


# ---------------------------------------------------------------------------
# LogEvent cache field tests
# ---------------------------------------------------------------------------

class TestLogEventCacheFields:
    def test_log_event_includes_cache_fields_when_nonzero(self):
        """LogEvent must include cache_creation_tokens and cache_read_tokens when > 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            mock_response = _make_response(
                text='[]',
                input_tokens=1200,
                output_tokens=50,
                cache_creation_input_tokens=1100,
                cache_read_input_tokens=0,
            )
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                call_model(
                    "user msg",
                    cfg=cfg,
                    stage="test",
                    run_id="run1",
                )

            events = _captured_events(tmpdir)
            assert len(events) == 1
            e = events[0]
            assert e.get("cache_creation_tokens") == 1100
            assert e.get("cache_read_tokens") == 0 or "cache_read_tokens" not in e

    def test_log_event_includes_cache_read_tokens(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            mock_response = _make_response(
                text='[]',
                input_tokens=1200,
                output_tokens=50,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=1100,
            )
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                call_model(
                    "user msg",
                    cfg=cfg,
                    stage="test",
                    run_id="run1",
                )

            events = _captured_events(tmpdir)
            assert len(events) == 1
            e = events[0]
            assert e.get("cache_read_tokens") == 1100

    def test_log_event_includes_prompt_cache_saved_usd(self):
        """prompt_cache_saved_usd must be present when cache_read_tokens > 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            mock_response = _make_response(
                text='[]',
                input_tokens=1500,
                output_tokens=50,
                cache_read_input_tokens=1200,
            )
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                call_model(
                    "user msg",
                    cfg=cfg,
                    stage="test",
                    run_id="run1",
                )

            events = _captured_events(tmpdir)
            e = events[0]
            assert "prompt_cache_saved_usd" in e
            assert e["prompt_cache_saved_usd"] > 0

    def test_log_event_no_cache_fields_when_zero(self):
        """When both cache token counts are 0, cache fields are absent from log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            mock_response = _make_response(
                text='[]',
                input_tokens=100,
                output_tokens=50,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            )
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                call_model(
                    "user msg",
                    cfg=cfg,
                    stage="test",
                    run_id="run1",
                )

            events = _captured_events(tmpdir)
            assert len(events) == 1
            e = events[0]
            assert "cache_creation_tokens" not in e
            assert "cache_read_tokens" not in e
            assert "prompt_cache_saved_usd" not in e

    def test_idempotency_cache_outcome_unchanged(self):
        """Idempotency cache hits still log outcome=skipped_cache — no change."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)

            # First call — populate idempotency cache.
            mock_response = _make_response(text='[]')
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                call_model(
                    "prompt",
                    cfg=cfg,
                    stage="test",
                    run_id="run1",
                    idempotency_key="ikey1",
                )
                # Second call — idempotency cache hit.
                call_model(
                    "prompt",
                    cfg=cfg,
                    stage="test",
                    run_id="run1",
                    idempotency_key="ikey1",
                )

            events = _captured_events(tmpdir)
            outcomes = [e["outcome"] for e in events]
            assert "skipped_cache" in outcomes, "idempotency cache hit must log skipped_cache"
            assert "ok" in outcomes, "first call must log ok"


# ---------------------------------------------------------------------------
# Zero-cache backward-compatibility test
# ---------------------------------------------------------------------------

class TestZeroCacheBackwardCompat:
    def test_cost_unchanged_with_no_cache_fields(self):
        """
        When response.usage has no cache_* attributes (old SDK behaviour),
        cost must equal the Phase 2 formula exactly.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            model = "claude-haiku-4-5-20251001"
            cfg.gen_model = model
            input_tokens = 300
            output_tokens = 60

            # Simulate old SDK response: no cache attributes on usage.
            usage = MagicMock(spec=["input_tokens", "output_tokens"])
            usage.input_tokens = input_tokens
            usage.output_tokens = output_tokens
            block = MagicMock()
            block.text = "[]"
            response = MagicMock()
            response.usage = usage
            response.content = [block]

            mock_client = MagicMock()
            mock_client.messages.create.return_value = response

            with patch("reliability.call_model.anthropic.Anthropic", return_value=mock_client):
                result = call_model(
                    "user msg",
                    cfg=cfg,
                    stage="test",
                    run_id="run1",
                )

            expected = _estimate_cost(model, input_tokens, output_tokens, 0)
            assert result.cost_usd == pytest.approx(expected)
            assert result.cache_creation_tokens == 0
            assert result.cache_read_tokens == 0


# ---------------------------------------------------------------------------
# analyze.py integration: system prompt has cache_control
# ---------------------------------------------------------------------------

class TestAnalyzeSystemPrompt:
    def test_system_prompt_is_nonempty(self):
        from pipeline.analyze import SYSTEM_PROMPT
        assert len(SYSTEM_PROMPT.split()) >= 400, (
            "SYSTEM_PROMPT must be large enough to qualify for prompt caching "
            "(Anthropic minimum ~1024 tokens)"
        )

    def test_system_block_has_cache_control(self):
        from pipeline.analyze import _SYSTEM_BLOCK
        assert len(_SYSTEM_BLOCK) == 1
        block = _SYSTEM_BLOCK[0]
        assert block["type"] == "text"
        assert "cache_control" in block
        assert block["cache_control"]["type"] == "ephemeral"

    def test_system_block_text_matches_system_prompt(self):
        from pipeline.analyze import _SYSTEM_BLOCK, SYSTEM_PROMPT
        assert _SYSTEM_BLOCK[0]["text"] == SYSTEM_PROMPT

    def test_user_template_contains_reviews_json_placeholder(self):
        from pipeline.analyze import _USER_TEMPLATE
        assert "{reviews_json}" in _USER_TEMPLATE

    def test_user_template_does_not_contain_system_instructions(self):
        """The user message must not duplicate the cached system instructions."""
        from pipeline.analyze import _USER_TEMPLATE, SYSTEM_PROMPT
        # The user template should be much shorter than the system prompt.
        assert len(_USER_TEMPLATE) < len(SYSTEM_PROMPT) * 0.5

    def test_analyze_run_passes_system_to_call_model(self):
        """
        Integration: analyze.run must pass system=_SYSTEM_BLOCK to call_model.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(tmpdir)
            cfg.min_reviews_for_brief = 1

            # Write a minimal reviews.jsonl
            processed_dir = os.path.join(tmpdir, "processed")
            os.makedirs(processed_dir, exist_ok=True)
            reviews_path = os.path.join(processed_dir, "reviews.jsonl")
            review = {
                "review_id": "r001",
                "business_id": "biz1",
                "week": "2024-W01",
                "stars": 5,
                "text": "Great place!",
            }
            with open(reviews_path, "w") as f:
                f.write(json.dumps(review) + "\n")

            captured_kwargs: list[dict] = []

            def fake_call_model(prompt, **kwargs):
                captured_kwargs.append(kwargs)
                return ModelResult(
                    text='[{"label":"Good vibes","sentiment":"positive","review_ids":["r001"],"sample_quotes":["Great place!"]}]',
                    model=cfg.gen_model,
                    input_tokens=100,
                    output_tokens=30,
                    cost_usd=0.0001,
                )

            with (
                patch("pipeline.analyze.call_model", side_effect=fake_call_model),
                patch(
                    "pipeline.analyze._load_reviews",
                    return_value=[review],
                ),
            ):
                from pipeline.analyze import _SYSTEM_BLOCK
                import pipeline.analyze as analyze_mod
                analyze_mod.run(
                    business_id="biz1",
                    week="2024-W01",
                    cfg=cfg,
                    run_id="test_run",
                )

            assert len(captured_kwargs) == 1
            kw = captured_kwargs[0]
            assert "system" in kw, "analyze.run must pass system= to call_model"
            from pipeline.analyze import _SYSTEM_BLOCK
            assert kw["system"] == _SYSTEM_BLOCK
