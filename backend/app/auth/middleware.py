"""Default-deny ASGI authentication at the application trust boundary."""

from __future__ import annotations

import ipaddress
import re
from http.cookies import SimpleCookie
from typing import Any

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .errors import AuthenticationRejected, AuthenticationUnavailable
from .share_access import SHARE_GRANT_COOKIE


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
_PUBLIC_SHARE_PATTERNS = (
    re.compile(r"^/session/[^/]+$"),
    re.compile(r"^/api/reports/share/[^/]+$"),
    re.compile(r"^/api/html-artifacts/share/[^/]+$"),
)
_DOCS_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
_UNTRUSTED_IDENTITY_HEADERS = {b"x-user-id", b"x-is-admin"}
_SHARE_ASSET_PATTERNS = (
    (re.compile(r"^/api/reports/([^/]+)/(?:assets|report_files)/.+$"), "report"),
    (re.compile(r"^/api/html-artifacts/([^/]+)/assets/.+$"), "html-artifact"),
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
        if scope.get("method") == "OPTIONS" or self._is_public(path):
            await self.app(scope, receive, send)
            return

        share_resource = self._share_resource(path)
        if share_resource is not None and self.share_access is not None:
            grant = self._share_grant(scope)
            if grant:
                kind, resource_id = share_resource
                if self.share_access.verify(grant, kind, resource_id):
                    await self.app(scope, receive, send)
                    return
                await self._error(scope, receive, send, 403, "invalid_share_grant")
                return

        if self.settings.auth_mode == "company" and not self._is_trusted_peer(scope):
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

    @staticmethod
    def _share_resource(path: str) -> tuple[str, str] | None:
        for pattern, kind in _SHARE_ASSET_PATTERNS:
            match = pattern.fullmatch(path)
            if match:
                return kind, match.group(1)
        return None

    @staticmethod
    def _share_grant(scope: Scope) -> str:
        cookie = SimpleCookie()
        try:
            cookie.load(Headers(scope=scope).get("cookie", ""))
        except ValueError:
            return ""
        morsel = cookie.get(SHARE_GRANT_COOKIE)
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
