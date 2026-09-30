from pathlib import Path

import pytest

from app.tools.visualization.create_business_chart.tool import CreateBusinessChartTool


def test_henan_city_map_uses_new_standard_breakpoints_by_metric():
    from app.tools.visualization.create_business_chart.domain.henan_city_map import (
        LEVELS,
        NEW_STANDARD_CONCENTRATION_BREAKS,
        _metric_key,
    )

    assert LEVELS == (50, 100, 150, 200, 300)
    assert NEW_STANDARD_CONCENTRATION_BREAKS["PM2_5"] == (35, 60, 115, 150, 250)
    assert NEW_STANDARD_CONCENTRATION_BREAKS["PM10"] == (50, 120, 250, 350, 420)
    assert NEW_STANDARD_CONCENTRATION_BREAKS["O3_8h"] == (100, 160, 215, 265, 800)
    assert _metric_key("PM2.5") == "PM2_5"
    assert _metric_key("O3_8H") == "O3_8h"


@pytest.mark.asyncio
async def test_wind_rose_renders_without_pollutant_concentrations():
    wind_directions = list(range(0, 360, 30)) * 2
    wind_speeds = [0.2 + (index % 6) * 0.8 for index in range(len(wind_directions))]
    result = await CreateBusinessChartTool().execute(
        chart_id="wind_rose_without_pollutant_case",
        chart_type="wind_rose",
        title="许昌市风向风速玫瑰图",
        data={"wind_directions": wind_directions, "wind_speeds": wind_speeds},
    )

    assert result["success"] is True
    assert result["data"]["metadata"]["applied_chart_type"] == "wind_rose"
    assert result["data"]["metadata"]["valid_point_count"] == len(wind_directions)
    assert result["data"]["metadata"]["calm_point_count"] > 0
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_wind_rose_rejects_mismatched_arrays():
    result = await CreateBusinessChartTool().execute(
        chart_type="wind_rose",
        title="风玫瑰图",
        data={"wind_directions": [0, 90], "wind_speeds": [1]},
    )

    assert result["success"] is False
    assert "长度必须一致" in result["error"]
