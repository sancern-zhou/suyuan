"""Fresh-result projection tests.

The current run's tool results reach the model verbatim within a bounded
budget; oversized results fall back to the compacted history form, and stale
oversized blocks shrink to stubs. See SessionMemory._plan_fresh_raw_injection
and SessionMemory._plan_stale_result_downgrade.
"""

import json

from app.agent.memory.session_memory import (
    MAX_FRESH_SINGLE_TOOL_RESULT_CHARS,
    MAX_FRESH_TOOL_RESULT_CHARS,
    SessionMemory,
    _prepare_tool_result_for_history,
)


def _make_session(tmp_path):
    return SessionMemory(
        session_id="fresh-projection",
        base_dir=str(tmp_path),
        use_llm_compression=False,
    )


def _reader_result(content: str, chunk_index: int = 0):
    return {
        "status": "success",
        "success": True,
        "data": {
            "document_id": "doc_001",
            "total_chunks": 1,
            "returned_chunks": 1,
            "chunks": [{"chunk_index": chunk_index, "content": content}],
        },
        "metadata": {"generator": "knowledge_document_reader"},
        "summary": "已读取文档并登记原文资源",
        "file_path": "backend_data_registry/sessions/doc_001.txt",
        "content_preview": content[:2000],
    }


def _add_tool_result(session, tool_use_id, result, tool_name="knowledge_document_reader"):
    session.add_streaming_tool_results([
        {
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "tool_input": {"document_id": "doc_001"},
            "result": result,
            "is_error": False,
        }
    ])


def _tool_result_contents(messages):
    return [
        block["content"]
        for message in messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
        if block.get("type") == "tool_result"
    ]


def test_fresh_tool_result_projected_verbatim_in_current_run(tmp_path):
    session = _make_session(tmp_path)
    # 小于单结果上限：当前轮工具结果原样投影
    full_text = "环境空气质量标准正文。" + ("GB 3095 " * 2000)
    assert len(full_text) < MAX_FRESH_SINGLE_TOOL_RESULT_CHARS
    session.add_user_message("读取文档全文")
    _add_tool_result(session, "call_read_1", _reader_result(full_text))

    content = _tool_result_contents(session.get_messages_for_llm())[-1]

    payload = json.loads(content)
    assert payload["data"]["chunks"][0]["content"] == full_text
    assert "tool_result_truncated" not in payload


def test_oversized_fresh_result_falls_back_to_compacted_form(tmp_path):
    session = _make_session(tmp_path)
    # 大于单结果上限：不做断头截断，退回结构化压缩形式（合法 JSON、字段限长）
    full_text = "环境空气质量标准正文。" + ("GB 3095 " * 6000)
    assert len(full_text) > MAX_FRESH_SINGLE_TOOL_RESULT_CHARS
    session.add_user_message("读取文档全文")
    _add_tool_result(session, "call_read_1", _reader_result(full_text))

    content = _tool_result_contents(session.get_messages_for_llm())[-1]
    assert full_text not in content
    payload = json.loads(content)  # 仍是合法 JSON
    assert payload["summary"]


def test_stale_oversized_result_downgraded_to_stub(tmp_path):
    session = _make_session(tmp_path)
    big_text = "历史文档正文。" + ("数据 " * 6000)
    session.add_user_message("第一个问题")
    _add_tool_result(session, "call_read_1", _reader_result(big_text))
    session.add_assistant_message("已读取")
    session.add_user_message("第二个问题")
    _add_tool_result(
        session,
        "call_read_2",
        _reader_result("第二个文档的内容", chunk_index=0),
    )

    messages = session.get_messages_for_llm()
    contents = _tool_result_contents(messages)
    assert len(contents) == 2
    stale_payload = json.loads(contents[0])
    # 早期超大结果收缩为存根：保留 summary/file_path，正文不再驻留
    assert stale_payload["tool_result_truncated"] is True
    assert stale_payload["summary"] == "已读取文档并登记原文资源"
    assert stale_payload["file_path"] == "backend_data_registry/sessions/doc_001.txt"
    assert big_text not in contents[0]
    assert len(contents[0]) <= 1_500


