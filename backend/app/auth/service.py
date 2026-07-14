"""Resolve normalized users from company credentials or explicit local mock mode."""

from __future__ import annotations

from typing import Any

from config.settings import Settings

from .errors import AuthenticationRejected
from .identity_cache import IdentityCache
from .models import CurrentUser


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
            roles = tuple(
                role.strip()
                for role in self._settings.auth_mock_role_codes.split(",")
                if role.strip()
            )
            return CurrentUser(
                id=self._settings.auth_mock_user_id,
                username=self._settings.auth_mock_username,
                display_name=self._settings.auth_mock_display_name,
                role_codes=roles,
                is_admin=bool(
                    set(roles).intersection(self._settings.auth_admin_role_codes_set)
                ),
                sys_code=sys_code,
                auth_source="mock",
            )

        cached = await self._cache.get(token)
        if cached is not None:
            return cached
        user = await self._platform_client.get_current_user(token, sys_code)
        await self._cache.set(token, user)
        return user

    async def close(self) -> None:
        await self._platform_client.close()
