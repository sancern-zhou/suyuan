from app.tools.agent_tools.call_sub_agent import CallSubAgentTool


def test_call_sub_agent_exposes_optional_structured_result_fields():
    properties = CallSubAgentTool().get_function_schema()["parameters"]["properties"]
    assert {"task_id", "parent_task_id", "task_contract", "result_schema"}.issubset(properties)


def test_call_sub_agent_validates_with_caller_schema():
    schema = {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}
    result, errors = CallSubAgentTool._validate_structured_result('```json\n{"answer": "已完成"}\n```', schema)
    assert result["answer"] == "已完成"
    assert errors == []


def test_call_sub_agent_returns_model_readable_validation_errors():
    result, errors = CallSubAgentTool._validate_structured_result("没有 JSON", {"type": "object"})
    assert result is None
    assert errors[0]["path"] == "$"
