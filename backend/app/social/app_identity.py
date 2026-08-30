"""Signed Android App identities and account provisioning contract."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import secrets
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
    auth_source: str = "app"
    username: str | None = None
    sys_code: str = "SUYUAN_APP"
    role_codes: tuple[str, ...] = ()

    def as_current_user(self) -> CurrentUser:
        return CurrentUser(
            id=self.social_user_id,
            username=self.username or self.account_id,
            display_name=self.display_name,
            role_codes=self.role_codes,
            sys_code=self.sys_code,
            auth_source="company" if self.auth_source == "company" else "app",
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
    identity = AppIdentity(
        account_id,
        str(account.get("name") or account_id),
        f"app:android:{account_id}",
        int(time.time()) + settings.app_access_token_ttl_seconds,
        auth_source="app",
        username=account_id,
    )
    return issue_access_token_for_identity(identity), identity


def _sign(payload: dict[str, Any]) -> str:
    encoded = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    signature = _b64(hmac.new(settings.app_auth_secret.encode(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def issue_access_token_for_identity(identity: AppIdentity) -> str:
    expires_at = int(time.time()) + settings.app_access_token_ttl_seconds
    return _sign({
        "sub": identity.account_id,
        "name": identity.display_name,
        "username": identity.username or identity.account_id,
        "social_user_id": identity.social_user_id,
        "sys_code": identity.sys_code,
        "source": identity.auth_source,
        "exp": expires_at,
        "iat": int(time.time()),
        "typ": "access",
    })


def issue_token_pair(identity: AppIdentity) -> tuple[str, str, int, int]:
    now = int(time.time())
    access_expires_at = now + settings.app_access_token_ttl_seconds
    refresh_expires_at = now + settings.app_refresh_token_ttl_seconds
    access = _sign({
        "sub": identity.account_id,
        "name": identity.display_name,
        "username": identity.username or identity.account_id,
        "social_user_id": identity.social_user_id,
        "sys_code": identity.sys_code,
        "source": identity.auth_source,
        "exp": access_expires_at,
        "iat": now,
        "typ": "access",
    })
    refresh = _sign({
        "sub": identity.account_id,
        "name": identity.display_name,
        "username": identity.username or identity.account_id,
        "social_user_id": identity.social_user_id,
        "sys_code": identity.sys_code,
        "source": identity.auth_source,
        "exp": refresh_expires_at,
        "iat": now,
        "jti": secrets.token_urlsafe(18),
        "typ": "refresh",
    })
    return access, refresh, access_expires_at, refresh_expires_at


def resolve_refresh_token(token: str) -> AppIdentity:
    payload = _verify_signed_token(token, expected_type="refresh")
    source = str(payload.get("source") or "app")
    account_id = str(payload.get("sub") or "").strip()
    if not account_id:
        raise HTTPException(status_code=401, detail="invalid_refresh_token")
    if source != "company":
        try:
            account = _accounts().get(account_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="app_auth_not_configured") from exc
        if not account or str(account.get("status", "active")).lower() != "active":
            raise HTTPException(status_code=403, detail="app_account_disabled")
    return AppIdentity(
        account_id=account_id,
        display_name=str(payload.get("name") or account_id),
        social_user_id=str(payload.get("social_user_id") or f"app:android:{account_id}"),
        expires_at=int(payload["exp"]),
        auth_source=source,
        username=str(payload.get("username") or account_id),
        sys_code=str(payload.get("sys_code") or ("SUYUAN_APP" if source != "company" else settings.auth_sys_code)),
    )


def _verify_signed_token(token: str, *, expected_type: str) -> dict[str, Any]:
    if not settings.app_auth_secret:
        raise HTTPException(status_code=503, detail="app_auth_not_configured")
    try:
        encoded, signature = token.strip().split(".", 1)
        expected = _b64(hmac.new(settings.app_auth_secret.encode(), encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(_unb64(encoded))
        token_type = payload.get("typ")
        # Keep already-issued pre-refresh App access tokens usable during the
        # rollout. Refresh tokens must always carry the explicit type marker.
        if (expected_type == "access" and token_type not in (None, "access")) or (
            expected_type == "refresh" and token_type != "refresh"
        ):
            raise ValueError("token_type")
        expires_at = int(payload["exp"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail=f"invalid_{expected_type}_token") from exc
    if expires_at <= int(time.time()):
        raise HTTPException(
            status_code=401,
            detail="app_token_expired" if expected_type == "access" else "refresh_token_expired",
        )
    return payload


def resolve_access_token(token: str) -> AppIdentity:
    payload = _verify_signed_token(token, expected_type="access")
    account_id = str(payload["sub"])
    expires_at = int(payload["exp"])
    source = str(payload.get("source") or "app")
    if source == "company":
        return AppIdentity(
            account_id=account_id,
            display_name=str(payload.get("name") or account_id),
            social_user_id=str(payload.get("social_user_id") or f"company:{account_id}"),
            expires_at=expires_at,
            auth_source="company",
            username=str(payload.get("username") or account_id),
            sys_code=str(payload.get("sys_code") or settings.auth_sys_code),
        )
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
        social_user_id=str(payload.get("social_user_id") or f"app:android:{account_id}"),
        expires_at=expires_at,
        auth_source="app",
        username=str(payload.get("username") or account_id),
    )


async def require_app_identity(authorization: str | None = Header(default=None)) -> AppIdentity:
    scheme, separator, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise HTTPException(status_code=401, detail="app_authentication_required")
    return resolve_access_token(token)
