"""
Model router for pipeline/analyze.py.

Scores a batch of reviews for complexity on a 0.0–1.0 scale, then picks the
cheapest Claude tier that can handle it.

Signals (weighted):
  - avg_token_len  : average token estimate per review (len(text.split()) * 1.3)
                     — longer reviews require more context to classify correctly
  - star_variance  : std-dev of star ratings in the batch
                     — high variance = mixed sentiment = genuinely harder task
  - vocab_richness : unique words / total words across the batch
                     — richer vocabulary = more diverse opinions = harder

All three are normalised to [0, 1] before weighting.  Normalisation caps:
  - token length:   600 tokens → 1.0  (a dense 5-paragraph review)
  - star variance:  2.0 → 1.0         (near-maximum std-dev for 1–5 scale)
  - vocab richness: passthrough (already 0–1 by definition)

Weights: 0.40 / 0.35 / 0.25  (length dominates because it most directly
predicts token cost; variance matters a lot for quality; vocab is a tie-breaker).

Thresholds are read from Config so the operator can tune without code changes:
  score ≤ router_haiku_threshold   → Haiku   (cheap, fast)
  score ≤ router_sonnet_threshold  → Sonnet  (default quality)
  score >  router_sonnet_threshold → Opus    (maximum quality)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.config import Config

# ── Normalisation caps ────────────────────────────────────────────────────────
_MAX_AVG_TOKENS: float = 600.0   # tokens per review at which length score = 1.0
_MAX_STAR_STDDEV: float = 2.0    # std-dev at which variance score = 1.0

# ── Signal weights (must sum to 1.0) ─────────────────────────────────────────
_W_LENGTH: float = 0.40
_W_VARIANCE: float = 0.35
_W_RICHNESS: float = 0.25


def score_batch_complexity(batch: list[dict]) -> float:
    """Return a complexity score in [0.0, 1.0] for a batch of review dicts.

    Each review dict is expected to have at least a ``"text"`` key (str) and
    optionally a ``"stars"`` key (float/int).  Missing keys degrade gracefully.

    Returns 0.0 for an empty batch (treated as trivially simple).
    """
    if not batch:
        return 0.0

    # ── Signal 1: average token estimate ─────────────────────────────────────
    token_estimates = []
    all_words: list[str] = []
    for review in batch:
        text = review.get("text", "") or ""
        words = text.split()
        all_words.extend(w.lower() for w in words)
        token_estimates.append(len(words) * 1.3)

    avg_tokens = sum(token_estimates) / len(token_estimates)
    length_score = min(avg_tokens / _MAX_AVG_TOKENS, 1.0)

    # ── Signal 2: star variance ───────────────────────────────────────────────
    stars = [r.get("stars") for r in batch if r.get("stars") is not None]
    if len(stars) >= 2:
        mean_stars = sum(stars) / len(stars)
        variance = sum((s - mean_stars) ** 2 for s in stars) / len(stars)
        stddev = math.sqrt(variance)
        variance_score = min(stddev / _MAX_STAR_STDDEV, 1.0)
    else:
        # Single review or no stars: treat variance as zero.
        variance_score = 0.0

    # ── Signal 3: vocabulary richness ─────────────────────────────────────────
    if all_words:
        richness_score = len(set(all_words)) / len(all_words)
    else:
        richness_score = 0.0

    # ── Weighted combination ──────────────────────────────────────────────────
    score = (
        _W_LENGTH * length_score
        + _W_VARIANCE * variance_score
        + _W_RICHNESS * richness_score
    )
    return round(min(max(score, 0.0), 1.0), 6)


def pick_model(batch: list[dict], cfg: "Config") -> str:
    """Return the model ID that should handle *batch*.

    When ``cfg.router_enabled`` is False, always returns ``cfg.gen_model``
    (preserving the pre-router behaviour exactly).
    """
    if not cfg.router_enabled:
        return cfg.gen_model

    score = score_batch_complexity(batch)

    if score <= cfg.router_haiku_threshold:
        return "claude-haiku-4-5-20251001"
    if score <= cfg.router_sonnet_threshold:
        return "claude-sonnet-4-6"
    return "claude-opus-4-8"
