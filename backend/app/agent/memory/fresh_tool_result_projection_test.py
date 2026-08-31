"""Fresh-result projection tests.

The current run's tool results must reach the model verbatim (bounded by the
tool's own output limits); only stale turns fall back to the compacted
history form. See SessionMemory._plan_fresh_raw_injection.
"""

import json

from app.agent.memory.session_memory import (
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


def _last_tool_result_content(messages):
    tool_result_messages = [
        message
        for message in messages
        if isinstance(message.get("content"), list)
        and any(block.get("type") == "tool_result" for block in message["content"])
    ]
    assert tool_result_messages, "expected at least one tool_result message"
    blocks = tool_result_messages[-1]["content"]
    return next(block["content"] for block in blocks if block.get("type") == "tool_result")


def test_fresh_tool_result_projected_verbatim_in_current_run(tmp_path):
    session = _make_session(tmp_path)
    full_text = "环境空气质量标准正文。" + ("GB 3095 " * 6000)
    session.add_user_message("读取文档全文")
    _add_tool_result(session, "call_read_1", _reader_result(full_text))

    content = _last_tool_result_content(session.get_messages_for_llm())

    payload = json.loads(content)
    assert payload["data"]["chunks"][0]["content"] == full_text
    assert "tool_result_truncated" not in payload
    assert len(content) > 20_000  # far beyond the old history budget


def test_stale_tool_result_compacted_after_next_user_turn(tmp_path):
    session = _make_session(tmp_path)
    full_text = "环境空气质量标准正文。" + ("GB 3095 " * 6000)
    session.add_user_message("读取文档全文")
    _add_tool_result(session, "call_read_1", _reader_result(full_text))
    session.add_assistant_message("已读取文档")

    session.add_user_message("第二个问题")
    _add_tool_result(
        session,
        "call_read_2",
        _reader_result("第二个文档的内容", chunk_index=0),
    )

    messages = session.get_messages_for_llm()
    tool_result_messages = [
        message
        for message in messages
        if isinstance(message.get("content"), list)
        and any(block.get("type") == "tool_result" for block in message["content"])
    ]
    first_result_content = next(
        block["content"]
        for block in tool_result_messages[0]["content"]
        if block.get("type") == "tool_result"
    )
    assert full_text not in first_result_content

    first_payload = json.loads(first_result_content)
    assert first_payload["summary"]
    # Stale per-field compaction keeps structure but bounds each chunk's text.
    stale_chunk = first_payload["data"]["chunks"][0]
    assert len(stale_chunk["content"]) <= 8_100
    assert "truncated" in stale_chunk["content"]


def test_budget_downgrades_oldest_result_first(tmp_path):
    session = _make_session(tmp_path)
    old_text = "A" * (MAX_FRESH_TOOL_RESULT_CHARS // 2 + 1000)
    new_text = "B" * (MAX_FRESH_TOOL_RESULT_CHARS // 2 + 1000)

    session.add_user_message("读取两份文档")
    _add_tool_result(session, "call_old", _reader_result(old_text))
    _add_tool_result(session, "call_new", _reader_result(new_text))

    messages = session.get_messages_for_llm()
    contents = [
        block["content"]
        for message in messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
        if block.get("type") == "tool_result"
    ]
    assert len(contents) == 2
    old_payload = json.loads(contents[0])
    new_payload = json.loads(contents[1])
    # Newest keeps verbatim text; oldest exceeded the budget and fell back to
    # the compacted stored form (structure kept, chunk text bounded).
    assert new_payload["data"]["chunks"][0]["content"] == new_text
    old_chunk = old_payload["data"]["chunks"][0]
    assert old_chunk["content"] != old_text
    assert len(old_chunk["content"]) <= 8_100
    assert "truncated" in old_chunk["content"]


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

    content = _last_tool_result_content(session.get_messages_for_llm())
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
