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
    # 回传信封供 runtime 识别交付边界（submit_result 即刻终止本轮）
    assert result["data"]["submitted_result"] == tool.submitted_result


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


def test_extract_submitted_result_reads_real_runtime_tool_use_event():
    """生产 runtime 下发的是 tool_use（data.tool_name/data.input），不是 tool_call。"""
    tool = CallSubAgentTool.__new__(CallSubAgentTool)
    events = [
        {
            "type": "tool_use",
            "data": {
                "tool_name": "submit_result",
                "input": {"result": {"status": "completed", "findings": [{"id": 1}]}},
            },
        },
    ]
    assert tool._extract_submitted_result(events) == {
        "status": "completed",
        "findings": [{"id": 1}],
    }


def test_extract_submitted_result_reads_tool_result_envelope():
    tool = CallSubAgentTool.__new__(CallSubAgentTool)
    events = [
        {
            "type": "tool_result",
            "data": {
                "tool_name": "submit_result",
                "result": {
                    "success": True,
                    "data": {"submitted_result": {"status": "completed_with_gaps"}},
                },
            },
        },
    ]
    assert tool._extract_submitted_result(events) == {"status": "completed_with_gaps"}


def test_extract_submitted_result_falls_back_to_submit_tool():
    tool = CallSubAgentTool.__new__(CallSubAgentTool)
    submit_tool = SubmitResultTool(RESULT_SCHEMA)
    submit_tool.submitted_result = {"status": "completed", "findings": [], "evidence": []}
    assert tool._extract_submitted_result([], submit_tool) == submit_tool.submitted_result


def test_fixed_workflow_deliver_progress_targets_last_phase():
    progress = CallSubAgentTool._fixed_workflow_deliver_progress("query_monitoring_city")
    assert progress is not None
    from app.agent.workflow.mode_workflows import get_mode_workflow

    definition = get_mode_workflow("query_monitoring_city")
    assert definition.phases[progress["phase_index"]].name == "deliver"
    assert CallSubAgentTool._fixed_workflow_deliver_progress("expert_analysis") is None


def test_submit_result_injection_follows_child_registry_assignment():
    """回归守卫：注入点必须位于 child_registry 赋值之后（曾因前向引用炸过生产）。"""
    import inspect

    from app.tools.agent_tools import call_sub_agent as mod

    src = inspect.getsource(mod)
    assert src.index("child_registry = capability_policy.filter_registry") < src.index(
        'child_registry["submit_result"] = submit_tool'
    )
