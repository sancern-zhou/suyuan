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
