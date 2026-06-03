"""
FastAPI seam — serves Brief, ThemeReport, ScheduleSettings, and RunRecords
from data/briefs/, data/schedule/, and data/logs/runs.jsonl.

All routes read from disk; no in-memory state. The UI can swap between
this API and static JSON import with no component changes.
"""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from pipeline.config import Config

cfg = Config()

app = FastAPI(title="Tideline API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "PUT"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _brief_dir(business_id: str) -> str:
    return os.path.join(cfg.briefs_dir, business_id)


def _brief_path(business_id: str, week: str) -> str:
    return os.path.join(_brief_dir(business_id), f"{week}.brief.json")


def _themes_path(business_id: str, week: str) -> str:
    return os.path.join(_brief_dir(business_id), f"{week}.themes.json")


def _schedule_path(business_id: str) -> str:
    return os.path.join(cfg.schedule_dir, f"{business_id}.json")


def _runs_path() -> str:
    return os.path.join(cfg.log_dir, "runs.jsonl")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/businesses")
def list_businesses() -> list[dict]:
    """
    Return all businesses that have at least one generated brief, along with
    the list of weeks available for each.
    """
    briefs_dir = cfg.briefs_dir
    if not os.path.isdir(briefs_dir):
        return []

    result = []
    for business_id in sorted(os.listdir(briefs_dir)):
        biz_dir = os.path.join(briefs_dir, business_id)
        if not os.path.isdir(biz_dir):
            continue
        weeks = sorted(
            f.replace(".brief.json", "")
            for f in os.listdir(biz_dir)
            if f.endswith(".brief.json")
        )
        if not weeks:
            continue
        # Try to get business_name from the most recent brief.
        name = business_id
        try:
            latest = _read_json(os.path.join(biz_dir, f"{weeks[-1]}.brief.json"))
            name = latest.get("business_name", business_id)
        except Exception:
            pass
        result.append({"business_id": business_id, "business_name": name, "weeks": weeks})

    return result


@app.get("/api/brief")
def get_brief(business_id: str, week: str) -> dict:
    """Return the Brief + ThemeReport for a given business/week."""
    bp = _brief_path(business_id, week)
    tp = _themes_path(business_id, week)

    if not os.path.exists(bp):
        raise HTTPException(
            status_code=404,
            detail=f"No brief found for {business_id!r} / {week!r}. Run the pipeline first.",
        )

    brief = _read_json(bp)
    theme_report = _read_json(tp) if os.path.exists(tp) else {}
    return {"brief": brief, "themeReport": theme_report}


@app.get("/api/schedule")
def get_schedule(business_id: str) -> dict:
    """Return ScheduleSettings for a business, or a default off schedule."""
    path = _schedule_path(business_id)
    if os.path.exists(path):
        return _read_json(path)
    # Return a sensible default rather than 404.
    return {
        "business_id": business_id,
        "cadence": "off",
        "day_of_week": "mon",
        "email_mode": "draft_only",
    }


@app.put("/api/schedule")
def put_schedule(settings: dict) -> dict:
    """Persist ScheduleSettings for a business."""
    business_id = settings.get("business_id", "")
    if not business_id:
        raise HTTPException(status_code=400, detail="business_id is required")

    required = {"business_id", "cadence", "day_of_week", "email_mode"}
    missing = required - set(settings.keys())
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {missing}")

    valid_cadence = {"weekly", "biweekly", "off"}
    valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    valid_modes = {"auto_send", "draft_only"}

    if settings["cadence"] not in valid_cadence:
        raise HTTPException(status_code=400, detail=f"cadence must be one of {valid_cadence}")
    if settings["day_of_week"] not in valid_days:
        raise HTTPException(status_code=400, detail=f"day_of_week must be one of {valid_days}")
    if settings["email_mode"] not in valid_modes:
        raise HTTPException(status_code=400, detail=f"email_mode must be one of {valid_modes}")

    os.makedirs(cfg.schedule_dir, exist_ok=True)
    path = _schedule_path(business_id)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)

    return settings


@app.get("/api/runs")
def get_runs(business_id: str) -> list[dict]:
    """Return all RunRecords for a business, newest first."""
    path = _runs_path()
    if not os.path.exists(path):
        return []

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("business_id") == business_id:
                records.append(rec)

    # Newest first
    records.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return records
