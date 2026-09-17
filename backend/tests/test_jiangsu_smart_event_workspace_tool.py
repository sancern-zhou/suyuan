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
