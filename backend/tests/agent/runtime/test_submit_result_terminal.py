"""submit_result 交付边界：工具结果命中即结束本轮，不再等待额外纯文本。"""

import json

import pytest

from app.agent.runtime.agent_runtime import AgentRuntime
from app.agent.runtime.types import PlannerResult, RunState


def test_submitted_result_from_records_reads_envelope():
    records = [{
        "tool_name": "submit_result",
        "result": {
            "success": True,
            "data": {"submitted_result": {"status": "completed", "findings": []}},
        },
    }]
    assert AgentRuntime._submitted_result_from_records(records) == {
        "status": "completed",
        "findings": [],
    }


def test_submitted_result_from_records_ignores_other_tools_and_failures():
    assert AgentRuntime._submitted_result_from_records([
        {"tool_name": "execute_python", "result": {"success": True}},
    ]) is None
    assert AgentRuntime._submitted_result_from_records([
        {"tool_name": "submit_result", "result": {"success": False, "error": "bad"}},
    ]) is None


def test_submitted_result_from_records_returns_empty_dict_without_envelope():
    assert AgentRuntime._submitted_result_from_records([
        {"tool_name": "submit_result", "result": {"success": True}},
    ]) == {}


@pytest.mark.asyncio
async def test_complete_after_submit_result_uses_envelope_as_answer():
    runtime = object.__new__(AgentRuntime)
    captured = {}

    async def fake_complete(state, planner_result, answer):
        captured["answer"] = answer
        yield {"type": "agent_finish"}

    runtime._complete_response = fake_complete
    state = RunState(session_id="s", user_query="q", mode="query_monitoring_city")
    events = [
        event
        async for event in runtime._complete_after_submit_result(
            state,
            PlannerResult(),
            {"status": "completed", "findings": [{"id": 1}]},
        )
    ]

    assert captured["answer"] == json.dumps(
        {"status": "completed", "findings": [{"id": 1}]}, ensure_ascii=False
    )
    assert events == [{"type": "agent_finish"}]
