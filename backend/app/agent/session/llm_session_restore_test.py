from datetime import datetime

import pytest

from app.agent.session.session_manager_db import SessionManagerDB


class _Repository:
    def __init__(self, llm_history=None):
        self.calls = []
        self.llm_history = llm_history

    async def get_session_with_messages(
        self,
        session_id,
        include_messages=True,
        include_artifacts=True,
    ):
        self.calls.append(
            ("get_session_with_messages", include_messages, include_artifacts)
        )
        return {
            "session_id": session_id,
            "query": "previous question",
            "created_at": datetime(2026, 6, 5, 7, 0, 0).isoformat(),
            "updated_at": datetime(2026, 6, 5, 7, 1, 0).isoformat(),
            "mode": "assistant",
            "current_step": None,
            "current_expert": None,
            "data_ids": ["data-1"],
            "visual_ids": [],
            "office_documents": [],
            "error": None,
            "metadata": {"mode": "assistant"},
            "conversation_history": [],
        }

    async def get_llm_history_messages(self, session_id):
        self.calls.append(("get_llm_history_messages",))
        return self.llm_history or [
            {
                "role": "user",
                "type": "user",
                "content": "hello",
                "timestamp": "2026-06-05T07:00:01",
                "id": "msg_1",
                "sequence_number": 0,
            }
        ]

    async def get_display_history_messages_light(self, session_id):
        self.calls.append(("get_display_history_messages_light",))
        return [
            {
                "role": "assistant",
                "type": "tool_result",
                "content": "preview",
                "timestamp": "2026-06-05T07:00:02",
                "id": "msg_2",
                "sequence_number": 1,
                "is_lightweight": True,
            }
        ]


@pytest.mark.asyncio
async def test_load_session_for_llm_uses_lightweight_history():
    manager = SessionManagerDB(enable_cache=False)
    repository = _Repository()
    manager.repository = repository

    session = await manager.load_session_for_llm("session-1")

    assert session.conversation_history[0]["content"] == "hello"
    assert repository.calls == [
        ("get_session_with_messages", False, True),
        ("get_llm_history_messages",),
    ]


@pytest.mark.asyncio
async def test_load_session_for_llm_returns_rebuilt_tool_blocks():
    manager = SessionManagerDB(enable_cache=False)
    repository = _Repository(
        llm_history=[
            {
                "role": "assistant",
                "type": "tool_use",
                "content": "调用工具: execute_ops_sql_query",
                "data": {
                    "tool_use_id": "toolu_1",
                    "tool_name": "execute_ops_sql_query",
                    "input": {"sql": "SELECT 1"},
                },
                "timestamp": "2026-06-05T07:00:01",
                "id": "msg_1",
                "sequence_number": 0,
            },
            {
                "role": "user",
                "type": "tool_result",
                "content": "查询到1条记录",
                "data": {
                    "tool_use_id": "toolu_1",
                    "tool_name": "execute_ops_sql_query",
                    "result": {
                        "status": "success",
                        "summary": "查询到1条记录",
                        "data": [{"large": "payload"}],
                    },
                    "is_error": False,
                },
                "timestamp": "2026-06-05T07:00:02",
                "id": "msg_2",
                "sequence_number": 1,
            },
        ]
    )
    manager.repository = repository

    session = await manager.load_session_for_llm("session-1")

    assert session.conversation_history == [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "execute_ops_sql_query",
                    "input": {"sql": "SELECT 1"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "is_error": False,
                    "content": '{\n  "tool_name": "execute_ops_sql_query",\n  "tool_use_id": "toolu_1",\n  "status": "success",\n  "is_error": false,\n  "summary": "查询到1条记录",\n  "result_truncated": true\n}',
                }
            ],
        },
    ]


@pytest.mark.asyncio
async def test_load_session_light_preserves_message_count_without_heavy_payloads():
    manager = SessionManagerDB(enable_cache=False)
    repository = _Repository()
    manager.repository = repository

    session = await manager.load_session_light("session-1")

    assert session.conversation_history[0]["is_lightweight"] is True
    assert repository.calls == [
        ("get_session_with_messages", False, True),
        ("get_display_history_messages_light",),
    ]
