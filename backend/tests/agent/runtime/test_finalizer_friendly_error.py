"""瞬时故障的终局出口要给友好文案，技术堆栈只进日志。"""

import asyncio

from app.agent.runtime.event_bus import RuntimeEventBus
from app.agent.runtime.finalizer import Finalizer
from app.agent.runtime.types import RunState
from app.services.llm_failover import TRANSIENT_FAILURE_USER_MESSAGE


class _StatusError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__(message or f"Server error '{status}'")
        self.status = status


def _state() -> RunState:
    return RunState(session_id="s", user_query="q", mode="assistant")


def _collect(finalizer: Finalizer, error: Exception) -> list[dict]:
    async def run() -> list[dict]:
        return [event async for event in finalizer.fatal_error(_state(), error)]

    return asyncio.run(run())


def test_transient_fatal_error_uses_friendly_message():
    finalizer = Finalizer(writer=None, event_bus=RuntimeEventBus())
    events = _collect(finalizer, _StatusError(504))
    assert events[-1]["type"] == "fatal_error"
    assert events[-1]["data"]["user_message"] == TRANSIENT_FAILURE_USER_MESSAGE


def test_non_transient_fatal_error_keeps_raw_error():
    finalizer = Finalizer(writer=None, event_bus=RuntimeEventBus())
    events = _collect(finalizer, _StatusError(400, "bad request"))
    assert "user_message" not in events[-1]["data"]
