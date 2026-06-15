"""
api/security.py — in-process security controls for BizBrief.

Controls implemented here (all Config-driven):
  1. Per-IP sliding-window rate limiter (reads vs. writes).
  2. Request-body size cap (413 before parsing).
  3. Hardened input validation for business_id and week (path-traversal prevention).
  4. Per-IP + global cost-amplification guard for model-triggering routes.
  5. API-key auth for mutating routes (X-API-Key header, from env BIZBRIEF_API_KEY).
  6. Generic error responses — secrets never appear in response bodies.

All guards fail closed: if the guard itself raises an unexpected exception the
request is denied with 500 rather than allowed through.

Usage in main.py:
  - Add RateLimitMiddleware to the FastAPI app.
  - Call validate_business_id(business_id) / validate_week(week) at route entry.
  - Use require_api_key as a FastAPI Depends() on mutating routes.
  - Use check_cost_guard as a FastAPI Depends() on model-triggering routes.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import Depends, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from pipeline.config import Config

logger = logging.getLogger("bizbrief.security")

# ---------------------------------------------------------------------------
# Patterns — used for path-safe validation
# ---------------------------------------------------------------------------

_BUSINESS_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")


def validate_business_id(value: str) -> str:
    """
    Raise HTTPException(400) if value is not a safe business_id.
    Returns the value unchanged if valid.
    Prevents path traversal into data/briefs/<business_id>/ and
    data/schedule/<business_id>.json.
    """
    if not _BUSINESS_ID_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail="Invalid business_id: must match ^[A-Za-z0-9_-]{1,64}$",
        )
    return value


def validate_week(value: str) -> str:
    """
    Raise HTTPException(400) if value is not a safe ISO week string.
    Returns the value unchanged if valid.
    """
    if not _WEEK_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail="Invalid week: must match YYYY-Www (e.g. 2024-W31)",
        )
    return value


def safe_path_join(base_dir: str, *parts: str) -> str:
    """
    Join base_dir with parts and assert the result stays under base_dir.
    Raises HTTPException(400) if path traversal is detected.
    Both paths are resolved with os.path.realpath to normalise symlinks and
    double-dots before comparison.  On macOS /var is a symlink to /private/var,
    so we compare realpath(base) against realpath(joined).
    """
    base_real = os.path.realpath(base_dir)
    joined = os.path.realpath(os.path.join(base_dir, *parts))
    # joined must be exactly base_real or a child of it
    if joined != base_real and not joined.startswith(base_real + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path: traversal detected")
    return joined


# ---------------------------------------------------------------------------
# Sliding-window rate limiter (in-process, per-IP)
# ---------------------------------------------------------------------------

class _SlidingWindow:
    """Thread-safe per-key sliding-window counter."""

    def __init__(self, max_requests: int, window_s: int):
        self._max = max_requests
        self._window = window_s
        self._lock = threading.Lock()
        self._buckets: dict[str, Deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """
        Returns (allowed, retry_after_seconds).
        retry_after_seconds is 0 when allowed.
        """
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            dq = self._buckets[key]
            # Evict expired timestamps
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self._max:
                # Oldest entry tells us when the next slot opens
                retry_after = int(dq[0] - cutoff) + 1
                return False, retry_after
            dq.append(now)
            return True, 0

    def clear_key(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware applying per-IP sliding-window rate limits.

    Reads are limited to cfg.rate_limit_reads_per_min per IP per minute.
    Writes (PUT / POST / DELETE / PATCH) are limited to
    cfg.rate_limit_writes_per_min per IP per minute.

    Returns 429 with a Retry-After header when limits are exceeded.
    """

    def __init__(self, app: ASGIApp, cfg: Config):
        super().__init__(app)
        self._read_limiter = _SlidingWindow(
            cfg.rate_limit_reads_per_min, 60
        )
        self._write_limiter = _SlidingWindow(
            cfg.rate_limit_writes_per_min, 60
        )

    async def dispatch(self, request: Request, call_next):
        try:
            ip = _client_ip(request)
            method = request.method.upper()
            is_write = method in {"PUT", "POST", "DELETE", "PATCH"}

            limiter = self._write_limiter if is_write else self._read_limiter
            allowed, retry_after = limiter.is_allowed(ip)

            if not allowed:
                return Response(
                    content='{"detail":"Rate limit exceeded"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": str(retry_after)},
                )
            return await call_next(request)
        except Exception:
            logger.exception("RateLimitMiddleware unexpected error — denying request")
            return Response(
                content='{"detail":"Internal error"}',
                status_code=500,
                media_type="application/json",
            )


