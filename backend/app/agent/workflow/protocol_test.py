from app.agent.workflow.protocol import EXPERT_ANALYSIS_RESULT_SCHEMA, build_expert_analysis_task, extract_structured_result, validate_result_schema


def test_expert_task_contains_stable_contract_and_lineage():
    task = build_expert_analysis_task(question="判断污染抬升原因", decision_context="供值班研判", scope={"city": "许昌市"}, task_id="expert-1", parent_task_id="report-1")
    assert task["protocol_version"] == "workflow.v1"
    assert task["task_id"] == "expert-1"
    assert task["parent_task_id"] == "report-1"
    assert task["result_schema"] == EXPERT_ANALYSIS_RESULT_SCHEMA


def test_structured_result_accepts_fenced_json_and_reports_missing_fields():
    value = extract_structured_result("结论如下：\n```json\n{\"status\": \"completed\"}\n```")
    assert value == {"status": "completed"}
    violations = validate_result_schema(value, EXPERT_ANALYSIS_RESULT_SCHEMA)
    assert any(item["path"] == "$.findings" for item in violations)


def test_structured_result_schema_accepts_complete_result():
    value = {"status": "completed_with_gaps", "findings": [], "evidence": [], "uncertainties": [], "data_gaps": []}
    assert validate_result_schema(value, EXPERT_ANALYSIS_RESULT_SCHEMA) == []
