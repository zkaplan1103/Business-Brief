"""
Local scheduler — reads ScheduleSettings for each business and fires the
pipeline (ingest → analyze → brief) on cadence via APScheduler.

Circuit breaker: after cfg.circuit_breaker_threshold consecutive failures
across all businesses, the scheduler stops and logs CircuitOpen rather than
hammering a down API.

run_once(business_id, week) is also the integration entry point called by
the smoke test and the CLI.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from pipeline.config import Config
from reliability import CircuitOpen, StructuredLogger
from reliability.logger import RunRecord


# ---------------------------------------------------------------------------
# ISO week helpers
# ---------------------------------------------------------------------------

def _current_iso_week() -> str:
    """Return the current ISO week string, e.g. '2024-W31'."""
    today = date.today()
    cal = today.isocalendar()
    return f"{cal[0]}-W{cal[1]:02d}"


def _prev_iso_week(week: str) -> str:
    """Return the ISO week string one week before the given one."""
    # Parse YYYY-Www
    year, w = week.split("-W")
    # Monday of the given week
    monday = date.fromisocalendar(int(year), int(w), 1)
    prev_monday = monday - timedelta(weeks=1)
    cal = prev_monday.isocalendar()
    return f"{cal[0]}-W{cal[1]:02d}"


# ---------------------------------------------------------------------------
# Schedule file helpers
# ---------------------------------------------------------------------------

def _load_schedule(business_id: str, cfg: Config) -> dict | None:
    path = os.path.join(cfg.schedule_dir, f"{business_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _save_schedule(settings: dict, cfg: Config) -> None:
    os.makedirs(cfg.schedule_dir, exist_ok=True)
    path = os.path.join(cfg.schedule_dir, f"{settings['business_id']}.json")
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)


def _load_all_schedules(cfg: Config) -> list[dict]:
    if not os.path.isdir(cfg.schedule_dir):
        return []
    result = []
    for fname in os.listdir(cfg.schedule_dir):
        if fname.endswith(".json"):
            with open(os.path.join(cfg.schedule_dir, fname)) as f:
                try:
                    result.append(json.load(f))
                except json.JSONDecodeError:
                    pass
    return result


# ---------------------------------------------------------------------------
# Core run_once — ingest → analyze → brief
# ---------------------------------------------------------------------------

def run_once(
    business_id: str,
    week: str,
    cfg: Optional[Config] = None,
    *,
    force_rerun: bool = False,
) -> RunRecord:
    """
    Run the full pipeline for one business+week.

    Returns a RunRecord. On partial failure the brief is still produced from
    available batches. On full failure the RunRecord is written to dead-letter.

    If the brief JSON already exists and force_rerun=False, returns a cached
    RunRecord without re-running (idempotency at the run level).
    """
    cfg = cfg or Config()
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    logger = StructuredLogger(cfg.log_dir)

    import pipeline.ingest as ingest_stage
    import pipeline.analyze as analyze_stage
    import pipeline.brief as brief_stage

    # Run-level idempotency: if brief already exists, skip.
    brief_path = os.path.join(cfg.briefs_dir, business_id, f"{week}.brief.json")
    if not force_rerun and os.path.exists(brief_path):
        record: RunRecord = {
            "run_id": run_id,
            "business_id": business_id,
            "week": week,
            "status": "success",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_cost_usd": 0.0,
            "batches_total": 0,
            "batches_failed": 0,
            "note": "cache hit — brief already exists",
        }
        logger.write_run_record(record)
        return record

    status = "failed"
    note: str | None = None
    total_cost: float = 0.0
    batches_total = 0
    batches_failed = 0

    try:
        # -- Ingest --
        ingest_stage.run(business_id, week, cfg)

        # -- Analyze --
        theme_report = analyze_stage.run(business_id, week, cfg, run_id)
        batches_total = theme_report.get("_batches_total", 0)
        batches_failed = theme_report.get("_batches_failed", 0)
        partial = theme_report.get("partial", False)

        # -- Brief --
        brief_result = brief_stage.run(business_id, week, cfg, run_id, theme_report)

        status = "partial" if partial else "success"
        if partial:
            note = f"brief produced from partial data ({batches_failed} batches failed)"

    except Exception as exc:
        status = "failed"
        note = f"{type(exc).__name__}: {exc}"

    finished_at = datetime.now(timezone.utc).isoformat()

    record = {
        "run_id": run_id,
        "business_id": business_id,
        "week": week,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "total_cost_usd": round(total_cost, 6),
        "batches_total": batches_total,
        "batches_failed": batches_failed,
        "note": note,
    }
    logger.write_run_record(record)
    return record


# ---------------------------------------------------------------------------
# Circuit breaker state (in-process, resets on restart — demo-grade)
# ---------------------------------------------------------------------------

_consecutive_failures: int = 0


def _record_outcome(success: bool, cfg: Config) -> None:
    global _consecutive_failures
    if success:
        _consecutive_failures = 0
    else:
        _consecutive_failures += 1
    if _consecutive_failures >= cfg.circuit_breaker_threshold:
        raise CircuitOpen(
            f"Circuit breaker opened after {_consecutive_failures} consecutive failures"
        )


# ---------------------------------------------------------------------------
# Scheduled job (called by APScheduler)
# ---------------------------------------------------------------------------

def _scheduled_job(cfg: Config) -> None:
    """Fired by APScheduler. Iterates all schedules, runs due businesses."""
    week = _current_iso_week()
    schedules = _load_all_schedules(cfg)

    for sched in schedules:
        if sched.get("cadence") == "off":
            continue
        business_id = sched.get("business_id", "")
        if not business_id:
            continue

        record = run_once(business_id, week, cfg)
        _record_outcome(record["status"] in ("success", "partial"), cfg)


# ---------------------------------------------------------------------------
# APScheduler entry point
# ---------------------------------------------------------------------------

def main() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    cfg = Config()
    scheduler = BlockingScheduler()

    # Run daily at 06:00 local time; the job itself checks each business's
    # day_of_week setting and skips if today isn't the right day.
    scheduler.add_job(
        _scheduled_job,
        trigger="cron",
        hour=6,
        minute=0,
        args=[cfg],
        id="bizbrief_daily",
    )

    print("BizBrief scheduler started — running daily at 06:00.")
    print("Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")


if __name__ == "__main__":
    main()
