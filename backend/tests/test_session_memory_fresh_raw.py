import json

from app.agent.memory.session_memory import SessionMemory


def test_current_run_projects_raw_tool_result_without_mutating_history(tmp_path):
    session = SessionMemory("fresh-raw", base_dir=tmp_path)
    session.add_user_message("读取当前数据")
    raw_result = {
        "success": True,
        "data": {"rows": [{"value": "exact-current-result"}]},
    }

    session.add_streaming_tool_results([{
        "tool_name": "read_data",
        "tool_use_id": "toolu_1",
        "tool_input": {},
        "result": raw_result,
    }])
    projected = session.get_messages_for_llm()

    content = json.loads(projected[-1]["content"][0]["content"])
    assert content == raw_result
    stored_raw = session.conversation_history[-1].data["raw_results"][0]["raw"]
    assert stored_raw is raw_result


def test_fresh_raw_budget_downgrades_oldest_results_first(tmp_path, monkeypatch):
    monkeypatch.setattr("app.agent.memory.session_memory._fresh_budgets", lambda: (70_000, 65_000))
    session = SessionMemory("fresh-budget", base_dir=tmp_path)
    session.add_user_message("读取多份数据")
    for index in range(3):
        session.add_streaming_tool_results([{
            "tool_name": "read_data",
            "tool_use_id": f"toolu_{index}",
            "tool_input": {},
            "result": {"success": True, "data": {"payload": "x" * 60_000, "index": index}},
        }])

    projected = session.get_messages_for_llm()
    results = [
        json.loads(message["content"][0]["content"])
        for message in projected
        if message.get("content")
        and isinstance(message["content"], list)
        and message["content"][0].get("type") == "tool_result"
    ]

    assert len(results) == 3
    payload_lengths = [len(result["data"]["payload"]) for result in results]
    assert max(payload_lengths) == 60_000
    assert sum(length == 60_000 for length in payload_lengths) == 1


def test_single_result_over_budget_keeps_structured_data_until_next_user(tmp_path, monkeypatch):
    monkeypatch.setattr("app.agent.memory.session_memory._fresh_budgets", lambda: (5000, 5000))
    session = SessionMemory("single-budget", base_dir=tmp_path)
    session.add_user_message("读取本轮数据")
    session.add_streaming_tool_results([{
        "tool_name": "read_data", "tool_use_id": "t1", "tool_input": {},
        "result": {"success": True, "summary": "当前测量", "data": {"payload": "x" * 6000}},
    }])
    stored = session.conversation_history[-1].content[0]["content"]
    current = json.loads(session.get_messages_for_llm()[-1]["content"][0]["content"])
    assert current["data"]["payload"] == "x" * 6000
    session.add_user_message("下一轮")
    previous = json.loads(session.get_messages_for_llm()[-2]["content"][0]["content"])
    assert previous["tool_result_truncated"] is True
    assert previous["summary"] == "当前测量"
    assert session.conversation_history[-2].content[0]["content"] == stored
