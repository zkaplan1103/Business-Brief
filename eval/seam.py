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

_STOP_WORDS = {"a", "an", "the", "and", "or", "in", "on", "at", "of", "for",
               "to", "with", "is", "are", "was", "were", "be", "been", "that"}

# Minimum token-overlap (Jaccard) to consider two theme labels a match.
# 0.25 means ~1-in-4 content words overlap — loose enough to match
# "Effective exfoliation and skin-smoothing" to "Effective exfoliation and
# skin improvement" (0.33), tight enough to reject unrelated themes.
_LABEL_MATCH_THRESHOLD = 0.25


def _norm_label(label: str) -> str:
    """Normalise a theme label to a canonical form for matching.

    Lowercases and collapses whitespace.  Does NOT stem or stop-word strip —
    we want label-level precision/recall (not token soup) so that "Good
    exfoliation results" and "good exfoliation results" match, but
    "Exfoliation" and "Good exfoliation results" do not.
    """
    return " ".join(label.lower().split())


def _label_tokens(label: str) -> set[str]:
    """Return content-word tokens from a label, excluding stop words."""
    return {w for w in label.lower().split() if w not in _STOP_WORDS}


def _labels_match(a: str, b: str, threshold: float = _LABEL_MATCH_THRESHOLD) -> bool:
    """True if token-overlap Jaccard(a, b) >= threshold."""
    ta, tb = _label_tokens(a), _label_tokens(b)
    if not ta and not tb:
        return True
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


def score_classification(predicted: dict, golden: dict) -> dict:
    """
    Compare a generated ThemeReport (predicted) against a rich golden dict.

    Metric definitions
    ------------------
    Theme-label precision/recall/F1
        Predicted and golden themes are matched by fuzzy token-overlap
        (Jaccard ≥ _LABEL_MATCH_THRESHOLD, stop-words excluded).  Each
        predicted theme is matched to at most one golden theme (greedy, by
        best overlap).  Standard precision / recall / F1 follow.

        precision = TP / (TP + FP)   where FP = predicted not matched to any golden
        recall    = TP / (TP + FN)   where FN = golden not matched by any predicted
        F1        = 2*P*R / (P+R)    (harmonic mean; 0.0 if both are 0)

    Evidence overlap (for matched themes only)
        For each true-positive pair, Jaccard similarity of their review_id
        sets.  Penalises themes that got the label right but cited wrong reviews.

    Sentiment accuracy (for matched themes only)
        For each true-positive pair, whether predicted sentiment equals golden
        sentiment (exact string match).  Fraction of TPs that match.

    Parameters
    ----------
    predicted : dict
        A ThemeReport (§2 CONTRACTS.md).  Expected keys: ``"themes"`` (list
        of Theme dicts with ``"label"``, ``"sentiment"``, ``"review_ids"``).
    golden : dict
        The rich golden record (eval/golden_candidate.json).  Expected keys:
        ``"themes"`` (list of dicts with ``"label"``, ``"sentiment"``,
        ``"review_ids"``).

    Returns
    -------
    dict with keys:
        label_precision    float  0.0–1.0
        label_recall       float  0.0–1.0
        label_f1           float  0.0–1.0
        evidence_overlap   float  0.0–1.0  (avg Jaccard for matched themes)
        sentiment_accuracy float  0.0–1.0  (fraction correct for matched themes)
        matched_themes     int    number of true positives
        total_golden_themes int   len(golden["themes"])
    """
    predicted_themes = predicted.get("themes", [])
    golden_themes = golden.get("themes", [])

    # Greedy fuzzy matching: for each predicted theme find the best golden match
    # (highest Jaccard), claim it, and don't reuse it.
    gold_labels = [t["label"] for t in golden_themes]
    gold_claimed: list[bool] = [False] * len(gold_labels)

    matched_pairs: list[tuple[dict, dict]] = []  # (pred_theme, gold_theme)
    unmatched_pred: int = 0

    for pred_t in predicted_themes:
        best_j, best_idx = 0.0, -1
        for gi, g_label in enumerate(gold_labels):
            if gold_claimed[gi]:
                continue
            ta = _label_tokens(pred_t["label"])
            tb = _label_tokens(g_label)
            if not ta and not tb:
                j = 1.0
            elif not ta or not tb:
                j = 0.0
            else:
                j = len(ta & tb) / len(ta | tb)
            if j > best_j:
                best_j, best_idx = j, gi
        if best_j >= _LABEL_MATCH_THRESHOLD and best_idx >= 0:
            gold_claimed[best_idx] = True
            matched_pairs.append((pred_t, golden_themes[best_idx]))
        else:
            unmatched_pred += 1

    tp = len(matched_pairs)
    fp = unmatched_pred
    fn = sum(1 for c in gold_claimed if not c)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)

    evidence_overlaps: list[float] = []
    sentiment_matches: list[bool] = []

    for pred_t, gold_t in matched_pairs:
        pred_ids = set(pred_t.get("review_ids", []))
        gold_ids = set(gold_t.get("review_ids", []))
        union = pred_ids | gold_ids
        jaccard = len(pred_ids & gold_ids) / len(union) if union else 1.0
        evidence_overlaps.append(jaccard)

        pred_sent = pred_t.get("sentiment", "").lower().strip()
        gold_sent = gold_t.get("sentiment", "").lower().strip()
        sentiment_matches.append(pred_sent == gold_sent)

    evidence_overlap = (
        sum(evidence_overlaps) / len(evidence_overlaps)
        if evidence_overlaps else 0.0
    )
    sentiment_accuracy = (
        sum(sentiment_matches) / len(sentiment_matches)
        if sentiment_matches else 0.0
    )

    return {
        "label_precision": round(precision, 4),
        "label_recall": round(recall, 4),
        "label_f1": round(f1, 4),
        "evidence_overlap": round(evidence_overlap, 4),
        "sentiment_accuracy": round(sentiment_accuracy, 4),
        "matched_themes": tp,
        "total_golden_themes": len(golden_themes),
    }


