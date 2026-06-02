"""
Local scheduler — reads ScheduleSettings for each business and fires the
pipeline on cadence. Wired in Phase 2 integration.

Implements the circuit breaker: after cfg.circuit_breaker_threshold consecutive
failures it stops and raises CircuitOpen rather than hammering a down API.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from pipeline.config import Config
from reliability import CircuitOpen, StructuredLogger
from reliability.logger import RunRecord


def _load_all_schedules(cfg: Config) -> list[dict]:
    if not os.path.isdir(cfg.schedule_dir):
        return []
    result = []
    for fname in os.listdir(cfg.schedule_dir):
        if fname.endswith(".json"):
            with open(os.path.join(cfg.schedule_dir, fname)) as f:
                result.append(json.load(f))
    return result


def run_once(business_id: str, week: str, cfg: Config | None = None) -> RunRecord:
    """Run the full pipeline for one business+week. Phase 2 wires real stages."""
    cfg = cfg or Config()
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    logger = StructuredLogger(cfg.log_dir)

    # Phase 2: call ingest → analyze → brief here.
    record: RunRecord = {
        "run_id": run_id,
        "business_id": business_id,
        "week": week,
        "status": "failed",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "total_cost_usd": 0.0,
        "batches_total": 0,
        "batches_failed": 0,
        "note": "Scheduler stub — Phase 2",
    }
    logger.write_run_record(record)
    return record


def main() -> None:
    print("Scheduler stub — Phase 2 will wire APScheduler here.")


if __name__ == "__main__":
    main()
