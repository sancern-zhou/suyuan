"""Public business-chart boundaries and supported rendering contracts."""

from pathlib import Path

import pytest

from app.tools.visualization.create_business_chart.renderer import (
    ChartDataError,
    render_business_chart,
)
from app.tools.visualization.create_business_chart.tool import CreateBusinessChartTool


GENERIC_TYPES = [
    "bar", "horizontal_bar", "line", "timeseries", "scatter", "pie",
    "stacked_area", "dual_axis_line", "stacked_bar", "percent_stacked_bar",
    "histogram", "correlation_heatmap", "boxplot", "combo", "range_line",
    "waterfall", "pareto", "diverging_bar", "step_line", "error_bar", "unknown",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("chart_type", GENERIC_TYPES)
@pytest.mark.parametrize("dry_run", [False, True])
async def test_generic_types_are_rejected_before_loading_or_rendering(chart_type, dry_run):
    class Context:
        def get_data_payload(self, file_path):
            pytest.fail("Unsupported charts must not load input files")

    result = await CreateBusinessChartTool().execute(
        context=Context(), chart_type=chart_type, title="Unsupported chart",
        file_path="/session/data/chart.json", options={"dry_run": dry_run},
    )
    assert result["success"] is False
    assert not result.get("visuals")
    assert not result.get("resources")
    assert "execute_echarts_python" in result["error"]
    assert "execute_python" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("dry_run", [False, True])
async def test_nested_charts_cannot_bypass_type_restrictions(dry_run):
    result = await CreateBusinessChartTool().execute(
        chart_type="pollutant_calendar", title="Nested request",
        data={"charts": [{"chart_type": "bar", "data": {"values": [1]}}]},
        options={"dry_run": dry_run},
    )
    assert result["success"] is False
    assert "charts" in result["error"]
    assert not result.get("visuals")


@pytest.mark.asyncio
async def test_nested_charts_loaded_from_file_are_rejected():
    class Context:
        def get_data_payload(self, file_path):
            return {"charts": [{"chart_type": "bar", "data": {"values": [1]}}]}

    result = await CreateBusinessChartTool().execute(
        context=Context(), chart_type="pollutant_calendar", title="Nested file",
        file_path="/session/data/chart.json",
    )
    assert result["success"] is False
    assert "charts" in result["error"]
    assert not result.get("visuals")


@pytest.mark.parametrize("chart_type", GENERIC_TYPES)
def test_public_renderer_rejects_generic_types(chart_type):
    with pytest.raises(ChartDataError, match="execute_python"):
        render_business_chart(chart_id="unsupported", chart_type=chart_type,
                            title="Unsupported", data={"values": [1]},
                            output_context="word", style_profile="report", options={})


@pytest.mark.asyncio
async def test_weather_template_still_renders_and_publishes_image():
    result = await CreateBusinessChartTool().execute(
        chart_type="weather_timeseries", title="Weather forecast",
        data={"records": [
            {"forecast_time": f"2026-05-01 {hour:02d}:00:00",
             "wind_speed": 3, "wind_direction_degrees": 90,
             "temperature": 25, "precipitation_probability": 20, "humidity": 60}
            for hour in [0, 3, 6]
        ]},
    )
    assert result["success"] is True, result.get("error")
    assert Path(result["visuals"][0]["local_path"]).is_file()
    assert len(result["resources"]) == 2
