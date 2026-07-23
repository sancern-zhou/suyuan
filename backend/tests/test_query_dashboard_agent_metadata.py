import asyncio
from types import SimpleNamespace

from app.agent.prompts.query_prompt import build_query_prompt
from app.agent.prompts import tool_registry
from app.agent.prompts.tool_registry import get_tool_order, get_tools_by_mode
from app.agent.core.planner import ReActPlanner
from app.agent.runtime.agent_runtime import AgentRuntime
from app.agent.runtime.assistant_stream_buffer import AssistantStreamBuffer
from app.agent.runtime.event_bus import RuntimeEventBus
from app.agent.runtime.finalizer import Finalizer
from app.agent.runtime.types import PlannerResult, RunState
from app.routers.agent import _build_final_message


def test_query_mode_exposes_station_day_tool():
    tool_name = "query_gd_suncere_station_day_new"

    assert tool_name in get_tools_by_mode("query")
    assert tool_name in get_tool_order("query")


def test_query_mode_tool_order_is_derived_from_allowlist():
    query_tool_names = list(get_tools_by_mode("query").keys())

    assert get_tool_order("query") == query_tool_names
    assert "knowledge_graph_query" in query_tool_names
    assert "resolve_station_geo" in query_tool_names


def test_all_mode_tool_orders_are_derived_from_allowlists():
    modes = [
        "assistant",
        "expert",
        "query",
        "report",
        "social",
        "chart",
        "ops",
        "memory_consolidator",
        "deliberation_meteorology",
        "deliberation_monitoring",
        "deliberation_chemistry",
        "deliberation_reviewer",
    ]

    for mode in modes:
        assert get_tool_order(mode) == list(get_tools_by_mode(mode).keys())


def test_tool_registry_does_not_expose_separate_tool_order_constants():
    assert not [
        name for name in dir(tool_registry)
        if name.endswith("_TOOL_ORDER")
    ]


def test_query_prompt_does_not_include_dashboard_metadata_contract():
    prompt = build_query_prompt(["query_city_standard_report"])

    assert "dashboard_focus" not in prompt
    assert "answer_evidence" not in prompt
    assert "query_dashboard_metadata" not in prompt
    assert "natural-language-only" not in prompt


def test_build_final_message_does_not_promote_dashboard_metadata():
    event_data = {
        "answer": "广州今日空气质量良好。",
        "timestamp": "2026-06-22T10:00:00+08:00",
        "visuals": [{"id": "v-1", "title": "AQI趋势"}],
        "dashboard_focus": {
            "scope": "city",
            "cities": ["广州"],
            "stations": [],
            "pollutants": ["AQI"],
            "time_range": {"label": "今日"},
            "modules": ["realtime"],
            "layer_state": {"heatmap": True},
            "source_data_ids": ["realtime-20260622"],
        },
        "answer_evidence": {
            "claims": [
                {
                    "text": "广州今日空气质量良好。",
                    "metrics": ["AQI"],
                    "source_data_ids": ["realtime-20260622"],
                }
            ]
        },
    }

    final_message = _build_final_message(event_data)

    assert final_message["type"] == "final"
    assert final_message["content"] == event_data["answer"]
    assert final_message["data"] == event_data
    assert final_message["visuals"] == event_data["visuals"]
    assert "dashboard_focus" not in final_message
    assert "answer_evidence" not in final_message


def test_planner_preserves_dashboard_metadata_json_as_plain_answer():
    planner = ReActPlanner(llm_client=object())
    text = (
        "广州今日空气质量良好。\n\n"
        "```json\n"
        "{\n"
        '  "query_dashboard_metadata": true,\n'
        '  "dashboard_focus": {"scope": "city", "cities": ["广州"]},\n'
        '  "answer_evidence": {"claims": []}\n'
        "}\n"
        "```"
    )
    result = planner._parse_accumulated_blocks([{"type": "text", "text": text}])

    action = result["action"]
    assert action["type"] == "PLAIN_TEXT_REPLY"
    assert action["answer"] == text
    assert "dashboard_focus" not in action
    assert "answer_evidence" not in action


def test_planner_preserves_marked_metadata_block_by_default_for_non_query_modes():
    planner = ReActPlanner(llm_client=object())
    text = (
        "下面是看板协议示例：\n\n"
        "```json\n"
        "{\n"
        '  "query_dashboard_metadata": true,\n'
        '  "dashboard_focus": {"scope": "city", "cities": ["广州"]},\n'
        '  "answer_evidence": {"claims": []}\n'
        "}\n"
        "```"
    )

    result = planner._parse_accumulated_blocks([{"type": "text", "text": text}])

    action = result["action"]
    assert action["type"] == "PLAIN_TEXT_REPLY"
    assert action["answer"] == text
    assert "dashboard_focus" not in action
    assert "answer_evidence" not in action


def test_planner_preserves_bare_marked_json_as_plain_answer_even_when_query_enabled():
    planner = ReActPlanner(llm_client=object())
    text = (
        "{\n"
        '  "query_dashboard_metadata": true,\n'
        '  "dashboard_focus": {"scope": "city", "cities": ["广州"]},\n'
        '  "answer_evidence": {"claims": []}\n'
        "}"
    )

    result = planner._parse_accumulated_blocks(
        [{"type": "text", "text": text}],
    )

    action = result["action"]
    assert action["type"] == "PLAIN_TEXT_REPLY"
    assert action["answer"] == text
    assert "dashboard_focus" not in action
    assert "answer_evidence" not in action


