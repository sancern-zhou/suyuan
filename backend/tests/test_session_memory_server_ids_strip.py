import json

from app.agent.memory.session_memory import SessionMemory


def _tool_result_payloads(session):
    projected = session.get_messages_for_llm()
    return [
        json.loads(message["content"][0]["content"])
        for message in projected
        if message.get("content")
        and isinstance(message["content"], list)
        and message["content"][0].get("type") == "tool_result"
    ]


def test_resource_tracking_ids_never_reach_llm_projection(tmp_path):
    """新鲜窗口 raw 注入路径：目录主键剥离，visuals 契约原样保留。"""
    session = SessionMemory("server-ids", base_dir=tmp_path)
    session.add_user_message("画图")
    raw = {
        "success": True,
        "summary": "已生成图",
        "resource_tracking": {
            "durable": True,
            "version": 15,
            "resource_ids": ["144b6c090a47cd3e53dbd52839b4560f"],
            "resource_group_ids": ["deadbeef"],
            "focus_resource_id": "144b6c090a47cd3e53dbd52839b4560f",
        },
        "visuals": [{"id": "matplotlib_x1", "type": "image"}],
    }
    session.add_streaming_tool_results([{
        "tool_name": "execute_python",
        "tool_use_id": "t1",
        "tool_input": {},
        "result": raw,
    }])

    results = _tool_result_payloads(session)
    assert len(results) == 1
    assert results[0]["resource_tracking"] == {"durable": True}
    assert "144b6c090a47cd3e53dbd52839b4560f" not in json.dumps(results)
    assert results[0]["visuals"] == raw["visuals"]
    # 进程内 stash 保留完整 tracking，SSE/落库/前端产物卡片仍可消费
    stored_raw = session.conversation_history[-1].data["raw_results"][0]["raw"]
    assert stored_raw["resource_tracking"]["resource_ids"] == [
        "144b6c090a47cd3e53dbd52839b4560f"
    ]


def test_resource_tracking_ids_stripped_in_compacted_history_path(tmp_path, monkeypatch):
    """超预算降级路径：LLM 视野回落到压缩历史，主键同样不得泄漏。"""
    monkeypatch.setattr(
        "app.agent.memory.session_memory._fresh_budgets", lambda: (100, 80)
    )
    session = SessionMemory("server-ids-big", base_dir=tmp_path)
    session.add_user_message("画图")
    session.add_streaming_tool_results([{
        "tool_name": "execute_python",
        "tool_use_id": "t1",
        "tool_input": {},
        "result": {
            "success": True,
            "summary": "已生成图",
            "data": {"payload": "x" * 500},
            "resource_tracking": {
                "durable": True,
                "version": 3,
                "resource_ids": ["abc123"],
                "resource_group_ids": ["g1"],
            },
        },
    }])

    for payload in _tool_result_payloads(session):
        assert "resource_ids" not in json.dumps(payload)
        assert "resource_group_ids" not in json.dumps(payload)