# ---------------------------------------------------------------------------
# StripProxyHeadersMiddleware — RT-001 defense-in-depth (app layer)
# ---------------------------------------------------------------------------

# Headers that must be stripped when trusted_proxy=False to prevent any
# downstream code from consuming attacker-controlled proxy headers.
_PROXY_HEADERS_TO_STRIP = frozenset([
    b"x-forwarded-for",
    b"x-forwarded-proto",
    b"x-forwarded-host",
    b"x-real-ip",
])


class StripProxyHeadersMiddleware:
    """
    Pure-ASGI middleware: strip proxy-related headers (X-Forwarded-For,
    X-Real-IP, etc.) from incoming requests when Config.trusted_proxy=False.

    This is the application-layer component of the RT-001 fix.  The primary
    fix is setting FORWARDED_ALLOW_IPS="" before uvicorn starts (see main.py),
    which prevents uvicorn from rewriting scope["client"].  This middleware
    adds a second defensive layer: even if scope["client"] were somehow
    rewritten upstream, no downstream code can read XFF from the headers.

    When trusted_proxy=True this middleware is a no-op; all headers pass
    through unchanged.

    Implemented as a pure ASGI class (not BaseHTTPMiddleware) so it is the
    true outermost wrapper in the middleware stack when added last via
    app.add_middleware().
    """

    def __init__(self, app: ASGIApp, cfg: Config):
        self._app = app
        self._trusted_proxy = cfg.trusted_proxy

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not self._trusted_proxy:
            # Rebuild the headers list without proxy-controlled entries.
            # Header names in ASGI scope are lowercased bytes.
            original_headers = scope.get("headers", [])
            stripped = [
                (name, value)
                for name, value in original_headers
                if name.lower() not in _PROXY_HEADERS_TO_STRIP
            ]
            if len(stripped) != len(original_headers):
                # Only replace if we actually removed something (avoids a copy
                # on the fast path when no proxy headers are present).
                scope = dict(scope)
                scope["headers"] = stripped
        await self._app(scope, receive, send)


# ---------------------------------------------------------------------------
# Request-body size cap middleware
# ---------------------------------------------------------------------------

# The _413_RESPONSE bytes are sent as a raw ASGI response when the body is too large.
_413_BODY = b'{"detail":"Request body too large"}'
_413_HEADERS = [
    (b"content-type", b"application/json"),
    (b"content-length", str(len(_413_BODY)).encode()),
]


