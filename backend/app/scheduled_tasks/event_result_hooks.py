"""Extensible callbacks for event-triggered task completion.

The scheduled-task engine owns execution.  Project domains can subscribe to
the completed ``TaskExecution`` without coupling the engine to a business
event store.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

logger = structlog.get_logger()

EventResultHandler = Callable[[Any, Any, Any], Awaitable[None] | None]
_handlers: list[EventResultHandler] = []


def register_event_result_handler(handler: EventResultHandler) -> None:
    """Register a handler once per process."""

    if handler not in _handlers:
        _handlers.append(handler)


async def notify_event_result(task: Any, event: Any, execution: Any) -> None:
    """Notify registered domains; a sink failure never changes task status."""

    for handler in tuple(_handlers):
        try:
            result = handler(task, event, execution)
            if result is not None:
                await result
        except Exception as exc:  # noqa: BLE001 - result sinks are best effort
            logger.warning(
                "scheduled_event_result_handler_failed",
                handler=getattr(handler, "__name__", repr(handler)),
                task_id=getattr(task, "task_id", None),
                event_id=getattr(event, "event_id", None),
                execution_id=getattr(execution, "execution_id", None),
                error=str(exc),
            )