def test_stale_result_stub_preserves_nested_data_id():
    content = json.dumps({
        "summary": "已生成数据集",
        "data": {"result": {"data_id": "air_quality:v1:abc123"}},
    }, ensure_ascii=False)
    stub = json.loads(SessionMemory._result_stub(content))
    assert stub["data_id"] == "air_quality:v1:abc123"


def test_budget_downgrades_oldest_result_first(tmp_path):
    session = _make_session(tmp_path)
    text = "X" * 20_000  # 单个不超上限，靠总预算触发降级

    session.add_user_message("读取三份文档")
    _add_tool_result(session, "call_old", _reader_result(text, chunk_index=0))
    session.add_assistant_message("第一份已读取")
    _add_tool_result(session, "call_mid", _reader_result(text, chunk_index=1))
    session.add_assistant_message("第二份已读取")
    _add_tool_result(session, "call_new", _reader_result(text, chunk_index=2))

    messages = session.get_messages_for_llm()
    contents = _tool_result_contents(messages)
    assert len(contents) == 3
    payloads = [json.loads(item) for item in contents]
    # 分配从最新 turn 开始：最新两个在预算内原样投影；最旧的超出总预算，
    # 且其压缩存储块也超过存根阈值 → 收缩为存根（保留 summary/file_path）
    assert payloads[2]["data"]["chunks"][0]["content"] == text
    assert payloads[1]["data"]["chunks"][0]["content"] == text
    assert payloads[0]["tool_result_truncated"] is True
    assert payloads[0]["summary"] == "已读取文档并登记原文资源"
    assert payloads[0]["file_path"] == "backend_data_registry/sessions/doc_001.txt"
    assert text not in contents[0]


def test_todowrite_result_excluded_from_fresh_projection(tmp_path):
    session = _make_session(tmp_path)
    todowrite_result = {
        "status": "success",
        "success": True,
        "data": {"active_items": [{"content": "任务", "status": "in_progress"}]},
        "metadata": {"generator": "TodoWrite"},
        "summary": "已更新任务清单",
        "total_count": 1,
    }
    session.add_user_message("规划任务")
    _add_tool_result(session, "call_todo", todowrite_result, tool_name="TodoWrite")

    content = _tool_result_contents(session.get_messages_for_llm())[-1]
    payload = json.loads(content)
    # Todowrite keeps its dedicated compacted form (no raw injection).
    assert "active_items" not in payload.get("data", {})


def test_minimal_tool_result_keeps_chunk_map(tmp_path, monkeypatch):
    from app.agent.memory import session_memory

    monkeypatch.setattr(session_memory, "MAX_TOOL_RESULT_JSON_CHARS", 500)
    chunks = [
        {"chunk_index": index, "content": f"第{index}块内容" + "x" * 200}
        for index in range(5)
    ]
    result = {
        "status": "success",
        "success": True,
        "data": {
            "document_id": "doc_001",
            "total_chunks": 5,
            "chunks": chunks,
        },
        "metadata": {"generator": "knowledge_document_reader"},
        "summary": "已读取文档",
    }

    history_result = _prepare_tool_result_for_history(result)

    assert history_result["tool_result_truncated"] is True
    chunk_map = history_result["data"]["chunk_map"]
    assert history_result["data"]["total_chunks"] == 5
    assert chunk_map[0]["chunk_index"] == 0
    assert chunk_map[0]["chars"] == len(chunks[0]["content"])
    assert chunk_map[0]["head"].startswith("第0块内容")
    assert chunks[0]["content"] not in history_result["data"]


def test_truncate_string_keeps_head_and_tail():
    from app.agent.memory.session_memory import _truncate_string

    value = "HEAD" + "x" * 20_000 + "TAIL"
    truncated = _truncate_string(value, max_chars=1_000)
    assert len(truncated) <= 1_050
    assert truncated.startswith("HEAD")
    assert truncated.endswith("TAIL")
    assert "truncated" in truncated
