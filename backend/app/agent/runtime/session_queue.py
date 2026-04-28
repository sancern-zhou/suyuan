"""Per-session in-process serialization for agent runs."""

from __future__ import annotations

import asyncio
from collections import defaultdict


class SessionRunQueue:
    _locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def lock(self, session_id: str) -> asyncio.Lock:
        return self._locks[session_id]
