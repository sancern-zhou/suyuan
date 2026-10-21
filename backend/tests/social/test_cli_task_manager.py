import asyncio
import sys

import pytest

from app.social.events import OutboundMessage


class DummyMessageBus:
    def __init__(self):
        self.messages = []

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        self.messages.append(msg)


@pytest.mark.asyncio
async def test_cli_task_manager_completes_and_notifies(tmp_path):
    from app.social.cli_task_manager import CliTaskManager
    from app.social.cli_task_store import CliTaskStore

    store = CliTaskStore(json_path=str(tmp_path / "cli_tasks.json"))
    bus = DummyMessageBus()
    manager = CliTaskManager(task_store=store, message_bus=bus)

    result = await manager.start_task(
        social_user_id="weixin:bot:user1",
        origin_info={"channel": "weixin", "chat_id": "user1", "sender_id": "user1"},
        provider="codex",
        session_name="demo",
        cwd=str(tmp_path),
        args=[sys.executable, "-c", "print('background ok')"],
        stdin_text="",
        timeout=5,
        label="后台CLI测试",
        parser=lambda stdout, stderr: (stdout.strip(), None),
    )

    assert result["success"] is True
    task_id = result["task_id"]

    for _ in range(50):
        task = await manager.get_task(task_id)
        if task and task["status"] == "completed":
            break
        await asyncio.sleep(0.05)

    task = await manager.get_task(task_id)
    assert task["status"] == "completed"
    assert task["progress"] == 1.0
    assert task["result"] == "background ok"
    assert task["exit_code"] == 0
    assert "background ok" in task["stdout_tail"]
    assert bus.messages
    assert "后台CLI任务完成" in bus.messages[0].content


@pytest.mark.asyncio
async def test_cli_task_manager_can_cancel_running_process(tmp_path):
    from app.social.cli_task_manager import CliTaskManager
    from app.social.cli_task_store import CliTaskStore

    store = CliTaskStore(json_path=str(tmp_path / "cli_tasks.json"))
    manager = CliTaskManager(task_store=store)

    result = await manager.start_task(
        social_user_id="weixin:bot:user1",
        origin_info={"channel": "weixin", "chat_id": "user1", "sender_id": "user1"},
        provider="codex",
        session_name="long",
        cwd=str(tmp_path),
        args=[sys.executable, "-c", "import time; time.sleep(30)"],
        stdin_text="",
        timeout=60,
        label="可取消任务",
        parser=lambda stdout, stderr: (stdout.strip(), None),
    )

    task_id = result["task_id"]
    cancelled = await manager.cancel_task(task_id)

    assert cancelled["success"] is True

    for _ in range(50):
        task = await manager.get_task(task_id)
        if task and task["status"] == "cancelled":
            break
        await asyncio.sleep(0.05)

    task = await manager.get_task(task_id)
    assert task["status"] == "cancelled"
    assert task["error"] == "任务已取消"
