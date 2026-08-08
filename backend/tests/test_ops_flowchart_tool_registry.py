from app.agent.prompts.tool_registry import get_tool_order, get_tools_by_mode


def test_ops_mode_exposes_flowchart_artifact_tool():
    ops_tools = get_tools_by_mode("ops")

    assert "create_flowchart_artifact" in ops_tools
    assert "execute_python" in ops_tools


def test_ops_tool_order_prefers_flowchart_artifact_before_execute_python():
    ops_order = get_tool_order("ops")

    assert ops_order.index("create_flowchart_artifact") < ops_order.index("execute_python")
