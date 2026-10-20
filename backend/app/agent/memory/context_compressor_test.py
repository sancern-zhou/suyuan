import json

import pytest

import app.agent.memory.session_memory as session_memory
from app.agent.memory.context_compressor import ContextCompressor
from app.agent.memory.session_memory import SessionMemory
from app.agent.tool_adapter import _standardize_tool_result


class FakeLLMClient:
    def __init__(self, response: str = "Goal\n- Continue the original task."):
        self.response = response
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


@pytest.mark.asyncio
async def test_summary_failure_preserves_previous_memory_and_recent_history():
    class Unavailable:
        async def chat(self, **kwargs):
            raise RuntimeError("summary unavailable")

    compressor = ContextCompressor(Unavailable())
    prior = {
        "role": "user", "type": "compact_memory",
        "content": compressor.COMPACT_MEMORY_PREFIX + "Verified fact: station A is upstream.",
    }
    original = [prior] + _long_history()
    compacted = await compressor.compress(original, force=True)
    assert prior in compacted
    assert sum(m.get("type") == "compact_memory" for m in compacted) == 1
    assert any("继续第 7 批" in str(m["content"]) for m in compacted)
    assert any(m.get("metadata", {}).get("compression_type") == "fallback" for m in compacted)


@pytest.mark.parametrize("result", [
    {"success": True, "refs": {"files": [{"path": "/tmp/report.qmd", "usage": "artifact"}],
        "artifacts": [{"file_path": "/tmp/report.qmd"}], "visuals": [{"id": "image1"}]}},
    {"success": True, "llm_resume": {"content_preview": "测量值为42", "tool_hint": "read_file"},
        "data": {"content": "A" * 5000, "path": "/tmp/source.md"}},
    {"success": True, "data_id": "aggregate:result", "report_data_id": "report:summary",
        "source_data_ids": ["raw:source"]},
])
def test_restore_preserves_current_result_reference_contract(tmp_path, result):
    session = SessionMemory("restore-current-contract", base_dir=tmp_path)
    history = [
        {"type": "tool_use", "data": {"tool_use_id": "t1", "tool_name": "custom_reader", "input": {}}},
        {"type": "tool_result", "data": {"tool_use_id": "t1", "tool_name": "custom_reader", "result": result}},
    ]
    session.load_history_messages(history)
    messages = session.get_messages_for_llm()
    assert messages[0]["content"][0]["id"] == "t1"
    restored = json.loads(messages[1]["content"][0]["content"])
    # Recovery preserves tool-owned fields; it does not fabricate duplicated
    # context_refs, top-level content_preview, or a summary from data_id.
    assert restored == result
    assert "context_refs" not in restored


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

    assert compacted[0]["type"] == "compact_memory"
    anchor_messages = [
        msg for msg in compacted
        if isinstance(msg.get("content"), str)
        and msg["content"].startswith(ContextCompressor.ANCHOR_LABEL)
    ]
    assert len(anchor_messages) == 1
    assert "东莞市生态环境局" in anchor_messages[0]["content"]
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

    assert compacted[0]["type"] == "system"
    anchor_messages = [
        msg for msg in compacted
        if isinstance(msg.get("content"), str)
        and msg["content"].startswith(ContextCompressor.ANCHOR_LABEL)
    ]
    assert len(anchor_messages) == 1
    assert "东莞市生态环境局" in anchor_messages[0]["content"]
    assert any(
        msg.get("metadata", {}).get("compact_boundary")
        and msg.get("metadata", {}).get("compression_type") == "fallback"
        for msg in compacted
    )
    assert len(compacted) < len(original)


def test_extract_user_anchor_normalizes_existing_anchor_prefix():
    compressor = ContextCompressor(FakeLLMClient())

    anchor = compressor._extract_user_anchor([
        {
            "type": "compact_memory",
            "role": "user",
            "content": ContextCompressor.COMPACT_MEMORY_PREFIX + "Goal\n- Continue.",
        },
        {
            "role": "user",
            "content": (
                f"{ContextCompressor.ANCHOR_PREFIX}"
                f"{ContextCompressor.ANCHOR_PREFIX}"
                "原始任务"
            ),
        },
    ])

    assert anchor == [{
        "type": "user",
        "role": "user",
        "content": f"{ContextCompressor.ANCHOR_PREFIX}原始任务",
    }]
    assert anchor[0]["content"].count(ContextCompressor.ANCHOR_LABEL) == 1


