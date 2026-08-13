def test_non_standard_failure_result_gets_failed_status():
    from app.agent.tool_adapter import _standardize_tool_result

    result = _standardize_tool_result(
        "browser",
        {
            "success": False,
            "error": "Task failed",
            "summary": "Task failed",
        },
        execution_time=0.1,
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["metadata"]["tool_name"] == "browser"


def test_non_standard_failure_preserves_error_contract_fields():
    from app.agent.tool_adapter import _standardize_tool_result

    result = _standardize_tool_result(
        "browser",
        {
            "success": False,
            "error": "error_code=UNKNOWN_REF | required_action=snapshot",
            "error_code": "UNKNOWN_REF",
            "required_action": "snapshot",
            "current_refs": ["f0:e1"],
            "summary": "Unknown ref",
        },
        execution_time=0.1,
    )

    assert result["status"] == "failed"
    assert result["success"] is False
    assert result["error_code"] == "UNKNOWN_REF"
    assert result["required_action"] == "snapshot"
    assert result["current_refs"] == ["f0:e1"]


def test_non_standard_result_preserves_resume_fields():
    from app.agent.tool_adapter import _standardize_tool_result

    result = _standardize_tool_result(
        "read_file",
        {
            "success": True,
            "summary": "读取成功",
            "data": {"content": "hello", "path": "/tmp/report.md"},
            "refs": {
                "files": [
                    {
                        "path": "/tmp/report.md",
                        "type": "text",
                        "usage": "read_file",
                    }
                ]
            },
            "llm_resume": {
                "content_preview": "hello",
                "tool_hint": "Use read_file(path='/tmp/report.md') to reread this file.",
            },
            "data_ids": ["data:v1:source"],
            "report_data_id": "report:v1:summary",
        },
        execution_time=0.1,
    )

    assert result["refs"]["files"][0]["path"] == "/tmp/report.md"
    assert result["llm_resume"]["content_preview"] == "hello"
    assert result["data_ids"] == ["data:v1:source"]
    assert result["report_data_id"] == "report:v1:summary"
