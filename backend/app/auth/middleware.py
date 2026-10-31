"""Default-deny ASGI authentication at the application trust boundary."""

from __future__ import annotations

import hmac
import ipaddress
import re
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, unquote
from typing import Any

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .errors import AuthenticationRejected, AuthenticationUnavailable
from .share_access import (
    RESOURCE_PREVIEW_COOKIE,
    RESOURCE_PREVIEW_TICKET,
    RESOURCE_PREVIEW_TICKET_PATH_SEGMENT,
    SCHEDULED_RESULT_PREVIEW_KIND,
    resource_preview_identity,
)


_PUBLIC_EXACT_PATHS = {
    "/",
    "/health",
    "/ready",
    "/api/health",
    "/api/ready",
    "/api/auth/runtime-config",
    "/api/auth/operation-session",
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
    r"^/api/sessions/([^/]+)/resources/([^/]+)/content(?:/.*)?$"
)
_SCHEDULED_RESULT_CONTENT_PATTERN = re.compile(
    r"^/api/scheduled-tasks/results/([^/]+)/(?:files|report)(?:/.*)?$"
)
_SHARED_REPORT_PREVIEW_PATTERN = re.compile(
    r"^/api/shared-conversations/([^/]+)/reports/_t/([^/]+)(?:/(.+))?$"
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
        access_policy: Any | None = None,
    ) -> None:
        self.app = app
        self.settings = settings
        self.auth_service = auth_service
        self.share_access = share_access
        self.access_policy = access_policy
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

        if method in {"GET", "HEAD"} and self._valid_dashboard_access(scope, path):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if (path == "/api/shared-conversations" or path.startswith("/api/shared-conversations/")) and not headers.get("syscode"):
            # Shared snapshots are consumed by both Web sessions and signed App identities.
            from fastapi import HTTPException
            from app.social.app_identity import resolve_access_token

            scheme, separator, app_token = headers.get("authorization", "").partition(" ")
            if scheme.lower() == "bearer" and separator and app_token.strip():
                try:
                    user = resolve_access_token(app_token.strip()).as_current_user()
                except HTTPException as exc:
                    await self._error(scope, receive, send, exc.status_code, str(exc.detail))
                    return
                await self.app(self._authenticated_scope(scope, user), receive, send)
                return

        if not self._is_trusted_peer(scope):
            await self._error(scope, receive, send, 403, "untrusted_gateway_peer")
            return

        if self.settings.auth_mode == "mock":
            token = "local-mock"
            sys_code = self.settings.auth_sys_code
        elif self.settings.auth_mode == "operation":
            # Prefer the agent-issued session token (keeps an idle session
            # alive beyond the ops platform's own ticket lifetime); otherwise
            # fall back to the ops Forms cookie, which is re-resolved through
            # the ops platform itself.
            sys_code = self.settings.auth_sys_code
            user = self.auth_service.resolve_session_token(
                self._bearer_token(headers)
            )
            if user is not None:
                denial = self._operation_access_denial(user)
                if denial is not None:
                    await self._error(scope, receive, send, 403, denial)
                    return
                await self.app(
                    self._authenticated_scope(scope, user), receive, send
                )
                return
            token = self._operation_cookie(headers)
            if not token:
                await self._error(scope, receive, send, 401, "authentication_required")
                return
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

        denial = self._operation_access_denial(user)
        if denial is not None:
            await self._error(scope, receive, send, 403, denial)
            return

        await self.app(self._authenticated_scope(scope, user), receive, send)

    def _operation_access_denial(self, user: Any) -> str | None:
        """Deny ops-platform accounts the roster blocks (unit whitelist)."""
        if self.access_policy is None:
            return None
        if getattr(user, "auth_source", "") != "operation":
            return None
        allowed, _reason = self.access_policy.decide(user.username)
        if allowed:
            return None
        return "operation_account_blocked"

    @staticmethod
    def _bearer_token(headers: Headers) -> str:
        authorization = headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator:
            return ""
        return token.strip()

    def _operation_cookie(self, headers: Headers) -> str:
        cookie = SimpleCookie()
        try:
            cookie.load(headers.get("cookie", ""))
        except ValueError:
            return ""
        name = self.settings.auth_operation_cookie_name
        morsel = cookie.get(name)
        return morsel.value if morsel else ""

    @staticmethod
    def _authenticated_scope(scope: Scope, user: Any) -> Scope:
        clean_scope = dict(scope)
        clean_scope["headers"] = [
            (name, value)
            for name, value in scope.get("headers", [])
            if name.lower() not in _UNTRUSTED_IDENTITY_HEADERS
        ]
        state = dict(scope.get("state") or {})
        state["current_user"] = user
        clean_scope["state"] = state
        return clean_scope

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
        if self.share_access is None:
            return False
        # Directory previews carry the ticket as a path segment so relative
        # assets inherit it inside an opaque-origin sandboxed iframe.
        ticket = ""
        base_path = path
        marker = f"/content/{RESOURCE_PREVIEW_TICKET_PATH_SEGMENT}/"
        if marker in path:
            before, _, remainder = path.partition(marker)
            base_path = before + "/content"
            ticket = remainder.split("/", 1)[0]
        else:
            report_marker = f"/report/{RESOURCE_PREVIEW_TICKET_PATH_SEGMENT}/"
            if report_marker in path:
                before, _, remainder = path.partition(report_marker)
                base_path = before + "/report"
                ticket = remainder.split("/", 1)[0]
        match = _RESOURCE_CONTENT_PATTERN.fullmatch(base_path)
        if match is not None:
            session_id, resource_id = (unquote(value) for value in match.groups())
            return self._verify_preview_ticket(
                scope,
                ticket,
                "session-resource",
                resource_preview_identity(session_id, resource_id),
            )
        scheduled = _SCHEDULED_RESULT_CONTENT_PATTERN.fullmatch(base_path)
        if scheduled:
            return self._verify_preview_ticket(
                scope,
                ticket,
                SCHEDULED_RESULT_PREVIEW_KIND,
                unquote(scheduled.group(1)),
            )
        shared_report = _SHARED_REPORT_PREVIEW_PATTERN.fullmatch(path)
        if shared_report:
            # The ticket is inherent in the path; scope reports to one share.
            return self._verify_preview_ticket(
                scope,
                unquote(shared_report.group(2)),
                "shared-report",
                unquote(shared_report.group(1)),
            )
        return False

    def _valid_dashboard_access(self, scope: Scope, path: str) -> bool:
        """部署级直连令牌：静态凭证，仅放行配置前缀（dashboard_api_prefix）的 GET。

        令牌或前缀为空（默认）时整体禁用；启用前缀的路由层仍需复核
        同一令牌，中间件放行不会绕过鉴权语义。
        """
        configured = getattr(self.settings, "dashboard_access_token", "")
        prefix = getattr(self.settings, "dashboard_api_prefix", "")
        if not configured or not prefix or not path.startswith(prefix):
            return False
        query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
        supplied = (query.get("access_token") or [""])[0]
        return bool(supplied) and hmac.compare_digest(supplied, configured)

    def _verify_preview_ticket(
        self,
        scope: Scope,
        ticket: str,
        kind: str,
        resource_id: str,
    ) -> bool:
        if not ticket:
            query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
            ticket = (query.get(RESOURCE_PREVIEW_TICKET) or [""])[0]
        if not ticket:
            ticket = self._resource_preview_cookie(scope)
        return bool(
            ticket
            and self.share_access.verify(ticket, kind, resource_id)
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
