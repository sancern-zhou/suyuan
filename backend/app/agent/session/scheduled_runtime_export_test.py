from types import SimpleNamespace

from app.agent.react_agent import ReActAgent


def test_export_runtime_session_contains_full_runtime_history_and_artifacts():
    agent = ReActAgent.__new__(ReActAgent)
    memory = SimpleNamespace(session=SimpleNamespace(conversation_history=[
        {"type": "user", "role": "user", "content": "执行任务"},
        {"type": "tool_use", "role": "assistant", "content": "调用工具"},
        {"type": "tool_result", "role": "user", "content": "工具结果"},
        {"type": "final", "role": "assistant", "content": "执行完成"},
    ]))
    agent._session_store = {
        "scheduled-session": {
            "memory": memory,
            "collected_data_ids": ["data-1"],
            "office_documents": [{"file_name": "报告.docx"}],
        }
    }

    session = agent.export_runtime_session(
        "scheduled-session",
        query="任务描述",
        mode="social",
    )

    assert [message["type"] for message in session.conversation_history] == [
        "user", "tool_use", "tool_result", "final"
    ]
    assert session.query == "任务描述"
    assert session.metadata["mode"] == "social"
    assert session.data_ids == ["data-1"]
    assert session.office_documents == [{"file_name": "报告.docx"}]


def test_export_runtime_session_returns_none_when_runtime_is_missing():
    agent = ReActAgent.__new__(ReActAgent)
    agent._session_store = {}

    assert agent.export_runtime_session("missing", query="任务", mode="expert") is None
