from app.agent.prompts.tool_registry import get_tool_order, get_tools_by_mode


def test_social_mode_uses_unified_session_file_publication():
    social_tools = get_tools_by_mode("social")

    assert "present_artifact" not in social_tools
    assert "publish_session_file" in social_tools


def test_social_tool_order_uses_unified_session_file_publication():
    social_order = get_tool_order("social")

    assert "present_artifact" not in social_order
    assert "publish_session_file" in social_order
