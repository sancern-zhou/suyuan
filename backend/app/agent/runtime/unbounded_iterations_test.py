"""无步数上限模式的运行时行为。

对齐 ZCode：默认不设迭代上限（None），终止只由任务完成/取消/熔断护栏决定。
本文件覆盖：
- 无上限时可跑到超过旧 120 / 固定工作流 20 的上限并正常完成；
- 无进展熔断在连续停摆时接管失控保护；
- 显式传入的 max_iterations 仍作兜底上限；
- provider 上下文溢出→强制压缩续跑（不计熔断），压缩无空间才终止。
"""

import pytest
from types import SimpleNamespace

from app.agent.runtime.agent_runtime import (
    AgentRuntime,
    NO_PROGRESS_ITERATION_LIMIT,
)
from app.agent.runtime.types import RunState


def _build_runtime(config_overrides=None, finalizer=None, iteration=None):
    """按 test_custom_agent_runtime.py 的既定模式拼一个最小 runtime。"""
    runtime = object.__new__(AgentRuntime)
    overrides = {
        "agent_logger": None,
        "max_iterations": None,
        "is_interruption": False,
        "runtime_metadata": None,  # time_budget 机制从该属性读取预算配置
    }
    overrides.update(config_overrides or {})
    runtime.config = SimpleNamespace(**overrides)
    runtime.planner = SimpleNamespace(is_interruption=False)
    runtime.writer = SimpleNamespace(load_initial_history_if_needed=lambda messages: None)
    runtime.events = SimpleNamespace(
        start=lambda state: {"type": "start"},
        error=lambda state, error: {"type": "error", "data": {"error": str(error)}},
    )
    runtime.finalizer = finalizer
    runtime._raise_if_cancelled = lambda: None
    runtime._ensure_user_message_written = lambda state: None

    async def close_steering(state):
        return None

    async def no_events(state):
        if False:
            yield None

    runtime._close_steering = close_steering
    runtime._apply_steering_inputs = no_events
    runtime._run_iteration = iteration
    return runtime


class _RecordingFinalizer:
    def __init__(self):
        self.calls = []

    async def complete(self, state, answer="", planner_result=None, thought=None):
        self.calls.append(("complete", state.response_text))
        yield {"type": "complete"}

    async def timeout(self, state, reason=None):
        self.calls.append(("timeout",))
        yield {"type": "complete", "data": {"status": "incomplete", "reason": reason or "max_iterations_reached"}}

    async def no_progress(self, state):
        self.calls.append(("no_progress",))
        yield {"type": "complete", "data": {"status": "incomplete", "reason": "no_progress_detected"}}

    async def fatal_error(self, state, error):
        self.calls.append(("fatal_error", str(error)))
        yield {"type": "fatal_error", "data": {"error": str(error)}}


@pytest.mark.asyncio
async def test_unlimited_iterations_run_past_legacy_caps_and_complete():
    """query_monitoring 旧上限 20、主循环旧上限 120：无上限模式下跑 130 轮仍正常完成。"""
    calls = 0

    async def iterating(state):
        nonlocal calls
        calls += 1
        state.progress_seq += 1  # 每轮都有工具进展
        if calls >= 130:
            state.task_completed = True
            state.response_text = "done"
        if False:
            yield None

    finalizer = _RecordingFinalizer()
    runtime = _build_runtime(finalizer=finalizer, iteration=iterating)
    state = RunState(session_id="s", user_query="run", mode="query_monitoring")

    events = [event async for event in runtime._run(state, None)]

    assert calls == 130
    assert state.task_completed is True
    # 未触发任何终态收尾（timeout/no_progress/fatal 都不应出现）
    assert finalizer.calls == []


@pytest.mark.asyncio
async def test_no_progress_breaker_stops_a_stalled_run():
    """连续无进展（无成功工具结果、无输出）达到阈值即熔断，不再无限空转。"""
    calls = 0

    async def stalled(state):
        nonlocal calls
        calls += 1  # 什么都不做：不标记进展、不完成
        if False:
            yield None

    finalizer = _RecordingFinalizer()
    runtime = _build_runtime(finalizer=finalizer, iteration=stalled)
    state = RunState(session_id="s", user_query="run", mode="expert")

    events = [event async for event in runtime._run(state, None)]

    assert calls == NO_PROGRESS_ITERATION_LIMIT
    assert finalizer.calls == [("no_progress",)]
    assert events[-1]["data"]["reason"] == "no_progress_detected"


