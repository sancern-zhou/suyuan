from pathlib import Path

import pytest

from app.tools.visualization.create_business_chart.tool import CreateBusinessChartTool
from app.utils.path_config import resolve_agent_path
from config.settings import settings


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


def test_xuchang_district_map_asset_and_district_scope():
    import json

    from app.tools.visualization.create_business_chart.domain.xuchang_district_map import (
        DEFAULT_BOUNDARY_ASSET,
        FUNCTIONAL_ZONE_STATIONS,
        OFFICIAL_DISTRICTS,
        SUPPORTED_DISTRICTS,
        _district_key,
    )

    assert DEFAULT_BOUNDARY_ASSET.exists()
    payload = json.loads(DEFAULT_BOUNDARY_ASSET.read_text(encoding="utf-8"))
    features = payload["features"]
    assert {feature["properties"]["name"] for feature in features} == set(OFFICIAL_DISTRICTS)
    assert {feature["properties"]["adcode"] for feature in features} == set(OFFICIAL_DISTRICTS.values())
    assert set(FUNCTIONAL_ZONE_STATIONS) == {"东城区", "开发区", "示范区"}
    assert sum(len(stations) for stations in FUNCTIONAL_ZONE_STATIONS.values()) == 8
    assert set(OFFICIAL_DISTRICTS) | set(FUNCTIONAL_ZONE_STATIONS) == set(SUPPORTED_DISTRICTS)
    assert _district_key("经济技术开发区") == "开发区"
    assert _district_key("许昌市城乡一体化示范区") == "示范区"
    assert _district_key("魏都") == "魏都区"
    assert _district_key("禹州市") == "禹州市"
    assert _district_key("许昌市建安区") == "建安区"
    assert _district_key("郑州") == ""


@pytest.mark.asyncio
async def test_xuchang_district_map_renders_official_and_functional_zones(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")
    records = [
        {"district": "魏都区", "value": 61},
        {"district": "建安区", "value": 72},
        {"district": "鄢陵县", "value": 58},
        {"district": "襄城县", "value": 65},
        {"district": "禹州市", "value": 81},
        {"district": "长葛市", "value": 69},
        {"district": "东城区", "value": 63},
        {"district": "经济技术开发区", "value": 66},
        {"district": "示范区", "value": 60},
    ]
    result = await CreateBusinessChartTool().execute(
        chart_id="xuchang_district_map_case",
        chart_type="xuchang_district_map",
        title="许昌市各区县空气质量指数分布",
        data={"metric": "AQI", "records": records},
    )

    assert result["success"] is True, result.get("error")
    metadata = result["data"]["metadata"]
    assert metadata["applied_chart_type"] == "xuchang_district_map"
    assert metadata["scope"] == "xuchang_districts"
    assert metadata["official_district_count"] == 6
    assert metadata["functional_zone_count"] == 3
    assert metadata["station_count"] == 8
    assert metadata["rendered_polygon_count"] >= 6
    assert metadata["unmatched_districts"] == []
    assert metadata["classification_basis"] == "AQI"
    assert sorted(metadata["functional_zone_stations"]) == ["东城区", "开发区", "示范区"]
    assert Path(result["visuals"][0]["local_path"]).exists()


@pytest.mark.asyncio
async def test_xuchang_district_map_fails_without_matching_districts(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")
    result = await CreateBusinessChartTool().execute(
        chart_type="xuchang_district_map",
        title="不匹配区县",
        data={"records": [{"district": "郑州市", "value": 50}]},
    )

    assert result["success"] is False
    assert "需要 records" in result["error"]


def test_xuchang_district_map_hidden_outside_xuchang_project(monkeypatch):
    from app.tools.visualization.create_business_chart.tool import (
        available_chart_types,
        business_chart_reference_paths,
        chart_type_enabled,
    )

    assert chart_type_enabled("xuchang_district_map", "xuchang") is True
    assert chart_type_enabled("xuchang_district_map", "default") is False
    assert "xuchang_district_map" not in available_chart_types("default")
    assert "xuchang_district_map" in available_chart_types("xuchang")

    monkeypatch.setattr(settings, "project_id", "default")
    assert "xuchang_district_map" not in business_chart_reference_paths()
    monkeypatch.setattr(settings, "project_id", "xuchang")
    paths = business_chart_reference_paths()
    assert "xuchang_district_map" in paths
    assert resolve_agent_path(paths["xuchang_district_map"]).exists()
