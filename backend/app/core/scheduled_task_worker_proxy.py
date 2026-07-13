"""Proxy scheduled-task management requests from Web processes to app.worker."""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


SCHEDULED_TASKS_PREFIX = "/api/scheduled-tasks"


def should_proxy_scheduled_tasks_request(path: str, app_role: str | None) -> bool:
    """Return whether a Web process must forward this scheduled-task request."""
    role = (app_role or "web").strip().lower()
    return role == "web" and (
        path == SCHEDULED_TASKS_PREFIX
        or path.startswith(f"{SCHEDULED_TASKS_PREFIX}/")
    )


def build_worker_scheduled_tasks_url(
    base_url: str,
    path: str,
    query_string: str = "",
) -> str:
    url = f"{base_url.rstrip('/')}{path}"
    return f"{url}?{query_string}" if query_string else url


class ScheduledTaskWorkerProxyMiddleware:
    """Forward all scheduled-task CRUD and execution requests to app.worker."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        app_role: str,
        worker_base_url: str,
        worker_token: str = "",
        timeout_seconds: float = 1900.0,
    ):
        self.app = app
        self.app_role = app_role
        self.worker_base_url = worker_base_url
        self.worker_token = worker_token
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not should_proxy_scheduled_tasks_request(
            scope.get("path", ""),
            self.app_role,
        ):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = scope.get("path", "")
        query_string = scope.get("query_string", b"").decode("latin-1")
        url = build_worker_scheduled_tasks_url(
            self.worker_base_url,
            path,
            query_string,
        )
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in {"host", "content-length"}
        }
        if self.worker_token:
            headers["x-social-worker-token"] = self.worker_token

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                worker_response = await client.request(
                    method=request.method,
                    url=url,
                    content=await request.body(),
                    headers=headers,
                )
        except httpx.RequestError as exc:
            response = JSONResponse(
                {"detail": f"Scheduled task worker unavailable: {exc}"},
                status_code=503,
            )
            await response(scope, receive, send)
            return

        response_headers = {
            key: value
            for key, value in worker_response.headers.items()
            if key.lower()
            not in {"content-encoding", "transfer-encoding", "connection"}
        }
        response = Response(
            content=worker_response.content,
            status_code=worker_response.status_code,
            headers=response_headers,
            media_type=worker_response.headers.get("content-type"),
        )
        await response(scope, receive, send)