@pytest.mark.asyncio
async def test_progress_resets_no_progress_counter():
    """穿插的进展轮重置计数：7 次停摆 + 1 次进展 + 7 次停摆 + 完成 不会熔断。"""
    calls = 0

    async def stuttering(state):
        nonlocal calls
        calls += 1
        # 第 8 轮有进展，其余轮停摆
        if calls == 8:
            state.progress_seq += 1
        if calls >= 16:
            state.task_completed = True
            state.response_text = "done"
        if False:
            yield None

    finalizer = _RecordingFinalizer()
    runtime = _build_runtime(finalizer=finalizer, iteration=stuttering)
    state = RunState(session_id="s", user_query="run", mode="expert")

    [event async for event in runtime._run(state, None)]

    assert calls == 16
    assert state.task_completed is True
    assert finalizer.calls == []


@pytest.mark.asyncio
async def test_explicit_max_iterations_still_acts_as_fallback_cap():
    """显式传入的上限仍然生效（timeout 路径保留）。"""
    calls = 0

    async def iterating(state):
        nonlocal calls
        calls += 1
        state.progress_seq += 1  # 一直有进展，排除无进展熔断干扰
        if False:
            yield None

    finalizer = _RecordingFinalizer()
    runtime = _build_runtime(
        config_overrides={"max_iterations": 5},
        finalizer=finalizer,
        iteration=iterating,
    )
    state = RunState(session_id="s", user_query="run", mode="expert")

    events = [event async for event in runtime._run(state, None)]

    assert calls == 5
    assert finalizer.calls == [("timeout",)]
    assert events[-1]["data"]["reason"] == "max_iterations_reached"


@pytest.mark.asyncio
async def test_context_overflow_forces_compaction_and_continues():
    """上下文溢出→强制压缩→继续执行，不计入确定性熔断。"""
    calls = 0
    compactions = 0

    async def overflow_then_complete(state):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("Error code: 400 - maximum context length exceeded")
        state.progress_seq += 1
        state.task_completed = True
        state.response_text = "done"
        if False:
            yield None

    finalizer = _RecordingFinalizer()
    runtime = _build_runtime(finalizer=finalizer, iteration=overflow_then_complete)

    async def fake_compact(state):
        nonlocal compactions
        compactions += 1
        return True

    runtime._force_compact_for_overflow = fake_compact
    state = RunState(session_id="s", user_query="run", mode="expert")

    events = [event async for event in runtime._run(state, None)]

    assert compactions == 1
    assert calls == 2
    assert state.task_completed is True
    # 溢出未计入熔断、未产生 fatal
    assert finalizer.calls == []


@pytest.mark.asyncio
async def test_context_overflow_without_compaction_room_is_fatal():
    """压缩已无可缩空间（如 system prompt 自身超限）→ 终止而非无限重试。"""
    calls = 0

    async def always_overflow(state):
        nonlocal calls
        calls += 1
        raise RuntimeError("Error code: 400 - prompt is too long")
        yield

    finalizer = _RecordingFinalizer()
    runtime = _build_runtime(finalizer=finalizer, iteration=always_overflow)

    async def fake_compact(state):
        return False

    runtime._force_compact_for_overflow = fake_compact
    state = RunState(session_id="s", user_query="run", mode="expert")

    events = [event async for event in runtime._run(state, None)]

    assert calls == 1
    assert finalizer.calls[0][0] == "fatal_error"
    assert "无法继续缩减" in finalizer.calls[0][1]


def test_context_overflow_error_classification():
    assert AgentRuntime._is_context_overflow_error(
        RuntimeError("Error code: 400 - This model's maximum context length is 4096 tokens")
    ) is True
    assert AgentRuntime._is_context_overflow_error(RuntimeError("HTTP 500 server error")) is False
