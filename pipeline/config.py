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

    # Security — rate limiting (requests per minute per IP)
    rate_limit_reads_per_min: int = 60
    rate_limit_writes_per_min: int = 10

    # Security — payload caps
    max_request_body_bytes: int = 10_240  # 10 KB

    # Security — cost-amplification guard
    # Max model-triggering requests per IP per window (seconds)
    cost_guard_per_ip_max: int = 5
    cost_guard_per_ip_window_s: int = 60
    # Global ceiling: max model-triggering requests across all IPs per window
    cost_guard_global_max: int = 20
    cost_guard_global_window_s: int = 60

    # Security — proxy trust (RT-001 fix)
    # When False (default/safe), X-Forwarded-For is ignored entirely and the
    # real TCP connection IP (request.client.host) is always used.
    # Only set to True if uvicorn is behind a known trusted reverse proxy that
    # you control and that strips/rewrites XFF before forwarding.
    trusted_proxy: bool = False

    # Security — auth-failure lockout (RT-005 fix)
    # After auth_lockout_attempts consecutive wrong-key attempts from one IP
    # within auth_lockout_window_s seconds, that IP is locked out for
    # auth_lockout_ban_s seconds (returns 429).
    auth_lockout_attempts: int = 5
    auth_lockout_window_s: int = 60
    auth_lockout_ban_s: int = 300  # 5 minutes

    # Security — schedule file cap (RT-008 fix)
    # Maximum number of entries allowed in data/schedule/.
    # When the cap is reached, PUT /api/schedule returns 429.
    max_schedule_entries: int = 100

    # Security — metrics endpoint file-read cap (Phase 4 gate)
    # GET /api/metrics reads one .jsonl file per calendar day.  Without a cap a
    # large log directory is a read-amplification DoS vector: one HTTP request
    # causes unbounded disk I/O and an unbounded-size JSON response.
    # Only the most recent metrics_max_days log files are scanned.
    # Default 30 days is enough for any dashboard view; raise if needed.
    metrics_max_days: int = 30

    # RT-012: per-endpoint total-line budget across all files read in one request.
    # Once this many lines have been parsed, reading stops and the response includes
    # "truncated": true so callers know the data is partial.  Bounds worst-case
    # latency regardless of individual file size.
    metrics_max_lines: int = 50_000

    # RT-011: allowlists for model and stage keys reflected in the response.
    # Log events whose model or stage value is not in these sets are counted in an
    # "other" bucket instead of being used as dict keys verbatim.  This prevents
    # attacker-controlled strings from appearing as top-level JSON keys.
    # Add new model IDs here when rolling out new tiers.
    allowed_models: frozenset = field(
        default_factory=lambda: frozenset({
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-6",
            "claude-opus-4-8",
        })
    )
    allowed_stages: frozenset = field(
        default_factory=lambda: frozenset({
            "analyze",
            "brief",
            "ingest",
            "compare_sonnet",
        })
    )

    # Router — model-tier selection (Phase 2)
    # When router_enabled=False, every batch uses gen_model (original behaviour).
    router_enabled: bool = True
    # Complexity score <= haiku_threshold → Haiku (simple, uniform batches)
    router_haiku_threshold: float = 0.35
    # haiku_threshold < score <= sonnet_threshold → Sonnet; above → Opus
    router_sonnet_threshold: float = 0.65
