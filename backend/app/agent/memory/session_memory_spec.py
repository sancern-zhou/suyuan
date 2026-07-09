from app.agent.memory.session_memory import SessionMemory


def test_history_projection_skips_display_tool_events():
    messages = [
        {"type": "user", "content": "把报告文件发给我", "timestamp": "2026-07-08T18:12:00"},
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
            "content": "工具 wait_task 执行失败",
            "timestamp": "2026-07-08T18:12:02",
            "data": {
                "tool_use_id": "call_wait",
                "tool_name": "wait_task",
                "result": {"status": "failed", "error": "boom"},
            },
        },
        {"type": "final", "content": "当前状态如下：...", "timestamp": "2026-07-08T18:12:03"},
    ]

    projected = SessionMemory.project_history_messages_for_llm(messages)

    assert projected == [
        {"role": "user", "content": "把报告文件发给我"},
        {"role": "assistant", "content": "当前状态如下：..."},
    ]
