"""Tests for agent-issued session tokens used by operation-mode SSO."""

import asyncio
import time

import pytest

from app.auth.errors import AuthenticationRejected
from app.auth.identity_cache import IdentityCache
from app.auth.models import CurrentUser
from app.auth.service import AuthenticationService
from app.auth.session_tokens import issue_session_token, verify_session_token
from config.settings import Settings


SECRET = "test-session-secret"


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def setex(self, key, ttl, value):
        self.data[key] = value
        return True

    async def delete(self, key):
        self.data.pop(key, None)
        return 1


class FakePlatformClient:
    async def get_current_user(self, token, sys_code):
        raise AssertionError("platform client must not be used in operation tests")

    async def close(self):
        pass


class FakeOperationClient:
    def __init__(self, user):
        self.user = user
        self.calls = []

    async def get_current_user(self, cookie_value, sys_code):
        self.calls.append(cookie_value)
        if cookie_value == "good-cookie":
            return self.user
        raise AuthenticationRejected("operation authentication rejected")

    async def close(self):
        pass


def make_user():
    return CurrentUser(
        id="ops-tester",
        username="tester",
        display_name="tester",
        role_codes=("SUYUAN_USER",),
        is_admin=False,
        sys_code="SUYUAN",
        auth_source="operation",
    )


def make_service(operation_client=None) -> AuthenticationService:
    settings = Settings(
        auth_mode="operation",
        auth_sys_code="SUYUAN",
        auth_session_token_secret=SECRET,
        auth_session_token_ttl_seconds=3600,
        auth_service_url="",
    )
    return AuthenticationService(
        settings=settings,
        cache=IdentityCache(FakeRedis(), key_prefix="test:", max_ttl_seconds=60),
        platform_client=FakePlatformClient(),
        operation_client=operation_client,
    )


def test_token_roundtrip_keeps_identity():
    user = make_user()
    token, expires_in = issue_session_token(user, secret=SECRET, ttl_seconds=3600)
    assert expires_in == 3600
    restored = verify_session_token(token, secret=SECRET, sys_code="SUYUAN")
    assert restored == user


def test_expired_token_is_rejected():
    user = make_user()
    token, _ = issue_session_token(
        user, secret=SECRET, ttl_seconds=60, now=time.time() - 120
    )
    with pytest.raises(ValueError):
        verify_session_token(token, secret=SECRET, sys_code="SUYUAN")


def test_tampered_token_is_rejected():
    user = make_user()
    token, _ = issue_session_token(user, secret=SECRET, ttl_seconds=3600)
    encoded, _, signature = token.partition(".")
    with pytest.raises(ValueError):
        verify_session_token(
            f"{encoded}.{signature[:-1]}x", secret=SECRET, sys_code="SUYUAN"
        )
    with pytest.raises(ValueError):
        verify_session_token(token, secret="another-secret", sys_code="SUYUAN")


def test_sys_code_mismatch_is_rejected():
    user = make_user()
    token, _ = issue_session_token(user, secret=SECRET, ttl_seconds=3600)
    with pytest.raises(ValueError):
        verify_session_token(token, secret=SECRET, sys_code="OTHER")


def test_service_resolves_token_before_touching_operation_client():
    operation_client = FakeOperationClient(make_user())
    service = make_service(operation_client)
    token, _ = issue_session_token(
        make_user(), secret=SECRET, ttl_seconds=3600
    )

    resolved = service.resolve_session_token(token)
    assert resolved is not None
    assert resolved.username == "tester"

    asyncio.run(service.authenticate("good-cookie", "SUYUAN"))
    assert operation_client.calls == ["good-cookie"]


def test_service_token_resolution_disabled_without_secret():
    settings = Settings(
        auth_mode="operation",
        auth_sys_code="SUYUAN",
        auth_session_token_secret="",
        auth_service_url="",
    )
    service = AuthenticationService(
        settings=settings,
        cache=IdentityCache(FakeRedis(), key_prefix="test:", max_ttl_seconds=60),
        platform_client=FakePlatformClient(),
        operation_client=FakeOperationClient(make_user()),
    )
    token, _ = issue_session_token(make_user(), secret=SECRET, ttl_seconds=3600)
    assert service.resolve_session_token(token) is None
