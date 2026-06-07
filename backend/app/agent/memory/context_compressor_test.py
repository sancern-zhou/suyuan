import json

import pytest

from app.agent.memory.context_compressor import ContextCompressor
from app.agent.memory.session_memory import SessionMemory


class FakeLLMClient:
    def __init__(self, response: str = "Goal\n- Continue the original task."):
        self.response = response
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _tool_pair(index: int):
    tool_id = f"toolu_{index}"
    return [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": "search_history",
                    "input": {"query": f"item {index}"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": f'{{"success": true, "summary": "result {index}", "data_id": "data:{index}"}}',
                    "is_error": False,
                }
            ],
        },
    ]


def _long_history():
    messages = [
        {"role": "user", "content": "请检索半年内东莞市生态环境局相关招标信息"}
    ]
    for index in range(1, 8):
        messages.extend(_tool_pair(index))
        messages.append({"role": "assistant", "content": f"阶段 {index} 小结"})
        messages.append({"role": "user", "content": f"继续第 {index} 批筛选"})
    return messages


@pytest.mark.asyncio
async def test_force_compaction_creates_plain_text_memory_and_keeps_recent_tool_pair():
    client = FakeLLMClient("Goal\n- Find matching tenders.\n\nEvidence and results\n- data:1 was used.")
    compressor = ContextCompressor(client)

    compacted = await compressor.compress(
        _long_history(),
        force=True,
        force_reason="test_context_tokens_exceeded",
    )

    compact_memory = [
        msg for msg in compacted
        if msg.get("type") == "compact_memory"
    ]
    assert len(compact_memory) == 1
    assert compact_memory[0]["role"] == "user"
    assert "Runtime memory summary from earlier turns." in compact_memory[0]["content"]
    assert "Find matching tenders" in compact_memory[0]["content"]

    assert compacted[0]["type"] == "user"
    assert "东莞市生态环境局" in compacted[0]["content"]
    assert any(
        isinstance(msg.get("content"), list)
        and any(block.get("type") == "tool_use" for block in msg["content"])
        for msg in compacted
    )
    assert any(
        isinstance(msg.get("content"), list)
        and any(block.get("type") == "tool_result" for block in msg["content"])
        for msg in compacted
    )
    assert client.calls
    assert "Return plain text only" in client.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_compaction_failure_uses_anchor_and_recent_history_not_recent_half_only():
    class FailingLLMClient(FakeLLMClient):
        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("summary unavailable")

    compressor = ContextCompressor(FailingLLMClient())
    original = _long_history()

    compacted = await compressor.compress(
        original,
        force=True,
        force_reason="test_failure",
    )

    assert compacted[0]["type"] == "user"
    assert "东莞市生态环境局" in compacted[0]["content"]
    assert any(
        msg.get("metadata", {}).get("compact_boundary")
        and msg.get("metadata", {}).get("compression_type") == "fallback"
        for msg in compacted
    )
    assert len(compacted) < len(original)


def test_session_memory_preserves_compact_memory_and_content_blocks_after_update(tmp_path):
    session = SessionMemory(session_id="compact-test", base_dir=tmp_path)
    compacted = [
        {"type": "user", "role": "user", "content": "[压缩保留的原始任务锚点]\n原始任务"},
        {
            "type": "compact_memory",
            "role": "user",
            "content": ContextCompressor.COMPACT_MEMORY_PREFIX + "Goal\n- Continue.",
        },
        *_tool_pair(99),
    ]

    session.update_messages(compacted)
    messages = session.get_messages_for_llm()

    assert messages[1]["role"] == "user"
    assert messages[1]["content"].startswith("Runtime memory summary from earlier turns.")
    assert isinstance(messages[2]["content"], list)
    assert messages[2]["content"][0]["type"] == "tool_use"
    assert isinstance(messages[3]["content"], list)
    assert messages[3]["content"][0]["type"] == "tool_result"


def test_session_memory_load_history_messages_restores_compact_memory(tmp_path):
    session = SessionMemory(session_id="restore-compact-test", base_dir=tmp_path)
    saved_messages = [
        {
            "type": "compact_memory",
            "role": "user",
            "content": ContextCompressor.COMPACT_MEMORY_PREFIX + "Goal\n- Continue.",
            "timestamp": "2026-06-02T00:00:00",
        }
    ]

    session.load_history_messages(saved_messages)
    messages = session.get_messages_for_llm()

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"].startswith("Runtime memory summary from earlier turns.")


