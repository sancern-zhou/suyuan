"""Agent-issued session tokens that outlive the ops-platform login ticket.

The ops platform keeps its Forms cookie short-lived (session cookie, internal
idle policy). Once a cookie has been validated, the agent issues its own
signed token so an idle user is not forced through the ops login page again
until the token expires.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time

from pydantic import ValidationError

from .models import CurrentUser


_MAX_TOKEN_LENGTH = 16384


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(encoded: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def issue_session_token(
    user: CurrentUser,
    *,
    secret: str,
    ttl_seconds: int,
    now: float | None = None,
) -> tuple[str, int]:
    issued_at = int(now if now is not None else time.time())
    expires_in = max(1, int(ttl_seconds))
    payload = {
        "user": user.model_dump(mode="json"),
        "exp": issued_at + expires_in,
    }
    encoded = _b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    return f"{encoded}.{_sign(encoded, secret)}", expires_in


def verify_session_token(
    raw: str,
    *,
    secret: str,
    sys_code: str,
    now: float | None = None,
) -> CurrentUser:
    if not raw or len(raw) > _MAX_TOKEN_LENGTH or not secret:
        raise ValueError("invalid_session_token")
    encoded, separator, supplied = raw.partition(".")
    if not separator or not hmac.compare_digest(_sign(encoded, secret), supplied):
        raise ValueError("invalid_session_token")
    try:
        payload = json.loads(_b64decode(encoded))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid_session_token") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_session_token")
    expires_at = payload.get("exp")
    current = int(now if now is not None else time.time())
    if not isinstance(expires_at, int) or expires_at <= current:
        raise ValueError("session_token_expired")
    try:
        user = CurrentUser.model_validate(payload.get("user"))
    except ValidationError as exc:
        raise ValueError("invalid_session_token") from exc
    if user.sys_code != sys_code:
        raise ValueError("invalid_session_token")
    return user
