from app.agent.context.context_builder import SimplifiedContextBuilder
import app.api.agent as agent_routes
from app.api.agent import AgentAnalyzeRequest


def test_agent_analyze_request_accepts_map_context_aliases():
    request = AgentAnalyzeRequest(
        query="分析框选区域污染来源",
        mode="query",
        mapContext={
            "type": "map_context",
            "session_id": "query_session_demo",
            "events": [{"type": "map_event", "event": "draw_completed"}],
        },
    )

    assert request.map_context["type"] == "map_context"
    assert request.map_context["events"][0]["event"] == "draw_completed"


def test_query_mode_injects_map_context_into_user_conversation():
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)
    builder.map_context = {
        "type": "map_context",
        "session_id": "query_session_demo",
        "current_program": {"program_id": "mapprog_turn_12"},
        "events": [
            {
                "type": "map_event",
                "event": "draw_completed",
                "geometry": {"type": "Polygon"},
                "active_layers": ["high_pm25"],
                "map_view": {"center": [113.26, 23.13], "zoom": 8},
            }
        ],
    }
    builder.current_mode = "query"

    conversation = builder._build_user_conversation(
        query="分析框选区域污染来源",
        iteration=1,
        latest_observation="",
        conversation_history=[],
    )

    assert "当前地图交互上下文" in conversation
    assert "mapprog_turn_12" in conversation
    assert "draw_completed" in conversation
    assert "high_pm25" in conversation
    assert "113.26" in conversation


def test_non_query_mode_strips_map_context():
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)
    builder.map_context = {"type": "map_context", "events": [{"event": "draw_completed"}]}

    builder._apply_mode_context_policy("expert")

    assert builder.map_context is None


def test_agent_route_does_not_short_circuit_map_commands_with_keyword_parser():
    assert not hasattr(agent_routes, "_direct_query_map_view_command")
