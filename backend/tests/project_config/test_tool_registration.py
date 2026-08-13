from app.project_config.loader import load_project_context
from app.tools import GIS_TOOL_NAMES, create_global_tool_registry


def test_jiangxi_does_not_register_gis_tools():
    context = load_project_context("jiangxi")

    registry = create_global_tool_registry(context=context)

    assert GIS_TOOL_NAMES.isdisjoint(registry.list_tools())


def test_xuchang_registers_only_the_unified_historical_weather_tool():
    context = load_project_context("xuchang")

    registry = create_global_tool_registry(context=context)

    assert "get_weather_data" in registry.list_tools()
    assert "get_observed_meteorology" not in registry.list_tools()