@pytest.mark.asyncio
async def test_recompaction_outputs_single_canonical_anchor():
    client = FakeLLMClient("Goal\n- Continue the original task.")
    compressor = ContextCompressor(client)
    messages = [
        {
            "type": "compact_memory",
            "role": "user",
            "content": ContextCompressor.COMPACT_MEMORY_PREFIX + "Goal\n- Previous summary.",
        },
        {
            "type": "user",
            "role": "user",
            "content": (
                f"{ContextCompressor.ANCHOR_PREFIX}"
                f"{ContextCompressor.ANCHOR_PREFIX}"
                "原始任务"
            ),
        },
    ]
    for index in range(8):
        messages.append({"role": "user", "content": f"继续第 {index} 步"})
        messages.append({"role": "assistant", "content": f"第 {index} 步完成"})

    compacted = await compressor.compress(
        messages,
        force=True,
        force_reason="test_recompaction",
    )

    anchor_messages = [
        msg for msg in compacted
        if isinstance(msg.get("content"), str)
        and msg["content"].startswith(ContextCompressor.ANCHOR_LABEL)
    ]
    assert len(anchor_messages) == 1
    assert anchor_messages[0]["content"] == f"{ContextCompressor.ANCHOR_PREFIX}原始任务"
    assert anchor_messages[0]["content"].count(ContextCompressor.ANCHOR_LABEL) == 1


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
    assert messages[1]["content"].startswith(ContextCompressor.COMPACT_MEMORY_PREFIX)
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
    assert messages[0]["content"].startswith(ContextCompressor.COMPACT_MEMORY_PREFIX)


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


def test_session_memory_load_history_messages_restores_field_compacted_tool_result(tmp_path):
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

    assert restored["status"] == "success"
    assert restored["summary_text"] == "已生成趋势图"
    assert restored["data_id"] == "chart_data:v1:abc"
    assert restored["visuals"][0]["id"] == "visual_1"
    assert restored["data"] == [{"large": "row"}]







def test_tool_result_history_minimalization_preserves_refs_and_resume(monkeypatch):
    monkeypatch.setattr(session_memory, "MAX_TOOL_RESULT_JSON_CHARS", 500)

    result = session_memory._prepare_tool_result_for_history({
        "success": True,
        "status": "success",
        "summary": "生成了大结果",
        "data": {"rows": [{"value": "x" * 1000}]},
        "refs": {
            "files": [
                {
                    "path": "/tmp/report.md",
                    "type": "text",
                    "usage": "artifact",
                }
            ]
        },
        "llm_resume": {
            "content_preview": "关键摘要",
            "tool_hint": "Use read_file(path='/tmp/report.md') to reread this file.",
        },
        "data_id": "large:v1:result",
        "report_data_ids": ["report:v1:summary"],
        "source_data_ids": ["raw:v1:source"],
    })

    assert result["tool_result_truncated"] is True
    assert result["refs"]["files"][0]["path"] == "/tmp/report.md"
    assert result["llm_resume"]["tool_hint"] == "Use read_file(path='/tmp/report.md') to reread this file."
    assert "data_id" not in result
    assert "report_data_ids" not in result
    assert "source_data_ids" not in result
    assert "rows" not in json.dumps(result, ensure_ascii=False)


def test_tool_result_history_minimalization_keeps_bounded_data_sample(monkeypatch):
    monkeypatch.setattr(session_memory, "MAX_TOOL_RESULT_JSON_CHARS", 500)

    records = [{"name": f"区县{index}", "aqi": str(20 + index)} for index in range(50)]
    result = session_memory._prepare_tool_result_for_history({
        "success": True,
        "status": "success",
        "summary": "生成了大结果",
        "data": records,
    })

    assert result["tool_result_truncated"] is True
    assert result["data_sampled"] is True
    assert result["data_original_record_count"] == 50
    sampled = result["data"]
    assert 1 <= len(sampled) <= 3
    assert sampled[0]["name"] == "区县0"
    assert sampled[-1]["name"] == "区县49"


def test_tool_result_history_minimalization_skips_oversized_data_sample(monkeypatch):
    monkeypatch.setattr(session_memory, "MAX_TOOL_RESULT_JSON_CHARS", 500)

    result = session_memory._prepare_tool_result_for_history({
        "success": True,
        "status": "success",
        "summary": "生成了大结果",
        "data": [{"blob": "x" * 10_000} for _ in range(50)],
    })

    assert result["tool_result_truncated"] is True
    assert "data" not in result
    assert "data_sampled" not in result


