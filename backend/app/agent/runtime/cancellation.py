"""Runtime cancellation registry for streaming agent runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from .ownership import run_ownership_registry

logger = structlog.get_logger()


class AgentRunCancelled(Exception):
    """Raised when a user cancels an in-flight agent run."""


class PauseCheckpointError(RuntimeError):
    """Raised when a paused run could not commit its durable transcript."""


@dataclass
class RunHandle:
    session_id: str
    cancel_event: asyncio.Event
    started_at: datetime
    streaming_executor: Optional[Any] = None
    run_task: Optional[asyncio.Task] = None
    run_id: Optional[str] = None
    pause_reason: Optional[str] = None
    task_armed: bool = False
    finished: asyncio.Event = field(default_factory=asyncio.Event)


class CancellationRegistry:
    def __init__(self) -> None:
        self._handles: Dict[str, RunHandle] = {}
        self._pause_errors: Dict[tuple[str, str], str] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str) -> asyncio.Event:
        while True:
            async with self._lock:
                previous = self._handles.get(session_id)
                if not previous:
                    cancel_event = asyncio.Event()
                    self._handles[session_id] = RunHandle(
                        session_id=session_id,
                        cancel_event=cancel_event,
                        started_at=datetime.now(),
                    )
                    logger.info("agent_run_registered", session_id=session_id)
                    return cancel_event
                previous_run_id = previous.run_id
                previous_finished = previous.finished

            # A new run for the same session must not overtake persistence of
            # the previous run's interrupted transcript.
            await self.cancel(
                session_id,
                expected_run_id=previous_run_id,
                reason="superseded_by_new_run",
            )
            await previous_finished.wait()
            if previous_run_id:
                await self.ensure_pause_succeeded(session_id, previous_run_id)

    async def attach_run_id(
        self,
        session_id: str,
        cancel_event: asyncio.Event,
        run_id: str,
    ) -> bool:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle or handle.cancel_event is not cancel_event:
                return False
            handle.run_id = run_id
            return True

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

    async def arm_run_task(self, session_id: str, cancel_event: asyncio.Event) -> None:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle or handle.cancel_event is not cancel_event:
                return
            handle.task_armed = True
            if handle.cancel_event.is_set() and handle.run_task and not handle.run_task.done():
                handle.run_task.cancel()

    async def cancel(
        self,
        session_id: str,
        *,
        expected_run_id: Optional[str] = None,
        reason: str = "user_paused",
    ) -> bool:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle:
                return False
            if expected_run_id is not None and handle.run_id != expected_run_id:
                logger.info(
                    "agent_run_cancel_ignored",
                    session_id=session_id,
                    expected_run_id=expected_run_id,
                    active_run_id=handle.run_id,
                )
                return False
            if handle.pause_reason != "user_paused" or reason == "user_paused":
                handle.pause_reason = reason
            run_id = handle.run_id

        await run_ownership_registry.begin_pause(session_id, run_id)
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle or (expected_run_id is not None and handle.run_id != expected_run_id):
                return False
            handle.cancel_event.set()
            if handle.streaming_executor:
                handle.streaming_executor.discard()
            if handle.task_armed and handle.run_task and not handle.run_task.done():
                handle.run_task.cancel()
        logger.info(
            "agent_run_cancelled",
            session_id=session_id,
            run_id=run_id,
            reason=reason,
        )
        return True

    async def pause_reason(
        self,
        session_id: str,
        cancel_event: asyncio.Event,
    ) -> Optional[str]:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle or handle.cancel_event is not cancel_event:
                return None
            return handle.pause_reason

    async def can_finalize(
        self,
        session_id: str,
        cancel_event: asyncio.Event,
    ) -> bool:
        async with self._lock:
            handle = self._handles.get(session_id)
            return bool(handle and handle.cancel_event is cancel_event)

    async def record_finalization_error(
        self,
        session_id: str,
        cancel_event: asyncio.Event,
        error: Exception,
    ) -> None:
        async with self._lock:
            handle = self._handles.get(session_id)
            if handle and handle.cancel_event is cancel_event and handle.run_id:
                self._pause_errors[(session_id, handle.run_id)] = str(error)

    async def ensure_pause_succeeded(self, session_id: str, run_id: str) -> None:
        async with self._lock:
            error = self._pause_errors.get((session_id, run_id))
        if error:
            raise PauseCheckpointError(error)

    async def unregister(self, session_id: str, cancel_event: asyncio.Event) -> None:
        run_id = None
        async with self._lock:
            handle = self._handles.get(session_id)
            if handle and handle.cancel_event is cancel_event:
                run_id = handle.run_id
                handle.finished.set()
                self._handles.pop(session_id, None)
                logger.info("agent_run_unregistered", session_id=session_id)
        if run_id is not None:
            await run_ownership_registry.revoke(session_id, run_id)

    async def is_cancelled(self, session_id: str) -> bool:
        async with self._lock:
            handle = self._handles.get(session_id)
            return bool(handle and handle.cancel_event.is_set())


cancellation_registry = CancellationRegistry()
