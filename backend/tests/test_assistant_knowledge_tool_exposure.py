from app.agent.prompts.tool_registry import get_tool_order, get_tools_by_mode


def test_assistant_mode_delegates_knowledge_work():
    assistant_tools = get_tools_by_mode("assistant")

    assert "knowledge_qa_workflow" not in assistant_tools
    assert "knowledge_document_reader" not in assistant_tools
    assert "call_sub_agent" in assistant_tools


def test_assistant_tool_order_excludes_knowledge_execution():
    assistant_order = get_tool_order("assistant")

    assert "knowledge_qa_workflow" not in assistant_order
    assert "knowledge_document_reader" not in assistant_order


def test_social_mode_excludes_heavy_browser_and_domain_weather_tool():
    social_tools = get_tools_by_mode("assistant")
    social_order = get_tool_order("assistant")

    assert "browser" not in social_tools
    assert "browser" not in social_order
    assert "get_weather_forecast" not in social_tools
    assert "get_weather_forecast" not in social_order
