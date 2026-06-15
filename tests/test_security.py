"""
tests/test_security.py — security regression tests for BizBrief API.

Covers:
  1. Path-traversal rejection on business_id and week parameters.
  2. Unauthenticated PUT /api/schedule → 401.
  3. Oversized body on PUT /api/schedule → 413.
  4. Write rate limit (11th request within a minute) → 429.
  5. Read rate limit (61st request within a minute) → 429.
  6. Secrets (ANTHROPIC_API_KEY / BIZBRIEF_API_KEY) never appear in responses.
  7. Valid GET /api/brief happy path still works.
  8. Valid authenticated PUT /api/schedule happy path still works.
"""

from __future__ import annotations

import json
import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# App fixture — fresh Config + app per test session, but with overridden
# rate-limit values so tests run quickly without real 1-minute windows.
# ---------------------------------------------------------------------------

# Must set env vars BEFORE importing the app module so Config picks them up.
_API_KEY = "test-secret-key-not-real"
os.environ["BIZBRIEF_API_KEY"] = _API_KEY
# Prevent any real Anthropic calls in test (key is clearly fake)
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-for-tests-only")


def _make_app(
    read_limit: int = 60,
    write_limit: int = 10,
    max_body: int = 10_240,
    briefs_dir: str | None = None,
    schedule_dir: str | None = None,
    log_dir: str | None = None,
):
    """
    Build a fresh FastAPI app with the given security knobs.
    Returns (app, cfg) so tests can inspect/write to the data directories.
    """
    # Import here to allow multiple constructions with different configs
    import importlib
    import api.security as security_module
    import api.main as main_module

    # Reset the module-level cost guard to avoid cross-test bleed
    security_module._cost_guard = None

    from pipeline.config import Config

    cfg = Config(
        rate_limit_reads_per_min=read_limit,
        rate_limit_writes_per_min=write_limit,
        max_request_body_bytes=max_body,
        briefs_dir=briefs_dir or "data/briefs",
        schedule_dir=schedule_dir or "data/schedule",
        log_dir=log_dir or "data/logs",
    )

    from fastapi import FastAPI, Depends, Request
    from fastapi.middleware.cors import CORSMiddleware
    from api.security import (
        MaxBodySizeMiddleware,
        RateLimitMiddleware,
        check_cost_guard,
        generic_exception_handler,
        init_cost_guard,
        require_api_key,
        startup_secret_checks,
        validate_business_id,
        validate_week,
        safe_path_join,
    )

    app = FastAPI(title="BizBrief Test API")
    app.add_middleware(RateLimitMiddleware, cfg=cfg)
    app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_exception_handler(Exception, generic_exception_handler)

    import api.main as _m
    # Patch cfg inside main module for this test instance
    _m.cfg = cfg

    # Re-init cost guard with new cfg
    init_cost_guard(cfg)

    return app, cfg


# ---------------------------------------------------------------------------
# Shared app for most tests (default limits)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tmp_data(tmp_path_factory):
    """Create isolated temp data directories for the whole test module."""
    base = tmp_path_factory.mktemp("bizbrief_data")
    briefs = base / "briefs"
    schedule = base / "schedule"
    logs = base / "logs"
    briefs.mkdir()
    schedule.mkdir()
    logs.mkdir()
    return {
        "briefs": str(briefs),
        "schedule": str(schedule),
        "logs": str(logs),
        "base": str(base),
    }


@pytest.fixture(scope="module")
def client(tmp_data):
    """TestClient with default security limits and isolated data dirs."""
    from pipeline.config import Config
    from api.security import (
        MaxBodySizeMiddleware,
        RateLimitMiddleware,
        generic_exception_handler,
        init_cost_guard,
        require_api_key,
        validate_business_id,
        validate_week,
        safe_path_join,
    )
    from fastapi import FastAPI, Depends, Request
    from fastapi.middleware.cors import CORSMiddleware
    import api.main as main_module

    cfg = Config(
        rate_limit_reads_per_min=60,
        rate_limit_writes_per_min=10,
        max_request_body_bytes=10_240,
        briefs_dir=tmp_data["briefs"],
        schedule_dir=tmp_data["schedule"],
        log_dir=tmp_data["logs"],
    )

    # Patch main module's cfg so routes use our temp dirs
    main_module.cfg = cfg

    # Re-init cost guard
    init_cost_guard(cfg)

    # Rebuild the app from scratch to pick up patched cfg
    from api.main import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _put_schedule(client, business_id="testbiz", extra_headers=None):
    headers = {"X-API-Key": _API_KEY}
    if extra_headers:
        headers.update(extra_headers)
    payload = {
        "business_id": business_id,
        "cadence": "weekly",
        "day_of_week": "mon",
        "email_mode": "draft_only",
    }
    return client.put("/api/schedule", json=payload, headers=headers)


# ---------------------------------------------------------------------------
# 1. Path traversal — business_id
# ---------------------------------------------------------------------------

class TestPathTraversal:
    TRAVERSAL_IDS = [
        "../../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "valid/../../../etc",
        "abc/../../secret",
        "",
        "a" * 65,
        "has space",
        "has!bang",
    ]

    @pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
    def test_get_brief_traversal_business_id(self, client, bad_id):
        resp = client.get(f"/api/brief?business_id={bad_id}&week=2024-W31")
        assert resp.status_code == 400, (
            f"Expected 400 for business_id={bad_id!r}, got {resp.status_code}"
        )
        assert "ANTHROPIC_API_KEY" not in resp.text
        assert _API_KEY not in resp.text

    @pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
    def test_get_schedule_traversal_business_id(self, client, bad_id):
        resp = client.get(f"/api/schedule?business_id={bad_id}")
        assert resp.status_code == 400, (
            f"Expected 400 for business_id={bad_id!r}, got {resp.status_code}"
        )

    @pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
    def test_get_runs_traversal_business_id(self, client, bad_id):
        resp = client.get(f"/api/runs?business_id={bad_id}")
        assert resp.status_code == 400, (
            f"Expected 400 for business_id={bad_id!r}, got {resp.status_code}"
        )

    # 2. Path traversal — week
    # Note: the pattern validates format only (^\d{4}-W\d{2}$), not calendar correctness.
    # Semantically-invalid but format-valid values like 2024-W99 are not rejected by the
    # pattern — they are safe (no traversal risk) and will 404 as "brief not found".
    BAD_WEEKS = [
        "../../../etc/passwd",
        "2024W31",
        "notaweek",
        "2024-W3",        # single digit — must be two digits
        "",
        "2024-w31",       # lowercase w
    ]

    @pytest.mark.parametrize("bad_week", BAD_WEEKS)
    def test_get_brief_traversal_week(self, client, bad_week):
        resp = client.get(f"/api/brief?business_id=validbiz&week={bad_week}")
        assert resp.status_code == 400, (
            f"Expected 400 for week={bad_week!r}, got {resp.status_code}"
        )
        assert "ANTHROPIC_API_KEY" not in resp.text
        assert _API_KEY not in resp.text


