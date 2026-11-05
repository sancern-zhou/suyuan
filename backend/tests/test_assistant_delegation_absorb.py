"""助手模式后台委派在交付边界注入观察的回归测试。

背景：run_in_background 委派受理后回合常以纯文本结束，委派完成后没有
任何回灌通路。修复为在交付边界等待本会话委派完成，把结果作为工具观察
注入（state.last_observation）并继续 agent loop；同时 yield
delegation_status 事件（running/completed/released）供前端状态卡展示。
"""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from app.social.assistant_runs import AssistantRunService, _PENDING_BY_SESSION


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


@pytest.mark.asyncio
async def test_wait_for_session_runs_returns_completed_results():
    service = _make_service()
    record = {
        "run_id": "delegation_a", "kind": "workflow", "status": "succeeded",
        "target_mode": "query_monitoring_city", "goal": "取数",
        "result": {"status": "succeeded", "summary": "ok"}, "source_session_id": "s1",
    }
    task = _register_session_task("s1", record)
    try:
        await asyncio.sleep(0.05)
        results, pending = await service.wait_for_session_runs("s1", timeout=2.0)
        assert pending == 0
        assert len(results) == 1
        assert results[0]["run_id"] == "delegation_a"
        assert results[0]["status"] == "succeeded"
        assert results[0]["result"]["summary"] == "ok"
    finally:
        _PENDING_BY_SESSION.pop("s1", None)


@pytest.mark.asyncio
async def test_wait_for_session_runs_timeout_keeps_pending():
    service = _make_service()
    record = {"run_id": "delegation_b", "status": "running", "source_session_id": "s2"}
    task = _register_session_task("s2", record, delay=5)
    try:
        results, pending = await service.wait_for_session_runs("s2", timeout=0.1)
        assert results == []
        assert pending == 1
        assert service.pending_background_count("s2") == 1
    finally:
        task.cancel()
        _PENDING_BY_SESSION.pop("s2", None)


def _make_runtime(runtime_mode="assistant"):
    from app.agent.runtime.agent_runtime import AgentRuntime

    runtime = object.__new__(AgentRuntime)
    runtime.config = NS(runtime_mode=runtime_mode)
    runtime.writer = NS(add_iteration=Mock(), add_user_message=Mock())
    return runtime


def _state(session_id="s1"):
    from app.agent.runtime.types import RunState

    return RunState(session_id=session_id, user_query="q", mode="assistant")


async def _collect(runtime, state, planner_result, action):
    events, absorbed = [], False
    async for event in runtime._absorb_background_delegations(state, planner_result, action):
        if event.get("type") == "_delegation_absorbed":
            absorbed = bool(event.get("absorbed"))
        else:
            events.append(event)
    return events, absorbed


@pytest.mark.asyncio
async def test_absorb_skips_non_assistant_runtime():
    runtime = _make_runtime(runtime_mode="expert")
    state = _state()
    task = _register_session_task("s1", {"run_id": "delegation_c", "status": "succeeded", "source_session_id": "s1"})
    try:
        await asyncio.sleep(0.05)
        events, absorbed = await _collect(runtime, state, NS(thought=None), NS())
        assert events == []
        assert absorbed is False
        assert state.last_observation is None
    finally:
        _PENDING_BY_SESSION.pop("s1", None)


@pytest.mark.asyncio
async def test_absorb_injects_completed_results_and_continues():
    runtime = _make_runtime()
    state = _state()
    record = {
        "run_id": "delegation_d", "kind": "workflow", "status": "succeeded",
        "goal": "取数", "result": {"summary": "done"}, "source_session_id": "s1",
    }
    task = _register_session_task("s1", record)
    try:
        await asyncio.sleep(0.05)
        action = NS()
        events, absorbed = await _collect(runtime, state, NS(thought="t"), action)
        assert absorbed is True
        phases = [event["data"]["phase"] for event in events if event["type"] == "delegation_status"]
        assert phases == ["running", "completed"]
        observation = state.last_observation
        assert observation is not None
        assert observation["success"] is True
        assert observation["delegation_results"][0]["run_id"] == "delegation_d"
        assert observation["delegation_results"][0]["result"] == {"summary": "done"}
        runtime.writer.add_iteration.assert_called_once()
        assert runtime.writer.add_iteration.call_args[0][2] is observation
    finally:
        _PENDING_BY_SESSION.pop("s1", None)


@pytest.mark.asyncio
async def test_absorb_releases_when_nothing_finishes(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "assistant_delegation_wait_seconds", 1)
    runtime = _make_runtime()
    state = _state("s3")
    record = {"run_id": "delegation_e", "status": "running", "source_session_id": "s3"}
    task = _register_session_task("s3", record, delay=30)
    try:
        events, absorbed = await _collect(runtime, state, NS(thought=None), NS())
        assert absorbed is False
        phases = [event["data"]["phase"] for event in events if event["type"] == "delegation_status"]
        assert phases == ["running", "released"]
        assert state.last_observation is None
    finally:
        task.cancel()
        _PENDING_BY_SESSION.pop("s3", None)


@pytest.mark.asyncio
async def test_background_runs_view_lists_pending_only():
    record = {"run_id": "delegation_f", "kind": "child", "status": "running",
              "goal": "整理材料", "target_mode": "office", "source_session_id": "s4"}
    task = _register_session_task("s4", record, delay=30)
    try:
        from app.social.assistant_runs import background_runs_view

        view = background_runs_view("s4")
        assert len(view) == 1
        assert view[0]["run_id"] == "delegation_f"
        assert view[0]["goal"] == "整理材料"
        assert "result" not in view[0]
    finally:
        task.cancel()
        _PENDING_BY_SESSION.pop("s4", None)
