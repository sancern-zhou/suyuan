"""委派阻塞等待与反轮询修复的回归测试（2026-11-08 轮询风暴复盘）。

覆盖：
- AssistantRunService.wait_for_run：进程内 task 完成即唤醒；跨进程场景退
  化为文件轮询兜底；超时放行仍非终态的 record。
- AssistantRunService.collect_completed_runs：非阻塞收割轮次边界已完成项。
- _polling_hint：连续无进展 get 第三次起返回改道指引；等待式查询/终态清零。
- wait_task 对 delegation_* 的识别与等待分流。
- ToolLoopGuard 对 manage_assistant_runs 循环的改道指引。
- AgentRuntime._inject_completed_delegation_results：轮次边界注入观察。
"""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from app.social.assistant_runs import (
    _GET_POLL_COUNTS,
    _PENDING_BY_SESSION,
    AssistantRunService,
)


def _make_service() -> AssistantRunService:
    return object.__new__(AssistantRunService)


def _register_session_task(session_id: str, record: dict, delay: float = 0) -> asyncio.Task:
    async def job():
        if delay:
            await asyncio.sleep(delay)

    task = asyncio.ensure_future(job())
    task._assistant_run_record = record
    _PENDING_BY_SESSION.setdefault(session_id, set()).add(task)
    return task


# --------------------------------------------------------------------- #
# wait_for_run
# --------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_wait_for_run_returns_immediately_when_terminal(monkeypatch):
    service = _make_service()
    record = {"run_id": "delegation_w1", "status": "succeeded"}
    def fake_get(project, owner, run_id):
        return record

    monkeypatch.setattr(service, "get", fake_get)
    result = await service.wait_for_run("p", "u", "delegation_w1", 0)
    assert result["status"] == "succeeded"


@pytest.mark.asyncio
async def test_wait_for_run_wakes_on_inprocess_task(monkeypatch):
    service = _make_service()
    record = {
        "run_id": "delegation_w2", "status": "running", "source_session_id": "s-w2",
    }
    def fake_get(project, owner, run_id):
        return record

    monkeypatch.setattr(service, "get", fake_get)

    async def job():
        await asyncio.sleep(0.05)
        record["status"] = "succeeded"

    task = asyncio.ensure_future(job())
    task._assistant_run_record = record
    _PENDING_BY_SESSION.setdefault("s-w2", set()).add(task)
    try:
        result = await service.wait_for_run("p", "u", "delegation_w2", 2.0)
        assert result["status"] == "succeeded"
    finally:
        _PENDING_BY_SESSION.pop("s-w2", None)


@pytest.mark.asyncio
async def test_wait_for_run_polls_record_when_not_inprocess(monkeypatch):
    """跨 worker 场景：pending task 不在本进程，按落盘 record 轮询兜底。"""
    service = _make_service()
    record = {
        "run_id": "delegation_w3", "status": "running", "source_session_id": "s-w3",
    }
    def fake_get(project, owner, run_id):
        return record

    monkeypatch.setattr(service, "get", fake_get)

    async def flip():
        await asyncio.sleep(0.05)
        record["status"] = "failed"

    flipper = asyncio.ensure_future(flip())
    try:
        result = await service.wait_for_run(
            "p", "u", "delegation_w3", 2.0, poll_interval=0.01
        )
        assert result["status"] == "failed"
    finally:
        await flipper


@pytest.mark.asyncio
async def test_wait_for_run_timeout_returns_running_record(monkeypatch):
    service = _make_service()
    record = {
        "run_id": "delegation_w4", "status": "running", "source_session_id": "s-w4",
    }
    def fake_get(project, owner, run_id):
        return record

    monkeypatch.setattr(service, "get", fake_get)
    result = await service.wait_for_run("p", "u", "delegation_w4", 0.05, poll_interval=0.01)
    assert result["status"] == "running"


