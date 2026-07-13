"""Generic business events consumed by event-triggered tasks."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskEvent(BaseModel):
    """A validated, immutable input envelope for task execution."""

    event_id: str
    event_type: str
    occurred_at: datetime = Field(default_factory=datetime.now)
    attributes: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "event_type")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    def matches(self, filters: dict[str, Any]) -> bool:
        """Match scalar equality and list membership against event attributes."""
        for key, expected in filters.items():
            actual = self.attributes.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True
