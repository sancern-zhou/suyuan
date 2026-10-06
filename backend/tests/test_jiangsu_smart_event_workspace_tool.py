"""Tests for the Jiangsu smart-event workspace agent tool."""

import pytest

from app.tools.jiangsu.smart_event_workspace import JiangsuSmartEventWorkspaceTool


class _FakeService:
    def __init__(self, event=None):
        self._event = event

    async def get_event(self, event_id):
        assert event_id == "evt-1"
        return self._event


@pytest.mark.asyncio
async def test_show_operation_history_returns_operation_records(monkeypatch):
    event = {
        "event_id": "evt-1",
        "event_status": "已反馈",
        "operation_records": [
            {
                "operation_id": "operation:a",
                "action": "dispatch_order",
                "summary": "已派单维修",
                "actor": {"user_id": "u1", "username": "张三"},
                "created_at": "2026-09-17T10:00:00+08:00",
                "details": {"order_type": "Fault", "assignee": "李四"},
            },
            "not-a-dict",
        ],
    }
    monkeypatch.setattr(
        "app.tools.jiangsu.smart_event_workspace.JiangsuSmartEventService",
        lambda: _FakeService(event),
    )
    result = await JiangsuSmartEventWorkspaceTool().execute(
        command="show_operation_history", event_id="evt-1"
    )

    assert result["success"] is True
    assert result["data"]["event_status"] == "已反馈"
    assert result["data"]["operation_records"] == [
        {
            "operation_id": "operation:a",
            "action": "dispatch_order",
            "summary": "已派单维修",
            "actor": "张三",
            "created_at": "2026-09-17T10:00:00+08:00",
            "details": {"order_type": "Fault", "assignee": "李四"},
        }
    ]
    assert result["data"]["ui_command"]["type"] == "show_operation_history"
    assert "1 条处置记录" in result["summary"]


@pytest.mark.asyncio
async def test_show_operation_history_reports_empty_records(monkeypatch):
    monkeypatch.setattr(
        "app.tools.jiangsu.smart_event_workspace.JiangsuSmartEventService",
        lambda: _FakeService({"event_id": "evt-1", "event_status": "待复核", "operation_records": []}),
    )
    result = await JiangsuSmartEventWorkspaceTool().execute(
        command="show_operation_history", event_id="evt-1"
    )

    assert result["success"] is True
    assert result["data"]["operation_records"] == []
    assert "暂无处置记录" in result["summary"]


@pytest.mark.asyncio
async def test_show_operation_history_fails_for_missing_event(monkeypatch):
    monkeypatch.setattr(
        "app.tools.jiangsu.smart_event_workspace.JiangsuSmartEventService",
        lambda: _FakeService(None),
    )
    result = await JiangsuSmartEventWorkspaceTool().execute(
        command="show_operation_history", event_id="evt-1"
    )

    assert result["success"] is False
    assert "未找到事件" in result["summary"]


@pytest.mark.asyncio
async def test_show_operation_history_requires_event_id():
    result = await JiangsuSmartEventWorkspaceTool().execute(command="show_operation_history")

    assert result["success"] is False
    assert "event_id" in result["summary"]


@pytest.mark.asyncio
async def test_open_event_detail_returns_alarm_content_and_clue_texts(monkeypatch):
    event = {
        "event_id": "evt-1",
        "event_name": "示例站仪器报警线索待研判事件",
        "site_name": "示例站",
        "event_status": "未研判",
        "alarm_content": "PM2.5-TH-2000PM-采样流量的值为15.942L/min，低于限定值【16.199】",
        "primary_clue_tag": "仪器状态超上下限报警",
        "source_alarm_rule_type": "仪器状态超上下限报警",
        "clue_tags": [
            {"tag_id": "a:alarm", "tag_display_text": "报警：仪器状态超上下限报警（采样流量低于限定值）"},
            {"tag_id": "b:alarm", "tag_display_text": "报警：偏差报警（PM2.5 偏差 34.29%）"},
            "not-a-dict",
        ],
    }
    monkeypatch.setattr(
        "app.tools.jiangsu.smart_event_workspace.JiangsuSmartEventService",
        lambda: _FakeService(event),
    )
    result = await JiangsuSmartEventWorkspaceTool().execute(
        command="open_event_detail", event_id="evt-1"
    )

    assert result["success"] is True
    event_payload = result["data"]["event"]
    assert event_payload["alarm_content"] == "PM2.5-TH-2000PM-采样流量的值为15.942L/min，低于限定值【16.199】"
    assert event_payload["clue_texts"] == [
        "报警：仪器状态超上下限报警（采样流量低于限定值）",
        "报警：偏差报警（PM2.5 偏差 34.29%）",
    ]
    assert "alarm_content" in result["summary"]
    assert result["data"]["ui_command"]["type"] == "open_event_detail"


@pytest.mark.asyncio
async def test_open_event_detail_fails_for_missing_event(monkeypatch):
    class _MissingService:
        async def get_event(self, event_id):
            return None

    monkeypatch.setattr(
        "app.tools.jiangsu.smart_event_workspace.JiangsuSmartEventService",
        lambda: _MissingService(),
    )
    result = await JiangsuSmartEventWorkspaceTool().execute(
        command="open_event_detail", event_id="evt-404"
    )

    assert result["success"] is False
    assert "未找到事件" in result["summary"]


class _FakeListService:
    async def list_events(self, **kwargs):
        return {
            "events": [
                {
                    "event_id": "evt-1",
                    "event_name": "示例站偏差报警线索待研判事件",
                    "alarm_content": "数据偏差：PM2.5浓度偏差34.29%，超出20%。",
                    "primary_clue_tag": "偏差报警",
                    "clue_tags": [
                        {"tag_id": "t1", "tag_display_text": "报警：偏差报警（PM2.5 偏差 34.29%）"},
                        {"tag_id": "t2", "tag_display_text": "数据：数据突升（PM10 由 61 变为 90）"},
                    ],
                }
            ],
            "total": 1,
        }


@pytest.mark.asyncio
async def test_event_list_summary_carries_alarm_content_and_clue_texts(monkeypatch):
    monkeypatch.setattr("app.tools.jiangsu.smart_event_workspace.demo_freeze_active", lambda: False)
    monkeypatch.setattr(
        "app.tools.jiangsu.smart_event_workspace.JiangsuSmartEventService",
        lambda: _FakeListService(),
    )
    result = await JiangsuSmartEventWorkspaceTool().execute(command="show_event_list")

    assert result["success"] is True
    event = result["data"]["events"][0]
    assert event["alarm_content"] == "数据偏差：PM2.5浓度偏差34.29%，超出20%。"
    assert event["primary_clue_tag"] == "偏差报警"
    assert event["clue_texts"] == [
        "报警：偏差报警（PM2.5 偏差 34.29%）",
        "数据：数据突升（PM10 由 61 变为 90）",
    ]
    # 原始标签结构不进列表摘要，只保留文本投影
    assert "clue_tags" not in event
