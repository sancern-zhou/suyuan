"""Log requests that are slow to produce their first response bytes."""

from __future__ import annotations

import time

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.get_logger()


class SlowRequestLoggingMiddleware:
    """Measure time-to-first-response-start and warn beyond a threshold.

    Streaming responses (SSE/WebSocket-style flows) are only judged by how
    long the initial response header takes, so long-lived streams stay quiet.
    """

    def __init__(self, app: ASGIApp, *, threshold_seconds: float = 2.0):
        self.app = app
        self.threshold_seconds = threshold_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        logged = False

        async def send_wrapper(message) -> None:
            nonlocal logged
            if message["type"] == "http.response.start" and not logged:
                elapsed = time.perf_counter() - started
                if elapsed >= self.threshold_seconds:
                    logged = True
                    logger.warning(
                        "slow_request_first_byte",
                        method=scope.get("method"),
                        path=scope.get("path"),
                        query_string=(scope.get("query_string") or b"").decode(
                            "latin-1"
                        ),
                        status=message.get("status"),
                        elapsed_ms=round(elapsed * 1000),
                        threshold_ms=round(self.threshold_seconds * 1000),
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)
