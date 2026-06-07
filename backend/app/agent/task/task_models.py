"""Incremental task list models for agent task management."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class TaskItem:
    id: str
    subject: str
    description: str
    active_form: str
    status: TaskStatus = TaskStatus.PENDING

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "subject": self.subject,
            "description": self.description,
            "activeForm": self.active_form,
            "status": self.status.value,
        }


class TaskList:
    """Session-scoped incremental task list."""

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskItem] = {}
        self._completed_snapshot: List[Dict[str, str]] = []
        self._next_id = 1

    def create(
        self,
        subject: str,
        description: str,
        active_form: Optional[str] = None,
    ) -> TaskItem:
        subject = self._require_text(subject, "subject")
        description = self._require_text(description, "description")
        active_form = self._require_text(active_form or subject, "activeForm")

        task = TaskItem(
            id=str(self._next_id),
            subject=subject,
            description=description,
            active_form=active_form,
        )
        self._next_id += 1
        self._tasks[task.id] = task
        return task

    def find_by_content(self, subject: str, description: str) -> Optional[TaskItem]:
        subject = self._require_text(subject, "subject")
        description = self._require_text(description, "description")
        for task in self._tasks.values():
            if task.subject == subject and task.description == description:
                return task
        return None

    def get(self, task_id: str) -> Optional[TaskItem]:
        return self._tasks.get(task_id)

    def list(self) -> List[TaskItem]:
        return list(self._tasks.values())

    def delete(self, task_id: str) -> bool:
        if task_id not in self._tasks:
            return False
        del self._tasks[task_id]
        return True

    def update(
        self,
        task_id: str,
        *,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        active_form: Optional[str] = None,
        status: Optional[TaskStatus | str] = None,
    ) -> TaskItem:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")

        next_status = TaskStatus(status) if status is not None else task.status
        if next_status == TaskStatus.IN_PROGRESS:
            for existing in self._tasks.values():
                if existing.id != task_id and existing.status == TaskStatus.IN_PROGRESS:
                    raise ValueError("Only one task can be in_progress at a time")

        if subject is not None:
            task.subject = self._require_text(subject, "subject")
        if description is not None:
            task.description = self._require_text(description, "description")
        if active_form is not None:
            task.active_form = self._require_text(active_form, "activeForm")
        task.status = next_status

        self._update_completed_snapshot()
        return task

    def completed_snapshot(self) -> List[Dict[str, str]]:
        return [item.copy() for item in self._completed_snapshot]

    def _update_completed_snapshot(self) -> None:
        if not self._tasks:
            return
        if not all(task.status == TaskStatus.COMPLETED for task in self._tasks.values()):
            return
        self._completed_snapshot = [task.to_dict() for task in self._tasks.values()]

    @staticmethod
    def _require_text(value: str, field_name: str) -> str:
        if not value or not value.strip():
            raise ValueError(f"{field_name} cannot be empty")
        return value.strip()
