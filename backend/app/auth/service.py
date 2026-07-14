"""Resolve normalized users from company credentials or explicit local mock mode."""

from __future__ import annotations

from typing import Any

from config.settings import Settings

from .errors import AuthenticationRejected
from .identity_cache import IdentityCache
from .models import CurrentUser


MOCK_ADMIN_ROLE_CODE = "SUYUAN_ADMIN"


def build_mock_user(settings: Settings, sys_code: str | None = None) -> CurrentUser:
    roles = [
        role.strip()
        for role in settings.auth_mock_role_codes.split(",")
        if role.strip()
    ]
    if MOCK_ADMIN_ROLE_CODE not in roles:
        roles.insert(0, MOCK_ADMIN_ROLE_CODE)
    return CurrentUser(
        id=settings.auth_mock_user_id,
        username=settings.auth_mock_username,
        display_name=settings.auth_mock_display_name,
        role_codes=tuple(roles),
        is_admin=True,
        sys_code=sys_code or settings.auth_sys_code,
        auth_source="mock",
    )


class AuthenticationService:
    def __init__(
        self,
        *,
        settings: Settings,
        cache: IdentityCache,
        platform_client: Any,
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._platform_client = platform_client

    async def authenticate(self, token: str, sys_code: str) -> CurrentUser:
        if sys_code != self._settings.auth_sys_code:
            raise AuthenticationRejected("invalid SysCode")

        if self._settings.auth_mode == "mock":
            if not self._settings.auth_mock_enabled:
                raise AuthenticationRejected("mock authentication is disabled")
            return build_mock_user(self._settings, sys_code)

        cached = await self._cache.get(token)
        if cached is not None:
            return cached
        user = await self._platform_client.get_current_user(token, sys_code)
        await self._cache.set(token, user)
        return user

    async def close(self) -> None:
        await self._platform_client.close()