class MaxBodySizeMiddleware:
    """
    Pure-ASGI middleware: reject request bodies > cfg.max_request_body_bytes
    with 413 before FastAPI parses anything.

    Implemented as a pure ASGI app (not BaseHTTPMiddleware) so that intercepting
    the 'receive' callable does not interfere with Starlette's body buffering.
    Body bytes are accumulated lazily; as soon as the running total exceeds the
    limit the 413 is sent and the connection is closed.

    Fast path: Content-Length header check (avoids streaming for clearly-over
    requests).
    """

    def __init__(self, app: ASGIApp, cfg: Config):
        self._app = app
        self._max_bytes = cfg.max_request_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # Fast path via Content-Length header
        headers = dict(scope.get("headers", []))
        cl_header = headers.get(b"content-length")
        if cl_header is not None:
            try:
                cl = int(cl_header)
            except (ValueError, TypeError):
                cl = 0
            if cl > self._max_bytes:
                await self._send_413(send)
                return

        method = scope.get("method", "GET").upper()
        if method not in {"PUT", "POST", "DELETE", "PATCH"}:
            # No body to check for safe methods
            await self._app(scope, receive, send)
            return

        # Wrap receive to enforce the cap as chunks arrive
        max_bytes = self._max_bytes
        total: list[int] = [0]
        limit_exceeded: list[bool] = [False]

        async def _capped_receive():
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                total[0] += len(chunk)
                if total[0] > max_bytes:
                    limit_exceeded[0] = True
                    # Return an empty body with more_body=False to close stream
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        # Use a flag to intercept send and replace with 413 if needed
        sent_413: list[bool] = [False]
        started: list[bool] = [False]

        async def _guarded_send(message):
            if limit_exceeded[0] and not sent_413[0]:
                if message.get("type") == "http.response.start":
                    # Replace with our 413
                    sent_413[0] = True
                    started[0] = True
                    await send({
                        "type": "http.response.start",
                        "status": 413,
                        "headers": _413_HEADERS,
                    })
                    await send({
                        "type": "http.response.body",
                        "body": _413_BODY,
                        "more_body": False,
                    })
                    return
                elif message.get("type") == "http.response.body" and started[0]:
                    # Suppress downstream body — we already sent ours
                    return
            await send(message)

        try:
            await self._app(scope, _capped_receive, _guarded_send)
        except Exception:
            if not sent_413[0]:
                raise

    @staticmethod
    async def _send_413(send) -> None:
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": _413_HEADERS,
        })
        await send({
            "type": "http.response.body",
            "body": _413_BODY,
            "more_body": False,
        })


# ---------------------------------------------------------------------------
# API-key auth dependency (mutating routes only)
# ---------------------------------------------------------------------------

def _load_api_key() -> str | None:
    """
    Load the API key from the environment.
    Returns None if the env var is unset or empty.
    The key is NEVER logged.
    """
    return os.environ.get("BIZBRIEF_API_KEY") or None


# ---------------------------------------------------------------------------
# Auth-failure lockout (RT-005 fix)
# ---------------------------------------------------------------------------

class _AuthFailureLockout:
    """
    Tracks consecutive wrong-key attempts per IP.

    After `max_attempts` failures within `window_s` seconds from the same IP,
    that IP is locked out for `ban_s` seconds (returns 429).

    This is intentionally separate from the general rate limiter so that a
    flood of bad-key requests is locked out even when the general write window
    still has capacity.
    """

    def __init__(self, max_attempts: int, window_s: int, ban_s: int):
        self._max_attempts = max_attempts
        self._window_s = window_s
        self._ban_s = ban_s
        self._lock = threading.Lock()
        # Maps IP -> deque of failure timestamps (monotonic)
        self._failures: dict[str, Deque[float]] = defaultdict(deque)
        # Maps IP -> ban-expiry time (monotonic); 0.0 = not banned
        self._banned_until: dict[str, float] = defaultdict(float)

    def check_and_record_failure(self, ip: str) -> None:
        """
        Record a failed auth attempt for `ip`.
        Raises HTTPException(429) if the IP has now exceeded the threshold,
        or HTTPException(429) if the IP is already banned.
        Must be called ONLY on failed auth, not on success.
        """
        now = time.monotonic()
        cutoff = now - self._window_s
        with self._lock:
            # Check / clear existing ban
            if self._banned_until[ip] > now:
                retry = int(self._banned_until[ip] - now) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed authentication attempts. Try again later.",
                    headers={"Retry-After": str(retry)},
                )

            # Evict old failures outside the window
            dq = self._failures[ip]
            while dq and dq[0] < cutoff:
                dq.popleft()

            dq.append(now)

            if len(dq) >= self._max_attempts:
                # Threshold crossed — apply ban
                self._banned_until[ip] = now + self._ban_s
                dq.clear()
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed authentication attempts. Try again later.",
                    headers={"Retry-After": str(self._ban_s)},
                )

    def check_ban(self, ip: str) -> None:
        """
        Raise HTTPException(429) if the IP is currently banned.
        Call this at the START of require_api_key so banned IPs can't even
        attempt a correct key during their ban window.
        """
        now = time.monotonic()
        with self._lock:
            if self._banned_until[ip] > now:
                retry = int(self._banned_until[ip] - now) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed authentication attempts. Try again later.",
                    headers={"Retry-After": str(retry)},
                )

    def clear_ip(self, ip: str) -> None:
        """Clear failure history and ban for an IP (e.g. after successful auth)."""
        with self._lock:
            self._failures.pop(ip, None)
            self._banned_until.pop(ip, None)


