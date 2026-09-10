"""Proxy manual Jiangsu smart-event AI dispatches to the background worker."""

from __future__ import annotations

import httpx
import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.auth.internal_identity import INTERNAL_USER_HEADER, encode_internal_user
from app.auth.models import CurrentUser

logger = structlog.get_logger()


SMART_EVENT_DISPATCH_PREFIX = "/api/jiangsu/smart-events/"
SMART_EVENT_PROXY_SUFFIXES = ("/ai-dispatch", "/feedback")
SMART_EVENT_INTERNAL_PREFIX = "/internal/jiangsu/smart-events/"


def _match_proxy_path(path: str) -> str | None:
    """Return the event id when the path is a proxied smart-event action."""
    if not path.startswith(SMART_EVENT_DISPATCH_PREFIX):
        return None
    for suffix in SMART_EVENT_PROXY_SUFFIXES:
        if path.endswith(suffix):
            event_id = path[len(SMART_EVENT_DISPATCH_PREFIX) : -len(suffix)]
            event_id = event_id.strip("/")
            if event_id and "/" not in event_id:
                return event_id
    return None


def should_proxy_jiangsu_smart_event_dispatch(path: str, method: str, app_role: str | None) -> bool:
    """Return whether a Web process should forward one manual AI dispatch."""
    role = (app_role or "web").strip().lower()
    if role != "web" or method.upper() != "POST":
        return False
    return _match_proxy_path(path) is not None


def build_worker_jiangsu_smart_event_dispatch_url(
    base_url: str,
    path: str,
    query_string: str = "",
) -> str:
    """Build the worker-only URL while preserving the event id and query."""
    event_id = _match_proxy_path(path) or ""
    for suffix in SMART_EVENT_PROXY_SUFFIXES:
        if path.endswith(suffix):
            internal_path = f"{SMART_EVENT_INTERNAL_PREFIX}{event_id}{suffix}"
            break
    else:  # pragma: no cover - guarded by should_proxy
        internal_path = f"{SMART_EVENT_INTERNAL_PREFIX}{event_id}/ai-dispatch"
    url = f"{base_url.rstrip('/')}{internal_path}"
    return f"{url}?{query_string}" if query_string else url


class JiangsuSmartEventWorkerProxyMiddleware:
    """Forward manual smart-event AI dispatches from Web to app.worker."""

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
        if scope["type"] != "http" or not should_proxy_jiangsu_smart_event_dispatch(
            scope.get("path", ""), scope.get("method", "GET"), self.app_role
        ):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        query_string = scope.get("query_string", b"").decode("latin-1")
        url = build_worker_jiangsu_smart_event_dispatch_url(
            self.worker_base_url,
            scope.get("path", ""),
            query_string,
        )
        logger.info(
            "jiangsu_smart_event_dispatch_proxy_started",
            path=scope.get("path", ""),
            worker_url=url,
        )
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
                    content=await request.body(),
                    headers=headers,
                )
        except httpx.RequestError as exc:
            logger.error(
                "jiangsu_smart_event_dispatch_proxy_failed",
                error=str(exc),
                worker_url=url,
            )
            response = JSONResponse(
                {"detail": f"Smart-event worker unavailable: {exc}"},
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
        logger.info(
            "jiangsu_smart_event_dispatch_proxy_completed",
            path=scope.get("path", ""),
            status_code=worker_response.status_code,
        )
        await response(scope, receive, send)
