"""阶段 B 回归：助手委派默认后台、内联/溢出吸收、HTTP 追问直通。"""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.social.assistant_runs as assistant_runs_module
from app.social.assistant_request import (
    begin_assistant_request,
    end_assistant_request,
)
from app.social.assistant_runs import (
    TERMINAL,
    AssistantRunService,
    _PENDING_BY_SESSION,
    apply_inline_or_spill,
    build_delegation_result_card,
)
from config.settings import settings


class FakeRegistry:
    def __init__(self):
        self.registered = []

    async def register(self, run_id, handle, session_id=None):
        self.registered.append(run_id)

    async def unregister(self, run_id):
        if run_id in self.registered:
            self.registered.remove(run_id)

    async def is_active(self, run_id):
        return run_id in self.registered

    async def cancel(self, run_id, reason=None):
        return True


def _service(tmp_path):
    return AssistantRunService(root=str(tmp_path), registry=FakeRegistry())


def _patch_env(monkeypatch, tmp_path, *, background_default=True):
    from app.auth.models import CurrentUser

    async def fake_resolve_user(context):
        return CurrentUser(id="u1", username="u1", display_name="u1")

    monkeypatch.setattr(assistant_runs_module, "resolve_task_user", fake_resolve_user)
    monkeypatch.setattr(settings, "project_id", "test", raising=False)
    monkeypatch.setattr(
        settings,
        "assistant_delegation_background_default",
        background_default,
        raising=False,
    )
    return _service(tmp_path)


def _context(session_id="sess1"):
    return SimpleNamespace(session_id=session_id, scheduled_task_context=None)


async def _execute_fast(context=None, **kwargs):
    return {"status": "success", "data": {"file_paths": []}, "summary": "完成"}


