"""Single-use, purpose-bound WebSocket authentication tickets."""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from .errors import AuthenticationUnavailable
from .models import CurrentUser


class InvalidWebSocketTicket(RuntimeError):
    """A ticket is missing, expired, corrupt, reused, or purpose-mismatched."""


class WebSocketTicketService:
    def __init__(self, redis: Any, *, key_prefix: str, ttl_seconds: int) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds

    def key_for_ticket(self, ticket: str) -> str:
        digest = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
        return f"{self._key_prefix}ws-ticket:{digest}"

    async def issue(self, user: CurrentUser, *, purpose: str) -> str:
        ticket = secrets.token_urlsafe(32)
        value = json.dumps(
            {"purpose": purpose, "user": user.model_dump(mode="json")},
            separators=(",", ":"),
            ensure_ascii=False,
        )
        try:
            await self._redis.setex(
                self.key_for_ticket(ticket), self.ttl_seconds, value
            )
        except Exception as exc:
            raise AuthenticationUnavailable("ticket service unavailable") from exc
        return ticket

    async def consume(self, ticket: str, *, purpose: str) -> CurrentUser:
        if not ticket:
            raise InvalidWebSocketTicket("invalid ticket")
        try:
            value = await self._redis.getdel(self.key_for_ticket(ticket))
        except Exception as exc:
            raise InvalidWebSocketTicket("invalid ticket") from exc
        if value is None:
            raise InvalidWebSocketTicket("invalid ticket")
        try:
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            payload = json.loads(value)
            if payload.get("purpose") != purpose:
                raise InvalidWebSocketTicket("invalid ticket")
            return CurrentUser.model_validate(payload["user"])
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
            raise InvalidWebSocketTicket("invalid ticket") from exc
