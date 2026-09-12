import pytest

from app.services.jiangsu_smart_event import JiangsuSmartEventService
from app.tools.jiangsu.smart_event_workspace import JiangsuSmartEventWorkspaceTool


@pytest.mark.asyncio
async def test_workspace_tool_returns_structured_detail_command():
    result = await JiangsuSmartEventWorkspaceTool().execute(
        command="open_event_detail",
        event_id="alarm:12",
        focus="alarm",
    )
    assert result["success"] is True
    assert result["data"]["ui_command"] == {
        "type": "open_event_detail",
        "event_id": "alarm:12",
        "focus": "alarm",
    }


@pytest.mark.asyncio
async def test_workspace_tool_rejects_missing_detail_id():
    result = await JiangsuSmartEventWorkspaceTool().execute(command="open_event_detail")
    assert result["success"] is False


@pytest.mark.asyncio
async def test_workspace_tool_requires_event_for_evidence_and_history():
    tool = JiangsuSmartEventWorkspaceTool()
    for command in ("focus_evidence", "show_operation_history"):
        result = await tool.execute(command=command)
        assert result["success"] is False


@pytest.mark.asyncio
async def test_workspace_tool_resolves_user_filters_and_returns_event_ids(monkeypatch):
    captured = {}

    async def fake_list_events(self, *, start_time, end_time, status=None, keyword=None,
                               event_type=None, level=None, limit=20, page=1,
                               summary=True, refresh=False):
        captured.update(
            start_time=start_time, end_time=end_time, status=status, keyword=keyword,
            event_type=event_type, level=level,
        )
        return {
            "events": [{
                "event_id": "alarm:1", "event_name": "常柴站断数", "site_name": "常柴站",
                "event_status": "待研判", "ai_event_type": "数据断数", "ai_suggested_level": "重要",
            }],
            "total": 1,
        }

    monkeypatch.setattr(JiangsuSmartEventService, "list_events", fake_list_events)
    result = await JiangsuSmartEventWorkspaceTool().execute(
        command="filter_event_list",
        filters={"station": "常柴站", "ai_event_type": "数据断数", "severity": "重要", "event_status": "待研判"},
    )
    assert result["success"] is True
    # 用户习惯字段（站点/类型/等级/状态）被归一化进查询契约，Agent 无需提供 event_id
    assert captured["keyword"] == "常柴站"
    assert captured["event_type"] == "数据断数"
    assert captured["level"] == "重要"
    assert captured["status"] == "待研判"
    # 工具把查询结果（含 event_id）回传给 Agent，供后续精确命令使用
    assert result["data"]["events"][0]["event_id"] == "alarm:1"
    assert result["data"]["ui_command"]["filters"]["keyword"] == "常柴站"
    assert result["data"]["ui_command"]["filters"]["level"] == "重要"


@pytest.mark.asyncio
async def test_workspace_tool_open_task_resolves_event_tasks(monkeypatch):
    monkeypatch.setattr(
        JiangsuSmartEventService,
        "list_tasks",
        lambda self, *, event_id, limit: [{
            "task_id": "task:1",
            "scheduled_task_id": "jiangsu_smart_event_ai_judgment",
            "event_id": event_id,
        }],
    )
    result = await JiangsuSmartEventWorkspaceTool().execute(command="open_task", event_id="alarm:9")
    assert result["success"] is True
    assert result["data"]["ui_command"]["task_id"] == "task:1"
    assert result["data"]["ui_command"]["event_id"] == "alarm:9"
    assert result["data"]["tasks"][0]["scheduled_task_id"] == "jiangsu_smart_event_ai_judgment"


@pytest.mark.asyncio
async def test_workspace_tool_open_task_without_any_id_fails():
    result = await JiangsuSmartEventWorkspaceTool().execute(command="open_task")
    assert result["success"] is False