def score_brief_quality(brief: dict, golden: dict) -> dict:
    """
    Compare a generated Brief's action items against the golden action items.

    Metric definitions
    ------------------
    Action-item label precision/recall/F1
        Same label-normalisation and exact-match logic as score_classification.
        A generated action item is a TP if its normalised label matches any
        golden action item label.

    Evidence present
        True if EVERY action item in the generated brief has a non-empty
        ``evidence_review_ids`` list.  A brief with any uncited action is
        considered to have failed the evidence check.

    Parameters
    ----------
    brief : dict
        A Brief (§3 CONTRACTS.md).  Expected keys: ``"action_items"`` (list
        of ActionItem dicts with ``"headline"`` or ``"label"`` and
        ``"evidence_review_ids"``).
    golden : dict
        Rich golden record.  Expected key: ``"action_items"`` (list of dicts
        with ``"label"``).

    Returns
    -------
    dict with keys:
        action_f1        float  0.0–1.0
        evidence_present bool   all action items have non-empty evidence_review_ids
        action_count     int    number of action items in the generated brief
    """
    gen_items = brief.get("action_items", [])
    golden_items = golden.get("action_items", [])

    # Use "headline" (Brief schema) or "label" (fallback) as the match key
    def _item_label(item: dict) -> str:
        return _norm_label(item.get("headline") or item.get("label") or "")

    golden_labels: set[str] = {_item_label(i) for i in golden_items}
    gen_labels = [_item_label(i) for i in gen_items]

    tp = sum(1 for lbl in gen_labels if lbl in golden_labels)
    fp = len(gen_labels) - tp
    fn = len(golden_labels) - tp

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)

    evidence_present = all(
        bool(item.get("evidence_review_ids"))
        for item in gen_items
    ) if gen_items else False

    return {
        "action_f1": round(f1, 4),
        "evidence_present": evidence_present,
        "action_count": len(gen_items),
    }


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
