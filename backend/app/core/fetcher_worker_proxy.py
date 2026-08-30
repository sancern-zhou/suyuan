"""Proxy fetcher management requests from web workers to app.worker."""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


FETCHERS_PREFIX = "/api/fetchers"
PROXIED_FETCHER_SUBPATHS = ("status", "trigger/", "pause/", "resume/")


def should_proxy_fetchers_request(
    path: str,
    app_role: str | None,
    *,
    fetchers_enabled: bool = True,
) -> bool:
    """Return True when a web process should forward fetcher management requests."""
    if not fetchers_enabled:
        return False
    role = (app_role or "web").strip().lower()
    if role != "web":
        return False

    if not path.startswith(f"{FETCHERS_PREFIX}/"):
        return False

    subpath = path.removeprefix(f"{FETCHERS_PREFIX}/")
    return any(subpath == allowed or subpath.startswith(allowed) for allowed in PROXIED_FETCHER_SUBPATHS)


def build_worker_fetchers_url(base_url: str, path: str, query_string: str = "") -> str:
    """Build the worker URL while preserving the original path and query string."""
    url = f"{base_url.rstrip('/')}{path}"
    if query_string:
        url = f"{url}?{query_string}"
    return url


class FetcherWorkerProxyMiddleware:
    """Forward fetcher lifecycle requests from web workers to app.worker."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        app_role: str,
        worker_base_url: str,
        worker_token: str = "",
        timeout_seconds: float = 30.0,
        fetchers_enabled: bool = True,
    ):
        self.app = app
        self.app_role = app_role
        self.worker_base_url = worker_base_url
        self.worker_token = worker_token
        self.timeout_seconds = timeout_seconds
        self.fetchers_enabled = fetchers_enabled

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not should_proxy_fetchers_request(
            path,
            self.app_role,
            fetchers_enabled=self.fetchers_enabled,
        ):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        query_string = scope.get("query_string", b"").decode("latin-1")
        url = build_worker_fetchers_url(self.worker_base_url, path, query_string)
        body = await request.body()

        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower()
            not in {"host", "content-length", "x-suyuan-current-user"}
        }
        if self.worker_token:
            headers["x-social-worker-token"] = self.worker_token

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
                {"detail": f"Fetcher worker unavailable: {exc}"},
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
