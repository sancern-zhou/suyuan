from pathlib import Path

import pytest

from app.tools.visualization.create_business_chart.specialized import (
    _direction_bin_index,
    _level_frequency_counts,
)
from app.tools.visualization.create_business_chart.tool import CreateBusinessChartTool


PM10_BREAKS = (50, 120, 250, 350, 420)


def _execute(concentrations, **options):
    return CreateBusinessChartTool().execute(
        chart_id="generic_pollutant_wind_rose_level_frequency",
        chart_type="generic_pollutant_wind_rose",
        title="PM10 污染玫瑰图",
        data={
            "wind_directions": [0] * len(concentrations),
            "wind_speeds": [1.0] * len(concentrations),
            "concentrations": concentrations,
        },
        options={"pollutant_name": "PM10", "unit": "μg/m³", **options},
    )


def test_direction_bin_index_centers_bins_on_compass_points():
    # 16 个扇区时每个扇区 22.5°，N 扇区覆盖 348.75°–11.25°。
    assert [_direction_bin_index(value, 16) for value in (0, 11, 12, 359)] == [0, 0, 1, 0]


def test_level_frequency_counts_center_bins_on_compass_points():
    counts, total = _level_frequency_counts(
        wind_directions=[0, 11, 12, 359],
        wind_speeds=[1.0, 1.0, 1.0, 1.0],
        concentrations=[10.0, 10.0, 10.0, 10.0],
        direction_bins=16,
        breaks=PM10_BREAKS,
        level_count=6,
    )

    assert total == 4
    # 0°、11° 和 359° 都落在以 N 为中心的扇区，12° 进入下一扇区。
    assert counts[0].sum() == 3
    assert counts[1].sum() == 1


def test_level_frequency_counts_drop_invalid_concentrations():
    counts, total = _level_frequency_counts(
        wind_directions=[0, 90, 180, 270],
        wind_speeds=[1.0, 1.0, -1.0, 1.0],
        concentrations=[30.0, float("nan"), 30.0, -5.0],
        direction_bins=8,
        breaks=PM10_BREAKS,
        level_count=6,
    )

    assert total == 1
    assert counts[:, 0].sum() == 1


@pytest.mark.asyncio
async def test_level_frequency_mode_stacks_levels_and_reports_shares():
    result = await _execute(
        [30, 30, 30, 30, 100, 100, 200, 500],
        radial_metric="level_frequency",
        direction_bins=16,
    )

    assert result["success"] is True
    metadata = result["data"]["metadata"]
    assert metadata["radial_metric"] == "level_frequency"
    assert metadata["radial_unit"] == "%"
    assert metadata["direction_bin_count"] == 16
    assert metadata["valid_point_count"] == 8
    assert metadata["level_frequency_totals"] == {
        "优": 50.0,
        "良": 25.0,
        "轻度污染": 12.5,
        "中度污染": 0.0,
        "重度污染": 0.0,
        "严重污染": 12.5,
    }
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_default_mode_keeps_mean_concentration_contract():
    result = await _execute([30, 60, 90])

    assert result["success"] is True
    metadata = result["data"]["metadata"]
    assert metadata["radial_metric"] == "mean_concentration"
    assert "radial_unit" not in metadata
    assert metadata["valid_point_count"] == 3
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_unknown_radial_metric_is_rejected():
    result = await _execute([30], radial_metric="frequency")

    assert result["success"] is False
    assert "radial_metric" in result["error"]
