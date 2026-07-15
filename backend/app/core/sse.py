"""Shared transport policy for every Server-Sent Events response."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import TypeAlias

import anyio
from sse_starlette import EventSourceResponse, ServerSentEvent
from sse_starlette.event import ensure_bytes
from sse_starlette.sse import SendTimeoutError
from starlette.types import Send

from config.settings import settings

SSEFrame: TypeAlias = str | bytes | bytearray | memoryview


class SystemEventSourceResponse(EventSourceResponse):
    """EventSourceResponse variant that also bounds heartbeat socket writes."""

    async def _ping(self, send: Send) -> None:
        while self.active:
            await anyio.sleep(self._ping_interval)
            ping = (
                self.ping_message_factory()
                if self.ping_message_factory
                else ServerSentEvent(
                    comment=f"ping - {datetime.now(UTC)}",
                    sep=self.sep,
                )
            )
            ping_bytes = ensure_bytes(ping, self.sep)
            async with self._send_lock:
                if not self.active:
                    continue
                with anyio.move_on_after(self.send_timeout) as cancel_scope:
                    await send(
                        {
                            "type": "http.response.body",
                            "body": ping_bytes,
                            "more_body": True,
                        }
                    )
                if cancel_scope.cancel_called:
                    raise SendTimeoutError()


async def _encode_sse_frames(source: AsyncIterable[SSEFrame]) -> AsyncIterator[bytes]:
    """Encode legacy complete SSE frames without adding another ``data:`` layer."""

    async for frame in source:
        if isinstance(frame, str):
            yield frame.encode("utf-8")
            continue
        if isinstance(frame, (bytes, bytearray, memoryview)):
            yield bytes(frame)
            continue
        raise TypeError(
            "SSE source must yield str or bytes-like frames, "
            f"got {type(frame).__name__}"
        )


def _keepalive_comment() -> ServerSentEvent:
    return ServerSentEvent(comment="keepalive")


def create_sse_response(
    source: AsyncIterable[SSEFrame],
    *,
    heartbeat_interval_seconds: float | None = None,
    send_timeout_seconds: float | None = None,
    headers: Mapping[str, str] | None = None,
) -> EventSourceResponse:
    """Build an SSE response whose heartbeats stay outside business event streams."""

    response_headers = dict(headers or {})
    response_headers.update(
        {
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
    return SystemEventSourceResponse(
        _encode_sse_frames(source),
        ping=(
            settings.sse_heartbeat_interval_seconds
            if heartbeat_interval_seconds is None
            else heartbeat_interval_seconds
        ),
        ping_message_factory=_keepalive_comment,
        send_timeout=(
            settings.sse_send_timeout_seconds
            if send_timeout_seconds is None
            else send_timeout_seconds
        ),
        headers=response_headers,
    )
