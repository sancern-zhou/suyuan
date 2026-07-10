from pathlib import Path


def test_agent_no_longer_injects_global_cognitive_map_directory():
    source = Path("backend/app/agent/react_agent.py").read_text()

    assert "build_cognitive_map_prompt_context" not in source
    assert "cognitive_map_context_set_to_context_builder" not in source


def test_query_and_ops_modes_use_knowledge_graph_query_tool():
    from app.agent.prompts.tool_registry import OPS_TOOL_NAMES, QUERY_TOOL_NAMES

    assert "knowledge_graph_query" in QUERY_TOOL_NAMES
    assert "knowledge_graph_query" in OPS_TOOL_NAMES
    assert "cognitive_map_guidance" not in OPS_TOOL_NAMES


def test_runtime_injects_selected_knowledge_bases_into_graph_tool():
    from app.agent.runtime.tool_coordinator import ToolCoordinator

    coordinator = ToolCoordinator(tool_executor=object(), knowledge_base_ids=["kb1"])

    assert coordinator.normalize_tool_input("knowledge_graph_query", {"query": "臭氧"}) == {
        "query": "臭氧",
        "knowledge_base_ids": ["kb1"],
    }
