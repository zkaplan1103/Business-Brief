"""
Cost-vs-quality comparison table.

Accepts the list of result dicts from eval.runner.run_eval() and renders:
  1. A markdown table (the consulting artifact).
  2. A CSV string (for export / spreadsheet).

The table columns are:
  Model | Cost/run ($) | Label F1 | Evidence Overlap | Sentiment Acc | Action F1 | Avg Latency (ms)

"Action F1" is included only when the rows contain "action_f1" keys.
Rows that have None for a metric (no golden loaded) show "—".

Usage
-----
    from eval.runner import run_eval
    from eval.compare_table import render_table

    rows = run_eval(...)
    markdown, csv_text = render_table(rows)
    print(markdown)
"""

from __future__ import annotations

import csv
import io


# ── Column definitions ────────────────────────────────────────────────────────
# Each entry: (key_in_row, header, format_spec or None for passthrough)
_BASE_COLUMNS: list[tuple[str, str, str | None]] = [
    ("model",            "Model",               None),
    ("cost_usd",         "Cost/run ($)",         ".6f"),
    ("label_f1",         "Label F1",             ".4f"),
    ("evidence_overlap", "Evidence Overlap",     ".4f"),
    ("sentiment_accuracy","Sentiment Acc",       ".4f"),
    ("latency_ms",       "Avg Latency (ms)",     ".0f"),
]

_OPTIONAL_COLUMNS: list[tuple[str, str, str | None]] = [
    ("action_f1",        "Action F1",            ".4f"),
]

_MODEL_SHORT: dict[str, str] = {
    "claude-haiku-4-5-20251001": "Haiku",
    "claude-sonnet-4-6":         "Sonnet",
    "claude-opus-4-8":           "Opus",
}


def _fmt(value: object, spec: str | None) -> str:
    """Format a value for display.  Returns '—' for None."""
    if value is None:
        return "—"  # em dash
    if spec is None:
        return str(value)
    return format(float(value), spec)


def render_table(rows: list[dict]) -> tuple[str, str]:
    """
    Render a markdown + CSV cost-vs-quality table.

    Parameters
    ----------
    rows : list[dict]
        Output of eval.runner.run_eval().

    Returns
    -------
    markdown : str
        GitHub-flavoured markdown table.
    csv_text : str
        RFC 4180 CSV with a header row.
    """
    if not rows:
        return "(no results)", ""

    # Decide which columns to include
    columns = list(_BASE_COLUMNS)
    for col in _OPTIONAL_COLUMNS:
        key = col[0]
        if any(key in row for row in rows):
            columns.append(col)

    headers = [col[1] for col in columns]

    # Build cell matrix
    cells: list[list[str]] = []
    for row in rows:
        model_raw = row.get("model", "")
        display_model = _MODEL_SHORT.get(model_raw, model_raw)
        cell_row: list[str] = []
        for key, _header, spec in columns:
            if key == "model":
                cell_row.append(display_model)
            else:
                cell_row.append(_fmt(row.get(key), spec))
        cells.append(cell_row)

    # ── Markdown ──────────────────────────────────────────────────────────────
    # Compute column widths
    col_widths = [max(len(h), max((len(r[i]) for r in cells), default=0))
                  for i, h in enumerate(headers)]

    def _pad(s: str, w: int) -> str:
        return s.ljust(w)

    header_row = "| " + " | ".join(_pad(h, col_widths[i]) for i, h in enumerate(headers)) + " |"
    sep_row    = "| " + " | ".join("-" * w for w in col_widths) + " |"
    data_rows  = [
        "| " + " | ".join(_pad(c, col_widths[i]) for i, c in enumerate(row)) + " |"
        for row in cells
    ]
    markdown = "\n".join([header_row, sep_row] + data_rows)

    # ── CSV ───────────────────────────────────────────────────────────────────
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in cells:
        writer.writerow(row)
    csv_text = buf.getvalue()

    return markdown, csv_text
