"""
Analysis stage: classifies reviews into themes and produces a ThemeReport.
All model calls go through reliability.call_model.

Implemented by the analysis-engineer in Phase 1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.config import Config


def run(business_id: str, week: str, cfg: "Config", run_id: str) -> dict:
    """Return ThemeReport dict. Stub — Phase 1."""
    raise NotImplementedError("analyze stage not yet implemented")