# --------------------------------------------------------------------- #
# collect_completed_runs
# --------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_collect_completed_runs_is_nonblocking():
    service = _make_service()
    done_record = {
        "run_id": "delegation_c1", "kind": "child", "status": "succeeded",
        "goal": "done", "target_mode": "office", "result": {"summary": "ok"},
        "source_session_id": "s-c",
    }
    running_record = {"run_id": "delegation_c2", "status": "running", "source_session_id": "s-c"}
    done_task = _register_session_task("s-c", done_record)
    running_task = _register_session_task("s-c", running_record, delay=30)
    try:
        await asyncio.sleep(0.05)
        results, still_running = await service.collect_completed_runs("s-c")
        assert still_running == 1
        assert len(results) == 1
        assert results[0]["run_id"] == "delegation_c1"
        assert results[0]["result"] == {"summary": "ok"}
    finally:
        running_task.cancel()
        _PENDING_BY_SESSION.pop("s-c", None)
        done_task.exception()


# --------------------------------------------------------------------- #
# _polling_hint
# --------------------------------------------------------------------- #

def test_polling_hint_appears_after_third_unchanged_get():
    _GET_POLL_COUNTS.clear()
    context = NS(session_id="s-hint")
    record = {"status": "running"}
    try:
        assert AssistantRunService._polling_hint(context, "delegation_h1", record, used_wait=False) is None
        assert AssistantRunService._polling_hint(context, "delegation_h1", record, used_wait=False) is None
        hint = AssistantRunService._polling_hint(context, "delegation_h1", record, used_wait=False)
        assert hint is not None
        assert "wait_seconds" in hint
        assert "不要继续轮询" in hint
    finally:
        _GET_POLL_COUNTS.clear()


def test_polling_hint_resets_when_wait_used_or_terminal():
    _GET_POLL_COUNTS.clear()
    context = NS(session_id="s-hint2")
    running = {"status": "running"}
    terminal = {"status": "succeeded"}
    try:
        AssistantRunService._polling_hint(context, "delegation_h2", running, used_wait=False)
        AssistantRunService._polling_hint(context, "delegation_h2", running, used_wait=False)
        # 等待式查询（used_wait=True）是正确用法：清零且不提示
        assert AssistantRunService._polling_hint(context, "delegation_h2", running, used_wait=True) is None
        assert ("s-hint2", "delegation_h2") not in _GET_POLL_COUNTS
        AssistantRunService._polling_hint(context, "delegation_h2", running, used_wait=False)
        # 到达终态：清零且不提示
        assert AssistantRunService._polling_hint(context, "delegation_h2", terminal, used_wait=False) is None
        assert ("s-hint2", "delegation_h2") not in _GET_POLL_COUNTS
    finally:
        _GET_POLL_COUNTS.clear()


# --------------------------------------------------------------------- #
# wait_task delegation 分支
# --------------------------------------------------------------------- #

def test_wait_task_resolves_delegation_prefix():
    from app.tools.social.wait_task.tool import WaitTaskTool

    tool = WaitTaskTool()
    assert tool._resolve_task_type("delegation_abc123", "auto") == "delegation"


@pytest.mark.asyncio
async def test_wait_task_waits_for_delegation(monkeypatch):
    from app.tools.social.wait_task import tool as wait_task_module

    class FakeService:
        async def wait_for_run(self, project, owner, run_id, timeout, poll_interval=1.0):
            assert run_id == "delegation_t1"
            return {"status": "succeeded", "kind": "child", "goal": "写简报"}

    async def fake_resolve_task_user(context):
        return NS(id="user-1")

    monkeypatch.setattr(
        "app.social.assistant_runs.AssistantRunService", FakeService
    )
    monkeypatch.setattr(
        "app.tools.scheduled_tasks.session_identity.resolve_task_user",
        fake_resolve_task_user,
    )
    tool = wait_task_module.WaitTaskTool()
    result = await tool.execute(
        task_id="delegation_t1", wait_timeout=5, context=NS(session_id="s")
    )
    assert result["success"] is True
    assert result["metadata"]["task_type"] == "delegation"
    assert result["metadata"]["wait_timed_out"] is False
    assert result["data"]["status"] == "succeeded"


# --------------------------------------------------------------------- #
# ToolLoopGuard 改道指引
# --------------------------------------------------------------------- #

