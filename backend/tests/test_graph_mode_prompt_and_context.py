from app.agent.prompts.tool_registry import get_tool_order_by_mode, get_tools_by_mode


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
