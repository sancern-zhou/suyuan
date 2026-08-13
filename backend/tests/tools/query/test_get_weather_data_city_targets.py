from datetime import datetime

import pytest

from app.config.weather_targets import (
    ERA5_MAIN_FETCHER,
    get_observed_station_targets,
    iter_era5_city_targets,
    resolve_weather_city_target,
)
from app.tools.query.get_weather_data.tool import GetWeatherDataTool


def test_shared_catalog_resolves_city_alias_and_drives_fetch_targets():
    nanjing = resolve_weather_city_target("南京")

    assert nanjing is not None
    assert nanjing.city == "南京市"
    assert nanjing.era5_point == {"lat": 32.0603, "lon": 118.7969}

    main_fetch_cities = {
        target.city for target in iter_era5_city_targets(ERA5_MAIN_FETCHER)
    }
    assert "南京市" in main_fetch_cities
    assert "运城市" in main_fetch_cities
    assert "济宁市" not in main_fetch_cities

    nmc_stations = get_observed_station_targets(provider="NMC")
    assert nmc_stations["yuncheng"].station_id == "AupnI"
    assert nmc_stations["xuchang"].station_id == "ZzMTA"


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
        cities=["南京", "不存在市"],
        start_time="2026-08-01T00:00:00",
        end_time="2026-08-01T23:59:59",
    )

    assert calls == [(32.0603, 118.7969, "南京市")]
    assert result["status"] == "partial"
    assert result["success"] is True
    assert result["data"][0]["city"] == "南京市"
    assert result["metadata"]["resolved_cities"] == ["南京市"]
    assert result["metadata"]["unresolved_cities"] == ["不存在市"]
    assert result["metadata"]["targets"][0]["grid_lat"] == 32.0
    assert result["metadata"]["targets"][0]["grid_lon"] == 118.75


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
        city="运城",
        start_time="2026-08-01T00:00:00",
        end_time="2026-08-01T23:59:59",
    )

    assert result["status"] == "success"
    assert result["data"][0]["city"] == "运城市"
    assert result["data"][0]["station_id"] == "AupnI"
    assert result["metadata"]["targets"][0]["provider"] == "NMC"
