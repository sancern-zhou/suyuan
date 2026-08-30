"""Default-deny ASGI authentication at the application trust boundary."""

from __future__ import annotations

import ipaddress
import re
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qs, unquote

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .errors import AuthenticationRejected, AuthenticationUnavailable
from .share_access import (
    RESOURCE_PREVIEW_COOKIE,
    RESOURCE_PREVIEW_TICKET,
    resource_preview_identity,
    split_resource_preview_path,
)

_PUBLIC_EXACT_PATHS = {
    "/",
    "/health",
    "/ready",
    "/api/health",
    "/api/ready",
    "/api/auth/runtime-config",
    "/index.html",
    "/favicon.ico",
    "/wechat-screenshot.png",
    "/suyuan-runtime-config.js",
    "/login",
    "/fetchers",
    "/knowledge-base",
    "/tools-management",
    "/skills-management",
    "/social-accounts",
    "/expert-deliberation",
}
_PUBLIC_STATIC_PREFIXES = ("/assets/", "/static/", "/dist/")
_APP_GATEWAY_PREFIXES = ("/api/social/app/",)
_PUBLIC_SHARE_PATTERNS = (re.compile(r"^/session/[^/]+$"),)
_DOCS_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
_UNTRUSTED_IDENTITY_HEADERS = {b"x-user-id", b"x-is-admin"}
_RESOURCE_CONTENT_PATTERN = re.compile(
    r"^/api/sessions/([^/]+)/resources/([^/]+)/content(?:/(.*))?$"
)


class GatewayAuthenticationMiddleware:
    """Require a gateway credential and expose only a server-resolved identity."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Any,
        auth_service: Any,
        share_access: Any | None = None,
    ) -> None:
        self.app = app
        self.settings = settings
        self.auth_service = auth_service
        self.share_access = share_access
        self._trusted_networks = tuple(
            ipaddress.ip_network(value, strict=False)
            for value in settings.trusted_gateway_networks_list
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        if method == "OPTIONS" or self._is_public(path):
            await self.app(scope, receive, send)
            return

        if method in {"GET", "HEAD"} and self._valid_resource_preview(scope, path):
            await self.app(scope, receive, send)
            return

        if not self._is_trusted_peer(scope):
            await self._error(scope, receive, send, 403, "untrusted_gateway_peer")
            return

        headers = Headers(scope=scope)
        if self.settings.auth_mode == "mock":
            token = "local-mock"
            sys_code = self.settings.auth_sys_code
        else:
            authorization = headers.get("authorization", "")
            scheme, separator, token = authorization.partition(" ")
            sys_code = headers.get("syscode", "")
            if scheme.lower() != "bearer" or not separator or not token.strip():
                await self._error(scope, receive, send, 401, "authentication_required")
                return
            token = token.strip()
            if sys_code != self.settings.auth_sys_code:
                await self._error(scope, receive, send, 401, "invalid_sys_code")
                return

        try:
            user = await self.auth_service.authenticate(token, sys_code)
        except AuthenticationRejected:
            await self._error(scope, receive, send, 401, "authentication_rejected")
            return
        except AuthenticationUnavailable:
            await self._error(scope, receive, send, 503, "authentication_unavailable")
            return

        clean_scope = dict(scope)
        clean_scope["headers"] = [
            (name, value)
            for name, value in scope.get("headers", [])
            if name.lower() not in _UNTRUSTED_IDENTITY_HEADERS
        ]
        state = dict(scope.get("state") or {})
        state["current_user"] = user
        clean_scope["state"] = state
        await self.app(clean_scope, receive, send)

    def _is_public(self, path: str) -> bool:
        if path in _PUBLIC_EXACT_PATHS:
            return True
        if path.startswith(_PUBLIC_STATIC_PREFIXES):
            return True
        # App Gateway performs its own HMAC token validation. It must be
        # reachable without the company gateway's syscode credential.
        if path.startswith(_APP_GATEWAY_PREFIXES):
            return True
        if self.settings.auth_docs_public and path in _DOCS_PATHS:
            return True
        return any(pattern.fullmatch(path) for pattern in _PUBLIC_SHARE_PATTERNS)

    def _is_trusted_peer(self, scope: Scope) -> bool:
        client = scope.get("client")
        if not client:
            return False
        try:
            address = ipaddress.ip_address(client[0])
        except ValueError:
            return False
        return any(address in network for network in self._trusted_networks)

    def _valid_resource_preview(self, scope: Scope, path: str) -> bool:
        match = _RESOURCE_CONTENT_PATTERN.fullmatch(path)
        if match is None or self.share_access is None:
            return False
        session_id, resource_id, asset_path = match.groups()
        path_ticket, _ = split_resource_preview_path(asset_path)
        query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
        ticket = path_ticket or (query.get(RESOURCE_PREVIEW_TICKET) or [""])[0]
        if not ticket:
            ticket = self._resource_preview_cookie(scope)
        session_id, resource_id = (
            unquote(value) for value in (session_id, resource_id)
        )
        return bool(
            ticket
            and self.share_access.verify(
                ticket,
                "session-resource",
                resource_preview_identity(session_id, resource_id),
            )
        )

    @staticmethod
    def _resource_preview_cookie(scope: Scope) -> str:
        cookie = SimpleCookie()
        try:
            cookie.load(Headers(scope=scope).get("cookie", ""))
        except ValueError:
            return ""
        morsel = cookie.get(RESOURCE_PREVIEW_COOKIE)
        return morsel.value if morsel else ""

    @staticmethod
    async def _error(
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        detail: str,
    ) -> None:
        response = JSONResponse({"detail": detail}, status_code=status_code)
        await response(scope, receive, send)
