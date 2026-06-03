from dataclasses import dataclass, field


@dataclass
class Config:
    # Generation
    gen_backend: str = "anthropic"
    gen_model: str = "claude-haiku-4-5-20251001"
    min_reviews_for_brief: int = 1
    max_themes: int = 8
    briefs_dir: str = "data/briefs"

    # Reliability
    max_retries: int = 4
    backoff_base_s: float = 1.0
    retry_on: tuple = (429, 500, 502, 503, 504, "timeout")
    run_cost_ceiling_usd: float = 1.00
    circuit_breaker_threshold: int = 5

    # Paths
    log_dir: str = "data/logs"
    schedule_dir: str = "data/schedule"
