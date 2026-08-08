from pathlib import Path

import pytest

from app.tools.social.cli_session.tool import CliSessionTool
from app.tools.social.wait_task.tool import WaitTaskTool


@pytest.mark.asyncio
async def test_cli_session_background_returns_task_id(monkeypatch, tmp_path):
    tool = CliSessionTool()

    monkeypatch.setattr(tool, "_resolve_binary", lambda provider: "codex-bin")
    monkeypatch.setattr(tool, "_resolve_cwd", lambda cwd: Path(tmp_path))

    async def fake_start_task(**kwargs):
        return {
            "status": "success",
            "success": True,
            "task_id": "cli_task_123",
            "label": "demo",
        }

    class FakeManager:
        start_task = staticmethod(fake_start_task)

    monkeypatch.setattr(tool, "_get_cli_task_manager", lambda: FakeManager())

    result = await tool.execute(
        action="send",
        provider="codex",
        session_name="demo",
        prompt="do work",
        cwd=str(tmp_path),
        background=True,
    )

    assert result["success"] is True
    assert result["data"]["task_id"] == "cli_task_123"
    assert result["data"]["background"] is True
    assert "后台" in result["summary"]


@pytest.mark.asyncio
async def test_cli_session_defaults_to_background(monkeypatch, tmp_path):
    tool = CliSessionTool()

    monkeypatch.setattr(tool, "_resolve_binary", lambda provider: "codex-bin")
    monkeypatch.setattr(tool, "_resolve_cwd", lambda cwd: Path(tmp_path))

    async def fake_start_task(**kwargs):
        return {
            "status": "success",
            "success": True,
            "task_id": "cli_task_default",
            "label": "demo",
        }

    class FakeManager:
        start_task = staticmethod(fake_start_task)

    monkeypatch.setattr(tool, "_get_cli_task_manager", lambda: FakeManager())

    result = await tool.execute(
        action="send",
        provider="codex",
        session_name="demo",
        prompt="do work",
        cwd=str(tmp_path),
    )

    assert result["success"] is True
    assert result["data"]["task_id"] == "cli_task_default"
    assert result["data"]["background"] is True


@pytest.mark.asyncio
async def test_cli_session_task_status_delegates_to_manager(monkeypatch):
    tool = CliSessionTool()

    async def fake_get_task(task_id):
        return {"task_id": task_id, "status": "running"}

    class FakeManager:
        get_task = staticmethod(fake_get_task)

    monkeypatch.setattr(tool, "_get_cli_task_manager", lambda: FakeManager())

    result = await tool.execute(action="task_status", task_id="cli_task_123")

    assert result["success"] is True
    assert result["data"]["task_id"] == "cli_task_123"
    assert result["data"]["status"] == "running"


@pytest.mark.asyncio
async def test_wait_task_returns_when_cli_task_completes(monkeypatch):
    tool = WaitTaskTool()
    calls = []

    async def fake_get_task(task_id):
        calls.append(task_id)
        if len(calls) == 1:
            return {"task_id": task_id, "status": "running"}
        return {"task_id": task_id, "status": "completed", "result": "done"}

    async def fake_sleep(_seconds):
        return None

    class FakeManager:
        get_task = staticmethod(fake_get_task)

    monkeypatch.setattr(tool, "_get_manager", lambda task_type: FakeManager())
    monkeypatch.setattr("app.tools.social.wait_task.tool.asyncio.sleep", fake_sleep)

    result = await tool.execute(
        task_id="cli_task_123",
        wait_timeout=5,
        wait_interval=1,
    )

    assert result["success"] is True
    assert result["data"]["task_id"] == "cli_task_123"
    assert result["data"]["task_type"] == "cli"
    assert result["data"]["status"] == "completed"
    assert result["data"]["wait_timed_out"] is False
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_wait_task_returns_current_state_on_timeout(monkeypatch):
    tool = WaitTaskTool()
    calls = []

    async def fake_get_task(task_id):
        calls.append(task_id)
        return {"task_id": task_id, "status": "running"}

    async def fake_sleep(_seconds):
        return None

    class FakeManager:
        get_task = staticmethod(fake_get_task)

    monkeypatch.setattr(tool, "_get_manager", lambda task_type: FakeManager())
    monkeypatch.setattr("app.tools.social.wait_task.tool.asyncio.sleep", fake_sleep)

    result = await tool.execute(
        task_id="cli_task_123",
        wait_timeout=0.01,
        wait_interval=1,
    )

    assert result["success"] is True
    assert result["data"]["task_id"] == "cli_task_123"
    assert result["data"]["status"] == "running"
    assert result["data"]["wait_timed_out"] is True
    assert len(calls) >= 1


@pytest.mark.asyncio
async def test_wait_task_auto_detects_spawn_task(monkeypatch):
    tool = WaitTaskTool()
    seen_task_types = []

    async def fake_get_task(task_id):
        return {"task_id": task_id, "status": "completed", "result": "spawn done"}

    class FakeManager:
        get_task = staticmethod(fake_get_task)

    def fake_get_manager(task_type):
        seen_task_types.append(task_type)
        return FakeManager()

    monkeypatch.setattr(tool, "_get_manager", fake_get_manager)

    result = await tool.execute(task_id="spawn_task_20260604_120000_abcd1234")

    assert result["success"] is True
    assert result["data"]["task_type"] == "spawn"
    assert seen_task_types == ["spawn"]
