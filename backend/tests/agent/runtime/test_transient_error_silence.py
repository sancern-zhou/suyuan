"""瞬时 LLM 故障（网关 504/过载/超时）不得渲染成用户可见错误气泡。

背景：网关在上游 6s 内无响应字节时返回 504，运行时会自动换候选重试。旧行为
每次失败都下发可见 error 事件，前端于是在对话区插一条“错误: Server error '504
Gateway Time-out'”，用户看到一串无意义的技术堆栈。
"""

import asyncio
from types import SimpleNamespace

from app.agent.runtime.agent_runtime import AgentRuntime
from app.agent.runtime.event_bus import RuntimeEventBus
from app.agent.runtime.types import RunState
from app.services.llm_failover import (
    TRANSIENT_FAILURE_USER_MESSAGE,
    classify_llm_failure,
    is_transient_failure,
)


class _StatusError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__(message or f"Server error '{status}'")
        self.status = status


def _state() -> RunState:
    return RunState(session_id="s", user_query="q", mode="assistant")


def test_text_504_is_classified_overloaded():
    error = RuntimeError(
        "Server error '504 Gateway Time-out' for url "
        "'http://<llm-gateway>:41080/large-model/api/v1/chat/completions'"
    )
    assert classify_llm_failure(error).reason == "overloaded"
    assert is_transient_failure(error) is True


def test_transient_reasons_cover_504_overload_and_timeout():
    assert is_transient_failure(_StatusError(504)) is True
    assert is_transient_failure(RuntimeError("overloaded_error")) is True
    assert is_transient_failure(RuntimeError("read timed out")) is True
    assert is_transient_failure(_StatusError(429)) is True


def test_non_transient_errors_stay_visible():
    assert is_transient_failure(_StatusError(400, "bad request")) is False
    assert is_transient_failure(_StatusError(401, "unauthorized")) is False
    assert is_transient_failure(RuntimeError("context length exceeded")) is False


def test_error_event_carries_silent_flag_only_for_transient():
    bus = RuntimeEventBus()
    state = _state()

    transient = bus.error(state, _StatusError(504), silent=True)
    assert transient["type"] == "error"
    assert transient["data"]["silent"] is True

    fatal = bus.error(state, _StatusError(400, "bad request"))
    assert "silent" not in fatal["data"]


def test_fatal_error_event_carries_friendly_user_message():
    bus = RuntimeEventBus()
    event = bus.fatal_error(
        _state(), _StatusError(504), user_message=TRANSIENT_FAILURE_USER_MESSAGE
    )
    assert event["data"]["user_message"] == TRANSIENT_FAILURE_USER_MESSAGE
    assert "504" in event["data"]["error"]


def test_fatal_error_event_without_user_message_keeps_raw_error():
    bus = RuntimeEventBus()
    event = bus.fatal_error(_state(), RuntimeError("boom"))
    assert "user_message" not in event["data"]


class _Finalizer:
    def __init__(self) -> None:
        self.calls: list = []

    async def fatal_error(self, state, error):
        self.calls.append(error)
        yield {"type": "fatal_error", "data": {"error": str(error)}}

    async def timeout(self, state):
        self.calls.append("timeout")
        yield {"type": "incomplete", "data": {"reason": "max_iterations_reached"}}


async def _no_events(state):
    if False:
        yield None


def _runtime(failing_error: Exception, max_iterations: int = 3) -> AgentRuntime:
    runtime = object.__new__(AgentRuntime)
    runtime.config = SimpleNamespace(
        agent_logger=None,
        max_iterations=max_iterations,
        is_interruption=False,
        runtime_mode="assistant",
        # 共享层 _run 会读 config.runtime_metadata 构建时间预算（None=不限）。
        runtime_metadata=None,
    )
    runtime.planner = SimpleNamespace(is_interruption=False)
    runtime.writer = SimpleNamespace(load_initial_history_if_needed=lambda messages: None)
    runtime.events = RuntimeEventBus()
    runtime.finalizer = _Finalizer()

    async def failing_iteration(state):
        raise failing_error
        yield

    runtime._raise_if_cancelled = lambda: None
    runtime._ensure_user_message_written = lambda state: None

    async def close_steering(state):
        return None

    runtime._close_steering_event = close_steering
    runtime._apply_steering_inputs = _no_events
    runtime._run_iteration = failing_iteration
    return runtime


def _run(runtime: AgentRuntime, state: RunState) -> list[dict]:
    async def collect() -> list[dict]:
        return [event async for event in runtime._run(state, None)]

    return asyncio.run(collect())


def test_transient_iteration_errors_are_silent_until_budget_exhausts():
    runtime = _runtime(_StatusError(504))
    events = _run(runtime, _state())

    iteration_errors = [event for event in events if event["type"] == "error"]
    assert iteration_errors, "瞬时失败仍要下发事件供调用方感知"
    assert all(event["data"].get("silent") is True for event in iteration_errors)

    # 预算耗尽：终点是友好致命错误，而不是“任务较复杂，是否继续？”
    assert events[-1]["type"] == "fatal_error"
    assert "timeout" not in runtime.finalizer.calls


def test_non_transient_iteration_errors_stay_visible():
    runtime = _runtime(_StatusError(400, "bad request"))
    events = _run(runtime, _state())

    iteration_errors = [event for event in events if event["type"] == "error"]
    assert iteration_errors
    assert all("silent" not in event["data"] for event in iteration_errors)