def test_loop_guard_block_carries_redirection_hint():
    from app.agent.runtime.tool_loop_guard import ToolLoopGuard

    guard = ToolLoopGuard()
    args = {"action": "get", "run_id": "delegation_g1"}
    result = None
    for _ in range(10):
        outcome = guard.before_call("manage_assistant_runs", args)
        if outcome is not None and outcome["severity"] == "block":
            result = outcome
            break
    assert result is not None
    assert result["severity"] == "block"
    assert "wait_seconds" in result["summary"]
    assert "改道" in result["summary"]


def test_loop_guard_warning_also_carries_hint():
    from app.agent.runtime.tool_loop_guard import ToolLoopGuard

    guard = ToolLoopGuard()
    args = {"action": "get", "run_id": "delegation_g2"}
    warning = None
    for _ in range(6):
        outcome = guard.before_call("manage_assistant_runs", args)
        if outcome is not None and outcome["severity"] == "warning":
            warning = outcome
            break
    assert warning is not None
    assert "wait_seconds" in warning["summary"]


# --------------------------------------------------------------------- #
# 轮次边界注入
# --------------------------------------------------------------------- #

def _make_runtime(runtime_mode="assistant"):
    from app.agent.runtime.agent_runtime import AgentRuntime

    runtime = object.__new__(AgentRuntime)
    runtime.config = NS(runtime_mode=runtime_mode)
    runtime.writer = NS(add_iteration=Mock(), add_user_message=Mock())
    return runtime


def _state(session_id="s-inj"):
    from app.agent.runtime.types import RunState

    return RunState(session_id=session_id, user_query="q", mode="assistant")


async def _collect_injection(runtime, state, planner_result):
    events = []
    async for event in runtime._inject_completed_delegation_results(state, planner_result):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_turn_boundary_injects_completed_delegation():
    runtime = _make_runtime()
    state = _state()
    record = {
        "run_id": "delegation_i1", "kind": "child", "status": "succeeded",
        "goal": "写简报", "target_mode": "office", "result": {"summary": "done"},
        "source_session_id": "s-inj",
    }
    task = _register_session_task("s-inj", record)
    try:
        await asyncio.sleep(0.05)
        events = await _collect_injection(runtime, state, NS(thought="t"))
        assert len(events) == 1
        assert events[0]["type"] == "delegation_status"
        assert events[0]["data"]["phase"] == "completed"
        observation = state.last_observation
        assert observation is not None
        assert observation["success"] is True
        assert observation["delegation_results"][0]["run_id"] == "delegation_i1"
        assert "manage_assistant_runs" in observation["summary"]
        runtime.writer.add_iteration.assert_called_once()
        injected_action = runtime.writer.add_iteration.call_args[0][1]
        assert injected_action["type"] == "DELEGATION_RESULT"
    finally:
        _PENDING_BY_SESSION.pop("s-inj", None)


@pytest.mark.asyncio
async def test_turn_boundary_injection_noop_when_nothing_completed():
    runtime = _make_runtime()
    state = _state("s-inj2")
    running = {"run_id": "delegation_i2", "status": "running", "source_session_id": "s-inj2"}
    task = _register_session_task("s-inj2", running, delay=30)
    try:
        events = await _collect_injection(runtime, state, NS(thought="t"))
        assert events == []
        assert state.last_observation is None
        runtime.writer.add_iteration.assert_not_called()
    finally:
        task.cancel()
        _PENDING_BY_SESSION.pop("s-inj2", None)


@pytest.mark.asyncio
async def test_turn_boundary_injection_skips_non_assistant():
    runtime = _make_runtime(runtime_mode="expert")
    state = _state("s-inj3")
    record = {"run_id": "delegation_i3", "status": "succeeded", "source_session_id": "s-inj3"}
    task = _register_session_task("s-inj3", record)
    try:
        await asyncio.sleep(0.05)
        events = await _collect_injection(runtime, state, NS(thought="t"))
        assert events == []
        assert state.last_observation is None
    finally:
        _PENDING_BY_SESSION.pop("s-inj3", None)
