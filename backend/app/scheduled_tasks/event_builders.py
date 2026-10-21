"""Event builders used when a user manually runs an event-backed task."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.scheduled_tasks.models import ScheduledTask, TaskEvent

ManualEventBuilder = Callable[["ScheduledTask"], Awaitable["TaskEvent"]]
_builders: dict[str, ManualEventBuilder] = {}


def register_manual_event_builder(event_type: str, builder: ManualEventBuilder) -> None:
    """Register a source that creates a fresh event for manual execution."""
    _builders[event_type] = builder


def get_manual_event_builder(event_type: str) -> ManualEventBuilder | None:
    return _builders.get(event_type)
