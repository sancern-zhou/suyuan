"""Domain-neutral runtime primitives for cooperating Agents.

The runtime deliberately knows nothing about reports, experts, or coding
tasks.  It owns the lifecycle and lineage of a task; mode adapters provide the
prompt, tools, and result schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional
import uuid


TASK_STATUSES = (
    "queued",
    "running",
    "waiting",
    "repairing",
    "succeeded",
    "failed",
    "cancelled",
)
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}

_ALLOWED_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"waiting", "repairing", "succeeded", "failed", "cancelled"},
    "waiting": {"running", "repairing", "failed", "cancelled"},
    "repairing": {"running", "succeeded", "failed", "cancelled"},
    "succeeded": set(),
    "failed": {"queued", "cancelled"},
    "cancelled": set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WorkflowEvent:
    """An append-only event in a workflow run's journal."""

    event_id: str
    sequence: int
    event_type: str
    run_id: str
    task_id: str
    parent_task_id: Optional[str]
    status: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "status": self.status,
            "payload": dict(self.payload),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkflowEvent":
        return cls(
            event_id=str(value.get("event_id") or uuid.uuid4().hex),
            sequence=int(value.get("sequence") or 0),
            event_type=str(value.get("event_type") or "unknown"),
            run_id=str(value.get("run_id") or ""),
            task_id=str(value.get("task_id") or ""),
            parent_task_id=value.get("parent_task_id"),
            status=str(value.get("status") or "queued"),
            payload=dict(value.get("payload") or {}),
            timestamp=str(value.get("timestamp") or utc_now()),
        )


