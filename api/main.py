"""
FastAPI seam — serves Brief, ThemeReport, ScheduleSettings, and RunRecords.

Wired to real data in Phase 2 integration. Until then, returns fixture stubs.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Tideline API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "PUT"],
    allow_headers=["*"],
)


@app.get("/api/businesses")
def list_businesses():
    return []


@app.get("/api/brief")
def get_brief(business_id: str, week: str):
    raise HTTPException(status_code=501, detail="Not implemented — Phase 2")


@app.get("/api/schedule")
def get_schedule(business_id: str):
    raise HTTPException(status_code=501, detail="Not implemented — Phase 2")


@app.put("/api/schedule")
def put_schedule(settings: dict):
    raise HTTPException(status_code=501, detail="Not implemented — Phase 2")


@app.get("/api/runs")
def get_runs(business_id: str):
    return []