async def _wait_terminal(service, project, owner, run_id, timeout=5.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        record = service.get(project, owner, run_id)
        if record["status"] in TERMINAL:
            return record
        await asyncio.sleep(0.01)
    raise AssertionError("后台委派未在超时内结束")


def test_launch_defaults_to_background(tmp_path, monkeypatch):
    service = _patch_env(monkeypatch, tmp_path, background_default=True)

    async def scenario():
        token = begin_assistant_request("sess1", "帮我取数")
        try:
            result = await service.launch(
                _context(), _execute_fast, {"target_mode": "office", "goal": "整理"}, kind="child"
            )
        finally:
            end_assistant_request(token)
        assert result["status"] == "async_launched"
        run_id = result["data"]["run_id"]
        # 后台登记到位（交付边界吸收与会话状态卡依赖它）
        assert service.pending_background_count("sess1") == 1
        assert len(assistant_runs_module.background_runs_view("sess1")) == 1
        record = await _wait_terminal(service, "test", "u1", run_id)
        assert record["status"] == "succeeded"
        # done 回调清登记晚于文件落盘，轮询等待
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 2.0
        while loop.time() < deadline and service.pending_background_count("sess1") == 1:
            await asyncio.sleep(0.01)
        assert service.pending_background_count("sess1") == 0

    asyncio.run(scenario())


def test_launch_explicit_false_stays_synchronous(tmp_path, monkeypatch):
    service = _patch_env(monkeypatch, tmp_path, background_default=True)

    async def scenario():
        token = begin_assistant_request("sess1", "帮我取数")
        try:
            result = await service.launch(
                _context(),
                _execute_fast,
                {"target_mode": "office", "goal": "整理", "run_in_background": False},
                kind="child",
            )
        finally:
            end_assistant_request(token)
        assert result["status"] == "success"
        assert result["metadata"]["assistant_run_id"].startswith("delegation_")
        assert service.pending_background_count("sess1") == 0

    asyncio.run(scenario())


def test_launch_setting_off_restores_sync_default(tmp_path, monkeypatch):
    service = _patch_env(monkeypatch, tmp_path, background_default=False)

    async def scenario():
        token = begin_assistant_request("sess1", "帮我取数")
        try:
            result = await service.launch(
                _context(), _execute_fast, {"target_mode": "office", "goal": "整理"}, kind="child"
            )
        finally:
            end_assistant_request(token)
        # 开关关闭：不传 run_in_background 恢复旧的同步等待行为
        assert result["status"] == "success"

    asyncio.run(scenario())


def test_apply_inline_or_spill_small_result_inlined():
    results = [
        {
            "run_id": "r1",
            "status": "succeeded",
            "result": {"status": "success", "data": {"x": 1}, "summary": "ok"},
        }
    ]
    apply_inline_or_spill(results, 4000)
    assert results[0]["result"]["summary"] == "ok"


def test_apply_inline_or_spill_large_result_becomes_card():
    big = {
        "status": "success",
        "summary": "工具摘要",
        "data": {
            "file_paths": ["/registry/reports/a.csv"],
            "chart_urls": ["http://host/a.png"],
            "resource_refs": [{"resource_id": "res1", "label": "数据集"}],
            "result_envelope": {"summary": "结论" * 400},
        },
    }
    results = [{"run_id": "delegation_" + uuid4().hex, "status": "succeeded", "result": big}]
    apply_inline_or_spill(results, 100)
    card = results[0]["result"]
    assert card["truncated"] is True
    assert len(card["content"]) <= 600
    assert card["artifacts"][0] == {"kind": "file", "path": "/registry/reports/a.csv"}
    assert {"kind": "chart", "url": "http://host/a.png"} in card["artifacts"]
    assert {"kind": "resource", "resource_id": "res1", "name": "数据集"} in card["artifacts"]
    assert "manage_assistant_runs action=result" in card["full_result_pointer"]
    assert json.dumps(card, ensure_ascii=False)  # 卡片本身可序列化


def test_build_delegation_result_card_handles_unshaped_result():
    card = build_delegation_result_card({"run_id": "r9"}, "x" * 10)
    assert card["content"] == ""
    assert card["artifacts"] == []
    assert "r9" in card["full_result_pointer"]


class StubSteering:
    def __init__(self):
        self.inputs = []

    async def add_input(self, session_id, message, input_id=None):
        self.inputs.append((session_id, message))
        return True


class StubRepository:
    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    async def add_message(self, session_id, message):
        if self.fail:
            raise RuntimeError("db down")
        self.messages.append((session_id, message))
        return True


def _patch_run_repository(monkeypatch, repo):
    import app.db.session_repository as repository_module

    monkeypatch.setattr(repository_module, "get_session_repository", lambda: repo)


def _child_record(session_id="sess1", status="running", kind="child"):
    return {
        "run_id": "delegation_" + uuid4().hex,
        "kind": kind,
        "status": status,
        "source_session_id": session_id,
        "child_session_id": "child1" if kind == "child" else None,
        "target_mode": "office",
        "goal": "整理材料",
        "created_at": "2026-11-01T00:00:00+00:00",
        "updated_at": "2026-11-01T00:00:00+00:00",
    }


def test_steer_run_happy_and_guards(tmp_path, monkeypatch):
    import app.agent.runtime.steering as steering_module

    stub = StubSteering()
    monkeypatch.setattr(steering_module, "steering_registry", stub)
    repo = StubRepository()
    _patch_run_repository(monkeypatch, repo)
    service = _service(tmp_path)
    record = _child_record()
    service._save("test", "u1", record)

    async def scenario():
        token = begin_assistant_request("sess1", "原始交办")
        try:
            accepted = await service.steer_run(
                "test", "u1", session_id="sess1", run_id=record["run_id"], message="改成柱状图"
            )
            assert accepted is True
            assert stub.inputs == [("child1", "改成柱状图")]
            # 转交消息落进父会话 transcript，前端轮询快照即可见
            assert len(repo.messages) == 1
            session_id, message = repo.messages[0]
            assert session_id == "sess1"
            assert message["content"] == "改成柱状图"
            assert message["data"] == {"source": "direct_through", "run_id": record["run_id"]}
            # 归属不符
            with pytest.raises(PermissionError):
                await service.steer_run(
                    "test", "u1", session_id="other", run_id=record["run_id"], message="x"
                )
        finally:
            end_assistant_request(token)

    asyncio.run(scenario())

    # 终态拒绝（需权限域，仿 HTTP web_assistant_request）
    record["status"] = "succeeded"
    service._save("test", "u1", record)
    token = begin_assistant_request("sess1", "追问")
    try:
        with pytest.raises(ValueError):
            asyncio.run(
                service.steer_run(
                    "test", "u1", session_id="sess1", run_id=record["run_id"], message="x"
                )
            )
    finally:
        end_assistant_request(token)


def test_steer_run_persist_failure_keeps_accepted(tmp_path, monkeypatch):
    import app.agent.runtime.steering as steering_module

    monkeypatch.setattr(steering_module, "steering_registry", StubSteering())
    _patch_run_repository(monkeypatch, StubRepository(fail=True))
    service = _service(tmp_path)
    record = _child_record()
    service._save("test", "u1", record)
    token = begin_assistant_request("sess1", "追问")
    try:
        accepted = asyncio.run(
            service.steer_run(
                "test", "u1", session_id="sess1", run_id=record["run_id"], message="x"
            )
        )
        assert accepted is True
    finally:
        end_assistant_request(token)


def test_steer_run_rejects_workflow_kind(tmp_path, monkeypatch):
    import app.agent.runtime.steering as steering_module

    monkeypatch.setattr(steering_module, "steering_registry", StubSteering())
    service = _service(tmp_path)
    record = _child_record(kind="workflow")
    service._save("test", "u1", record)
    token = begin_assistant_request("sess1", "追问")
    try:
        with pytest.raises(ValueError):
            asyncio.run(
                service.steer_run(
                    "test", "u1", session_id="sess1", run_id=record["run_id"], message="x"
                )
            )
    finally:
        end_assistant_request(token)


def test_steer_run_requires_request_scope(tmp_path, monkeypatch):
    import app.agent.runtime.steering as steering_module

    monkeypatch.setattr(steering_module, "steering_registry", StubSteering())
    service = _service(tmp_path)
    record = _child_record()
    service._save("test", "u1", record)

    async def scenario():
        with pytest.raises(PermissionError):
            await service.steer_run(
                "test", "u1", session_id="sess1", run_id=record["run_id"], message="x"
            )

    asyncio.run(scenario())
