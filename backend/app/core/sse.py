"""Shared transport policy for every Server-Sent Events response."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Mapping
from typing import TypeAlias

from sse_starlette import EventSourceResponse, ServerSentEvent

from config.settings import settings

SSEFrame: TypeAlias = str | bytes | bytearray | memoryview


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
    return EventSourceResponse(
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
