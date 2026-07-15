"""Shared transport policy for every Server-Sent Events response."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from typing import TypeAlias


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