def test_session_memory_load_history_messages_prefers_db_role_content(tmp_path):
    session = SessionMemory(session_id="restore-db-role-content-test", base_dir=tmp_path)
    saved_messages = [
        {
            "type": "final",
            "role": "assistant",
            "content": "这是新的截图回复",
            "data": {},
            "timestamp": "2026-06-04T00:00:00",
        }
    ]

    session.load_history_messages(saved_messages)
    messages = session.get_messages_for_llm()

    assert len(messages) == 1
    assert messages[0] == {
        "role": "assistant",
        "content": "这是新的截图回复",
    }


def test_session_memory_load_history_messages_skips_display_only_react_events(tmp_path):
    session = SessionMemory(session_id="restore-display-only-events-test", base_dir=tmp_path)
    saved_messages = [
        {
            "type": "user",
            "content": "帮我查看目录",
            "timestamp": "2026-06-04T00:00:00",
        },
        {
            "type": "thought",
            "content": "准备调用工具: list_directory",
            "data": {"thought": "准备调用工具: list_directory"},
            "timestamp": "2026-06-04T00:00:01",
        },
        {
            "type": "tool_use",
            "content": "调用工具: list_directory",
            "data": {"tool_name": "list_directory", "input": {"path": "."}},
            "timestamp": "2026-06-04T00:00:02",
        },
        {
            "type": "tool_result",
            "content": "Tool Result: 列出文件",
            "data": {"tool_name": "list_directory", "result": {"summary": "列出文件"}},
            "timestamp": "2026-06-04T00:00:03",
        },
        {
            "type": "final",
            "content": "目录里有 backend 和 frontend。",
            "timestamp": "2026-06-04T00:00:04",
        },
    ]

    session.load_history_messages(saved_messages)
    messages = session.get_messages_for_llm()

    assert messages == [
        {"role": "user", "content": "帮我查看目录"},
        {"role": "assistant", "content": "目录里有 backend 和 frontend。"},
    ]


def test_session_memory_load_history_messages_rebuilds_tool_blocks_from_display_data(tmp_path):
    session = SessionMemory(session_id="restore-display-tool-data-test", base_dir=tmp_path)
    saved_messages = [
        {
            "type": "user",
            "role": "user",
            "content": "继续分析",
            "timestamp": "2026-06-04T00:00:00",
        },
        {
            "type": "tool_use",
            "role": "assistant",
            "content": "调用工具: execute_ops_sql_query",
            "data": {
                "tool_use_id": "toolu_query_1",
                "tool_name": "execute_ops_sql_query",
                "input": {"sql": "SELECT 1"},
            },
            "timestamp": "2026-06-04T00:00:01",
        },
        {
            "type": "thought",
            "role": "assistant",
            "content": "准备调用工具: execute_ops_sql_query",
            "data": {"thought": "准备调用工具"},
            "timestamp": "2026-06-04T00:00:02",
        },
        {
            "type": "tool_result",
            "role": "user",
            "content": "查询到1条记录",
            "data": {
                "tool_use_id": "toolu_query_1",
                "tool_name": "execute_ops_sql_query",
                "result": {"summary": "查询到1条记录", "rows": [{"value": 1}]},
                "is_error": False,
            },
            "timestamp": "2026-06-04T00:00:03",
        },
    ]

    session.load_history_messages(saved_messages)
    messages = session.get_messages_for_llm()

    assert messages[0] == {"role": "user", "content": "继续分析"}
    assert messages[1] == {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_query_1",
                "name": "execute_ops_sql_query",
                "input": {"sql": "SELECT 1"},
            }
        ],
    }
    assert messages[2]["role"] == "user"
    assert messages[2]["content"][0]["type"] == "tool_result"
    assert messages[2]["content"][0]["tool_use_id"] == "toolu_query_1"
    assert messages[2]["content"][0]["is_error"] is False
    assert "\"summary\": \"查询到1条记录\"" in messages[2]["content"][0]["content"]


def test_session_memory_load_history_messages_restores_only_lightweight_tool_result_fields(tmp_path):
    session = SessionMemory(session_id="restore-light-tool-result-test", base_dir=tmp_path)
    saved_messages = [
        {
            "type": "tool_use",
            "role": "assistant",
            "content": "调用工具: render_chart",
            "data": {
                "tool_use_id": "toolu_chart_1",
                "tool_name": "render_chart",
                "input": {"chart_type": "line"},
            },
            "timestamp": "2026-06-04T00:00:01",
        },
        {
            "type": "tool_result",
            "role": "user",
            "content": "已生成图表",
            "data": {
                "tool_use_id": "toolu_chart_1",
                "tool_name": "render_chart",
                "result": {
                    "status": "success",
                    "summary_text": "已生成趋势图",
                    "data_id": "chart_data:v1:abc",
                    "data_ids": ["chart_data:v1:abc"],
                    "visuals": [
                        {"id": "visual_1", "title": "趋势图", "spec": {"large": "payload"}},
                        {"id": "visual_2"},
                    ],
                    "data": [{"large": "row"}],
                    "rows": [{"large": "row"}],
                    "html": "<div>large</div>",
                },
                "is_error": False,
            },
            "timestamp": "2026-06-04T00:00:02",
        },
    ]

    session.load_history_messages(saved_messages)
    messages = session.get_messages_for_llm()
    restored = json.loads(messages[1]["content"][0]["content"])

    assert restored == {
        "tool_name": "render_chart",
        "tool_use_id": "toolu_chart_1",
        "status": "success",
        "is_error": False,
        "summary_text": "已生成趋势图",
        "data_id": "chart_data:v1:abc",
        "data_ids": ["chart_data:v1:abc"],
        "visual_ids": ["visual_1", "visual_2"],
        "result_truncated": True,
    }


