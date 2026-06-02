"""
Brief stage: prioritizes themes and produces a Brief (+ optional email draft).
All model calls go through reliability.call_model.

Implemented by the brief-engineer in Phase 1.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.config import Config


def run(
    business_id: str, week: str, cfg: "Config", run_id: str, theme_report: dict
) -> dict:
    """Return Brief dict. Stub — Phase 1."""
    raise NotImplementedError("brief stage not yet implemented")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Tideline brief pipeline")
    parser.add_argument("--business", required=True, help="Business ID")
    parser.add_argument("--week", required=True, help="ISO week, e.g. 2024-W31")
    args = parser.parse_args()

    from pipeline.config import Config
    cfg = Config()
    print(f"Running pipeline for {args.business} / {args.week} — stub only")
    sys.exit(0)


if __name__ == "__main__":
    main()
