from pathlib import Path


def test_legacy_cognitive_map_runtime_is_not_registered():
    routing = Path("backend/app/core/routing.py").read_text()
    tools = Path("backend/app/tools/__init__.py").read_text()
    registry = Path("backend/app/agent/prompts/tool_registry.py").read_text()
    agent = Path("backend/app/agent/react_agent.py").read_text()

    assert "app.api.cognitive_map_routes" not in routing
    for legacy_name in (
        "cognitive_map_guidance",
        "cognitive_map_entity_query",
        "cognitive_map_graph_traverse",
    ):
        assert legacy_name not in tools
        assert legacy_name not in registry
    assert "backend_data_registry/cognitive_maps" not in agent
