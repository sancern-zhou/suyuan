"""In-process projection for background sub-agent tasks.

The durable source remains ``WorkflowRuntime`` in the session snapshot.  This
registry only holds the live asyncio task and a compact status projection.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackgroundTaskRegistry:
    def __init__(self) -> None:
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._events: list[Dict[str, Any]] = []

    def launch(self, task_id: str, task: "asyncio.Task[Any]", *, metadata: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "task_id": task_id,
            "task": task,
            "status": "running",
            "created_at": _now(),
            "updated_at": _now(),
            **metadata,
        }
        self._tasks[task_id] = record
        self._record_event("background_task_started", record)

        def complete(done: "asyncio.Task[Any]") -> None:
            record["updated_at"] = _now()
            if done.cancelled():
                record["status"] = "cancelled"
                self._record_event("background_task_cancelled", record)
                return
            error = done.exception()
            if error is not None:
                record["status"] = "failed"
                record["error"] = str(error)
                self._record_event("background_task_failed", record)
                return
            result = done.result()
            record["status"] = result.get("status", "completed") if isinstance(result, dict) else "completed"
            if isinstance(result, dict):
                record["result_summary"] = result.get("summary") or result.get("result", "")[:1000]
                record["workflow_run_id"] = (result.get("metadata") or {}).get("workflow_run_id")
            self._record_event("background_task_completed", record)

        task.add_done_callback(complete)
        return self.public_record(record)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        record = self._tasks.get(task_id)
        return self.public_record(record) if record else None

    def cancel(self, task_id: str) -> Optional[Dict[str, Any]]:
        record = self._tasks.get(task_id)
        task = record.get("task") if record else None
        if task is not None and not task.done():
            task.cancel()
            record["status"] = "cancelled"
            record["updated_at"] = _now()
            self._record_event("background_task_cancelled", record)
        return self.public_record(record) if record else None

    def events(self, *, task_id: Optional[str] = None) -> list[Dict[str, Any]]:
        events = self._events if task_id is None else [event for event in self._events if event["task_id"] == task_id]
        return [dict(event) for event in events]

    def _record_event(self, event_type: str, record: Dict[str, Any]) -> None:
        self._events.append({
            "event_type": event_type,
            "task_id": record["task_id"],
            "status": record.get("status"),
            "timestamp": _now(),
        })

    @staticmethod
    def public_record(record: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in record.items() if key != "task"}


background_task_registry = BackgroundTaskRegistry()
