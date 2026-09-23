from app.agent.workflow.protocol import EXPERT_ANALYSIS_RESULT_SCHEMA
from app.tools.agent_tools.call_sub_agent import CallSubAgentTool


def test_call_sub_agent_exposes_workflow_contract_fields():
    properties = CallSubAgentTool().get_function_schema()["parameters"]["properties"]
    assert {"task_id", "parent_task_id", "task_contract", "result_schema"}.issubset(properties)


def test_call_sub_agent_validates_and_extracts_expert_result():
    answer = "```json\n{\"status\": \"completed\", \"findings\": [], \"evidence\": [], \"uncertainties\": [], \"data_gaps\": []}\n```"
    result, errors = CallSubAgentTool._validate_structured_result(answer, EXPERT_ANALYSIS_RESULT_SCHEMA)
    assert result["status"] == "completed"
    assert errors == []


def test_call_sub_agent_returns_model_readable_validation_errors():
    result, errors = CallSubAgentTool._validate_structured_result("没有 JSON", EXPERT_ANALYSIS_RESULT_SCHEMA)
    assert result is None
    assert errors[0]["path"] == "$"
