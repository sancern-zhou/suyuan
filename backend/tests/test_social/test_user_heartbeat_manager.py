from pathlib import Path

import pytest

from app.social.user_heartbeat_manager import UserHeartbeatManager


class StubHeartbeat:
    def __init__(self, *args, **kwargs):
        self.user_id = kwargs["user_id"]
        self.workspace = kwargs["workspace"]
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_restore_existing_heartbeats_resolves_stale_channel_user_id(tmp_path, monkeypatch):
    old_user_id = (
        "weixin:auto_mpunp1h4:55f85b8e2638@im.bot:"
        "o9cq804yEHqzcgkjhxwp7MKjSYec@im.wechat"
    )
    current_user_id = (
        "weixin:auto_mr1t5n08:55f85b8e2638@im.bot:"
        "o9cq804yEHqzcgkjhxwp7MKjSYec@im.wechat"
    )
    workspace = tmp_path / old_user_id.replace(":", "_")
    workspace.mkdir()
    (workspace / ".user_id").write_text(old_user_id, encoding="utf-8")
    (workspace / "HEARTBEAT.md").write_text("# tasks\n", encoding="utf-8")

    monkeypatch.setattr("app.social.user_heartbeat_manager.HeartbeatService", StubHeartbeat)

    manager = UserHeartbeatManager(
        base_workspace=tmp_path,
        on_execute_callback=lambda tasks, user_id: None,
        on_notify_callback=lambda response, user_id: None,
        user_id_resolver=lambda user_id: current_user_id if user_id == old_user_id else user_id,
    )

    restored = await manager.restore_existing_heartbeats()

    assert restored == 1
    assert await manager.get_all_cached_users() == [current_user_id]
    assert (workspace / ".user_id").read_text(encoding="utf-8") == current_user_id
