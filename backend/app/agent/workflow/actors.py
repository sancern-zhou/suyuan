"""Per-actor FIFO serialization for shared Agent runtimes."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Tuple


class AgentActorRegistry:
    """Serialize turns targeting the same logical child runtime.

    Locks are scoped to the current event loop because web workers may host
    independent loops.  Different actor keys remain fully concurrent.
    """

    def __init__(self) -> None:
        self._locks: Dict[Tuple[int, str], asyncio.Lock] = {}

    @asynccontextmanager
    async def lease(self, actor_key: str) -> AsyncIterator[None]:
        loop = asyncio.get_running_loop()
        key = (id(loop), str(actor_key))
        lock = self._locks.setdefault(key, asyncio.Lock())
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
            if not lock.locked():
                self._locks.pop(key, None)

    def active_actor_count(self) -> int:
        return sum(1 for lock in self._locks.values() if lock.locked())


child_actor_registry = AgentActorRegistry()
