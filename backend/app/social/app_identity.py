"""Signed Android App identities and account provisioning contract."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Header, HTTPException

from app.auth.models import CurrentUser
from config.settings import settings


@dataclass(frozen=True)
class AppIdentity:
    account_id: str
    display_name: str
    social_user_id: str
    expires_at: int

    def as_current_user(self) -> CurrentUser:
        return CurrentUser(
            id=self.social_user_id,
            username=self.account_id,
            display_name=self.display_name,
            sys_code="SUYUAN_APP",
            auth_source="app",
        )


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _accounts() -> dict[str, dict[str, Any]]:
    try:
        parsed = json.loads(settings.app_accounts_json or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("APP_ACCOUNTS_JSON is invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("APP_ACCOUNTS_JSON must be an object")
    return {str(key): value for key, value in parsed.items() if isinstance(value, dict)}


def issue_access_token(account_id: str, account_secret: str) -> tuple[str, AppIdentity]:
    account_id = account_id.strip()
    if not account_id or not settings.app_auth_secret:
        raise HTTPException(status_code=503, detail="app_auth_not_configured")
    try:
        account = _accounts().get(account_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="app_auth_not_configured") from exc
    if not account or not hmac.compare_digest(str(account.get("secret", "")), account_secret):
        raise HTTPException(status_code=401, detail="invalid_app_credentials")
    if str(account.get("status", "active")).lower() != "active":
        raise HTTPException(status_code=403, detail="app_account_disabled")
    expires_at = int(time.time()) + settings.app_access_token_ttl_seconds
    payload = {
        "sub": account_id,
        "name": str(account.get("name") or account_id),
        "exp": expires_at,
        "iat": int(time.time()),
    }
    encoded = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    signature = _b64(hmac.new(settings.app_auth_secret.encode(), encoded.encode(), hashlib.sha256).digest())
    identity = AppIdentity(account_id, payload["name"], f"app:android:{account_id}", expires_at)
    return f"{encoded}.{signature}", identity


def resolve_access_token(token: str) -> AppIdentity:
    if not settings.app_auth_secret:
        raise HTTPException(status_code=503, detail="app_auth_not_configured")
    try:
        encoded, signature = token.strip().split(".", 1)
        expected = _b64(hmac.new(settings.app_auth_secret.encode(), encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(_unb64(encoded))
        account_id = str(payload["sub"])
        expires_at = int(payload["exp"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="invalid_app_token") from exc
    if expires_at <= int(time.time()):
        raise HTTPException(status_code=401, detail="app_token_expired")
    try:
        account = _accounts().get(account_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="app_auth_not_configured") from exc
    if not account or str(account.get("status", "active")).lower() != "active":
        raise HTTPException(status_code=403, detail="app_account_disabled")
    return AppIdentity(
        account_id=account_id,
        display_name=str(account.get("name") or payload.get("name") or account_id),
        social_user_id=f"app:android:{account_id}",
        expires_at=expires_at,
    )


async def require_app_identity(authorization: str | None = Header(default=None)) -> AppIdentity:
    scheme, separator, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise HTTPException(status_code=401, detail="app_authentication_required")
    return resolve_access_token(token)
