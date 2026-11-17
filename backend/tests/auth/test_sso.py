import pytest

from app.auth.sso import (
    SsoSessionStore,
    SsoTicketError,
    SsoTicketService,
    build_sso_user,
)


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def setex(self, key, ttl, value):
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)


def _service(**kwargs):
    return SsoTicketService("sso-secret", ttl_seconds=60, **kwargs)


def test_ticket_round_trip_and_one_time_claims():
    ticket = _service().issue({"u": "u1", "n": "zhangsan", "r": ["viewer"]})

    claims = _service().verify(ticket)

    assert claims["u"] == "u1"
    assert claims["n"] == "zhangsan"
    assert claims["r"] == ["viewer"]
    assert claims["j"]


def test_ticket_rejects_tampering_and_expiry():
    ticket = _service().issue({"u": "u1"}, now=1000)
    encoded, signature = ticket.split(".", 1)

    with pytest.raises(SsoTicketError):
        _service().verify(f"{encoded}x.{signature}", now=1000)
    with pytest.raises(SsoTicketError):
        _service().verify(ticket, now=1000 + 61)


def test_ticket_requires_an_identity_claim():
    with pytest.raises(SsoTicketError):
        _service().verify(_service().issue({"n": "no-id"}))


@pytest.mark.asyncio
async def test_ticket_id_is_consumed_only_once():
    store = SsoSessionStore(FakeRedis(), key_prefix="test:", ttl_seconds=60)

    assert await store.consume_ticket("jti-1") is True
    assert await store.consume_ticket("jti-1") is False


@pytest.mark.asyncio
async def test_session_token_is_stored_by_digest_and_resolves_the_user():
    store = SsoSessionStore(FakeRedis(), key_prefix="test:", ttl_seconds=60)
    user = build_sso_user(
        {"u": "u1", "n": "zhangsan"},
        default_roles={"viewer"},
        admin_role_codes=set(),
        sys_code="SUYUAN",
    )

    token = await store.issue(user)

    assert token not in store._redis.values
    resolved = await store.get(token)
    assert resolved is not None
    assert resolved.id == "u1"
    assert resolved.role_codes == ("viewer",)
    assert resolved.is_admin is False


def test_build_sso_user_maps_admin_roles_and_keeps_display_name():
    user = build_sso_user(
        {"u": "u2", "n": "lisi", "d": "李四", "r": ["NOISE_ADMIN"]},
        default_roles={"viewer"},
        admin_role_codes={"NOISE_ADMIN"},
        sys_code="SUYUAN",
    )

    assert user.display_name == "李四"
    assert user.is_admin is True


def test_build_sso_user_falls_back_to_default_roles():
    user = build_sso_user(
        {"u": "u3"},
        default_roles={"viewer", "analyst"},
        admin_role_codes=set(),
        sys_code="SUYUAN",
    )

    assert user.username == "u3"
    assert user.display_name == "u3"
    assert user.role_codes == ("analyst", "viewer")
