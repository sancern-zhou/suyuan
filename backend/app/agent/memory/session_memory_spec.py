from app.agent.memory.session_memory import SessionMemory


def test_history_projection_restores_paired_display_tool_events():
    messages = [
        {"type": "user", "content": "USER_MESSAGE_1", "timestamp": "2026-07-08T18:12:00"},
        {
            "type": "tool_use",
            "content": "调用工具: wait_task",
            "timestamp": "2026-07-08T18:12:01",
            "data": {
                "tool_use_id": "call_wait",
                "tool_name": "wait_task",
                "input": {"task_id": "spawn_task_1"},
            },
        },
        {
            "type": "tool_result",
            "content": "TOOL_RESULT_DISPLAY_1",
            "timestamp": "2026-07-08T18:12:02",
            "data": {
                "tool_use_id": "call_wait",
                "tool_name": "wait_task",
                "result": {"status": "failed", "error": "boom"},
            },
        },
        {"type": "final", "content": "ASSISTANT_MESSAGE_1", "timestamp": "2026-07-08T18:12:03"},
    ]

    projected = SessionMemory.project_history_messages_for_llm(messages)

    assert projected[0] == {"role": "user", "content": "USER_MESSAGE_1"}
    assert projected[1]["role"] == "assistant"
    assert projected[1]["content"] == [{
        "type": "tool_use",
        "id": "call_wait",
        "name": "wait_task",
        "input": {"task_id": "spawn_task_1"},
    }]
    assert projected[2]["role"] == "user"
    assert projected[2]["content"][0]["type"] == "tool_result"
    assert projected[2]["content"][0]["tool_use_id"] == "call_wait"
    assert '"error": "boom"' in projected[2]["content"][0]["content"]
    assert projected[3] == {"role": "assistant", "content": "ASSISTANT_MESSAGE_1"}


def test_history_projection_bounds_long_tool_result_without_dropping_pair():
    messages = [
        {"type": "tool_use", "content": "调用工具", "data": {
            "tool_use_id": "call_long", "tool_name": "read_file", "input": {"path": "large.txt"},
        }},
        {"type": "tool_result", "content": "读取完成", "data": {
            "tool_use_id": "call_long", "tool_name": "read_file",
            "result": {"success": True, "content": "x" * 100_000, "file_path": "large.txt"},
        }},
    ]

    projected = SessionMemory.project_history_messages_for_llm(messages)

    assert len(projected) == 2
    assert projected[0]["content"][0]["id"] == "call_long"
    result_block = projected[1]["content"][0]
    assert result_block["tool_use_id"] == "call_long"
    assert len(result_block["content"]) < 21_000
    assert "tool_result_truncated" in result_block["content"]


def test_84_persisted_rows_restore_every_valid_tool_exchange():
    messages = [{"type": "user", "content": "开始任务"}]
    messages.extend(
        {"type": "thought", "content": f"过程 {index}"}
        for index in range(14)
    )
    for index in range(32):
        tool_use_id = f"call_{index}"
        messages.extend([
            {"type": "tool_use", "content": "调用工具", "data": {
                "tool_use_id": tool_use_id,
                "tool_name": "read_file",
                "input": {"path": f"file_{index}.txt"},
            }},
            {"type": "tool_result", "content": "读取完成", "data": {
                "tool_use_id": tool_use_id,
                "tool_name": "read_file",
                "result": {"success": True, "summary": f"result {index}"},
            }},
        ])
    messages.extend([
        {"type": "tool_result", "content": "孤立结果", "data": {
            "tool_use_id": "orphan", "result": {"success": True},
        }},
        {"type": "final", "content": "阶段一完成"},
        {"type": "final", "content": "阶段二完成"},
        {"type": "final", "content": "任务完成"},
        {"type": "user", "content": "继续"},
    ])
    assert len(messages) == 84

    projected = SessionMemory.project_history_messages_for_llm(messages)

    tool_use_ids = {
        block["id"]
        for message in projected
        for block in message.get("content", [])
        if isinstance(message.get("content"), list) and block.get("type") == "tool_use"
    }
    tool_result_ids = {
        block["tool_use_id"]
        for message in projected
        for block in message.get("content", [])
        if isinstance(message.get("content"), list) and block.get("type") == "tool_result"
    }
    assert tool_use_ids == {f"call_{index}" for index in range(32)}
    assert tool_result_ids == tool_use_ids
    assert "orphan" not in tool_result_ids
    assert all("过程 " not in str(message) for message in projected)
