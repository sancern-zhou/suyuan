from app.agent.prompts.tool_registry import get_tool_order, get_tools_by_mode


def test_assistant_mode_exposes_knowledge_tools():
    assistant_tools = get_tools_by_mode("assistant")

    assert "knowledge_qa_workflow" in assistant_tools
    assert "knowledge_document_reader" in assistant_tools


def test_assistant_tool_order_places_knowledge_reader_after_retrieval():
    assistant_order = get_tool_order("assistant")

    assert "knowledge_qa_workflow" in assistant_order
    assert "knowledge_document_reader" in assistant_order
    assert assistant_order.index("knowledge_qa_workflow") < assistant_order.index("knowledge_document_reader")


def test_social_mode_excludes_heavy_browser_and_domain_weather_tool():
    social_tools = get_tools_by_mode("social")
    social_order = get_tool_order("social")

    assert "browser" not in social_tools
    assert "browser" not in social_order
    assert "get_weather_forecast" not in social_tools
    assert "get_weather_forecast" not in social_order
