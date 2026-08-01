"""Run ownership guard for session-scoped agent writes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, Dict, Optional, TypeVar


T = TypeVar("T")


@dataclass
class RunOwnership:
    session_id: str
    run_id: str
    status: str
    updated_at: str


class RunOwnershipRegistry:
    """Tracks which run currently owns write permission for a session."""

    def __init__(self) -> None:
        self._runs: Dict[str, RunOwnership] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    async def register(self, session_id: str, run_id: str) -> None:
        async with self._lock_for(session_id):
            self._runs[session_id] = RunOwnership(
                session_id=session_id,
                run_id=run_id,
                status="running",
                updated_at=datetime.now().isoformat(),
            )

    async def revoke(self, session_id: str, run_id: Optional[str] = None) -> bool:
        async with self._lock_for(session_id):
            current = self._runs.get(session_id)
            if not current:
                return False
            if run_id is not None and current.run_id != run_id:
                return False
            current.status = "interrupted"
            current.updated_at = datetime.now().isoformat()
            self._runs.pop(session_id, None)
            return True

    async def complete(self, session_id: str, run_id: str) -> bool:
        async with self._lock_for(session_id):
            current = self._runs.get(session_id)
            if not current or current.run_id != run_id:
                return False
            current.status = "completed"
            current.updated_at = datetime.now().isoformat()
            self._runs.pop(session_id, None)
            return True

    async def can_write(self, session_id: str, run_id: Optional[str]) -> bool:
        if not session_id or not run_id:
            return True
        async with self._lock_for(session_id):
            current = self._runs.get(session_id)
            return bool(current and current.run_id == run_id and current.status == "running")

    async def current_run_id(self, session_id: str) -> Optional[str]:
        async with self._lock_for(session_id):
            current = self._runs.get(session_id)
            return current.run_id if current and current.status == "running" else None

    async def execute_if_owner(
        self,
        session_id: str,
        run_id: Optional[str],
        operation: Callable[[], Awaitable[T]],
    ) -> tuple[bool, T | None]:
        """Hold the session ownership boundary through the durable commit."""
        if not session_id or not run_id:
            return True, await operation()
        async with self._lock_for(session_id):
            current = self._runs.get(session_id)
            if not current or current.run_id != run_id or current.status != "running":
                return False, None
            return True, await operation()


run_ownership_registry = RunOwnershipRegistry()
