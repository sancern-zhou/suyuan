from app.agent.workflow.protocol import (
    AGENT_RESULT_ENVELOPE_SCHEMA,
    build_result_envelope,
    extract_structured_result,
    validate_result_schema,
)


def test_result_envelope_is_domain_neutral():
    result = build_result_envelope(status="completed", summary="完成")
    assert validate_result_schema(result, AGENT_RESULT_ENVELOPE_SCHEMA) == []


def test_structured_result_accepts_fenced_json_and_uses_caller_schema():
    value = extract_structured_result("结论如下：\n```json\n{\"status\": \"completed\"}\n```")
    assert value == {"status": "completed"}
    schema = {"type": "object", "required": ["findings"], "properties": {"findings": {"type": "array"}}}
    assert any(item["path"] == "$.findings" for item in validate_result_schema(value, schema))
    assert validate_result_schema({**value, "findings": []}, schema) == []


def test_caller_may_opt_into_evidence_reference_validation():
    schema = {
        "type": "object",
        "x-evidence-references": True,
        "properties": {"findings": {"type": "array"}, "evidence": {"type": "array"}},
    }
    valid = {
        "findings": [{"statement": "浓度升高", "evidence_ids": ["e1"]}],
        "evidence": [{"id": "e1", "source": "监测数据", "locator": "air.json"}],
    }
    assert validate_result_schema(valid, schema) == []
    invalid = {"findings": [{"statement": "浓度升高", "evidence_ids": ["invented"]}], "evidence": []}
    assert validate_result_schema(invalid, schema)
