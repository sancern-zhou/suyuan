"""Short-lived, secret-safe cache for resolved identities."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

import structlog

from .models import CurrentUser


class IdentityCache:
    """Cache identities by a one-way token digest, never by the raw credential."""

    def __init__(
        self,
        redis: Any,
        *,
        key_prefix: str,
        max_ttl_seconds: int,
        logger: Any | None = None,
    ) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._max_ttl_seconds = max_ttl_seconds
        self._logger = logger or structlog.get_logger(__name__)

    def key_for_token(self, token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"{self._key_prefix}identity:{digest}"

    async def get(self, token: str) -> CurrentUser | None:
        key = self.key_for_token(token)
        try:
            value = await self._redis.get(key)
        except Exception as exc:  # Redis is an optimization, not the authority.
            self._logger.warning("identity_cache_read_failed", error_type=type(exc).__name__)
            return None
        if value is None:
            return None

        try:
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return CurrentUser.model_validate_json(value)
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            self._logger.warning(
                "identity_cache_entry_invalid", error_type=type(exc).__name__
            )
            try:
                await self._redis.delete(key)
            except Exception as delete_exc:
                self._logger.warning(
                    "identity_cache_delete_failed",
                    error_type=type(delete_exc).__name__,
                )
            return None

    async def set(self, token: str, user: CurrentUser) -> None:
        ttl = _cache_ttl(token, self._max_ttl_seconds)
        try:
            await self._redis.setex(
                self.key_for_token(token), ttl, user.model_dump_json()
            )
        except Exception as exc:  # A successful authority lookup remains valid.
            self._logger.warning("identity_cache_write_failed", error_type=type(exc).__name__)


def _cache_ttl(token: str, maximum: int) -> int:
    """Clamp cache life to an unverified JWT expiry when one can be decoded."""

    try:
        payload = token.split(".", 2)[1]
        padding = "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload + padding))
        remaining = int(claims["exp"]) - int(time.time())
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return maximum
    return max(1, min(maximum, remaining))
