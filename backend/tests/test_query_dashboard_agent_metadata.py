from app.agent.prompts.query_prompt import build_query_prompt
from app.agent.core.planner import ReActPlanner
from app.agent.runtime import agent_runtime as runtime_module
from app.agent.runtime.event_bus import RuntimeEventBus
from app.agent.runtime.types import RunState
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
