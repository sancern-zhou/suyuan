import json

import pytest

from app.auth.models import CurrentUser
from app.auth.ws_tickets import InvalidWebSocketTicket, WebSocketTicketService


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}

    async def setex(self, key, ttl, value):
        self.data[key] = value
        self.ttls[key] = ttl

    async def getdel(self, key):
        return self.data.pop(key, None)


@pytest.mark.asyncio
async def test_ticket_is_high_entropy_digest_only_and_bound_to_user_and_purpose():
    redis = FakeRedis()
    service = WebSocketTicketService(
        redis, key_prefix="suyuan:auth:", ttl_seconds=30
    )
    user = CurrentUser(id="u1", username="u", display_name="U")

    ticket = await service.issue(user, purpose="scheduled-tasks")

    assert len(ticket) >= 40
    assert all(ticket not in str(item) for item in (*redis.data.keys(), *redis.data.values()))
    assert next(iter(redis.ttls.values())) == 30
    stored = json.loads(next(iter(redis.data.values())))
    assert stored["user"]["id"] == "u1"
    assert stored["purpose"] == "scheduled-tasks"


@pytest.mark.asyncio
async def test_ticket_is_atomically_single_use():
    service = WebSocketTicketService(
        FakeRedis(), key_prefix="suyuan:auth:", ttl_seconds=30
    )
    user = CurrentUser(id="u1", username="u", display_name="U")
    ticket = await service.issue(user, purpose="scheduled-tasks")

    resolved = await service.consume(ticket, purpose="scheduled-tasks")

    assert resolved.id == "u1"
    with pytest.raises(InvalidWebSocketTicket):
        await service.consume(ticket, purpose="scheduled-tasks")


@pytest.mark.asyncio
async def test_ticket_cannot_be_used_for_another_purpose():
    service = WebSocketTicketService(
        FakeRedis(), key_prefix="suyuan:auth:", ttl_seconds=30
    )
    ticket = await service.issue(
        CurrentUser(id="u1", username="u", display_name="U"),
        purpose="scheduled-tasks",
    )

    with pytest.raises(InvalidWebSocketTicket):
        await service.consume(ticket, purpose="other")


@pytest.mark.asyncio
async def test_missing_and_corrupt_tickets_are_rejected():
    redis = FakeRedis()
    service = WebSocketTicketService(
        redis, key_prefix="suyuan:auth:", ttl_seconds=30
    )
    with pytest.raises(InvalidWebSocketTicket):
        await service.consume("missing", purpose="scheduled-tasks")

    key = service.key_for_ticket("corrupt")
    redis.data[key] = "not-json"
    with pytest.raises(InvalidWebSocketTicket):
        await service.consume("corrupt", purpose="scheduled-tasks")
