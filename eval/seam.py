"""
Eval seam — interface documented; metrics scaffolded but NOT filled.

The harness loads GoldenWeek records (human-labelled expected top themes),
runs compare() against a generated ThemeReport, and returns an EvalResult.
A future eval agent fills score_classification() and score_brief_quality().

Usage (once the pipeline has generated briefs):
    uv run python -m eval.seam
"""

from __future__ import annotations

import json
import os
from typing import TypedDict


# ---------------------------------------------------------------------------
# Contract types (from CONTRACTS.md §8)
# ---------------------------------------------------------------------------

class GoldenWeek(TypedDict):
    business_id: str
    week: str
    expected_top_theme_labels: list[str]


class EvalResult(TypedDict):
    business_id: str
    week: str
    themes_generated: int
    themes_expected: int
    top_theme_match: bool        # True if generated rank-1 theme ≈ expected rank-1
    label_overlap: float         # Jaccard similarity of label sets (0.0–1.0)
    note: str


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_golden(path: str) -> list[GoldenWeek]:
    """Load human-labelled golden weeks from a JSON file."""
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Compare — seam entry point
# ---------------------------------------------------------------------------

def _normalize(label: str) -> set[str]:
    """Tokenize a label for fuzzy comparison (lowercase words, stop-word stripped)."""
    stop = {"a", "an", "the", "and", "or", "in", "on", "at", "of", "for", "to", "with"}
    return {w for w in label.lower().split() if w not in stop}


def _label_overlap(generated: list[str], expected: list[str]) -> float:
    """Jaccard similarity between the two sets of theme labels (token-level)."""
    gen_tokens: set[str] = set()
    for l in generated:
        gen_tokens |= _normalize(l)
    exp_tokens: set[str] = set()
    for l in expected:
        exp_tokens |= _normalize(l)
    if not gen_tokens and not exp_tokens:
        return 1.0
    if not gen_tokens or not exp_tokens:
        return 0.0
    return len(gen_tokens & exp_tokens) / len(gen_tokens | exp_tokens)


def compare(golden: GoldenWeek, theme_report: dict) -> EvalResult:
    """
    Compare a generated ThemeReport against a GoldenWeek.

    Returns an EvalResult. Does NOT compute classification accuracy or brief
    quality — those are left for the future eval harness.
    """
    generated_labels = [t["label"] for t in theme_report.get("themes", [])]
    expected_labels = golden["expected_top_theme_labels"]

    top_match = False
    if generated_labels and expected_labels:
        gen_top_tokens = _normalize(generated_labels[0])
        exp_top_tokens = _normalize(expected_labels[0])
        # Match if token overlap >= 40%
        if gen_top_tokens and exp_top_tokens:
            overlap = len(gen_top_tokens & exp_top_tokens) / len(gen_top_tokens | exp_top_tokens)
            top_match = overlap >= 0.4

    label_sim = _label_overlap(generated_labels, expected_labels)

    note_parts = []
    if not theme_report.get("sufficient"):
        note_parts.append("ThemeReport.sufficient=False — pipeline abstained")
    if theme_report.get("partial"):
        note_parts.append("partial run")
    if not note_parts:
        note_parts.append("full run")

    return EvalResult(
        business_id=golden["business_id"],
        week=golden["week"],
        themes_generated=len(generated_labels),
        themes_expected=len(expected_labels),
        top_theme_match=top_match,
        label_overlap=round(label_sim, 3),
        note="; ".join(note_parts),
    )


# ---------------------------------------------------------------------------
# Future hooks (not implemented — left for eval harness)
# ---------------------------------------------------------------------------

def score_classification(theme_report: dict, golden: GoldenWeek) -> float:
    """
    Precision/recall of generated themes vs golden labels.
    NOT IMPLEMENTED — eval harness fills this.
    """
    raise NotImplementedError("score_classification — Phase 3 eval harness")


def score_brief_quality(brief: dict, golden: GoldenWeek) -> float:
    """
    Quality score of the generated brief vs golden expected themes.
    NOT IMPLEMENTED — eval harness fills this.
    """
    raise NotImplementedError("score_brief_quality — Phase 3 eval harness")


# ---------------------------------------------------------------------------
# CLI — runs compare() against all golden weeks with available briefs
# ---------------------------------------------------------------------------

def _load_theme_report(briefs_dir: str, business_id: str, week: str) -> dict | None:
    path = os.path.join(briefs_dir, business_id, f"{week}.themes.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def main() -> None:
    from pipeline.config import Config
    cfg = Config()

    golden_path = os.path.join("eval", "golden.json")
    if not os.path.exists(golden_path):
        print(f"No golden file found at {golden_path}")
        print("Create eval/golden.json with GoldenWeek records to run eval.")
        return

    golden_weeks = load_golden(golden_path)
    results: list[EvalResult] = []

    for gw in golden_weeks:
        report = _load_theme_report(cfg.briefs_dir, gw["business_id"], gw["week"])
        if report is None:
            print(f"  SKIP {gw['business_id']} / {gw['week']} — no ThemeReport found")
            continue
        result = compare(gw, report)
        results.append(result)
        print(
            f"  {result['business_id']} / {result['week']}: "
            f"themes={result['themes_generated']}/{result['themes_expected']}, "
            f"top_match={result['top_theme_match']}, "
            f"overlap={result['label_overlap']:.2f} — {result['note']}"
        )

    if results:
        avg_overlap = sum(r["label_overlap"] for r in results) / len(results)
        top_matches = sum(1 for r in results if r["top_theme_match"])
        print(f"\nSummary: {len(results)} runs — avg overlap={avg_overlap:.2f}, top_match={top_matches}/{len(results)}")


if __name__ == "__main__":
    main()