# Module-level singleton; replaced at startup via init_auth_lockout()
_auth_lockout: _AuthFailureLockout | None = None


def init_auth_lockout(cfg: Config) -> None:
    """Call once at application startup (alongside init_cost_guard)."""
    global _auth_lockout
    _auth_lockout = _AuthFailureLockout(
        max_attempts=cfg.auth_lockout_attempts,
        window_s=cfg.auth_lockout_window_s,
        ban_s=cfg.auth_lockout_ban_s,
    )


def require_api_key(request: Request) -> None:
    """
    FastAPI dependency: enforce X-API-Key header on mutating routes.

    - If BIZBRIEF_API_KEY env var is not set, deny all writes with 503.
    - If the IP is currently banned (too many recent failures), return 429.
    - If header is missing or wrong, record the failure and return 401
      (or 429 when the failure threshold is just crossed).
    - Key is never included in any response body or logged.

    Secret source: environment variable BIZBRIEF_API_KEY.
    Never hard-code the key; never log it.
    """
    import hmac

    expected = _load_api_key()
    if expected is None:
        # Config error — not safe to allow writes
        logger.error(
            "BIZBRIEF_API_KEY is not set — all writes are denied (503). "
            "Set the env var to enable mutations."
        )
        raise HTTPException(
            status_code=503,
            detail="Service not configured for writes. Contact the administrator.",
        )

    ip = _client_ip(request)

    # Check whether this IP is already banned before even looking at the key.
    if _auth_lockout is not None:
        _auth_lockout.check_ban(ip)

    provided = request.headers.get("X-API-Key", "")
    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        # Record the failure; may raise 429 if threshold crossed
        if _auth_lockout is not None:
            _auth_lockout.check_and_record_failure(ip)
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Successful auth — clear any accumulated failure count for this IP
    if _auth_lockout is not None:
        _auth_lockout.clear_ip(ip)


# ---------------------------------------------------------------------------
# Cost-amplification guard
# ---------------------------------------------------------------------------

class CostGuard:
    """
    Tracks model-triggering requests per IP and globally.
    Uses two sliding windows: per-IP and global.
    Instantiate once at application startup and share the instance.
    """

    def __init__(self, cfg: Config):
        self._per_ip = _SlidingWindow(cfg.cost_guard_per_ip_max, cfg.cost_guard_per_ip_window_s)
        self._global = _SlidingWindow(cfg.cost_guard_global_max, cfg.cost_guard_global_window_s)

    def check(self, ip: str) -> None:
        """
        Raise HTTPException(429) if either the per-IP or global budget is exhausted.
        Call this from any route that triggers a model call.
        """
        # Check global first (cheaper — single key)
        g_allowed, g_retry = self._global.is_allowed("__global__")
        if not g_allowed:
            raise HTTPException(
                status_code=429,
                detail="Global model-call budget exceeded. Try again later.",
                headers={"Retry-After": str(g_retry)},
            )

        ip_allowed, ip_retry = self._per_ip.is_allowed(ip)
        if not ip_allowed:
            # Roll back the global increment we just made
            # (We accepted above, so compensate by noting it's still bounded)
            raise HTTPException(
                status_code=429,
                detail="Per-IP model-call budget exceeded. Try again later.",
                headers={"Retry-After": str(ip_retry)},
            )


# Module-level singleton, replaced after app startup with a real cfg
_cost_guard: CostGuard | None = None


def init_cost_guard(cfg: Config) -> None:
    """Call once at application startup."""
    global _cost_guard
    _cost_guard = CostGuard(cfg)


