import pytest

from app.social.message_bus_singleton import reset_current_context, set_current_context
from app.tools.social.schedule_task.tool import ScheduleTaskTool


class FakeHeartbeat:
    def __init__(self):
        self.tasks = []

    def add_task(self, **kwargs):
        self.tasks.append(kwargs)


class FakeHeartbeatManager:
    def __init__(self):
        self.heartbeat = FakeHeartbeat()
        self.user_ids = []

    async def get_user_heartbeat(self, user_id):
        self.user_ids.append(user_id)
        return self.heartbeat


@pytest.mark.asyncio
async def test_schedule_task_list_returns_current_users_enabled_and_disabled_tasks(tmp_path, monkeypatch):
    from app.social import user_preferences as user_preferences_module

    social_dir = tmp_path / "social"
    monkeypatch.setattr(user_preferences_module, "get_social_dir", lambda: social_dir)

    user_a_dir = social_dir / "heartbeat" / "weixin_bot_user_a"
    user_a_dir.mkdir(parents=True)
    (user_a_dir / "HEARTBEAT.md").write_text(
        """
# 心跳任务列表

- name: 污染告警故障诊断结论推送
  schedule: "30 * * * *"
  description: 静默生成诊断结论
  enabled: false
  channels: ["weixin"]
  manual_mode: social

- name: 运城市告警溯源报告推送
  schedule: "10 * * * *"
  description: 生成并推送溯源报告
  enabled: true
  channels: ["weixin"]
  manual_mode: social
  next_run_at: "2026-07-09T16:10:00+08:00"
""",
        encoding="utf-8",
    )

    user_b_dir = social_dir / "heartbeat" / "weixin_bot_user_b"
    user_b_dir.mkdir(parents=True)
    (user_b_dir / "HEARTBEAT.md").write_text(
        """
- name: 其他用户任务
  schedule: "0 9 * * *"
  description: 不应出现在 user_a 的列表里
  enabled: true
""",
        encoding="utf-8",
    )

    tokens = set_current_context(channel="weixin", bot_account="bot", chat_id="user_a")
    try:
        result = await ScheduleTaskTool().execute(action="list")
    finally:
        reset_current_context(tokens)

    assert result["success"] is True
    assert set(result) == {"status", "success", "data", "metadata", "summary"}
    assert result["data"]["enabled_count"] == 1
    assert result["data"]["disabled_count"] == 1
    assert [task["name"] for task in result["data"]["tasks"]] == [
        "污染告警故障诊断结论推送",
        "运城市告警溯源报告推送",
    ]
    assert result["data"]["tasks"][0]["enabled"] is False
    assert result["data"]["tasks"][1]["enabled"] is True
    assert result["data"]["tasks"][1]["manual_mode"] == "social"
    assert result["metadata"]["schema_version"] == "v1.0"
    assert result["metadata"]["action"] == "list"
    assert "heartbeat_file_path" not in result["data"]
    assert "其他用户任务" not in result["summary"]


@pytest.mark.asyncio
async def test_schedule_task_create_returns_standard_result_without_top_level_business_fields():
    manager = FakeHeartbeatManager()
    tokens = set_current_context(channel="weixin", bot_account="bot", chat_id="user_a")
    try:
        result = await ScheduleTaskTool(user_heartbeat_manager=manager).execute(
            action="create",
            task_description="每小时推送污染告警性质判定结果",
            schedule="11 * * * *",
        )
    finally:
        reset_current_context(tokens)

    assert set(result) == {"status", "success", "data", "metadata", "summary"}
    assert result["success"] is True
    assert result["data"]["task_name"] == "每小时推送污染告警性质判定结果"
    assert result["data"]["schedule"] == "11 * * * *"
    assert result["data"]["channels"] == ["weixin"]
    assert result["data"]["user_id"] == "weixin:bot:user_a"
    assert result["metadata"]["schema_version"] == "v1.0"
    assert result["metadata"]["action"] == "create"
    assert manager.user_ids == ["weixin:bot:user_a"]
    assert manager.heartbeat.tasks == [
        {
            "name": "每小时推送污染告警性质判定结果",
            "schedule": "11 * * * *",
            "description": "每小时推送污染告警性质判定结果",
            "channels": ["weixin"],
        }
    ]


