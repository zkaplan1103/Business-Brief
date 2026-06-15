"""Structured JSONL logger. Appends LogEvent dicts to data/logs/<date>.jsonl."""

import json
import os
from datetime import datetime, timezone
from typing import TypedDict


class LogEvent(TypedDict, total=False):
    ts: str
    run_id: str
    business_id: str
    week: str
    stage: str
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int | None
    outcome: str           # "ok" | "retry" | "fail" | "skipped_cache"
    error_class: str | None
    # Prompt-cache fields (distinct from idempotency-cache skips):
    # cache_creation_tokens  = tokens written to Anthropic's prompt cache (billed at input rate)
    # cache_read_tokens      = tokens served from prompt cache (billed at cached_input rate)
    # prompt_cache_saved_usd = cost delta vs. calling with no caching (informational)
    cache_creation_tokens: int | None
    cache_read_tokens: int | None
    prompt_cache_saved_usd: float | None


class RunRecord(TypedDict, total=False):
    run_id: str
    business_id: str
    week: str
    status: str            # "success" | "partial" | "failed"
    started_at: str
    finished_at: str
    total_cost_usd: float
    batches_total: int
    batches_failed: int
    note: str | None


class StructuredLogger:
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(os.path.join(log_dir, "dead-letter"), exist_ok=True)

    def _log_path(self) -> str:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"{date}.jsonl")

    def emit(self, event: LogEvent) -> None:
        line = json.dumps(event, default=str)
        with open(self._log_path(), "a") as f:
            f.write(line + "\n")

    def write_run_record(self, record: RunRecord) -> None:
        path = os.path.join(self.log_dir, "runs.jsonl")
        line = json.dumps(record, default=str)
        with open(path, "a") as f:
            f.write(line + "\n")
        if record.get("status") == "failed":
            dead_path = os.path.join(
                self.log_dir, "dead-letter", f"{record['run_id']}.json"
            )
            with open(dead_path, "w") as f:
                json.dump(record, f, indent=2, default=str)
