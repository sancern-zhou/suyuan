from datetime import datetime

import pytest

from app.config.weather_targets import (
    ERA5_CITY_HISTORY_FETCHER,
    get_observed_station_targets,
    iter_era5_city_targets,
    resolve_weather_city_target,
)
from app.tools.query.get_weather_data.tool import GetWeatherDataTool


def test_shared_catalog_resolves_city_alias_and_drives_fetch_targets():
    guangzhou = resolve_weather_city_target("广州")

    assert guangzhou is not None
    assert guangzhou.city == "广州市"
    assert guangzhou.province == "广东省"
    assert guangzhou.era5_point == {"lat": 23.13, "lon": 113.26}

    history_cities = {
        target.city for target in iter_era5_city_targets(ERA5_CITY_HISTORY_FETCHER)
    }
    assert "广州市" in history_cities
    assert len(history_cities) == 21
    assert resolve_weather_city_target("南京市") is None

    nmc_stations = get_observed_station_targets(provider="NMC")
    assert nmc_stations["guangzhou"].station_id == "DwzZf"


def test_weather_tool_schema_accepts_single_and_multiple_cities():
    properties = GetWeatherDataTool().function_schema["parameters"]["properties"]

    assert properties["city"]["type"] == "string"
    assert properties["cities"]["type"] == "array"


@pytest.mark.asyncio
async def test_era5_city_query_uses_shared_catalog_and_reports_partial_result(monkeypatch):
    tool = GetWeatherDataTool()
    calls = []

    async def fake_query_era5(context, lat, lon, start_time, end_time, city=None):
        calls.append((lat, lon, city))
        return {
            "data": [{"timestamp": start_time.isoformat(), "temperature": 20.0}],
            "metadata": {
                "lat": round(lat * 4) / 4,
                "lon": round(lon * 4) / 4,
            },
        }

    monkeypatch.setattr(tool, "_query_era5", fake_query_era5)

    result = await tool.execute(
        context=None,
        data_type="era5",
        cities=["广州", "不存在市"],
        start_time="2026-08-01T00:00:00",
        end_time="2026-08-01T23:59:59",
    )

    assert calls == [(23.13, 113.26, "广州市")]
    assert result["status"] == "partial"
    assert result["success"] is True
    assert result["data"][0]["city"] == "广州市"
    assert result["metadata"]["resolved_cities"] == ["广州市"]
    assert result["metadata"]["unresolved_cities"] == ["不存在市"]
    assert result["metadata"]["targets"][0]["grid_lat"] == 23.25
    assert result["metadata"]["targets"][0]["grid_lon"] == 113.25


@pytest.mark.asyncio
async def test_observed_city_query_uses_catalog_station_ids(monkeypatch):
    tool = GetWeatherDataTool()

    async def fake_get_active_stations_by_cities(cities):
        return {city: [] for city in cities}

    async def fake_query_observed(
        context, station_id, start_time, end_time, city=None
    ):
        return {
            "data": [
                {
                    "timestamp": datetime(2026, 8, 1).isoformat(),
                    "station_id": station_id,
                }
            ]
        }

    monkeypatch.setattr(
        tool.repo,
        "get_active_stations_by_cities",
        fake_get_active_stations_by_cities,
    )
    monkeypatch.setattr(tool, "_query_observed", fake_query_observed)

    result = await tool.execute(
        context=None,
        data_type="observed",
        city="广州",
        start_time="2026-08-01T00:00:00",
        end_time="2026-08-01T23:59:59",
    )

    assert result["status"] == "success"
    assert result["data"][0]["city"] == "广州市"
    assert result["data"][0]["station_id"] == "DwzZf"
    assert result["metadata"]["targets"][0]["provider"] == "NMC"
