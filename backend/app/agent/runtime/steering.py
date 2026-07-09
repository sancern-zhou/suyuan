"""Active-run steering queues for in-flight agent runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


STEERABLE_MODES = {"assistant", "social"}


@dataclass
class SteeringInput:
    content: str
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ActiveRun:
    session_id: str
    run_id: str
    mode: str
    queue: List[SteeringInput] = field(default_factory=list)


class SteeringRegistry:
    """In-process queue of user steering inputs keyed by active session."""

    def __init__(self) -> None:
        self._runs: Dict[str, ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, run_id: str, mode: str) -> bool:
        async with self._lock:
            steerable = mode in STEERABLE_MODES
            if steerable:
                self._runs[session_id] = ActiveRun(session_id=session_id, run_id=run_id, mode=mode)
            else:
                self._runs.pop(session_id, None)
            return steerable

    async def unregister(self, session_id: str, run_id: str) -> None:
        async with self._lock:
            active = self._runs.get(session_id)
            if active and active.run_id == run_id:
                self._runs.pop(session_id, None)

    async def add_input(
        self,
        session_id: str,
        content: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        text = (content or "").strip()
        clean_attachments = [dict(item) for item in attachments or [] if isinstance(item, dict)]
        if not text and not clean_attachments:
            return False
        async with self._lock:
            active = self._runs.get(session_id)
            if not active or active.mode not in STEERABLE_MODES:
                return False
            active.queue.append(SteeringInput(content=text, attachments=clean_attachments))
            return True

    async def drain(self, session_id: str, run_id: str) -> List[SteeringInput]:
        async with self._lock:
            active = self._runs.get(session_id)
            if not active or active.run_id != run_id:
                return []
            items = list(active.queue)
            active.queue.clear()
            return items

    async def is_active(self, session_id: str, mode: str | None = None) -> bool:
        async with self._lock:
            active = self._runs.get(session_id)
            if not active:
                return False
            return mode is None or active.mode == mode


steering_registry = SteeringRegistry()
