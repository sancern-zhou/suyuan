"""Process-local registry for active Agent workflow coordinators.

The registry is deliberately small: durable state remains in the workflow
snapshot, while this module only holds live cancellation handles.  A future
worker/Redis adapter can implement the same interface without changing the
coordinator or API contract.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ActiveWorkflow:
    workflow_id: str
    session_id: Optional[str]
    coordinator: Any


class ActiveWorkflowRegistry:
    """Track live coordinators for inspection and cooperative cancellation."""

    def __init__(self, *, store: Any = None, poll_interval: float = 0.1) -> None:
        self._items: Dict[str, ActiveWorkflow] = {}
        self._lock = asyncio.Lock()
        self._store = store
        self._poll_interval = max(0.02, float(poll_interval))
        self._monitors: Dict[str, asyncio.Task] = {}

    async def register(self, workflow_id: str, coordinator: Any, *, session_id: Optional[str] = None) -> None:
        workflow_id = str(workflow_id).strip()
        if not workflow_id:
            raise ValueError("workflow_id is required")
        async with self._lock:
            current = self._items.get(workflow_id)
            if current is not None and current.coordinator is not coordinator:
                raise ValueError(f"workflow is already active: {workflow_id}")
            self._items[workflow_id] = ActiveWorkflow(
                workflow_id=workflow_id,
                session_id=session_id,
                coordinator=coordinator,
            )
            if self._store is not None:
                try:
                    accepted = await self._store.register(self._state_key(workflow_id), workflow_id)
                except Exception:
                    # Redis availability must not prevent an in-process run.
                    accepted = True
                if not accepted:
                    self._items.pop(workflow_id, None)
                    raise ValueError(f"workflow is already active remotely: {workflow_id}")
                self._monitors[workflow_id] = asyncio.create_task(
                    self._monitor_cancel(workflow_id, coordinator)
                )

    async def unregister(self, workflow_id: str, coordinator: Any | None = None) -> None:
        async with self._lock:
            current = self._items.get(workflow_id)
            if current is None:
                return
            if coordinator is not None and current.coordinator is not coordinator:
                return
            self._items.pop(workflow_id, None)
            monitor = self._monitors.pop(workflow_id, None)
            if monitor is not None and monitor is not asyncio.current_task():
                monitor.cancel()
            if self._store is not None:
                try:
                    await self._store.finish(self._state_key(workflow_id), workflow_id)
                except Exception:
                    pass

    async def get(self, workflow_id: str) -> Optional[ActiveWorkflow]:
        async with self._lock:
            return self._items.get(workflow_id)

    async def list(self, *, session_id: Optional[str] = None) -> list[ActiveWorkflow]:
        async with self._lock:
            values = list(self._items.values())
        if session_id is None:
            return values
        return [item for item in values if item.session_id == session_id]

    async def cancel(self, workflow_id: str, *, reason: str = "cancelled by API") -> bool:
        item = await self.get(workflow_id)
        remote_requested = False
        if self._store is not None:
            try:
                remote_requested = await self._store.request_cancel(
                    self._state_key(workflow_id), workflow_id, reason
                )
            except Exception:
                remote_requested = False
        if item is not None:
            await item.coordinator.cancel(reason=reason)
            return True
        return remote_requested

    async def _monitor_cancel(self, workflow_id: str, coordinator: Any) -> None:
        while True:
            try:
                state = await self._store.get(self._state_key(workflow_id))
                if (
                    state
                    and state.run_id == workflow_id
                    and state.status == "pause_requested"
                ):
                    await coordinator.cancel(reason=state.reason or "cancelled by API")
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                # The local coordinator remains authoritative if Redis is
                # temporarily unavailable; the next API request can retry.
                pass
            await asyncio.sleep(self._poll_interval)

    @staticmethod
    def _state_key(workflow_id: str) -> str:
        return f"agent-workflow:{workflow_id}"


def _production_store() -> Any:
    try:
        # Reuse the already configured Redis cancellation store so deployment
        # settings, credentials and TTL behavior remain consistent.
        from app.agent.runtime.cancellation import cancellation_registry

        return cancellation_registry._store
    except Exception:
        return None


active_workflow_registry = ActiveWorkflowRegistry(store=_production_store())
