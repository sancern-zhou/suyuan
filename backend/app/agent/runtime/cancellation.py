"""Runtime cancellation registry for streaming agent runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()


class AgentRunCancelled(Exception):
    """Raised when a user cancels an in-flight agent run."""


@dataclass
class RunHandle:
    session_id: str
    cancel_event: asyncio.Event
    started_at: datetime
    streaming_executor: Optional[Any] = None
    run_task: Optional[asyncio.Task] = None


class CancellationRegistry:
    def __init__(self) -> None:
        self._handles: Dict[str, RunHandle] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str) -> asyncio.Event:
        async with self._lock:
            previous = self._handles.get(session_id)
            if previous:
                previous.cancel_event.set()
                if previous.streaming_executor:
                    previous.streaming_executor.discard()
                if previous.run_task and not previous.run_task.done():
                    previous.run_task.cancel()

            cancel_event = asyncio.Event()
            self._handles[session_id] = RunHandle(
                session_id=session_id,
                cancel_event=cancel_event,
                started_at=datetime.now(),
            )
            logger.info("agent_run_registered", session_id=session_id)
            return cancel_event

    async def attach_streaming_executor(self, session_id: str, executor: Any) -> None:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle:
                return
            handle.streaming_executor = executor
            if handle.cancel_event.is_set():
                executor.discard()

    async def attach_run_task(self, session_id: str, task: asyncio.Task) -> None:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle:
                return
            handle.run_task = task
            if handle.cancel_event.is_set() and not task.done():
                task.cancel()

    async def cancel(self, session_id: str) -> bool:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle:
                return False
            handle.cancel_event.set()
            if handle.streaming_executor:
                handle.streaming_executor.discard()
            if handle.run_task and not handle.run_task.done():
                handle.run_task.cancel()
            logger.info("agent_run_cancelled", session_id=session_id)
            return True

    async def unregister(self, session_id: str, cancel_event: asyncio.Event) -> None:
        async with self._lock:
            handle = self._handles.get(session_id)
            if handle and handle.cancel_event is cancel_event:
                self._handles.pop(session_id, None)
                logger.info("agent_run_unregistered", session_id=session_id)

    async def is_cancelled(self, session_id: str) -> bool:
        async with self._lock:
            handle = self._handles.get(session_id)
            return bool(handle and handle.cancel_event.is_set())


cancellation_registry = CancellationRegistry()