def check_cost_guard(request: Request) -> None:
    """
    FastAPI dependency for model-triggering routes.
    Raises 429 when per-IP or global budget is exhausted.
    Fails closed if the guard has not been initialized.
    """
    global _cost_guard
    if _cost_guard is None:
        logger.error("CostGuard not initialised — denying model-triggering request")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    try:
        _cost_guard.check(_client_ip(request))
    except HTTPException:
        raise
    except Exception:
        logger.exception("CostGuard.check raised unexpectedly — denying request")
        raise HTTPException(status_code=500, detail="Internal error")


# ---------------------------------------------------------------------------
# Exception handlers — ensure secrets never leak in responses
# ---------------------------------------------------------------------------

async def generic_exception_handler(request: Request, exc: Exception) -> Response:
    """
    Catch-all handler. Returns a generic message; logs detail server-side.
    Secrets (ANTHROPIC_API_KEY, BIZBRIEF_API_KEY) are never included in output.
    """
    logger.exception("Unhandled exception for %s %s", request.method, request.url.path)
    return Response(
        content='{"detail":"An internal error occurred"}',
        status_code=500,
        media_type="application/json",
    )


async def validation_exception_handler(request: Request, exc: Exception) -> Response:
    """
    Handler for FastAPI RequestValidationError (HTTP 422).

    FastAPI's default 422 handler echoes the raw 'input' field from the
    request body in its response — this can reflect secrets or credential
    values submitted in a malformed body (RT-007).

    This handler returns a generic message instead, consistent with the
    generic_exception_handler philosophy: detailed errors go to server logs,
    never to the client.
    """
    logger.warning(
        "Request validation error for %s %s", request.method, request.url.path
    )
    return Response(
        content='{"detail":"Invalid request"}',
        status_code=422,
        media_type="application/json",
    )


# ---------------------------------------------------------------------------
# Startup checks
# ---------------------------------------------------------------------------

def startup_secret_checks() -> None:
    """
    Run at application startup. Logs warnings for missing/unsafe configuration.
    Does NOT log secret values.
    """
    api_key = os.environ.get("BIZBRIEF_API_KEY")
    if not api_key:
        logger.warning(
            "BIZBRIEF_API_KEY is not set — all mutating routes will return 503. "
            "Set this env var (never hard-code it) to enable writes."
        )

    # Sanity-check: ANTHROPIC_API_KEY must not be empty for model calls to work,
    # but we never log its value.
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        logger.warning(
            "ANTHROPIC_API_KEY is not set — pipeline/model calls will fail. "
            "Set it in the environment (never hard-code it)."
        )


def init_security(cfg: Config) -> None:
    """
    Convenience function: call once at application startup to initialise all
    security singletons that depend on Config.

    Replaces separate calls to init_cost_guard() and init_auth_lockout().
    Also wires in the Config reference for _client_ip so trusted_proxy is
    respected without passing Config through every call site.
    """
    set_cfg(cfg)
    init_cost_guard(cfg)
    init_auth_lockout(cfg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    """
    Return the real client IP.

    By default (Config.trusted_proxy=False) X-Forwarded-For is ignored entirely
    because the demo runs without a reverse proxy and the header is fully
    attacker-controlled.  Trusting it would allow any client to spoof an
    arbitrary IP and bypass all per-IP controls (RT-001).

    Only when trusted_proxy=True (opt-in, never the default) is the leftmost
    XFF entry used — appropriate only when uvicorn sits behind a proxy you own
    that strips/rewrites the header before forwarding.
    """
    # Lazy import to avoid circular imports; _cfg is set after app startup.
    trusted = getattr(_get_cfg(), "trusted_proxy", False)
    if trusted:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


# Module-level config reference so _client_ip can read it without carrying
# a Config argument through every call site.
_cfg_ref: "Config | None" = None


def _get_cfg() -> "Config":
    if _cfg_ref is None:
        # Fall back to a default config (safe: trusted_proxy=False)
        return Config()
    return _cfg_ref


def set_cfg(cfg: "Config") -> None:
    """Called once at app startup to wire in the live Config."""
    global _cfg_ref
    _cfg_ref = cfg
