"""
Secret hydration for the Lambda handlers.

Production secret hygiene: the Anthropic API key is NOT stored as a plaintext
Lambda environment variable. Instead it lives in AWS Secrets Manager, and the
handlers fetch it once at cold start and place it in os.environ so the shared
``reliability.call_model`` code (which reads ``ANTHROPIC_API_KEY`` from the
environment) works unchanged — local app and cloud handlers stay identical.

Resolution order (first hit wins):
  1. ANTHROPIC_API_KEY already in the environment  → use it (local dev / tests;
     also the fast path on a warm Lambda after the first hydration).
  2. ANTHROPIC_SECRET_ARN / ANTHROPIC_SECRET_NAME set → fetch from Secrets
     Manager and cache into os.environ for the rest of the container's life.

The secret may be either a raw string (the key itself) or a JSON object with an
``ANTHROPIC_API_KEY`` field — both are handled.

boto3 is imported lazily so this module stays importable without the SDK.
"""

from __future__ import annotations

import json
import os

# Module-level guard so a warm Lambda hydrates at most once per container.
_hydrated = False


def ensure_anthropic_key() -> None:
    """Make ANTHROPIC_API_KEY available in os.environ, fetching from Secrets
    Manager if it isn't already set. Idempotent and cheap to call repeatedly."""
    global _hydrated

    if os.environ.get("ANTHROPIC_API_KEY"):
        return  # already present (local dev, tests, or warm container)
    if _hydrated:
        return  # we tried once this container; don't re-hit Secrets Manager

    secret_id = os.environ.get("ANTHROPIC_SECRET_ARN") or os.environ.get(
        "ANTHROPIC_SECRET_NAME"
    )
    if not secret_id:
        # No secret configured. Leave the env untouched; call_model will raise a
        # clear auth error if a model call is actually attempted.
        _hydrated = True
        return

    import boto3  # noqa: PLC0415 — lazy
    from botocore.config import Config  # noqa: PLC0415

    # Short timeouts and few retries: boto3's defaults (60s connect + 60s read,
    # retried) could eat the whole Lambda timeout and look like a hang.
    client = boto3.client(
        "secretsmanager",
        config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2}),
    )
    try:
        raw = client.get_secret_value(SecretId=secret_id).get("SecretString", "")
    except Exception as exc:  # noqa: BLE001 — re-raised with a clear message
        raise RuntimeError(
            f"Could not read the Anthropic API key from Secrets Manager "
            f"({secret_id}): {exc}"
        ) from exc

    key = raw
    # If the secret is a JSON blob, pull the ANTHROPIC_API_KEY field out of it.
    if raw.strip().startswith("{"):
        try:
            key = json.loads(raw).get("ANTHROPIC_API_KEY", "")
        except json.JSONDecodeError:
            key = ""

    if not key:
        raise RuntimeError(f"Secret {secret_id} holds no Anthropic API key")
    os.environ["ANTHROPIC_API_KEY"] = key
    _hydrated = True
