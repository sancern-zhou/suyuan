from app.api.session_routes import _strip_lazy_artifacts


def test_strip_lazy_artifacts_removes_path_fields():
    payload = {
        "report_input_path": "/data/report_input.json",
        "items": [{"issue_id": "1", "attachment_original_path": "/tmp/a.png"}],
    }

    stripped = _strip_lazy_artifacts(payload)

    assert "report_input_path" not in stripped
    assert "attachment_original_path" not in stripped["items"][0]


def test_strip_lazy_artifacts_keeps_human_feedback_subtree_intact():
    payload = {
        "human_feedback": {
            "feedback_id": "ops-audit:abc",
            "report_input_path": "/data/report_input.json",
            "source_sha256": "abc",
            "items": [{"item_id": "issue-1", "details": {"model_result_path": "/tmp/m.json"}}],
        },
        "conversation_history": [
            {
                "type": "tool_result",
                "data": {
                    "result": {
                        "data": {
                            "human_feedback": {"report_input_path": "/data/report_input.json"}
                        }
                    }
                },
            }
        ],
    }

    stripped = _strip_lazy_artifacts(payload)

    feedback = stripped["human_feedback"]
    assert feedback["report_input_path"] == "/data/report_input.json"
    assert feedback["items"][0]["details"]["model_result_path"] == "/tmp/m.json"
    message = stripped["conversation_history"][0]
    assert (
        message["data"]["result"]["data"]["human_feedback"]["report_input_path"]
        == "/data/report_input.json"
    )
