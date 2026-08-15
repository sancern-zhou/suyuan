from datetime import datetime
from types import SimpleNamespace

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
    assert properties["district"]["type"] == "string"
    assert properties["districts"]["type"] == "array"


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


class FakeWeatherContext:
    def __init__(self):
        self.saved = []

    def save_data(self, *, data, schema):
        self.saved.append((data, schema))
        return "weather-data-id"


@pytest.mark.asyncio
async def test_jiangsu_observed_city_name_queries_internal_station_directory(monkeypatch):
    from config.settings import settings

    tool = GetWeatherDataTool()
    context = FakeWeatherContext()
    calls = []
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")

    async def fake_targets(*, city_names, district_names):
        calls.append(("targets", city_names, district_names))
        return [
            {
                "station_id": "NANJING",
                "city_code": "320100",
                "city_name": "南京市",
                "district_code": None,
                "district_name": None,
                "location_level": "city",
                "nmc_location_name": "南京",
            },
            {
                "station_id": "JIANGNING",
                "city_code": "320100",
                "city_name": "南京市",
                "district_code": "320115",
                "district_name": "江宁区",
                "location_level": "district",
                "nmc_location_name": "江宁",
            },
        ]

    async def fake_data(*, city_names, district_names, start_time, end_time):
        calls.append(("data", city_names, district_names))
        return [
            SimpleNamespace(
                time=datetime(2026, 8, 13, hour),
                station_id="JIANGNING",
                province_name="江苏省",
                city_code="320100",
                city_name="南京市",
                district_code="320115",
                district_name="江宁区",
                location_level="district",
                nmc_location_name="江宁",
                temperature_2m=30.0,
                relative_humidity_2m=60.0,
                wind_speed_10m=2.0,
                wind_direction_10m=180.0,
                surface_pressure=1000.0,
                precipitation=0.0,
                data_source="NMC",
                data_quality="good",
            )
            for hour in range(24)
        ] + [
            SimpleNamespace(
                time=datetime(2026, 8, 14, hour),
                station_id="NANJING",
                province_name="江苏省",
                city_code="320100",
                city_name="南京市",
                district_code=None,
                district_name=None,
                location_level="city",
                nmc_location_name="南京",
                temperature_2m=29.0,
                relative_humidity_2m=65.0,
                wind_speed_10m=1.8,
                wind_direction_10m=170.0,
                surface_pressure=1001.0,
                precipitation=0.0,
                data_source="NMC",
                data_quality="good",
            )
            for hour in range(6)
        ]

    monkeypatch.setattr(tool.jiangsu_nmc_repo, "get_area_targets", fake_targets)
    monkeypatch.setattr(tool.jiangsu_nmc_repo, "get_area_observed_data", fake_data)

    result = await tool.execute(
        context=context,
        data_type="observed",
        city="南京",
        start_time="2026-08-13T00:00:00",
        end_time="2026-08-14T23:59:59",
    )

    assert calls == [
        ("targets", ["南京市"], []),
        ("data", ["南京市"], []),
    ]
    assert result["status"] == "success"
    assert result["record_count"] == 30
    assert result["returned_records"] == 24
    assert result["data_complete"] is False
    assert result["file_path"] == "weather-data-id"
    assert len(context.saved[0][0]) == 30
    assert result["metadata"]["station_count"] == 2
    assert "targets" not in result["metadata"]


@pytest.mark.asyncio
async def test_jiangsu_observed_district_name_queries_only_the_district(monkeypatch):
    tool = GetWeatherDataTool()

    async def fake_targets(*, city_names, district_names):
        assert city_names == []
        assert district_names == ["江宁"]
        return [{
            "station_id": "JIANGNING",
            "city_name": "南京市",
            "district_name": "江宁区",
            "location_level": "district",
        }]

    async def fake_data(**kwargs):
        return []

    monkeypatch.setattr(tool.jiangsu_nmc_repo, "get_area_targets", fake_targets)
    monkeypatch.setattr(tool.jiangsu_nmc_repo, "get_area_observed_data", fake_data)

    result = await tool.execute(
        context=None,
        data_type="observed",
        district="江宁",
        start_time="2026-08-13T00:00:00",
        end_time="2026-08-13T23:59:59",
    )

    assert result["status"] == "empty"
    assert result["metadata"]["resolved_districts"] == ["江宁区"]
    assert result["metadata"]["station_count"] == 1


@pytest.mark.asyncio
async def test_era5_rejects_district_name_without_inventing_a_grid_point():
    result = await GetWeatherDataTool().execute(
        context=None,
        data_type="era5",
        district="江宁区",
        start_time="2026-08-13T00:00:00",
        end_time="2026-08-13T23:59:59",
    )

    assert result["status"] == "failed"
    assert "仅支持 observed" in result["error"]
