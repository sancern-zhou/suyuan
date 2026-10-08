import pytest

from app.tools.visualization.create_business_chart.tool import (
    CreateBusinessChartTool,
    available_chart_types,
    chart_type_enabled,
    business_chart_reference_paths,
)
from config.settings import settings

# 广东省专用 chart_type -> 非广东项目的替代图型。
SCOPED_CHART_TYPES = {
    "pollutant_wind_rose": "generic_pollutant_wind_rose",
    "aqi_calendar": "pollutant_calendar",
}


@pytest.mark.parametrize("chart_type, fallback", SCOPED_CHART_TYPES.items())
def test_guangdong_chart_types_are_scoped_to_default(chart_type, fallback):
    assert chart_type_enabled(chart_type, "default") is True
    assert chart_type_enabled(chart_type, "xuchang") is False

    assert chart_type in available_chart_types("default")
    assert chart_type not in available_chart_types("xuchang")
    assert fallback in available_chart_types("xuchang")


def test_xuchang_reference_paths_hide_guangdong_chart_types(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")
    xuchang_paths = business_chart_reference_paths()
    monkeypatch.setattr(settings, "project_id", "default")
    default_paths = business_chart_reference_paths()

    for chart_type, fallback in SCOPED_CHART_TYPES.items():
        assert chart_type not in xuchang_paths
        assert chart_type in default_paths
        assert fallback in xuchang_paths


def test_xuchang_schema_omits_guangdong_chart_types(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")
    tool = CreateBusinessChartTool()

    enum = tool.get_function_schema()["parameters"]["properties"]["chart_type"]["enum"]
    for chart_type, fallback in SCOPED_CHART_TYPES.items():
        assert chart_type not in enum
        assert fallback in enum


def test_default_schema_keeps_guangdong_chart_types(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "default")
    tool = CreateBusinessChartTool()

    enum = tool.get_function_schema()["parameters"]["properties"]["chart_type"]["enum"]
    for chart_type, fallback in SCOPED_CHART_TYPES.items():
        assert chart_type in enum
        assert fallback in enum


@pytest.mark.asyncio
@pytest.mark.parametrize("chart_type, fallback", SCOPED_CHART_TYPES.items())
async def test_xuchang_rejects_guangdong_chart_type_calls(monkeypatch, chart_type, fallback):
    monkeypatch.setattr(settings, "project_id", "xuchang")
    tool = CreateBusinessChartTool()

    result = await tool.execute(
        chart_type=chart_type,
        title="广东专用图型",
        data={"wind_directions": [0.0], "wind_speeds": [1.0], "concentrations": [10.0]},
    )

    assert result["success"] is False
    assert fallback in result["error"]
