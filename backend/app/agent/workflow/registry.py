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

    def __init__(self) -> None:
        self._items: Dict[str, ActiveWorkflow] = {}
        self._lock = asyncio.Lock()

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

    async def unregister(self, workflow_id: str, coordinator: Any | None = None) -> None:
        async with self._lock:
            current = self._items.get(workflow_id)
            if current is None:
                return
            if coordinator is not None and current.coordinator is not coordinator:
                return
            self._items.pop(workflow_id, None)

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
        if item is None:
            return False
        await item.coordinator.cancel(reason=reason)
        return True


active_workflow_registry = ActiveWorkflowRegistry()
