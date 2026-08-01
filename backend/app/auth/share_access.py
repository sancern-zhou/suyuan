"""Resource-scoped grants for anonymously opened signed shares."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from config.settings import settings


RESOURCE_PREVIEW_TICKET = "preview_ticket"
RESOURCE_PREVIEW_COOKIE = "suyuan-resource-preview"


def resource_preview_identity(session_id: str, resource_id: str) -> str:
    return f"{session_id}:{resource_id}"


def external_api_path(internal_path: str, gateway_prefix: str | None = None) -> str:
    """Map one leading /api segment to the configured external gateway prefix."""
    prefix = (gateway_prefix or settings.gateway_api_prefix).rstrip("/")
    if internal_path == "/api":
        return prefix
    if internal_path.startswith("/api/"):
        return f"{prefix}{internal_path[4:]}"
    return internal_path


class ShareAccessService:
    def __init__(self, secret: str, *, ttl_seconds: int) -> None:
        if not secret:
            raise ValueError("share grant secret is required")
        self._secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def issue(self, kind: str, resource_id: str, *, now: int | None = None) -> str:
        issued_at = int(time.time()) if now is None else int(now)
        payload = {"k": kind, "r": resource_id, "e": issued_at + self.ttl_seconds}
        encoded = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = _encode(hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest())
        return f"{encoded}.{signature}"

    def verify(
        self,
        grant: str,
        kind: str,
        resource_id: str,
        *,
        now: int | None = None,
    ) -> bool:
        try:
            encoded, supplied = grant.split(".", 1)
            expected = _encode(
                hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(expected, supplied):
                return False
            payload = json.loads(_decode(encoded))
            current = int(time.time()) if now is None else int(now)
            return (
                payload.get("k") == kind
                and payload.get("r") == resource_id
                and int(payload.get("e", 0)) >= current
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            return False


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


_service: ShareAccessService | None = None


def get_share_access_service() -> ShareAccessService:
    global _service
    if _service is None:
        secret = (
            settings.share_signing_secret
            or settings.minimax_api_key
            or "development-share-grant-secret"
        )
        _service = ShareAccessService(
            secret,
            ttl_seconds=settings.auth_share_grant_ttl_seconds,
        )
    return _service
