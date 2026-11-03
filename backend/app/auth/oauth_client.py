"""Client for the unified auth platform's OAuth2.0 authorization-code endpoints.

契约见《基于OAuth2.0协议接入平台页面》v1.2：
- GET {base}/auth/oauth/token?client_id&client_secret&grantType=authorization_code
  &code&redirectUri -> {state, msg, success, result: {accessToken, refreshToken, ...}}
- grantType=refresh_token + refreshToken 用于静默续期。
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from .errors import AuthenticationRejected, AuthenticationUnavailable


_SUCCESS_STATES = {0, 200}


class PlatformOAuthClient:
    """Exchange authorization codes for platform access tokens (server-side only)."""

    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str,
        token_path: str = "/auth/oauth/token",
        authorize_path: str = "/auth/oauth/directAuthorize",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        logger: Any | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._url = f"{self._base_url}/{token_path.lstrip('/')}"
        self._authorize_path = authorize_path
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = httpx.AsyncClient(timeout=timeout_seconds, transport=transport)
        self._logger = logger or structlog.get_logger(__name__)

    @property
    def configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    async def authorize_code(self, *, client_id: str, user_mark: str, secret_name: str,
                             redirect_uri: str, scope: str = "all") -> str:
        """调用 directAuthorize 取一次性授权码（不跟随重定向，从 Location 提取）。"""
        from urllib.parse import parse_qs, urlparse

        try:
            response = await self._client.get(
                f"{self._base_url}/{self._authorize_path.lstrip('/')}",
                params={
                    "clientId": client_id,
                    "userMark": user_mark,
                    "secretName": secret_name,
                    "responseType": "code",
                    "redirectUri": redirect_uri,
                    "scope": scope,
                },
            )
        except httpx.HTTPError as exc:
            self._logger.warning(
                "oauth_authorize_unavailable", error_type=type(exc).__name__
            )
            raise AuthenticationUnavailable("oauth authorize unavailable") from exc
        if response.status_code >= 500:
            raise AuthenticationUnavailable("oauth authorize unavailable")
        location = response.headers.get("location", "")
        if response.status_code != 302 or "code=" not in location:
            detail = ""
            try:
                detail = str(response.json().get("msg") or "")
            except ValueError:
                pass
            self._logger.info("oauth_authorize_rejected", detail=detail[:120])
            raise AuthenticationRejected(detail or "oauth authorize rejected")
        query = parse_qs(urlparse(location).query)
        code = (query.get("code") or [""])[0]
        if not code:
            raise AuthenticationRejected("oauth authorize returned no code")
        return code

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        return await self._token_request(
            {
                "grantType": "authorization_code",
                "code": code,
                "redirectUri": redirect_uri,
            }
        )

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        return await self._token_request(
            {
                "grantType": "refresh_token",
                "refreshToken": refresh_token,
            }
        )

    async def _token_request(self, extra_params: dict[str, str]) -> dict[str, Any]:
        try:
            response = await self._client.get(
                self._url,
                params={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    **extra_params,
                },
            )
        except httpx.HTTPError as exc:
            self._logger.warning(
                "oauth_token_request_unavailable",
                error_type=type(exc).__name__,
            )
            raise AuthenticationUnavailable(
                "oauth token endpoint unavailable"
            ) from exc

        if response.status_code >= 500:
            self._logger.warning(
                "oauth_token_request_unavailable",
                status_code=response.status_code,
            )
            raise AuthenticationUnavailable("oauth token endpoint unavailable")

        try:
            body = response.json()
        except ValueError as exc:
            raise AuthenticationUnavailable(
                "oauth token endpoint returned non-JSON"
            ) from exc
        if not isinstance(body, dict):
            raise AuthenticationRejected("oauth token exchange rejected")

        state = body.get("state")
        if body.get("success") is False or (
            isinstance(state, int) and state not in _SUCCESS_STATES
        ):
            self._logger.info(
                "oauth_token_exchange_rejected",
                msg=str(body.get("msg") or ""),
            )
            raise AuthenticationRejected(str(body.get("msg") or "oauth token exchange rejected"))

        result = body.get("result")
        if not isinstance(result, dict) or not str(result.get("accessToken") or "").strip():
            raise AuthenticationRejected("oauth token exchange returned no access token")
        return result

    async def close(self) -> None:
        await self._client.aclose()
