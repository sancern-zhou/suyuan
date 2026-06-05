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