def test_planner_preserves_plain_fenced_marked_json_when_query_enabled():
    planner = ReActPlanner(llm_client=object())
    text = (
        "广州今日空气质量良好。\n\n"
        "```\n"
        "{\n"
        '  "query_dashboard_metadata": true,\n'
        '  "dashboard_focus": {"scope": "city", "cities": ["广州"]},\n'
        '  "answer_evidence": {"claims": []}\n'
        "}\n"
        "```"
    )

    result = planner._parse_accumulated_blocks(
        [{"type": "text", "text": text}],
    )

    action = result["action"]
    assert action["type"] == "PLAIN_TEXT_REPLY"
    assert action["answer"] == text
    assert "dashboard_focus" not in action
    assert "answer_evidence" not in action


def test_planner_preserves_ordinary_json_that_mentions_dashboard_focus():
    planner = ReActPlanner(llm_client=object())
    text = (
        "下面是接口示例，不是看板联动元数据：\n\n"
        "```json\n"
        "{\n"
        '  "dashboard_focus": {"scope": "city", "cities": ["广州"]},\n'
        '  "note": "普通文档示例"\n'
        "}\n"
        "```"
    )

    result = planner._parse_accumulated_blocks([{"type": "text", "text": text}])

    action = result["action"]
    assert action["type"] == "PLAIN_TEXT_REPLY"
    assert action["answer"] == text
    assert "dashboard_focus" not in action
    assert "answer_evidence" not in action


def test_assistant_stream_buffer_preserves_marked_metadata_block():
    buffer = AssistantStreamBuffer()
    chunks = [
        "广州今日空气质量良好。",
        "\n\n```json\n",
        "{\n",
        '  "query_dashboard_metadata": true,\n',
        '  "dashboard_focus": {"scope": "city", "cities": ["广州"]},\n',
        '  "answer_evidence": {"claims": []}\n',
        "}\n```",
    ]

    visible = "".join(buffer.append(chunk) for chunk in chunks)

    assert visible == "".join(chunks)


def test_completion_action_dashboard_metadata_is_not_captured_on_run_state():
    state = RunState(session_id="session-1", user_query="广州今日空气", mode="query")
    action = {
        "type": "PLAIN_TEXT_REPLY",
        "answer": "广州今日空气质量良好。",
        "dashboard_focus": {"scope": "city", "cities": ["广州"], "source_data_ids": ["d-1"]},
        "answer_evidence": {
            "claims": [
                {
                    "text": "广州今日空气质量良好。",
                    "metrics": ["AQI"],
                    "source_data_ids": ["d-1"],
                }
            ]
        },
    }

    assert not hasattr(state, "dashboard_focus")
    assert not hasattr(state, "answer_evidence")


def test_complete_event_does_not_include_dashboard_metadata():
    state = RunState(session_id="session-1", user_query="广州今日空气", mode="query")
    state.response_text = "广州今日空气质量良好。"

    event = RuntimeEventBus().complete(state)

    assert "dashboard_focus" not in event["data"]
    assert "answer_evidence" not in event["data"]


def test_complete_response_integration_does_not_emit_dashboard_metadata():
    dashboard_focus = {"scope": "city", "cities": ["广州"], "source_data_ids": ["d-1"]}
    answer_evidence = {
        "claims": [
            {
                "text": "广州今日空气质量良好。",
                "metrics": ["AQI"],
                "source_data_ids": ["d-1"],
            }
        ]
    }

    class Writer:
        def __init__(self):
            self.user_messages = []
            self.iterations = []
            self.final_messages = []
            self.session = SimpleNamespace(add_assistant_response=lambda text: None)

        def add_user_message(self, content):
            self.user_messages.append(content)

        def add_iteration(self, thought, action, observation):
            self.iterations.append((thought, action, observation))

        def add_final_assistant_message(self, state, planner_result, thought=None):
            self.final_messages.append((state.response_text, thought))
            state.assistant_message_written = True

    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = SimpleNamespace(agent_logger=None)
    runtime.events = RuntimeEventBus()
    runtime.writer = Writer()
    runtime.finalizer = Finalizer(runtime.writer, runtime.events)
    runtime.observation_processor = SimpleNamespace(
        capture_last_knowledge_sources=lambda state: False
    )
    state = RunState(session_id="session-1", user_query="广州今日空气", mode="query")
    planner_result = PlannerResult(
        thought="整理最终答案",
        action={
            "type": "PLAIN_TEXT_REPLY",
            "answer": "广州今日空气质量良好。",
            "dashboard_focus": dashboard_focus,
            "answer_evidence": answer_evidence,
        },
    )

    async def collect_events():
        return [
            event
            async for event in runtime._complete_response(
                state,
                planner_result,
                "广州今日空气质量良好。",
            )
        ]

    events = asyncio.run(collect_events())
    complete = next(event for event in events if event["type"] == "complete")

    assert complete["data"]["answer"] == "广州今日空气质量良好。"
    assert "dashboard_focus" not in complete["data"]
    assert "answer_evidence" not in complete["data"]