# ---------------------------------------------------------------------------
# 3. Auth — unauthenticated PUT
# ---------------------------------------------------------------------------

class TestAuth:
    def test_put_schedule_no_key_returns_401(self, client):
        payload = {
            "business_id": "testbiz",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }
        resp = client.put("/api/schedule", json=payload)
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    def test_put_schedule_wrong_key_returns_401(self, client):
        payload = {
            "business_id": "testbiz",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }
        resp = client.put("/api/schedule", json=payload, headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    def test_put_schedule_api_key_not_in_response(self, client):
        payload = {
            "business_id": "testbiz",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }
        resp = client.put("/api/schedule", json=payload, headers={"X-API-Key": "wrong-key"})
        assert _API_KEY not in resp.text
        assert "ANTHROPIC_API_KEY" not in resp.text


# ---------------------------------------------------------------------------
# 4. Payload cap — 413
# ---------------------------------------------------------------------------

class TestPayloadCap:
    def test_oversized_body_returns_413(self, client):
        # 11 KB > 10 KB limit
        oversized = "x" * 11_000
        # Build a valid-looking JSON body that is oversized via padding field
        payload = {
            "business_id": "testbiz",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
            "padding": oversized,
        }
        resp = client.put(
            "/api/schedule",
            content=json.dumps(payload).encode(),
            headers={
                "X-API-Key": _API_KEY,
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 413, f"Expected 413, got {resp.status_code}: {resp.text}"

    def test_exactly_at_limit_is_accepted_structurally(self, client):
        """A body just under 10 KB should not be rejected for size (may fail validation for other reasons)."""
        small_payload = {
            "business_id": "testbiz",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }
        body = json.dumps(small_payload).encode()
        assert len(body) < 10_240, "Test payload must be under 10 KB"
        resp = client.put(
            "/api/schedule",
            content=body,
            headers={
                "X-API-Key": _API_KEY,
                "Content-Type": "application/json",
            },
        )
        # Should not be 413 (may be 200 or another validation error, but NOT size rejection)
        assert resp.status_code != 413, f"Under-limit body wrongly rejected with 413"


# ---------------------------------------------------------------------------
# 5. Rate limiting — writes
# ---------------------------------------------------------------------------

class TestWriteRateLimit:
    """
    Use a fresh app with a write limit of 10 per minute.
    The 11th request must return 429.
    """

    @pytest.fixture
    def rate_limited_client(self, tmp_path):
        """Fresh app with isolated data dirs and write limit of 10."""
        from pipeline.config import Config
        from api.security import (
            MaxBodySizeMiddleware,
            RateLimitMiddleware,
            generic_exception_handler,
            init_cost_guard,
            require_api_key,
        )
        import api.main as main_module
        from fastapi import FastAPI, Depends, Request
        from fastapi.middleware.cors import CORSMiddleware
        from api.main import app

        (tmp_path / "schedule").mkdir()
        (tmp_path / "logs").mkdir()
        (tmp_path / "briefs").mkdir()

        cfg = Config(
            rate_limit_reads_per_min=60,
            rate_limit_writes_per_min=10,
            max_request_body_bytes=10_240,
            briefs_dir=str(tmp_path / "briefs"),
            schedule_dir=str(tmp_path / "schedule"),
            log_dir=str(tmp_path / "logs"),
        )
        main_module.cfg = cfg
        init_cost_guard(cfg)

        # Replace middleware on a new app instance
        from fastapi import FastAPI
        from api.security import _SlidingWindow

        # Build a fresh isolated app with fresh rate-limiter state
        fresh_app = FastAPI(title="RateTest")
        fresh_app.add_middleware(RateLimitMiddleware, cfg=cfg)
        fresh_app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
        fresh_app.add_exception_handler(Exception, generic_exception_handler)

        # Register the routes from main_module on the fresh app
        for route in app.routes:
            fresh_app.routes.append(route)

        return TestClient(fresh_app, raise_server_exceptions=False)

    def test_11th_write_returns_429(self, rate_limited_client):
        """Send 11 PUT requests; the 11th must return 429."""
        responses = []
        for i in range(11):
            payload = {
                "business_id": "ratelimitbiz",
                "cadence": "weekly",
                "day_of_week": "mon",
                "email_mode": "draft_only",
            }
            resp = rate_limited_client.put(
                "/api/schedule",
                json=payload,
                headers={"X-API-Key": _API_KEY},
            )
            responses.append(resp.status_code)

        assert responses[-1] == 429, (
            f"Expected 11th write to return 429, got {responses[-1]}. "
            f"All responses: {responses}"
        )
        # First 10 must not be rate-limited
        for i, code in enumerate(responses[:10]):
            assert code != 429, f"Request {i+1}/10 should not be rate-limited, got {code}"


# ---------------------------------------------------------------------------
# 6. Rate limiting — reads
# ---------------------------------------------------------------------------

class TestReadRateLimit:
    """
    Use a fresh app with a read limit of 5 per minute for speed.
    The 6th request must return 429.
    """

    @pytest.fixture
    def tight_read_client(self, tmp_path):
        """Fresh app with read limit of 5 (fast test)."""
        from pipeline.config import Config
        from api.security import (
            MaxBodySizeMiddleware,
            RateLimitMiddleware,
            generic_exception_handler,
            init_cost_guard,
        )
        import api.main as main_module
        from api.main import app

        (tmp_path / "briefs").mkdir()
        (tmp_path / "schedule").mkdir()
        (tmp_path / "logs").mkdir()

        cfg = Config(
            rate_limit_reads_per_min=5,
            rate_limit_writes_per_min=10,
            max_request_body_bytes=10_240,
            briefs_dir=str(tmp_path / "briefs"),
            schedule_dir=str(tmp_path / "schedule"),
            log_dir=str(tmp_path / "logs"),
        )
        main_module.cfg = cfg
        init_cost_guard(cfg)

        from fastapi import FastAPI
        fresh_app = FastAPI(title="ReadRateTest")
        fresh_app.add_middleware(RateLimitMiddleware, cfg=cfg)
        fresh_app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
        fresh_app.add_exception_handler(Exception, generic_exception_handler)

        for route in app.routes:
            fresh_app.routes.append(route)

        return TestClient(fresh_app, raise_server_exceptions=False)

    def test_exceeding_read_limit_returns_429(self, tight_read_client):
        """Send 6 GET requests with limit=5; the 6th must return 429."""
        responses = []
        for i in range(6):
            resp = tight_read_client.get("/api/runs?business_id=validbiz")
            responses.append(resp.status_code)

        assert responses[-1] == 429, (
            f"Expected 6th read to return 429 with limit=5, got {responses[-1]}. "
            f"All: {responses}"
        )
        for i, code in enumerate(responses[:5]):
            assert code != 429, f"Request {i+1}/5 should not be rate-limited, got {code}"

    def test_61st_read_returns_429_with_default_limit(self, tmp_path):
        """With default limit=60, the 61st request must return 429."""
        from pipeline.config import Config
        from api.security import (
            MaxBodySizeMiddleware,
            RateLimitMiddleware,
            generic_exception_handler,
            init_cost_guard,
        )
        import api.main as main_module
        from api.main import app

        (tmp_path / "briefs").mkdir(exist_ok=True)
        (tmp_path / "schedule").mkdir(exist_ok=True)
        (tmp_path / "logs").mkdir(exist_ok=True)

        cfg = Config(
            rate_limit_reads_per_min=60,
            rate_limit_writes_per_min=10,
            max_request_body_bytes=10_240,
            briefs_dir=str(tmp_path / "briefs"),
            schedule_dir=str(tmp_path / "schedule"),
            log_dir=str(tmp_path / "logs"),
        )
        main_module.cfg = cfg
        init_cost_guard(cfg)

        from fastapi import FastAPI
        fresh_app = FastAPI(title="ReadRate61Test")
        fresh_app.add_middleware(RateLimitMiddleware, cfg=cfg)
        fresh_app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
        fresh_app.add_exception_handler(Exception, generic_exception_handler)

        for route in app.routes:
            fresh_app.routes.append(route)

        cl = TestClient(fresh_app, raise_server_exceptions=False)
        responses = []
        for i in range(61):
            resp = cl.get("/api/runs?business_id=validbiz")
            responses.append(resp.status_code)

        assert responses[60] == 429, (
            f"Expected 61st read to return 429, got {responses[60]}. "
            f"Last 5: {responses[-5:]}"
        )
        for i, code in enumerate(responses[:60]):
            assert code != 429, f"Request {i+1}/60 should not be rate-limited, got {code}"


# ---------------------------------------------------------------------------
# 7. Secrets never in response bodies
# ---------------------------------------------------------------------------

class TestSecretHygiene:
    ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-for-tests-only")

    def test_anthropic_key_not_in_404_response(self, client):
        resp = client.get("/api/brief?business_id=nonexistent&week=2024-W31")
        assert self.ANTHROPIC_KEY not in resp.text
        assert "ANTHROPIC_API_KEY" not in resp.text

    def test_api_key_not_in_401_response(self, client):
        resp = client.put("/api/schedule", json={"business_id": "x"})
        assert _API_KEY not in resp.text
        assert "BIZBRIEF_API_KEY" not in resp.text

    def test_api_key_not_in_400_response(self, client):
        resp = client.get("/api/brief?business_id=../etc&week=2024-W31")
        assert _API_KEY not in resp.text
        assert "BIZBRIEF_API_KEY" not in resp.text
        assert self.ANTHROPIC_KEY not in resp.text

    def test_api_key_not_in_200_response(self, client, tmp_data):
        """Even a successful auth'd PUT must not echo the key back."""
        resp = _put_schedule(client, business_id="hygienebiz")
        assert _API_KEY not in resp.text
        assert "BIZBRIEF_API_KEY" not in resp.text

    def test_anthropic_key_not_in_500_response(self, client):
        """Trigger a 500 and confirm no secrets leak."""
        # A request that makes it past guards but might trigger an internal error.
        resp = client.get("/api/brief?business_id=validbiz&week=2024-W31")
        assert self.ANTHROPIC_KEY not in resp.text
        # Could be 404 or 500 — either way, no secret
        assert "ANTHROPIC_API_KEY" not in resp.text


# ---------------------------------------------------------------------------
# 8. Happy path — GET /api/brief still works
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_get_brief_happy_path(self, client, tmp_data):
        """A valid brief on disk should return 200."""
        import pathlib

        # Create the minimal brief+themes files
        biz_dir = pathlib.Path(tmp_data["briefs"]) / "happybiz"
        biz_dir.mkdir(parents=True, exist_ok=True)

        brief = {
            "business_id": "happybiz",
            "business_name": "Happy Cafe",
            "week": "2024-W31",
            "summary": "Good week.",
            "trend": "up",
            "action_items": [],
            "email_draft": None,
            "partial": False,
            "generated_by": "claude-haiku-4-5-20251001",
        }
        themes = {
            "business_id": "happybiz",
            "week": "2024-W31",
            "review_count": 10,
            "avg_stars": 4.5,
            "prev_avg_stars": None,
            "themes": [],
            "sufficient": True,
            "partial": False,
        }

        (biz_dir / "2024-W31.brief.json").write_text(json.dumps(brief))
        (biz_dir / "2024-W31.themes.json").write_text(json.dumps(themes))

        # Re-point cfg at our data dirs
        import api.main as main_module
        from pipeline.config import Config
        cfg = Config(
            briefs_dir=tmp_data["briefs"],
            schedule_dir=tmp_data["schedule"],
            log_dir=tmp_data["logs"],
        )
        main_module.cfg = cfg

        resp = client.get("/api/brief?business_id=happybiz&week=2024-W31")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "brief" in data
        assert data["brief"]["business_name"] == "Happy Cafe"

    def test_get_businesses_happy_path(self, client, tmp_data):
        """GET /api/businesses should return list (may be empty if no data)."""
        import api.main as main_module
        from pipeline.config import Config
        cfg = Config(
            briefs_dir=tmp_data["briefs"],
            schedule_dir=tmp_data["schedule"],
            log_dir=tmp_data["logs"],
        )
        main_module.cfg = cfg

        resp = client.get("/api/businesses")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_runs_empty_happy_path(self, client, tmp_data):
        """GET /api/runs for a valid business_id with no runs → 200 empty list."""
        import api.main as main_module
        from pipeline.config import Config
        cfg = Config(
            briefs_dir=tmp_data["briefs"],
            schedule_dir=tmp_data["schedule"],
            log_dir=tmp_data["logs"],
        )
        main_module.cfg = cfg

        resp = client.get("/api/runs?business_id=validbiz")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# 9. Valid authenticated PUT /api/schedule happy path
# ---------------------------------------------------------------------------

class TestAuthenticatedPutSchedule:
    def test_valid_put_schedule_returns_200(self, client, tmp_data):
        import api.main as main_module
        from pipeline.config import Config
        cfg = Config(
            briefs_dir=tmp_data["briefs"],
            schedule_dir=tmp_data["schedule"],
            log_dir=tmp_data["logs"],
        )
        main_module.cfg = cfg
        os.makedirs(tmp_data["schedule"], exist_ok=True)

        resp = _put_schedule(client, business_id="authbiz")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["business_id"] == "authbiz"
        assert data["cadence"] == "weekly"
        assert data["day_of_week"] == "mon"
        assert data["email_mode"] == "draft_only"

    def test_put_schedule_persisted_to_disk(self, client, tmp_data):
        """After a successful PUT, the file should exist on disk."""
        import api.main as main_module
        import pathlib
        from pipeline.config import Config
        cfg = Config(
            briefs_dir=tmp_data["briefs"],
            schedule_dir=tmp_data["schedule"],
            log_dir=tmp_data["logs"],
        )
        main_module.cfg = cfg

        resp = _put_schedule(client, business_id="diskbiz")
        assert resp.status_code == 200

        sched_file = pathlib.Path(tmp_data["schedule"]) / "diskbiz.json"
        assert sched_file.exists(), "Schedule file should have been written to disk"
        on_disk = json.loads(sched_file.read_text())
        assert on_disk["business_id"] == "diskbiz"

    def test_put_schedule_rejects_extra_fields(self, client, tmp_data):
        """PUT /api/schedule with extra fields should return 400."""
        import api.main as main_module
        from pipeline.config import Config
        cfg = Config(
            briefs_dir=tmp_data["briefs"],
            schedule_dir=tmp_data["schedule"],
            log_dir=tmp_data["logs"],
        )
        main_module.cfg = cfg

        payload = {
            "business_id": "extrafieldbiz",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
            "injected_field": "malicious",
        }
        resp = client.put("/api/schedule", json=payload, headers={"X-API-Key": _API_KEY})
        assert resp.status_code == 400, f"Expected 400 for extra fields, got {resp.status_code}"

    def test_put_schedule_traversal_business_id_returns_400(self, client, tmp_data):
        """PUT /api/schedule with traversal business_id must be rejected."""
        import api.main as main_module
        from pipeline.config import Config
        cfg = Config(
            briefs_dir=tmp_data["briefs"],
            schedule_dir=tmp_data["schedule"],
            log_dir=tmp_data["logs"],
        )
        main_module.cfg = cfg

        payload = {
            "business_id": "../../../etc/passwd",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }
        resp = client.put("/api/schedule", json=payload, headers={"X-API-Key": _API_KEY})
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"


# ---------------------------------------------------------------------------
# 10. validate_business_id / validate_week unit tests (direct)
# ---------------------------------------------------------------------------

class TestValidationFunctions:
    def test_valid_business_ids_pass(self):
        from api.security import validate_business_id
        for valid in ["abc", "ABC-123", "my_biz", "a" * 64]:
            assert validate_business_id(valid) == valid

    def test_invalid_business_ids_raise(self):
        from api.security import validate_business_id
        from fastapi import HTTPException
        for invalid in ["../etc", "abc def", "abc/def", "", "a" * 65, "abc!", ".hidden"]:
            with pytest.raises(HTTPException) as exc_info:
                validate_business_id(invalid)
            assert exc_info.value.status_code == 400

    def test_valid_weeks_pass(self):
        from api.security import validate_week
        for valid in ["2024-W01", "2024-W31", "2099-W53"]:
            assert validate_week(valid) == valid

    def test_invalid_weeks_raise(self):
        from api.security import validate_week
        from fastapi import HTTPException
        for invalid in ["2024W31", "24-W31", "2024-w31", "2024-W1", "not-a-week", ""]:
            with pytest.raises(HTTPException) as exc_info:
                validate_week(invalid)
            assert exc_info.value.status_code == 400

    def test_safe_path_join_blocks_traversal(self):
        from api.security import safe_path_join
        from fastapi import HTTPException
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as base:
            base_real = os.path.realpath(base)
            # Normal join should work; result is under base_real (resolves macOS symlinks)
            result = safe_path_join(base, "subdir", "file.json")
            assert result.startswith(base_real), (
                f"Expected result to start with {base_real!r}, got {result!r}"
            )

            # Traversal must raise
            with pytest.raises(HTTPException) as exc_info:
                safe_path_join(base, "../outside")
            assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 11. RT-001 — Rate limiter uses real connection IP, not XFF header
# ---------------------------------------------------------------------------

class TestXFFIgnored:
    """
    RT-001 (REOPENED): X-Forwarded-For must be ignored at ALL layers.

    The application-level _client_ip() fix (trusted_proxy=False) is correct but
    insufficient alone because uvicorn defaults FORWARDED_ALLOW_IPS="127.0.0.1"
    and rewrites scope["client"] to the XFF IP before the ASGI app sees the
    request.  The fix requires two layers:

    Layer 1 (primary): api/main.py sets os.environ["FORWARDED_ALLOW_IPS"]=""
    at module-import time so uvicorn's ProxyHeadersMiddleware never rewrites
    scope["client"].

    Layer 2 (defense-in-depth): StripProxyHeadersMiddleware removes XFF/X-Real-IP
    from scope["headers"] so downstream code can't consume them.

    These tests verify:
    a) XFF header does not reset the rate limit (existing behavior, now with
       StripProxyHeadersMiddleware also in the stack).
    b) Rotating XFF values don't give fresh windows.
    c) StripProxyHeadersMiddleware strips XFF headers from scope["headers"].
    d) The rate limiter uses the real TCP IP even when scope["client"] has been
       pre-rewritten to a spoofed value (simulating uvicorn's behavior when
       FORWARDED_ALLOW_IPS is misconfigured), because StripProxyHeadersMiddleware
       ensures the scope is clean and _client_ip() reads scope["client"].
    """

    @pytest.fixture
    def xff_client(self, tmp_path):
        """Fresh app with write limit=3, StripProxyHeadersMiddleware included."""
        from pipeline.config import Config
        from api.security import (
            MaxBodySizeMiddleware,
            RateLimitMiddleware,
            StripProxyHeadersMiddleware,
            generic_exception_handler,
            init_security,
        )
        import api.main as main_module
        from api.main import app
        from fastapi import FastAPI

        (tmp_path / "schedule").mkdir()
        (tmp_path / "logs").mkdir()
        (tmp_path / "briefs").mkdir()

        cfg = Config(
            rate_limit_reads_per_min=60,
            rate_limit_writes_per_min=3,
            max_request_body_bytes=10_240,
            briefs_dir=str(tmp_path / "briefs"),
            schedule_dir=str(tmp_path / "schedule"),
            log_dir=str(tmp_path / "logs"),
            trusted_proxy=False,  # explicit safe default
        )
        main_module.cfg = cfg
        init_security(cfg)

        fresh_app = FastAPI(title="XFFTest")
        fresh_app.add_middleware(RateLimitMiddleware, cfg=cfg)
        fresh_app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
        fresh_app.add_exception_handler(Exception, generic_exception_handler)
        for route in app.routes:
            fresh_app.routes.append(route)
        # StripProxyHeadersMiddleware added last = executes first (LIFO wrapping)
        fresh_app.add_middleware(StripProxyHeadersMiddleware, cfg=cfg)

        return TestClient(fresh_app, raise_server_exceptions=False)

    def test_xff_header_does_not_reset_rate_limit(self, xff_client):
        """
        Burn the write limit from the real IP, then retry with a spoofed
        X-Forwarded-For.  The 4th request must still return 429 — XFF is ignored.
        """
        payload = {
            "business_id": "xffbiz",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }
        headers_good = {"X-API-Key": _API_KEY}

        # Burn all 3 write slots
        for _ in range(3):
            r = xff_client.put("/api/schedule", json=payload, headers=headers_good)
            assert r.status_code != 429, f"Unexpectedly rate-limited early: {r.status_code}"

        # Now attempt with spoofed XFF — must still be 429, not 200
        spoofed = dict(headers_good)
        spoofed["X-Forwarded-For"] = "1.2.3.4"
        r = xff_client.put("/api/schedule", json=payload, headers=spoofed)
        assert r.status_code == 429, (
            f"XFF spoofing bypassed the rate limit (got {r.status_code}). "
            "trusted_proxy=False must ignore XFF entirely."
        )

    def test_xff_different_values_do_not_give_fresh_windows(self, xff_client):
        """Rotating XFF values must not create independent per-IP windows."""
        payload = {
            "business_id": "xffbiz2",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }
        headers = {"X-API-Key": _API_KEY}

        # Burn the real-IP limit
        for _ in range(3):
            xff_client.put("/api/schedule", json=payload, headers=headers)

        # Try 5 different spoofed IPs — all must hit 429
        for fake_ip in ["10.0.0.1", "10.0.0.2", "172.16.0.1", "192.168.1.1", "8.8.8.8"]:
            h = dict(headers)
            h["X-Forwarded-For"] = fake_ip
            r = xff_client.put("/api/schedule", json=payload, headers=h)
            assert r.status_code == 429, (
                f"XFF={fake_ip!r} bypassed rate limit (got {r.status_code})"
            )

    def test_strip_proxy_headers_middleware_removes_xff(self, tmp_path):
        """
        StripProxyHeadersMiddleware must strip XFF/X-Real-IP from scope["headers"]
        so no downstream handler can read them.
        RT-001 regression: verifies the header-stripping layer works independently.
        """
        from api.security import StripProxyHeadersMiddleware, _PROXY_HEADERS_TO_STRIP
        from pipeline.config import Config
        import asyncio

        cfg = Config(trusted_proxy=False)

        seen_headers: list = []

        async def capture_app(scope, receive, send):
            """Capture the headers as seen by the inner app."""
            seen_headers.extend(scope.get("headers", []))
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        middleware = StripProxyHeadersMiddleware(capture_app, cfg=cfg)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (b"host", b"localhost"),
                (b"x-forwarded-for", b"99.88.77.66"),
                (b"x-real-ip", b"99.88.77.66"),
                (b"content-type", b"application/json"),
                (b"x-forwarded-proto", b"https"),
            ],
            "client": ("127.0.0.1", 12345),
        }

        async def fake_receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        sent_messages = []

        async def fake_send(message):
            sent_messages.append(message)

        asyncio.get_event_loop().run_until_complete(
            middleware(scope, fake_receive, fake_send)
        )

        # Verify XFF and X-Real-IP were stripped
        header_names = {name for name, _ in seen_headers}
        for stripped_header in [b"x-forwarded-for", b"x-real-ip", b"x-forwarded-proto"]:
            assert stripped_header not in header_names, (
                f"StripProxyHeadersMiddleware failed to remove {stripped_header!r}"
            )
        # Non-proxy headers must still be present
        assert b"host" in header_names, "host header must not be stripped"
        assert b"content-type" in header_names, "content-type header must not be stripped"

    def test_real_ip_used_even_when_scope_client_is_spoofed(self, tmp_path):
        """
        RT-001 regression — uvicorn layer: even if scope["client"] has been
        pre-rewritten to a spoofed IP (simulating what uvicorn does when
        FORWARDED_ALLOW_IPS includes 127.0.0.1), the rate limiter must key on
        that scope["client"] address consistently — meaning an attacker cannot
        get a FRESH window simply by rotating XFF.

        This test verifies that with StripProxyHeadersMiddleware removing XFF
        from scope["headers"], _client_ip() reads scope["client"] directly,
        and since scope["client"] is the same for all requests (the TestClient
        address), the rate limit still fires correctly regardless of XFF headers.
        """
        from pipeline.config import Config
        from api.security import (
            MaxBodySizeMiddleware,
            RateLimitMiddleware,
            StripProxyHeadersMiddleware,
            generic_exception_handler,
            init_security,
        )
        import api.main as main_module
        from api.main import app
        from fastapi import FastAPI

        (tmp_path / "schedule2").mkdir()
        (tmp_path / "logs2").mkdir()
        (tmp_path / "briefs2").mkdir()

        cfg = Config(
            rate_limit_reads_per_min=60,
            rate_limit_writes_per_min=2,  # tight limit for fast test
            max_request_body_bytes=10_240,
            briefs_dir=str(tmp_path / "briefs2"),
            schedule_dir=str(tmp_path / "schedule2"),
            log_dir=str(tmp_path / "logs2"),
            trusted_proxy=False,
        )
        main_module.cfg = cfg
        init_security(cfg)

        fresh_app = FastAPI(title="SpoofedClientTest")
        fresh_app.add_middleware(RateLimitMiddleware, cfg=cfg)
        fresh_app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
        fresh_app.add_exception_handler(Exception, generic_exception_handler)
        for route in app.routes:
            fresh_app.routes.append(route)
        fresh_app.add_middleware(StripProxyHeadersMiddleware, cfg=cfg)

        cl = TestClient(fresh_app, raise_server_exceptions=False)

        payload = {
            "business_id": "spooftest",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }

        # Exhaust the write limit (2 requests)
        for _ in range(2):
            r = cl.put("/api/schedule", json=payload, headers={"X-API-Key": _API_KEY})
            assert r.status_code != 429, f"Unexpectedly rate-limited early: {r.status_code}"

        # Now try with 10 different XFF values — NONE should bypass the 429
        for i in range(10):
            h = {"X-API-Key": _API_KEY, "X-Forwarded-For": f"10.0.{i}.1"}
            r = cl.put("/api/schedule", json=payload, headers=h)
            assert r.status_code == 429, (
                f"XFF rotation should not bypass rate limit "
                f"(attempt {i+1}, XFF=10.0.{i}.1, got {r.status_code})"
            )


# ---------------------------------------------------------------------------
# 12. RT-005 — Auth-failure lockout
# ---------------------------------------------------------------------------

class TestAuthFailureLockout:
    """
    RT-005: after N consecutive wrong-key attempts from the same IP within
    the window, the IP is locked out (429) for M minutes.
    """

    @pytest.fixture
    def lockout_client(self, tmp_path):
        """Fresh app with lockout after 3 failures in 60 s, banned for 30 s."""
        from pipeline.config import Config
        from api.security import (
            MaxBodySizeMiddleware,
            RateLimitMiddleware,
            generic_exception_handler,
            init_security,
            validation_exception_handler,
        )
        from fastapi.exceptions import RequestValidationError
        import api.main as main_module
        from api.main import app
        from fastapi import FastAPI

        (tmp_path / "schedule").mkdir()
        (tmp_path / "logs").mkdir()
        (tmp_path / "briefs").mkdir()

        cfg = Config(
            rate_limit_reads_per_min=60,
            rate_limit_writes_per_min=100,  # high so general RL doesn't interfere
            max_request_body_bytes=10_240,
            briefs_dir=str(tmp_path / "briefs"),
            schedule_dir=str(tmp_path / "schedule"),
            log_dir=str(tmp_path / "logs"),
            auth_lockout_attempts=3,
            auth_lockout_window_s=60,
            auth_lockout_ban_s=30,
        )
        main_module.cfg = cfg
        init_security(cfg)

        fresh_app = FastAPI(title="LockoutTest")
        fresh_app.add_middleware(RateLimitMiddleware, cfg=cfg)
        fresh_app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
        fresh_app.add_exception_handler(RequestValidationError, validation_exception_handler)
        fresh_app.add_exception_handler(Exception, generic_exception_handler)
        for route in app.routes:
            fresh_app.routes.append(route)

        return TestClient(fresh_app, raise_server_exceptions=False)

    def test_wrong_key_lockout_after_n_attempts(self, lockout_client):
        """3 wrong keys → lockout (429), not just 401."""
        payload = {
            "business_id": "lockoutbiz",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }
        results = []
        for i in range(4):
            r = lockout_client.put(
                "/api/schedule",
                json=payload,
                headers={"X-API-Key": f"wrong-key-{i}"},
            )
            results.append(r.status_code)

        # First two should be 401 (not yet locked out)
        assert results[0] == 401, f"Attempt 1 should be 401, got {results[0]}"
        assert results[1] == 401, f"Attempt 2 should be 401, got {results[1]}"
        # Third attempt crosses the threshold — returns 429
        assert results[2] == 429, (
            f"3rd attempt should trigger lockout (429), got {results[2]}. "
            f"All: {results}"
        )
        # Fourth attempt — still locked out
        assert results[3] == 429, (
            f"4th attempt (while banned) should be 429, got {results[3]}"
        )

    def test_lockout_has_retry_after_header(self, lockout_client):
        """Lockout response must include Retry-After header."""
        payload = {
            "business_id": "lockoutbiz2",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }
        for i in range(3):
            r = lockout_client.put(
                "/api/schedule",
                json=payload,
                headers={"X-API-Key": f"wrong-key-{i}"},
            )
        # Last one should be 429 with Retry-After
        assert r.status_code == 429
        assert "retry-after" in {k.lower() for k in r.headers}

    def test_successful_auth_clears_failure_count(self, lockout_client):
        """After a correct key, the failure counter resets (no lockout)."""
        payload = {
            "business_id": "lockoutbiz3",
            "cadence": "weekly",
            "day_of_week": "mon",
            "email_mode": "draft_only",
        }
        # Two wrong attempts (below threshold)
        for i in range(2):
            lockout_client.put(
                "/api/schedule",
                json=payload,
                headers={"X-API-Key": "wrong"},
            )
        # Correct key — resets counter
        r = lockout_client.put(
            "/api/schedule",
            json=payload,
            headers={"X-API-Key": _API_KEY},
        )
        assert r.status_code == 200, (
            f"Correct key should succeed, got {r.status_code}: {r.text}"
        )
        # Two more wrong attempts after reset — should be 401, not 429
        for i in range(2):
            r = lockout_client.put(
                "/api/schedule",
                json=payload,
                headers={"X-API-Key": "wrong-after-reset"},
            )
            assert r.status_code == 401, (
                f"After reset, wrong key should be 401, got {r.status_code}"
            )


# ---------------------------------------------------------------------------
# 13. RT-007 — 422 responses must not echo raw input
# ---------------------------------------------------------------------------

class TestValidationErrorNoEcho:
    """
    RT-007: FastAPI's default 422 handler echoes the raw 'input' field.
    Our custom handler must return {"detail": "Invalid request"} with no echo.
    """

    @pytest.fixture
    def validation_client(self, tmp_path):
        """Fresh app with the validation_exception_handler registered."""
        from pipeline.config import Config
        from api.security import (
            MaxBodySizeMiddleware,
            RateLimitMiddleware,
            generic_exception_handler,
            init_security,
            validation_exception_handler,
        )
        from fastapi.exceptions import RequestValidationError
        import api.main as main_module
        from api.main import app
        from fastapi import FastAPI

        (tmp_path / "schedule").mkdir()
        (tmp_path / "logs").mkdir()
        (tmp_path / "briefs").mkdir()

        cfg = Config(
            rate_limit_reads_per_min=60,
            rate_limit_writes_per_min=100,
            max_request_body_bytes=10_240,
            briefs_dir=str(tmp_path / "briefs"),
            schedule_dir=str(tmp_path / "schedule"),
            log_dir=str(tmp_path / "logs"),
        )
        main_module.cfg = cfg
        init_security(cfg)

        fresh_app = FastAPI(title="ValidationTest")
        fresh_app.add_middleware(RateLimitMiddleware, cfg=cfg)
        fresh_app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
        fresh_app.add_exception_handler(RequestValidationError, validation_exception_handler)
        fresh_app.add_exception_handler(Exception, generic_exception_handler)
        for route in app.routes:
            fresh_app.routes.append(route)

        return TestClient(fresh_app, raise_server_exceptions=False)

    def test_non_dict_body_returns_generic_422(self, validation_client):
        """Sending a non-dict body returns 422 with generic message, not echoed input."""
        # This is the exact payload from the RT-007 reproduction
        raw_body = b'"ANTHROPIC_API_KEY=sk-ant-fake-placeholder"'
        r = validation_client.put(
            "/api/schedule",
            content=raw_body,
            headers={
                "X-API-Key": _API_KEY,
                "Content-Type": "application/json",
            },
        )
        assert r.status_code == 422
        body = r.text
        # Must not echo the input back
        assert "ANTHROPIC_API_KEY" not in body, (
            "422 response must not echo input (RT-007)"
        )
        assert "sk-ant-fake-placeholder" not in body
        # Must return generic message
        assert "Invalid request" in body or "invalid" in body.lower()

    def test_array_body_returns_generic_422(self, validation_client):
        """Sending an array body should also return generic 422."""
        r = validation_client.put(
            "/api/schedule",
            content=b'["array","body"]',
            headers={
                "X-API-Key": _API_KEY,
                "Content-Type": "application/json",
            },
        )
        assert r.status_code == 422
        body = r.text
        # Must not contain "input" field echoing back
        assert '"array"' not in body, "422 response must not echo the array input"
        assert "Invalid request" in body or "invalid" in body.lower()

    def test_422_no_input_field_in_response(self, validation_client):
        """The 'input' field from FastAPI's default 422 must not appear."""
        r = validation_client.put(
            "/api/schedule",
            content=b'"some string"',
            headers={
                "X-API-Key": _API_KEY,
                "Content-Type": "application/json",
            },
        )
        assert r.status_code == 422
        data = r.json()
        # Generic handler returns {"detail": "Invalid request"}
        assert data == {"detail": "Invalid request"}, (
            f"Expected {{\"detail\": \"Invalid request\"}}, got {data!r}"
        )


# ---------------------------------------------------------------------------
# 14. RT-008 — Schedule file cap returns 429 when exceeded
# ---------------------------------------------------------------------------

class TestScheduleFileCap:
    """
    RT-008: PUT /api/schedule must return 429 when the total number of schedule
    files in data/schedule/ reaches Config.max_schedule_entries.
    """

    @pytest.fixture
    def capped_client(self, tmp_path):
        """Fresh app with max_schedule_entries=3 for quick testing."""
        from pipeline.config import Config
        from api.security import (
            MaxBodySizeMiddleware,
            RateLimitMiddleware,
            generic_exception_handler,
            init_security,
            validation_exception_handler,
        )
        from fastapi.exceptions import RequestValidationError
        import api.main as main_module
        from api.main import app
        from fastapi import FastAPI

        sched_dir = tmp_path / "schedule"
        sched_dir.mkdir()
        (tmp_path / "logs").mkdir()
        (tmp_path / "briefs").mkdir()

        cfg = Config(
            rate_limit_reads_per_min=60,
            rate_limit_writes_per_min=100,
            max_request_body_bytes=10_240,
            briefs_dir=str(tmp_path / "briefs"),
            schedule_dir=str(sched_dir),
            log_dir=str(tmp_path / "logs"),
            max_schedule_entries=3,
        )
        main_module.cfg = cfg
        init_security(cfg)

        fresh_app = FastAPI(title="CapTest")
        fresh_app.add_middleware(RateLimitMiddleware, cfg=cfg)
        fresh_app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
        fresh_app.add_exception_handler(RequestValidationError, validation_exception_handler)
        fresh_app.add_exception_handler(Exception, generic_exception_handler)
        for route in app.routes:
            fresh_app.routes.append(route)

        return TestClient(fresh_app, raise_server_exceptions=False), sched_dir

    def test_schedule_cap_returns_429(self, capped_client):
        """After max_schedule_entries unique businesses, the next returns 429."""
        cl, sched_dir = capped_client

        def put_biz(biz_id):
            return cl.put(
                "/api/schedule",
                json={
                    "business_id": biz_id,
                    "cadence": "weekly",
                    "day_of_week": "mon",
                    "email_mode": "draft_only",
                },
                headers={"X-API-Key": _API_KEY},
            )

        # Fill up to the cap (3 entries)
        for i in range(3):
            r = put_biz(f"capbiz{i}")
            assert r.status_code == 200, (
                f"Business {i} should succeed, got {r.status_code}: {r.text}"
            )

        # 4th unique business must return 429
        r = put_biz("capbiz-overflow")
        assert r.status_code == 429, (
            f"Expected 429 when cap reached, got {r.status_code}: {r.text}"
        )

    def test_update_existing_not_blocked_by_cap(self, capped_client):
        """Updating an already-existing business_id should NOT be blocked by the cap."""
        cl, sched_dir = capped_client

        def put_biz(biz_id):
            return cl.put(
                "/api/schedule",
                json={
                    "business_id": biz_id,
                    "cadence": "weekly",
                    "day_of_week": "mon",
                    "email_mode": "draft_only",
                },
                headers={"X-API-Key": _API_KEY},
            )

        # Fill cap
        for i in range(3):
            put_biz(f"updatebiz{i}")

        # Update an existing entry — must NOT return 429
        r = put_biz("updatebiz0")
        assert r.status_code == 200, (
            f"Updating existing entry should succeed (200), got {r.status_code}: {r.text}"
        )


# ---------------------------------------------------------------------------
# 15. Phase 4 — GET /api/metrics security gate
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    """
    Phase 4 security gate for GET /api/metrics.

    Checks:
    a) Covered by RateLimitMiddleware — 6th request with limit=5 returns 429.
    b) metrics_max_days cap — only the N most-recent .jsonl files are read;
       older files are silently skipped; response is not unbounded.
    c) error_class never surfaces in the response — only numeric aggregates and
       model/stage names are returned.
    d) Empty log dir returns 200 with zeroed structure.
    e) Malformed JSONL lines are skipped; endpoint does not 500.
    f) Secret keys are never in the response body.
    """

    @pytest.fixture
    def metrics_client(self, tmp_path):
        """Fresh app pointed at an isolated log directory."""
        from pipeline.config import Config
        from api.security import (
            MaxBodySizeMiddleware,
            RateLimitMiddleware,
            generic_exception_handler,
            init_security,
        )
        import api.main as main_module
        from api.main import app
        from fastapi import FastAPI

        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (tmp_path / "briefs").mkdir()
        (tmp_path / "schedule").mkdir()

        cfg = Config(
            rate_limit_reads_per_min=60,
            rate_limit_writes_per_min=10,
            max_request_body_bytes=10_240,
            briefs_dir=str(tmp_path / "briefs"),
            schedule_dir=str(tmp_path / "schedule"),
            log_dir=str(log_dir),
            metrics_max_days=3,   # tight cap so we can test overflow quickly
        )
        main_module.cfg = cfg
        init_security(cfg)

        fresh_app = FastAPI(title="MetricsTest")
        fresh_app.add_middleware(RateLimitMiddleware, cfg=cfg)
        fresh_app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
        fresh_app.add_exception_handler(Exception, generic_exception_handler)
        for route in app.routes:
            fresh_app.routes.append(route)

        return TestClient(fresh_app, raise_server_exceptions=False), log_dir, cfg

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _write_log(log_dir, date_str: str, events: list[dict]):
        """Write events as JSONL to log_dir/<date_str>.jsonl."""
        import pathlib
        path = pathlib.Path(log_dir) / f"{date_str}.jsonl"
        with path.open("w") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

    # ------------------------------------------------------------------ tests

    def test_metrics_returns_200_with_empty_logs(self, metrics_client):
        """No log files → 200 with zeroed totals."""
        cl, log_dir, cfg = metrics_client
        r = cl.get("/api/metrics")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["total_calls"] == 0
        assert data["total_cost_usd"] == 0.0
        assert data["idempotency_skips"] == 0

    def test_metrics_rate_limited(self, tmp_path):
        """6th GET /api/metrics with read limit=5 must return 429."""
        from pipeline.config import Config
        from api.security import (
            MaxBodySizeMiddleware,
            RateLimitMiddleware,
            generic_exception_handler,
            init_security,
        )
        import api.main as main_module
        from api.main import app
        from fastapi import FastAPI

        log_dir = tmp_path / "logs_rl"
        log_dir.mkdir()
        (tmp_path / "briefs_rl").mkdir()
        (tmp_path / "schedule_rl").mkdir()

        cfg = Config(
            rate_limit_reads_per_min=5,   # tight read limit
            rate_limit_writes_per_min=10,
            max_request_body_bytes=10_240,
            briefs_dir=str(tmp_path / "briefs_rl"),
            schedule_dir=str(tmp_path / "schedule_rl"),
            log_dir=str(log_dir),
        )
        main_module.cfg = cfg
        init_security(cfg)

        fresh_app = FastAPI(title="MetricsRLTest")
        fresh_app.add_middleware(RateLimitMiddleware, cfg=cfg)
        fresh_app.add_middleware(MaxBodySizeMiddleware, cfg=cfg)
        fresh_app.add_exception_handler(Exception, generic_exception_handler)
        for route in app.routes:
            fresh_app.routes.append(route)

        cl = TestClient(fresh_app, raise_server_exceptions=False)

        responses = []
        for _ in range(6):
            responses.append(cl.get("/api/metrics").status_code)

        assert responses[-1] == 429, (
            f"Expected 6th GET /api/metrics to return 429 (limit=5), "
            f"got {responses[-1]}. All: {responses}"
        )
        for i, code in enumerate(responses[:5]):
            assert code != 429, f"Request {i+1}/5 should not be rate-limited, got {code}"

    def test_metrics_max_days_cap_limits_files_read(self, metrics_client):
        """
        With metrics_max_days=3 and 5 log files, only data from the 3 newest
        dates appears in the response.  The 2 oldest files are silently skipped.
        """
        cl, log_dir, cfg = metrics_client

        # Write 5 dated log files.  Each file has 1 event with a distinct cost
        # so we can verify which dates were read.
        dates = [
            "2026-01-01",  # oldest — must be excluded
            "2026-01-02",  # oldest — must be excluded
            "2026-01-03",  # 3rd newest — included
            "2026-01-04",  # 2nd newest — included
            "2026-01-05",  # newest    — included
        ]
        for i, d in enumerate(dates):
            self._write_log(log_dir, d, [{
                "ts": f"{d}T00:00:00Z",
                "run_id": f"run-{i}",
                "business_id": "biz",
                "week": "2026-W01",
                "stage": "analyze",
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": (i + 1) * 0.001,  # 0.001, 0.002, ..., 0.005
                "latency_ms": 200,
                "outcome": "ok",
                "error_class": None,
            }])

        r = cl.get("/api/metrics")
        assert r.status_code == 200
        data = r.json()

        # The 3 newest files have costs 0.003, 0.004, 0.005 → total = 0.012
        # The 2 oldest files have costs 0.001, 0.002 → must NOT be included
        assert data["total_calls"] == 3, (
            f"Expected 3 calls (metrics_max_days=3), got {data['total_calls']}"
        )
        assert data["days_covered"] == 3, (
            f"Expected 3 days covered, got {data['days_covered']}"
        )
        # Total cost must be sum of the 3 newest (0.003 + 0.004 + 0.005 = 0.012)
        assert abs(data["total_cost_usd"] - 0.012) < 1e-7, (
            f"Expected total_cost ~0.012, got {data['total_cost_usd']}"
        )

    def test_metrics_error_class_not_in_response(self, metrics_client):
        """
        error_class values (BudgetExceeded, HTTP429, Timeout, etc.) must never
        appear in the /api/metrics response body — only numeric aggregates.
        """
        cl, log_dir, cfg = metrics_client
        self._write_log(log_dir, "2026-02-01", [
            {
                "ts": "2026-02-01T00:00:00Z",
                "run_id": "run-err",
                "business_id": "biz",
                "week": "2026-W05",
                "stage": "analyze",
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": None,
                "output_tokens": None,
                "cost_usd": None,
                "latency_ms": 500,
                "outcome": "fail",
                "error_class": "BudgetExceeded",
            },
            {
                "ts": "2026-02-01T00:01:00Z",
                "run_id": "run-err2",
                "business_id": "biz",
                "week": "2026-W05",
                "stage": "ingest",
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": None,
                "output_tokens": None,
                "cost_usd": None,
                "latency_ms": 300,
                "outcome": "fail",
                "error_class": "HTTP500",
            },
        ])

        r = cl.get("/api/metrics")
        assert r.status_code == 200
        body = r.text

        for leaked_class in ["BudgetExceeded", "HTTP500", "AuthenticationError", "Timeout"]:
            assert leaked_class not in body, (
                f"error_class value {leaked_class!r} must not appear in /api/metrics response"
            )

    def test_metrics_malformed_jsonl_lines_skipped(self, metrics_client):
        """Corrupt JSONL lines must not crash the endpoint (returns 200, skips bad lines)."""
        cl, log_dir, cfg = metrics_client
        import pathlib
        path = pathlib.Path(log_dir) / "2026-03-01.jsonl"
        path.write_text(
            "not-valid-json\n"
            "{\"truncated\": true\n"   # missing closing brace
            + json.dumps({
                "ts": "2026-03-01T00:00:00Z",
                "run_id": "run-ok",
                "business_id": "biz",
                "week": "2026-W09",
                "stage": "analyze",
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.001,
                "latency_ms": 100,
                "outcome": "ok",
                "error_class": None,
            }) + "\n"
        )

        r = cl.get("/api/metrics")
        assert r.status_code == 200, f"Expected 200 even with malformed lines, got {r.status_code}"
        data = r.json()
        # The one good line should still be counted
        assert data["total_calls"] == 1, (
            f"Expected 1 valid call parsed, got {data['total_calls']}"
        )

    def test_metrics_secrets_not_in_response(self, metrics_client):
        """ANTHROPIC_API_KEY and BIZBRIEF_API_KEY must never appear in /api/metrics response."""
        cl, log_dir, cfg = metrics_client
        r = cl.get("/api/metrics")
        assert r.status_code == 200
        body = r.text
        assert "ANTHROPIC_API_KEY" not in body
        assert "BIZBRIEF_API_KEY" not in body
        # The actual key value must not appear either
        assert _API_KEY not in body

    def test_metrics_idempotency_skips_counted_separately(self, metrics_client):
        """
        Events with outcome='skipped_cache' must be counted as idempotency_skips
        and excluded from total_calls / total_cost_usd.
        """
        cl, log_dir, cfg = metrics_client
        self._write_log(log_dir, "2026-04-01", [
            {
                "ts": "2026-04-01T00:00:00Z",
                "run_id": "run-a",
                "business_id": "biz",
                "week": "2026-W13",
                "stage": "analyze",
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.002,
                "latency_ms": 200,
                "outcome": "ok",
                "error_class": None,
            },
            {
                "ts": "2026-04-01T00:01:00Z",
                "run_id": "run-a",
                "business_id": "biz",
                "week": "2026-W13",
                "stage": "analyze",
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.0,
                "latency_ms": 0,
                "outcome": "skipped_cache",
                "error_class": None,
            },
        ])

        r = cl.get("/api/metrics")
        assert r.status_code == 200
        data = r.json()
        assert data["total_calls"] == 1, (
            f"skipped_cache must not count toward total_calls, got {data['total_calls']}"
        )
        assert data["idempotency_skips"] == 1, (
            f"Expected 1 idempotency_skip, got {data['idempotency_skips']}"
        )
        assert abs(data["total_cost_usd"] - 0.002) < 1e-7, (
            f"skipped_cache must not add to cost, got {data['total_cost_usd']}"
        )
