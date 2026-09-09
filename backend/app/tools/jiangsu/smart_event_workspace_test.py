import pytest

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