@dataclass
class WorkflowRun:
    """Serializable state reconstructed from the event journal."""

    run_id: str
    task_id: str
    parent_task_id: Optional[str] = None
    status: str = "queued"
    attempt: int = 0
    max_attempts: int = 1
    cancel_requested: bool = False
    cancel_reason: Optional[str] = None
    child_task_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    deadline_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "status": self.status,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "cancel_requested": self.cancel_requested,
            "cancel_reason": self.cancel_reason,
            "child_task_ids": list(self.child_task_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deadline_at": self.deadline_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkflowRun":
        return cls(
            run_id=str(value.get("run_id") or ""),
            task_id=str(value.get("task_id") or ""),
            parent_task_id=value.get("parent_task_id"),
            status=str(value.get("status") or "queued"),
            attempt=max(0, int(value.get("attempt") or 0)),
            max_attempts=max(1, int(value.get("max_attempts") or 1)),
            cancel_requested=bool(value.get("cancel_requested")),
            cancel_reason=value.get("cancel_reason"),
            child_task_ids=[str(item) for item in value.get("child_task_ids") or []],
            created_at=str(value.get("created_at") or utc_now()),
            updated_at=str(value.get("updated_at") or utc_now()),
            deadline_at=value.get("deadline_at"),
        )


class WorkflowRuntime:
    """Small deterministic workflow runtime with optional snapshot persistence.

    Persistence is injected so API sessions, database records, or a future
    Redis-backed journal can use the same runtime.  The snapshot contains both
    the current run state and append-only events, which makes recovery and
    inspection deterministic without coupling this package to storage.
    """

    def __init__(
        self,
        *,
        snapshot: Optional[Mapping[str, Any]] = None,
        persist: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self._persist = persist
        self._runs: Dict[str, WorkflowRun] = {}
        self._events: List[WorkflowEvent] = []
        snapshot = snapshot or {}
        for run_id, value in (snapshot.get("runs") or {}).items():
            if isinstance(value, Mapping):
                run = WorkflowRun.from_dict(value)
                run.run_id = run_id or run.run_id
                self._runs[run.run_id] = run
        self._events = [
            WorkflowEvent.from_dict(value)
            for value in snapshot.get("events") or []
            if isinstance(value, Mapping)
        ]
        self._events.sort(key=lambda event: event.sequence)

    def create_run(
        self,
        *,
        task_id: str,
        parent_task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        max_attempts: int = 1,
        deadline_at: Optional[str] = None,
    ) -> WorkflowRun:
        if not task_id or not str(task_id).strip():
            raise ValueError("task_id is required")
        run_id = run_id or uuid.uuid4().hex
        if run_id in self._runs:
            return self._runs[run_id]
        run = WorkflowRun(
            run_id=run_id,
            task_id=str(task_id),
            parent_task_id=parent_task_id,
            max_attempts=max(1, int(max_attempts)),
            deadline_at=deadline_at,
        )
        self._runs[run_id] = run
        self._record("task.created", run, {"max_attempts": run.max_attempts})
        self._flush()
        return run

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        return self._runs.get(run_id)

    def find_run(self, *, task_id: str) -> Optional[WorkflowRun]:
        """Return the latest run for a task, useful during snapshot recovery."""
        matches = [run for run in self._runs.values() if run.task_id == task_id]
        return matches[-1] if matches else None

    def transition(self, run_id: str, status: str, *, payload: Optional[Mapping[str, Any]] = None) -> WorkflowRun:
        if status not in TASK_STATUSES:
            raise ValueError(f"unknown workflow status: {status}")
        run = self._require_run(run_id)
        if status != run.status and status not in _ALLOWED_TRANSITIONS.get(run.status, set()):
            raise ValueError(f"invalid workflow transition: {run.status} -> {status}")
        run.status = status
        run.updated_at = utc_now()
        self._record(f"task.{status}", run, payload or {})
        self._flush()
        return run

    def start(self, run_id: str) -> WorkflowRun:
        run = self._require_run(run_id)
        if run.status == "queued":
            run.attempt += 1
            return self.transition(run_id, "running", payload={"attempt": run.attempt})
        if run.status == "failed" and run.attempt < run.max_attempts:
            self.retry(run_id, reason="resume failed workflow run")
            return self.start(run_id)
        if run.status in {"waiting", "repairing"}:
            return self.transition(run_id, "running", payload={"attempt": run.attempt})
        return run

    def begin_repair(self, run_id: str, *, errors: Iterable[Mapping[str, Any]]) -> WorkflowRun:
        return self.transition(run_id, "repairing", payload={"validation_errors": [dict(item) for item in errors]})

    def retry(self, run_id: str, *, reason: str = "") -> WorkflowRun:
        run = self._require_run(run_id)
        if run.status != "failed":
            raise ValueError(f"only failed runs can retry: {run.status}")
        if run.attempt >= run.max_attempts:
            raise ValueError("workflow retry budget exhausted")
        return self.transition(run_id, "queued", payload={"reason": reason, "next_attempt": run.attempt + 1})

    def register_child(self, parent_run_id: str, child_task_id: str) -> WorkflowRun:
        parent = self._require_run(parent_run_id)
        if child_task_id not in parent.child_task_ids:
            parent.child_task_ids.append(child_task_id)
            parent.updated_at = utc_now()
            self._record("task.child_registered", parent, {"child_task_id": child_task_id})
            self._flush()
        return parent

    def request_cancel(self, run_id: str, *, reason: str = "") -> WorkflowRun:
        return self._request_cancel(run_id, reason=reason, visited=set())

    def _request_cancel(self, run_id: str, *, reason: str, visited: set[str]) -> WorkflowRun:
        if run_id in visited:
            return self._require_run(run_id)
        visited.add(run_id)
        run = self._require_run(run_id)
        run.cancel_requested = True
        run.cancel_reason = reason or "cancel requested"
        run.updated_at = utc_now()
        if run.status not in TERMINAL_STATUSES:
            run.status = "cancelled"
        self._record("task.cancel_requested", run, {"reason": run.cancel_reason})
        self._flush()
        for child_task_id in list(run.child_task_ids):
            for child in self._runs.values():
                if child.task_id == child_task_id and child.status not in TERMINAL_STATUSES:
                    self._request_cancel(
                        child.run_id,
                        reason=f"parent cancelled: {run.cancel_reason}",
                        visited=visited,
                    )
        return run

    def should_cancel(self, run_id: str) -> bool:
        return self._require_run(run_id).cancel_requested

    def check_deadline(self, run_id: str, *, now: Optional[datetime] = None) -> bool:
        """Mark an overdue run cancelled and return whether it is expired."""
        run = self._require_run(run_id)
        if not run.deadline_at or run.status in TERMINAL_STATUSES:
            return False
        try:
            deadline = datetime.fromisoformat(run.deadline_at.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return False
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if current < deadline:
            return False
        self.request_cancel(run_id, reason="workflow deadline exceeded")
        self.append(run_id, "task.deadline_exceeded", payload={"deadline_at": run.deadline_at})
        return True

    def append(self, run_id: str, event_type: str, *, payload: Optional[Mapping[str, Any]] = None) -> WorkflowEvent:
        run = self._require_run(run_id)
        event = self._record(event_type, run, payload or {})
        self._flush()
        return event

    def snapshot(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "runs": {run_id: run.to_dict() for run_id, run in self._runs.items()},
            "events": [event.to_dict() for event in self._events],
        }

    def set_persist(self, persist: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        """Attach storage after construction when the run's session is known."""
        self._persist = persist

    def events(self, *, run_id: Optional[str] = None) -> List[WorkflowEvent]:
        if run_id is None:
            return list(self._events)
        return [event for event in self._events if event.run_id == run_id]

    def _require_run(self, run_id: str) -> WorkflowRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown workflow run: {run_id}")
        return run

    def _record(self, event_type: str, run: WorkflowRun, payload: Mapping[str, Any]) -> WorkflowEvent:
        event = WorkflowEvent(
            event_id=uuid.uuid4().hex,
            sequence=len(self._events) + 1,
            event_type=event_type,
            run_id=run.run_id,
            task_id=run.task_id,
            parent_task_id=run.parent_task_id,
            status=run.status,
            payload=dict(payload),
        )
        self._events.append(event)
        return event

    def _flush(self) -> None:
        if self._persist is not None:
            self._persist(self.snapshot())
