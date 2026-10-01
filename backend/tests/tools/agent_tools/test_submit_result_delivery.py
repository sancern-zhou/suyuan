"""submit_result 结构化交付：工具与事件提取。"""

import pytest

from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
from app.tools.agent_tools.submit_result_tool import SubmitResultTool, envelope_parameters


RESULT_SCHEMA = {
    "type": "object",
    "required": ["status", "findings", "evidence"],
    "properties": {
        "status": {"type": "string", "enum": ["completed", "completed_with_gaps"]},
        "findings": {"type": "array"},
        "evidence": {"type": "array"},
    },
}


def test_envelope_parameters_propagate_schema_shape():
    params = envelope_parameters(RESULT_SCHEMA)
    result_param = params["properties"]["result"]
    assert result_param["required"] == ["status", "findings", "evidence"]
    assert "findings" in result_param["properties"]
    assert params["required"] == ["result"]


@pytest.mark.asyncio
async def test_submit_result_tool_stores_payload():
    tool = SubmitResultTool(RESULT_SCHEMA)
    result = await tool.execute(result={"status": "completed", "findings": [], "evidence": []})
    assert result["success"] is True
    assert tool.submitted_result["status"] == "completed"


def test_extract_submitted_result_prefers_latest_call():
    tool = CallSubAgentTool.__new__(CallSubAgentTool)
    events = [
        {"type": "tool_call", "tool_name": "execute_python", "args": {"code": "print(1)"}},
        {"type": "tool_call", "tool_name": "submit_result", "args": {"result": {"status": "completed", "v": 1}}},
        {"type": "tool_result", "content": "ok"},
        {"type": "tool_call", "tool_name": "submit_result", "args": {"result": {"status": "completed_with_gaps", "v": 2}}},
    ]
    submitted = tool._extract_submitted_result(events)
    assert submitted == {"status": "completed_with_gaps", "v": 2}


def test_extract_submitted_result_returns_none_without_submission():
    tool = CallSubAgentTool.__new__(CallSubAgentTool)
    events = [{"type": "tool_call", "tool_name": "execute_python", "args": {"code": "print(1)"}}]
    assert tool._extract_submitted_result(events) is None


def test_extract_submitted_result_tolerates_flat_payload():
    tool = CallSubAgentTool.__new__(CallSubAgentTool)
    events = [
        {"type": "tool_call", "name": "submit_result", "arguments": {"status": "completed", "findings": []}}
    ]
    assert tool._extract_submitted_result(events) == {"status": "completed", "findings": []}
