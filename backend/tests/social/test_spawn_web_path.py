# -*- coding: utf-8 -*-
"""spawn/wait_task 的 Web 助手会话路径测试（A4c）。

社交路径已有生产验证；本文件聚焦新增能力：
- 社交上下文缺失时回退到服务端认证身份（不允许匿名派发）；
- 归属键 web:assistant:{owner} 在 spawn 与 wait_task 两侧一致（原始冒号形态）；
- owner 记忆身份透传给 SubagentManager。
"""
import asyncio
from types import SimpleNamespace

from app.tools.social.spawn.tool import SpawnTool
from app.tools.social.wait_task.tool import WaitTaskTool


class _FakeManager:
    def __init__(self):
        self.calls = []

    async def spawn_subagent(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": True, "task_id": "spawn_task_1", "label": "测试任务"}


def _no_social_context(monkeypatch):
    """模拟 Web 会话：社交消息总线上下文为空。"""
    import app.social.message_bus_singleton as bus

    monkeypatch.setattr(bus, "get_current_chat_id", lambda: None)
    monkeypatch.setattr(bus, "get_current_channel", lambda: None)
    monkeypatch.setattr(bus, "get_current_bot_account", lambda: None)


def _web_context(owner="zhangsan", user_identifier="web:abc123"):
    return SimpleNamespace(
        scheduled_task_context=None,
        user_identifier=user_identifier,
        runtime_metadata={"authenticated_account": {"username": owner}},
    )


def test_spawn_web_fallback_uses_authenticated_owner(monkeypatch):
    _no_social_context(monkeypatch)
    tool = SpawnTool()
    manager = _FakeManager()
    monkeypatch.setattr(SpawnTool, "manager", property(lambda self: manager))

    result = asyncio.run(
        tool.execute(
            context=_web_context(),
            task="对广州站做 PMF 源解析",
            label="PMF",
        )
    )
    assert result["success"] is True
    call = manager.calls[0]
    assert call["social_user_id"] == "web:assistant:zhangsan"
    assert call["origin_channel"] == "web"
    assert call["origin_chat_id"] == "zhangsan"
    assert call["owner_user_identifier"] == "web:abc123"


def test_spawn_web_rejected_without_authenticated_owner(monkeypatch):
    _no_social_context(monkeypatch)
    tool = SpawnTool()
    manager = _FakeManager()
    monkeypatch.setattr(SpawnTool, "manager", property(lambda self: manager))

    # 无服务端认证身份（runtime_metadata 缺 authenticated_account）→ 拒绝
    result = asyncio.run(
        tool.execute(
            context=SimpleNamespace(
                scheduled_task_context=None,
                user_identifier="web:abc123",
                runtime_metadata={},
            ),
            task="匿名任务",
        )
    )
    assert result["success"] is False
    assert "身份" in str(result.get("error", ""))
    assert manager.calls == []


def test_wait_task_user_key_matches_spawn_web_identity(monkeypatch):
    """wait_task 的 Web 归属键必须与 spawn 存储的 social_user_id 完全一致。"""
    _no_social_context(monkeypatch)
    key = WaitTaskTool()._get_user_key(_web_context())
    assert key == "web:assistant:zhangsan"


def test_wait_task_user_key_keeps_raw_colons_for_social(monkeypatch):
    """社交路径归属键保留原始冒号（此前 _safe_name 导致校验恒失败）。"""
    import app.social.message_bus_singleton as bus

    monkeypatch.setattr(bus, "get_current_chat_id", lambda: "chat-9")
    monkeypatch.setattr(bus, "get_current_channel", lambda: "weixin")
    monkeypatch.setattr(bus, "get_current_bot_account", lambda: "default")
    key = WaitTaskTool()._get_user_key(context=None)
    assert key == "weixin:default:chat-9"
