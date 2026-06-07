from app.db.session_repository import SessionRepository


class _Row:
    id = 42
    role = "user"
    msg_type = "tool_result"
    content = "查询到1条记录"
    data = {"tool_use_id": "toolu_1", "result": {"summary": "ok"}}
    timestamp = None
    sequence_number = 7


def test_message_metadata_excludes_large_runtime_payloads():
    message = {
        "id": "frontend-id",
        "role": "assistant",
        "type": "tool_result",
        "content": "tool completed",
        "timestamp": "2026-06-05T07:30:00",
        "data": {"result": {"rows": [1, 2, 3]}},
        "metadata": {"duplicated": True},
        "visuals": [{"id": "visual-1"}],
        "tool_use_id": "toolu_123",
        "tool_name": "query_orders",
        "is_error": False,
        "source": "agent",
    }

    metadata = SessionRepository._message_metadata(message)

    assert metadata == {"source": "agent"}


def test_message_data_preserves_tool_fields_without_existing_data():
    message = {
        "type": "tool_result",
        "content": "failed",
        "tool_use_id": "toolu_123",
        "tool_name": "query_orders",
        "is_error": True,
    }

    data = SessionRepository._message_data(message)

    assert data == {
        "tool_use_id": "toolu_123",
        "tool_name": "query_orders",
        "is_error": True,
    }


def test_llm_context_row_can_include_data_while_light_row_omits_it():
    repository = SessionRepository()

    llm_message = repository._message_row_to_context_dict(_Row(), include_data=True)
    light_message = repository._message_row_to_context_dict(_Row(), include_data=False)

    assert llm_message["data"] == {
        "tool_use_id": "toolu_1",
        "result": {"summary": "ok"},
    }
    assert "data" not in light_message