def test_session_memory_load_history_messages_uses_data_id_reference_when_summary_missing(tmp_path):
    session = SessionMemory(session_id="restore-data-id-reference-test", base_dir=tmp_path)
    saved_messages = [
        {
            "type": "tool_use",
            "role": "assistant",
            "content": "调用工具: query_data",
            "data": {
                "tool_use_id": "toolu_data_1",
                "tool_name": "query_data",
                "input": {"table": "events"},
            },
            "timestamp": "2026-06-04T00:00:01",
        },
        {
            "type": "tool_result",
            "role": "user",
            "content": "查询完成",
            "data": {
                "tool_use_id": "toolu_data_1",
                "tool_name": "query_data",
                "result": {
                    "data_id": "sql_query_result:v1:abc",
                    "data": [{"large": "payload"}],
                },
                "is_error": False,
            },
            "timestamp": "2026-06-04T00:00:02",
        },
    ]

    session.load_history_messages(saved_messages)
    messages = session.get_messages_for_llm()
    restored = json.loads(messages[1]["content"][0]["content"])

    assert restored["summary"] == "结果已保存为 data_id=sql_query_result:v1:abc，可用 read_data_registry 读取。"
    assert restored["data_id"] == "sql_query_result:v1:abc"
    assert restored["result_truncated"] is True


def test_session_memory_load_history_messages_drops_orphan_tool_protocol_blocks(tmp_path):
    session = SessionMemory(session_id="restore-drop-orphan-tool-test", base_dir=tmp_path)
    saved_messages = [
        {
            "type": "tool_use",
            "role": "assistant",
            "content": "调用工具: missing_result",
            "data": {
                "tool_use_id": "toolu_orphan_use",
                "tool_name": "missing_result",
                "input": {},
            },
            "timestamp": "2026-06-04T00:00:01",
        },
        {
            "type": "tool_result",
            "role": "user",
            "content": "孤儿结果",
            "data": {
                "tool_use_id": "toolu_orphan_result",
                "tool_name": "missing_use",
                "result": {"summary": "orphan"},
                "is_error": False,
            },
            "timestamp": "2026-06-04T00:00:02",
        },
        {
            "type": "tool_use",
            "role": "assistant",
            "content": "调用工具: valid_tool",
            "data": {
                "tool_use_id": "toolu_valid",
                "tool_name": "valid_tool",
                "input": {"x": 1},
            },
            "timestamp": "2026-06-04T00:00:03",
        },
        {
            "type": "tool_result",
            "role": "user",
            "content": "有效结果",
            "data": {
                "tool_use_id": "toolu_valid",
                "tool_name": "valid_tool",
                "result": {"summary": "valid"},
                "is_error": False,
            },
            "timestamp": "2026-06-04T00:00:04",
        },
    ]

    session.load_history_messages(saved_messages)
    messages = session.get_messages_for_llm()

    assert len(messages) == 2
    assert messages[0]["content"][0]["id"] == "toolu_valid"
    assert messages[1]["content"][0]["tool_use_id"] == "toolu_valid"


def test_session_memory_load_history_messages_preserves_native_tool_blocks(tmp_path):
    session = SessionMemory(session_id="restore-native-tool-blocks-test", base_dir=tmp_path)
    saved_messages = [
        {
            "role": "assistant",
            "type": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "list_directory",
                    "input": {"path": "."},
                }
            ],
            "timestamp": "2026-06-04T00:00:00",
        },
        {
            "role": "user",
            "type": "tool_result",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "{\"summary\":\"ok\"}",
                    "is_error": False,
                }
            ],
            "timestamp": "2026-06-04T00:00:01",
        },
    ]

    session.load_history_messages(saved_messages)
    messages = session.get_messages_for_llm()

    assert messages == [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "list_directory",
                    "input": {"path": "."},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "{\"summary\":\"ok\"}",
                    "is_error": False,
                }
            ],
        },
    ]
