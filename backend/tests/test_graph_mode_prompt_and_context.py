from pathlib import Path

from app.agent.context.context_builder import SimplifiedContextBuilder
from app.agent.prompts.tool_registry import get_tool_order_by_mode, get_tools_by_mode
from app.agent.prompts.prompt_builder import build_react_system_prompt


def test_graph_mode_exposes_existing_safe_tools_only():
    tools = get_tools_by_mode("graph")

    assert list(tools.keys()) == [
        "cognitive_map_guidance",
        "read_file",
        "grep",
        "list_directory",
        "search_files",
        "execute_python",
    ]
    assert "edit_file" not in tools
    assert "write_file" not in tools
    assert "bash" not in tools


def test_graph_mode_tool_order_matches_registry_order():
    assert get_tool_order_by_mode("graph") == [
        "cognitive_map_guidance",
        "read_file",
        "grep",
        "list_directory",
        "search_files",
        "execute_python",
    ]


def test_graph_prompt_routes_from_prompt_builder():
    prompt = build_react_system_prompt("graph")

    assert "认知地图图谱编辑 Agent" in prompt
    assert "POST   /api/cognitive-maps/{map_id}/entities" in prompt
    assert "PATCH  /api/cognitive-maps/{map_id}/relations/{relation_id}" in prompt
    assert "禁止默认直接编辑 `extraction.json`" in prompt
    assert "execute_python" in prompt


def test_graph_prompt_rejects_unavailable_write_tools():
    prompt = build_react_system_prompt(
        "graph",
        available_tools=["read_file", "write_file", "edit_file", "execute_python"],
    )

    assert "execute_python" in prompt
    assert "read_file" in prompt
    assert "write_file" not in prompt
    assert "edit_file" not in prompt


def test_graph_mode_preserves_map_context_and_builds_summary():
    builder = SimplifiedContextBuilder(None, None)
    builder.current_mode = "graph"
    builder.map_context = {
        "active_map_id": "map_123",
        "active_map_name": "站点故障图谱",
        "selected_item": {
            "kind": "relation",
            "id": "relation_abc",
            "name": "零点漂移 -> indicates -> 零漂异常",
        },
        "visible_entity_ids": ["entity_a", "entity_b", "entity_c"],
        "visible_relation_ids": ["relation_abc"],
        "entity_count": 3,
        "relation_count": 1,
    }

    builder._apply_mode_context_policy("graph")
    summary = builder._build_graph_map_context_user_summary()

    assert builder.map_context is not None
    assert "当前认知地图上下文" in summary
    assert "map_123" in summary
    assert "站点故障图谱" in summary
    assert "relation_abc" in summary
    assert "visible_entity_ids=3" in summary


def test_non_graph_non_query_modes_strip_map_context():
    builder = SimplifiedContextBuilder(None, None)
    builder.current_mode = "assistant"
    builder.map_context = {"active_map_id": "map_123"}

    builder._apply_mode_context_policy("assistant")

    assert builder.map_context is None


def test_router_forwards_map_context_for_graph_mode():
    source = Path("backend/app/routers/agent.py").read_text(encoding="utf-8")

    assert 'if request.mode in {"query", "graph"} and request.map_context:' in source
    assert 'analyze_kwargs["map_context"] = request.map_context' in source


def test_react_agent_sets_map_context_for_graph_mode():
    source = Path("backend/app/agent/react_agent.py").read_text(encoding="utf-8")

    assert 'if manual_mode in {"query", "graph"} and map_context:' in source
    assert "react_loop.context_builder.map_context = map_context" in source
