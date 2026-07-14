import base64
import json
import time

import pytest

from app.auth.dependencies import require_current_user
from app.auth.errors import AuthenticationRejected, AuthenticationUnavailable
from app.auth.identity_cache import IdentityCache
from app.auth.models import CurrentUser
from app.auth.service import AuthenticationService
from config.settings import Settings


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}
        self.fail_get = False
        self.fail_set = False
        self.deleted = []

    async def get(self, key):
        if self.fail_get:
            raise RuntimeError("redis unavailable")
        return self.data.get(key)

    async def setex(self, key, ttl, value):
        if self.fail_set:
            raise RuntimeError("redis unavailable")
        self.data[key] = value
        self.ttls[key] = ttl
        return True

    async def delete(self, key):
        self.deleted.append(key)
        self.data.pop(key, None)
        return 1

    def serialized_state(self):
        return [str(item) for pair in self.data.items() for item in pair]


class FakePlatformClient:
    def __init__(self, user=None, error=None):
        self.user = user or CurrentUser(
            id="user-1",
            username="zhangsan",
            display_name="张三",
        )
        self.error = error
        self.calls = []

    async def get_current_user(self, token, sys_code):
        self.calls.append((token, sys_code))
        if self.error:
            raise self.error
        return self.user

    async def close(self):
        return None


def _settings(**overrides):
    values = {
        "_env_file": None,
        "auth_mode": "company",
        "auth_mock_enabled": False,
        "auth_sys_code": "SUYUAN",
        "auth_identity_cache_ttl_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)


def _jwt_with_exp(exp):
    def encode(value):
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{encode({'alg': 'none'})}.{encode({'exp': exp})}.signature"


@pytest.mark.asyncio
async def test_cache_miss_resolves_company_user_and_never_stores_raw_token():
    redis = FakeRedis()
    platform = FakePlatformClient()
    service = AuthenticationService(
        settings=_settings(),
        cache=IdentityCache(redis, key_prefix="suyuan:auth:", max_ttl_seconds=60),
        platform_client=platform,
    )

    user = await service.authenticate("raw-company-token", "SUYUAN")

    assert user.id == "user-1"
    assert platform.calls == [("raw-company-token", "SUYUAN")]
    assert all("raw-company-token" not in item for item in redis.serialized_state())
    assert next(iter(redis.data)).startswith("suyuan:auth:identity:")


@pytest.mark.asyncio
async def test_cache_hit_skips_platform_lookup():
    redis = FakeRedis()
    cache = IdentityCache(redis, key_prefix="suyuan:auth:", max_ttl_seconds=60)
    expected = CurrentUser(id="cached", username="cached", display_name="Cached")
    await cache.set("token", expected)
    platform = FakePlatformClient(error=AssertionError("platform must not be called"))
    service = AuthenticationService(
        settings=_settings(), cache=cache, platform_client=platform
    )

    user = await service.authenticate("token", "SUYUAN")

    assert user == expected
    assert platform.calls == []


@pytest.mark.asyncio
async def test_corrupt_cache_entry_is_deleted_and_refetched():
    redis = FakeRedis()
    cache = IdentityCache(redis, key_prefix="suyuan:auth:", max_ttl_seconds=60)
    redis.data[cache.key_for_token("token")] = "not-json"
    platform = FakePlatformClient()
    service = AuthenticationService(
        settings=_settings(), cache=cache, platform_client=platform
    )

    user = await service.authenticate("token", "SUYUAN")

    assert user.id == "user-1"
    assert redis.deleted == [cache.key_for_token("token")]


@pytest.mark.asyncio
async def test_redis_failure_falls_back_to_platform_without_masking_user():
    redis = FakeRedis()
    redis.fail_get = True
    redis.fail_set = True
    platform = FakePlatformClient()
    service = AuthenticationService(
        settings=_settings(),
        cache=IdentityCache(redis, key_prefix="suyuan:auth:", max_ttl_seconds=60),
        platform_client=platform,
    )

    user = await service.authenticate("token", "SUYUAN")

    assert user.id == "user-1"
    assert platform.calls == [("token", "SUYUAN")]


@pytest.mark.asyncio
async def test_platform_unavailable_without_cache_is_fail_closed():
    service = AuthenticationService(
        settings=_settings(),
        cache=IdentityCache(FakeRedis(), key_prefix="suyuan:auth:", max_ttl_seconds=60),
        platform_client=FakePlatformClient(
            error=AuthenticationUnavailable("company authentication unavailable")
        ),
    )

    with pytest.raises(AuthenticationUnavailable):
        await service.authenticate("token", "SUYUAN")


@pytest.mark.asyncio
async def test_wrong_sys_code_is_rejected_before_cache_or_platform():
    platform = FakePlatformClient()
    service = AuthenticationService(
        settings=_settings(),
        cache=IdentityCache(FakeRedis(), key_prefix="suyuan:auth:", max_ttl_seconds=60),
        platform_client=platform,
    )

    with pytest.raises(AuthenticationRejected, match="invalid SysCode"):
        await service.authenticate("token", "OTHER")
    assert platform.calls == []


@pytest.mark.asyncio
async def test_mock_mode_returns_fixed_non_production_identity():
    service = AuthenticationService(
        settings=_settings(
            auth_mode="mock",
            auth_mock_enabled=True,
            auth_mock_user_id="developer",
            auth_mock_username="dev",
            auth_mock_display_name="开发用户",
            auth_mock_role_codes="SUYUAN_ADMIN,viewer",
            auth_admin_role_codes="SUYUAN_ADMIN",
        ),
        cache=IdentityCache(FakeRedis(), key_prefix="suyuan:auth:", max_ttl_seconds=60),
        platform_client=FakePlatformClient(error=AssertionError("must not call platform")),
    )

    user = await service.authenticate("ignored", "SUYUAN")

    assert user.id == "developer"
    assert user.auth_source == "mock"
    assert user.role_codes == ("SUYUAN_ADMIN", "viewer")
    assert user.is_admin is True


@pytest.mark.asyncio
async def test_jwt_exp_clamps_cache_ttl():
    redis = FakeRedis()
    cache = IdentityCache(redis, key_prefix="suyuan:auth:", max_ttl_seconds=60)
    token = _jwt_with_exp(int(time.time()) + 10)

    await cache.set(token, CurrentUser(id="u1", username="u", display_name="U"))

    assert 1 <= next(iter(redis.ttls.values())) <= 10


def test_dependency_requires_request_state_user():
    class State:
        pass

    class Request:
        state = State()

    with pytest.raises(Exception) as raised:
        require_current_user(Request())
    assert raised.value.status_code == 401

    Request.state.current_user = CurrentUser(id="u1", username="u", display_name="U")
    assert require_current_user(Request()).id == "u1"