def test_standardized_legacy_tool_result_survives_history_restore_projection(tmp_path):
    standardized = _standardize_tool_result(
        "read_file",
        {
            "success": True,
            "summary": "读取成功",
            "data": {
                "content": "关键正文",
                "path": "/tmp/report.md",
                "rows": [{"large": "payload"}],
            },
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
                "content_preview": "关键正文",
                "tool_hint": "Use read_file(path='/tmp/report.md') to reread this file.",
            },
            "source_data_ids": ["raw:v1:source"],
        },
        execution_time=0.1,
    )

    runtime_session = SessionMemory(session_id="runtime-projection-source", base_dir=tmp_path)
    runtime_session.add_streaming_tool_results([
        {
            "tool_name": "read_file",
            "tool_use_id": "toolu_read_1",
            "tool_input": {"path": "/tmp/report.md"},
            "result": standardized,
            "is_error": False,
        }
    ])
    display_history = [
        {
            "type": turn.type,
            "role": turn.role,
            "content": "display event",
            "data": turn.data,
            "timestamp": turn.timestamp,
        }
        for turn in runtime_session.conversation_history
    ]

    projected = SessionMemory.project_history_messages_for_llm(
        display_history,
        session_id="runtime-projection-restore",
    )
    restored = json.loads(projected[1]["content"][0]["content"])

    assert restored["refs"]["files"][0]["path"] == "/tmp/report.md"
    assert restored["llm_resume"]["tool_hint"] == "Use read_file(path='/tmp/report.md') to reread this file."
    assert restored["data"]["content"] == "关键正文"


def test_document_artifact_tool_result_survives_history_restore_projection(tmp_path):
    artifact_path = tmp_path / "deck.pptx"
    artifact_path.write_bytes(b"fake pptx bytes")
    result = {
        "success": True,
        "status": "success",
        "summary": "已生成PPT",
        "metadata": {"generator": "create_pptx_with_ppt_master"},
        "data": {
            "file_path": str(artifact_path),
            "project_dir": str(tmp_path / "project"),
        },
        "refs": {
            "files": [
                {
                    "path": str(artifact_path),
                    "type": "document",
                    "format": "pptx",
                    "usage": "artifact",
                }
            ],
            "artifacts": [
                {
                    "type": "document",
                    "kind": "office",
                    "format": "pptx",
                    "file_path": str(artifact_path),
                    "file_name": "deck.pptx",
                }
            ],
        },
        "llm_resume": {
            "artifact_path": str(artifact_path),
            "project_dir": str(tmp_path / "project"),
            "tool_hint": f"Use present_artifact(file_path='{artifact_path}') to preview this artifact.",
        },
    }

    runtime_session = SessionMemory(session_id="artifact-projection-source", base_dir=tmp_path)
    runtime_session.add_streaming_tool_results([
        {
            "tool_name": "create_pptx_with_ppt_master",
            "tool_use_id": "toolu_ppt_1",
            "tool_input": {"title": "deck"},
            "result": result,
            "is_error": False,
        }
    ])
    display_history = [
        {
            "type": turn.type,
            "role": turn.role,
            "content": "display event",
            "data": turn.data,
            "timestamp": turn.timestamp,
        }
        for turn in runtime_session.conversation_history
    ]

    projected = SessionMemory.project_history_messages_for_llm(
        display_history,
        session_id="artifact-projection-restore",
    )
    restored = json.loads(projected[1]["content"][0]["content"])

    assert restored["refs"]["files"][0]["path"] == str(artifact_path)
    assert restored["refs"]["artifacts"][0]["file_path"] == str(artifact_path)
    assert restored["llm_resume"]["artifact_path"] == str(artifact_path)
    assert restored["llm_resume"]["project_dir"] == str(tmp_path / "project")
    assert "present_artifact" in restored["llm_resume"]["tool_hint"]



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


def test_content_to_text_preserves_workflow_findings_and_full_results_pointer():
    workflow_result = json.dumps({
        "tool_use_id": "call_1",
        "tool_name": "run_agent_workflow",
        "result": {
            "status": "success",
            "result": "工作流已完成",
            "data": {
                "workflow_id": "xc-week-1",
                "status": "succeeded",
                "node_results": {
                    "corr": {
                        "task_id": "corr",
                        "target_mode": "expert_analysis",
                        "status": "success",
                        "result_envelope": {
                            "status": "completed",
                            "summary": "相关性分析完成",
                            "findings": [
                                {"statement": "PM2.5 与 CO 相关系数 r=0.62"}
                            ],
                            "data_gaps": ["组分缺测"],
                        },
                        "file_paths": ["backend/backend_data_registry/sessions/child/data/memo.md"],
                    }
                },
                "full_results": {"path": "backend/backend_data_registry/sessions/p/data/workflow_xc-week-1_node_results.json"},
            },
        },
    }, ensure_ascii=False)
    compressor = ContextCompressor(FakeLLMClient())

    rendered = compressor._content_to_text(workflow_result, max_chars=3000)

    assert "full_results_path=backend/backend_data_registry/sessions/p/data/workflow_xc-week-1_node_results.json" in rendered
    assert "r=0.62" in rendered
    assert "memo.md" in rendered
    assert "组分缺测" in rendered
    assert "...[truncated]" not in rendered

    plain_large = json.dumps({"rows": [{"value": "x" * 4000}]}, ensure_ascii=False)
    rendered_plain = compressor._content_to_text(plain_large, max_chars=3000)
    assert rendered_plain.endswith("...[truncated]")
