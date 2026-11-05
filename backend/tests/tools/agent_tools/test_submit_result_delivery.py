"""submit_result 结构化交付：工具与事件提取。"""

import json

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


def test_validate_structured_result_checks_deliverables_against_real_files(tmp_path):
    """交付信封的 deliverables 与真实文件机械核对，违规进同一校验错误通道（修复轮喂回）。"""
    good = tmp_path / "air.csv"
    good.write_text("time,pm25\n2026-10-01,42\n", encoding="utf-8")
    envelope = json.dumps({
        "status": "completed", "findings": [], "evidence": [],
        "deliverables": [{"path": str(good), "format": "csv", "fields": ["pm25"]}],
    }, ensure_ascii=False)
    _, errors = CallSubAgentTool._validate_structured_result(envelope, RESULT_SCHEMA)
    assert errors == []

    bad = json.dumps({
        "status": "completed", "findings": [], "evidence": [],
        "deliverables": [{"path": str(tmp_path / "absent.csv"), "format": "csv"}],
    }, ensure_ascii=False)
    _, errors = CallSubAgentTool._validate_structured_result(bad, RESULT_SCHEMA)
    assert {"path": "$.deliverables[0].path", "expected": "existing file", "got": "not found"} in errors


@pytest.mark.asyncio
async def test_submit_result_rejects_invalid_envelope_without_storing():
    """提交时校验：违规信封 success=False + 明细回传，不写入 submitted_result。

    runtime 终止判定跳过失败提交（test_submit_result_terminal），错误作为
    observation 回给子 Agent 轮内修复，不再等子会话结束才发现交付无效。
    """
    tool = SubmitResultTool(RESULT_SCHEMA)
    result = await tool.execute(result={"status": "bogus"})
    assert result["success"] is False
    assert result["status"] == "validation_failed"
    violations = result["data"]["validation_errors"]
    assert {"path": "$.status", "expected": "one of ['completed', 'completed_with_gaps']", "got": "'bogus'"} in violations
    assert {"path": "$.findings", "expected": "required", "got": "missing"} in violations
    assert tool.submitted_result is None


@pytest.mark.asyncio
async def test_submit_result_checks_deliverables_at_submit_time(tmp_path):
    """占位路径在提交时被打回（此前"结果已提交"成功假象，节点事后才判死）。"""
    tool = SubmitResultTool(RESULT_SCHEMA)
    envelope = {
        "status": "completed", "findings": [], "evidence": [],
        "deliverables": [{"path": "a", "format": "json", "fields": ["x"]}],
    }
    result = await tool.execute(result=envelope)
    assert result["success"] is False
    assert {"path": "$.deliverables[0].path", "expected": "existing file", "got": "not found"} in result["data"]["validation_errors"]
    assert tool.submitted_result is None


@pytest.mark.asyncio
async def test_submit_result_accepts_unverifiable_fields_and_real_paths(tmp_path):
    """降档后：图片声明 fields 不再导致提交失败；真实路径 + 合规信封正常交付。"""
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"\x89PNG\r\n")
    tool = SubmitResultTool(RESULT_SCHEMA)
    envelope = {
        "status": "completed", "findings": [], "evidence": [],
        "deliverables": [{"path": str(chart), "format": "png", "fields": ["AQI"]}],
    }
    result = await tool.execute(result=envelope)
    assert result["success"] is True
    assert result["data"]["submitted_result"] == envelope
    assert tool.submitted_result == envelope
