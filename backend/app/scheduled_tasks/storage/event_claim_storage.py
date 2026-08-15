"""Durable cross-process idempotency claims for event-triggered tasks."""

from __future__ import annotations

import fcntl
import hashlib
import json
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Literal

from pydantic import BaseModel, Field

from app.utils.path_config import get_data_registry
from ..models.event import TaskEvent


ClaimStatus = Literal["claimed", "running", "succeeded", "failed"]


class EventClaim(BaseModel):
    claim_id: str
    task_id: str
    event_id: str
    event_type: str
    event_snapshot: dict[str, Any]
    status: ClaimStatus = "claimed"
    attempt: int = 1
    execution_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    updated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class EventClaimStorage:
    """Store one immutable claim file per task and event pair."""

    def __init__(self, storage_dir: str | Path | None = None):
        root = Path(storage_dir) if storage_dir else get_data_registry() / "scheduled_tasks"
        self.claims_dir = root / "event_claims"
        self.claims_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.claims_dir / ".claims.lock"

    @staticmethod
    def _claim_id(task_id: str, event_id: str) -> str:
        value = f"{task_id}\0{event_id}".encode("utf-8")
        return hashlib.sha256(value).hexdigest()

    def _claim_path(self, task_id: str, event_id: str) -> Path:
        return self.claims_dir / f"{self._claim_id(task_id, event_id)}.json"

    def _claim_path_by_id(self, claim_id: str) -> Path:
        return self.claims_dir / f"{claim_id}.json"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.lock_path.touch(exist_ok=True)
        with self.lock_path.open("r+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _read(path: Path) -> EventClaim:
        return EventClaim.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as temp_file:
            json.dump(payload, temp_file, ensure_ascii=False, indent=2, default=str)
            temp_path = Path(temp_file.name)
        temp_path.replace(path)

    def try_claim(self, task_id: str, event: TaskEvent) -> EventClaim | None:
        path = self._claim_path(task_id, event.event_id)
        with self._locked():
            if path.exists():
                return None
            claim = EventClaim(
                claim_id=path.stem,
                task_id=task_id,
                event_id=event.event_id,
                event_type=event.event_type,
                event_snapshot=event.model_dump(mode="json"),
            )
            self._atomic_write(path, claim.model_dump(mode="json"))
            return claim

    def get(self, task_id: str, event_id: str) -> EventClaim | None:
        path = self._claim_path(task_id, event_id)
        with self._locked():
            return self._read(path) if path.exists() else None

    def list_by_status(self, status: ClaimStatus) -> list[EventClaim]:
        """List durable claims in a given state, oldest first."""
        with self._locked():
            claims = [
                self._read(path)
                for path in self.claims_dir.glob("*.json")
            ]
        return sorted(
            (claim for claim in claims if claim.status == status),
            key=lambda claim: claim.created_at,
        )

    def mark_status(
        self,
        claim_id: str,
        status: ClaimStatus,
        *,
        execution_id: str | None = None,
    ) -> EventClaim:
        path = self._claim_path_by_id(claim_id)
        with self._locked():
            if not path.exists():
                raise ValueError(f"Event claim {claim_id} not found")
            claim = self._read(path)
            claim.status = status
            if execution_id is not None:
                claim.execution_id = execution_id
            claim.updated_at = datetime.now().astimezone()
            self._atomic_write(path, claim.model_dump(mode="json"))
            return claim

    def retry_failed(self, task_id: str, event_id: str) -> EventClaim:
        path = self._claim_path(task_id, event_id)
        with self._locked():
            if not path.exists():
                raise ValueError(f"Event claim for {task_id}/{event_id} not found")
            claim = self._read(path)
            if claim.status != "failed":
                raise ValueError("Only failed event claims can be retried")
            claim.status = "claimed"
            claim.attempt += 1
            claim.execution_id = None
            claim.updated_at = datetime.now().astimezone()
            self._atomic_write(path, claim.model_dump(mode="json"))
            return claim

    def fail_stale_running(
        self,
        task_id: str,
        event_id: str,
        *,
        timeout_seconds: int,
        now: datetime | None = None,
    ) -> EventClaim | None:
        """Atomically fail a running claim only after its execution timeout."""
        path = self._claim_path(task_id, event_id)
        with self._locked():
            if not path.exists():
                return None
            claim = self._read(path)
            current_time = now or datetime.now().astimezone()
            elapsed = (current_time - claim.updated_at).total_seconds()
            if claim.status != "running" or elapsed <= max(timeout_seconds, 0):
                return None
            claim.status = "failed"
            claim.updated_at = current_time
            self._atomic_write(path, claim.model_dump(mode="json"))
            return claim

    def latest_event(self, event_type: str) -> TaskEvent | None:
        with self._locked():
            claims = [self._read(path) for path in self.claims_dir.glob("*.json")]
            events = [
                TaskEvent.model_validate(claim.event_snapshot)
                for claim in claims
                if claim.event_type == event_type
            ]
        return max(events, key=lambda event: event.occurred_at) if events else None