@pytest.mark.asyncio
async def test_schedule_task_disable_only_updates_current_users_named_task(tmp_path, monkeypatch):
    from app.social import user_preferences as user_preferences_module

    social_dir = tmp_path / "social"
    monkeypatch.setattr(user_preferences_module, "get_social_dir", lambda: social_dir)

    user_a_dir = social_dir / "heartbeat" / "weixin_bot_user_a"
    user_a_dir.mkdir(parents=True)
    user_a_file = user_a_dir / "HEARTBEAT.md"
    user_a_file.write_text(
        """
- name: 污染告警性质判定
  schedule: "11 * * * *"
  description: 每小时推送污染告警性质判定结果
  enabled: true
  channels: ["weixin"]

- name: 运城市告警溯源报告推送
  schedule: "10 * * * *"
  description: 生成并推送溯源报告
  enabled: true
  channels: ["weixin"]
""",
        encoding="utf-8",
    )

    user_b_dir = social_dir / "heartbeat" / "weixin_bot_user_b"
    user_b_dir.mkdir(parents=True)
    user_b_file = user_b_dir / "HEARTBEAT.md"
    user_b_file.write_text(
        """
- name: 污染告警性质判定
  schedule: "11 * * * *"
  description: 其他用户的任务
  enabled: true
  channels: ["weixin"]
""",
        encoding="utf-8",
    )

    tokens = set_current_context(channel="weixin", bot_account="bot", chat_id="user_a")
    try:
        result = await ScheduleTaskTool().execute(action="disable", task_name="污染告警性质判定")
    finally:
        reset_current_context(tokens)

    assert set(result) == {"status", "success", "data", "metadata", "summary"}
    assert result["success"] is True
    assert result["metadata"]["action"] == "disable"
    assert result["data"]["task_name"] == "污染告警性质判定"
    assert result["data"]["enabled"] is False
    assert "heartbeat_file_path" not in result["data"]

    user_a_content = user_a_file.read_text(encoding="utf-8")
    user_b_content = user_b_file.read_text(encoding="utf-8")
    assert "name: 污染告警性质判定\n  schedule: \"11 * * * *\"\n  description: 每小时推送污染告警性质判定结果\n  enabled: false" in user_a_content
    assert "name: 运城市告警溯源报告推送\n  schedule: \"10 * * * *\"\n  description: 生成并推送溯源报告\n  enabled: true" in user_a_content
    assert "description: 其他用户的任务\n  enabled: true" in user_b_content


@pytest.mark.asyncio
async def test_schedule_task_enable_and_delete_manage_current_users_task_file(tmp_path, monkeypatch):
    from app.social import user_preferences as user_preferences_module

    social_dir = tmp_path / "social"
    monkeypatch.setattr(user_preferences_module, "get_social_dir", lambda: social_dir)

    user_dir = social_dir / "heartbeat" / "weixin_bot_user_a"
    user_dir.mkdir(parents=True)
    heartbeat_file = user_dir / "HEARTBEAT.md"
    heartbeat_file.write_text(
        """
- name: 污染告警性质判定
  schedule: "11 * * * *"
  description: 每小时推送污染告警性质判定结果
  enabled: false
  channels: ["weixin"]

- name: 运城市告警溯源报告推送
  schedule: "10 * * * *"
  description: 生成并推送溯源报告
  enabled: true
  channels: ["weixin"]
""",
        encoding="utf-8",
    )

    tokens = set_current_context(channel="weixin", bot_account="bot", chat_id="user_a")
    try:
        enable_result = await ScheduleTaskTool().execute(action="enable", task_name="污染告警性质判定")
        delete_result = await ScheduleTaskTool().execute(action="delete", task_name="污染告警性质判定")
    finally:
        reset_current_context(tokens)

    assert enable_result["success"] is True
    assert enable_result["data"]["enabled"] is True
    assert "heartbeat_file_path" not in enable_result["data"]

    assert delete_result["success"] is True
    assert delete_result["metadata"]["action"] == "delete"
    assert delete_result["data"]["task_name"] == "污染告警性质判定"
    assert "enabled" not in delete_result["data"]
    assert "heartbeat_file_path" not in delete_result["data"]

    content = heartbeat_file.read_text(encoding="utf-8")
    assert "污染告警性质判定" not in content
    assert "运城市告警溯源报告推送" in content
