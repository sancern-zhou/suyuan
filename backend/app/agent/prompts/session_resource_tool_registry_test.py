import pytest

from app.agent.prompts import tool_registry


ALL_MODE_LISTS = [
    tool_registry.ASSISTANT_TOOL_NAMES,
    tool_registry.PPT_TOOL_NAMES,
    tool_registry.EXPERT_TOOL_NAMES,
    tool_registry.QUERY_TOOL_NAMES,
    tool_registry.REPORT_TOOL_NAMES,
    tool_registry.CHART_TOOL_NAMES,
    tool_registry.OPS_TOOL_NAMES,
    tool_registry.GRAPH_TOOL_NAMES,
    tool_registry.SOCIAL_TOOL_NAMES,
    tool_registry.MEMORY_CONSOLIDATOR_TOOL_NAMES,
    tool_registry.DELIBERATION_METEOROLOGY_TOOL_NAMES,
    tool_registry.DELIBERATION_MONITORING_TOOL_NAMES,
    tool_registry.DELIBERATION_CHEMISTRY_TOOL_NAMES,
    tool_registry.DELIBERATION_REVIEWER_TOOL_NAMES,
]


@pytest.mark.parametrize("tool_names", ALL_MODE_LISTS)
def test_resource_discovery_is_available_exactly_once_in_every_mode(tool_names):
    assert tool_names.count("list_session_resources") == 1
