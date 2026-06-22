import asyncio
from types import SimpleNamespace

from app.agent.prompts.query_prompt import build_query_prompt
from app.agent.core.planner import ReActPlanner
from app.agent.runtime import agent_runtime as runtime_module
from app.agent.runtime.agent_runtime import AgentRuntime
from app.agent.runtime.assistant_stream_buffer import AssistantStreamBuffer
from app.agent.runtime.event_bus import RuntimeEventBus
from app.agent.runtime.finalizer import Finalizer
from app.agent.runtime.types import PlannerResult, RunState
from app.routers.agent import _build_final_message
from app.schemas.query_dashboard import AnswerEvidence, DashboardFocus


def test_dashboard_focus_contract_accepts_city_question_metadata():
    focus = DashboardFocus(
        scope="city",
        cities=["广州"],
        stations=["天河"],
        pollutants=["O3", "PM2.5"],
        time_range={
            "start": "2026-06-01",
            "end": "2026-06-21",
            "label": "6月以来",
        },
        modules=["realtime", "ranking"],
        layer_state={"heatmap": True, "stations": False},
        source_data_ids=["city-standard-202606"],
    )
    evidence = AnswerEvidence(
        claims=[
            {
                "text": "广州6月以来O3较高。",
                "metrics": ["O3"],
                "source_data_ids": ["city-standard-202606"],
            }
        ]
    )

    assert focus.model_dump() == {
        "scope": "city",
        "cities": ["广州"],
        "stations": ["天河"],
        "pollutants": ["O3", "PM2.5"],
        "time_range": {
            "start": "2026-06-01",
            "end": "2026-06-21",
            "label": "6月以来",
        },
        "modules": ["realtime", "ranking"],
        "layer_state": {"heatmap": True, "stations": False},
        "source_data_ids": ["city-standard-202606"],
    }
    assert evidence.model_dump() == {
        "claims": [
            {
                "text": "广州6月以来O3较高。",
                "metrics": ["O3"],
                "source_data_ids": ["city-standard-202606"],
            }
        ],
        "query_params": {},
    }


def test_query_prompt_includes_dashboard_metadata_contract():
    prompt = build_query_prompt(["query_city_standard_report"])

    assert "dashboard_focus" in prompt
    assert "answer_evidence" in prompt
    assert "source_data_ids" in prompt
    assert "layer_state" in prompt
    assert "query_dashboard_metadata" in prompt
    assert "natural-language-only" in prompt
    for field_name in (
        "scope",
        "cities",
        "stations",
        "pollutants",
        "time_range",
        "modules",
        "claims",
        "metrics",
    ):
        assert field_name in prompt


def test_build_final_message_preserves_dashboard_metadata():
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
    assert final_message["dashboard_focus"] == event_data["dashboard_focus"]
    assert final_message["answer_evidence"] == event_data["answer_evidence"]


def test_planner_extracts_dashboard_metadata_from_final_json_block():
    planner = ReActPlanner(llm_client=object())
    result = planner._parse_accumulated_blocks([
        {
            "type": "text",
            "text": (
                "广州今日空气质量良好。\n\n"
                "```json\n"
                "{\n"
                '  "query_dashboard_metadata": true,\n'
                '  "dashboard_focus": {\n'
                '    "scope": "city",\n'
                '    "cities": ["广州"],\n'
                '    "stations": [],\n'
                '    "pollutants": ["AQI"],\n'
                '    "time_range": {"label": "今日"},\n'
                '    "modules": ["realtime"],\n'
                '    "layer_state": {"heatmap": true},\n'
                '    "source_data_ids": ["realtime-20260622"]\n'
                "  },\n"
                '  "answer_evidence": {\n'
                '    "claims": [{\n'
                '      "text": "广州今日空气质量良好。",\n'
                '      "metrics": ["AQI"],\n'
                '      "source_data_ids": ["realtime-20260622"]\n'
                "    }]\n"
                "  }\n"
                "}\n"
                "```"
            ),
        }
    ])

    action = result["action"]
    assert action["type"] == "PLAIN_TEXT_REPLY"
    assert action["answer"] == "广州今日空气质量良好。"
    assert action["dashboard_focus"]["cities"] == ["广州"]
    assert action["answer_evidence"]["claims"][0]["source_data_ids"] == ["realtime-20260622"]


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


def test_query_dashboard_stream_buffer_suppresses_marked_metadata_block():
    buffer = AssistantStreamBuffer(suppress_marked_dashboard_metadata=True)
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

    assert visible == "广州今日空气质量良好。\n\n"
    assert "query_dashboard_metadata" not in visible
    assert "dashboard_focus" not in visible


def test_query_dashboard_stream_buffer_preserves_unmarked_json_block():
    buffer = AssistantStreamBuffer(suppress_marked_dashboard_metadata=True)
    chunks = [
        "下面是示例：\n",
        "```json\n",
        '{"dashboard_focus": {"scope": "city"}}',
        "\n```",
    ]

    visible = "".join(buffer.append(chunk) for chunk in chunks)

    assert visible == "".join(chunks)


def test_completion_action_metadata_is_captured_on_run_state():
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

    runtime_module._capture_final_response_metadata(state, action)

    assert state.dashboard_focus == action["dashboard_focus"]
    assert state.answer_evidence == action["answer_evidence"]


def test_completion_action_metadata_is_query_mode_only():
    state = RunState(session_id="session-1", user_query="解释字段", mode="assistant")
    action = {
        "type": "PLAIN_TEXT_REPLY",
        "answer": "示例。",
        "dashboard_focus": {"scope": "city", "cities": ["广州"]},
        "answer_evidence": {"claims": []},
    }

    runtime_module._capture_final_response_metadata(state, action)

    assert state.dashboard_focus is None
    assert state.answer_evidence is None


def test_complete_event_includes_dashboard_metadata_from_state():
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
    state = RunState(
        session_id="session-1",
        user_query="广州今日空气",
        mode="query",
        dashboard_focus=dashboard_focus,
        answer_evidence=answer_evidence,
    )
    state.response_text = "广州今日空气质量良好。"

    event = RuntimeEventBus().complete(state)

    assert event["data"]["dashboard_focus"] == dashboard_focus
    assert event["data"]["answer_evidence"] == answer_evidence


def test_complete_response_integration_emits_dashboard_metadata():
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

    class Guard:
        async def check(self, session_id):
            return {"has_incomplete": False}

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
    runtime.config = SimpleNamespace(task_completion_guard=Guard(), agent_logger=None)
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
    assert complete["data"]["dashboard_focus"] == dashboard_focus
    assert complete["data"]["answer_evidence"] == answer_evidence
