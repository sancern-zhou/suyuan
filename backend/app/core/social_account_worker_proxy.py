"""Proxy social account management requests from web workers to app.worker."""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.auth.internal_identity import INTERNAL_USER_HEADER, encode_internal_user
from app.auth.models import CurrentUser


SOCIAL_ACCOUNTS_PREFIX = "/api/social/accounts"


def should_proxy_social_accounts_request(path: str, app_role: str | None) -> bool:
    """Return True when a web process should forward social account requests."""
    role = (app_role or "web").strip().lower()
    return role == "web" and (
        path == SOCIAL_ACCOUNTS_PREFIX or path.startswith(f"{SOCIAL_ACCOUNTS_PREFIX}/")
    )


def build_worker_social_accounts_url(base_url: str, path: str, query_string: str = "") -> str:
    """Build the worker URL while preserving the original path and query string."""
    url = f"{base_url.rstrip('/')}{path}"
    if query_string:
        url = f"{url}?{query_string}"
    return url


class SocialAccountWorkerProxyMiddleware:
    """Forward social account lifecycle requests from web workers to app.worker."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        app_role: str,
        worker_base_url: str,
        worker_token: str = "",
        timeout_seconds: float = 30.0,
    ):
        self.app = app
        self.app_role = app_role
        self.worker_base_url = worker_base_url
        self.worker_token = worker_token
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not should_proxy_social_accounts_request(path, self.app_role):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        query_string = scope.get("query_string", b"").decode("latin-1")
        url = build_worker_social_accounts_url(self.worker_base_url, path, query_string)
        body = await request.body()

        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in {"host", "content-length", INTERNAL_USER_HEADER}
        }
        if self.worker_token:
            headers["x-social-worker-token"] = self.worker_token
        current_user = (scope.get("state") or {}).get("current_user")
        if isinstance(current_user, CurrentUser):
            headers[INTERNAL_USER_HEADER] = encode_internal_user(
                current_user,
                secret=self.worker_token,
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                worker_response = await client.request(
                    method=request.method,
                    url=url,
                    content=body,
                    headers=headers,
                )
        except httpx.RequestError as exc:
            response = JSONResponse(
                {"detail": f"Social worker unavailable: {exc}"},
                status_code=503,
            )
            await response(scope, receive, send)
            return

        response_headers = {
            key: value
            for key, value in worker_response.headers.items()
            if key.lower() not in {"content-encoding", "transfer-encoding", "connection"}
        }
        response = Response(
            content=worker_response.content,
            status_code=worker_response.status_code,
            headers=response_headers,
            media_type=worker_response.headers.get("content-type"),
        )
        await response(scope, receive, send)
