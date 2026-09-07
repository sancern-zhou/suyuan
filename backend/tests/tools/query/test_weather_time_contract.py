from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.db.repositories.weather_repo import WeatherRepository
from app.tools.query.get_weather_data.tool import GetWeatherDataTool
from app.utils.weather_time import OPEN_METEO_SOURCE, open_meteo_time, weather_query_time


@pytest.mark.parametrize("value", ["2026-09-05T00:00:00", "2026-09-05T00:00:00+08:00", "2026-09-04T16:00:00Z"])
def test_query_times_resolve_to_the_same_instant(value):
    assert weather_query_time(value) == datetime(2026, 9, 4, 16, tzinfo=timezone.utc)


@pytest.mark.parametrize("value,offset", [("2026-09-05T00:00", 0), ("2026-09-05T08:00", 28800), ("2026-09-05T08:00+08:00", 0)])
def test_provider_times_respect_response_offset_and_explicit_suffix(value, offset):
    assert open_meteo_time(value, {"utc_offset_seconds": offset}) == datetime(2026, 9, 5, tzinfo=timezone.utc)


def test_provider_rejects_unqualified_time_without_offset():
    with pytest.raises(ValueError, match="timezone"):
        open_meteo_time("2026-09-05T00:00", {})


def test_ingestion_preserves_utc_and_normalizes_storage_units():
    response = {
        "utc_offset_seconds": 0,
        "hourly": {"time": ["2026-09-05T00:00"], "boundary_layer_height": [220], "wind_speed_10m": [2.5]},
        "hourly_units": {"wind_speed_10m": "m/s"},
    }
    row = WeatherRepository.build_era5_records(34, 113.75, response)[0]
    assert row["time"] == datetime(2026, 9, 5, tzinfo=timezone.utc)
    assert row["wind_speed_10m"] == 9
    assert row["data_source"] == OPEN_METEO_SOURCE
    response["hourly_units"] = {}
    with pytest.raises(ValueError, match="unit"):
        WeatherRepository.build_era5_records(34, 113.75, response)


@pytest.mark.asyncio
@pytest.mark.parametrize("city", [None, "许昌市"])
async def test_tool_emits_beijing_time_si_wind_and_source_in_saved_data(monkeypatch, city):
    tool = GetWeatherDataTool()
    fields = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "surface_pressure", "precipitation", "cloud_cover", "shortwave_radiation", "visibility", "boundary_layer_height"]
    row = SimpleNamespace(**dict.fromkeys(fields, 0))
    row.time = datetime(2026, 9, 5, tzinfo=timezone.utc)
    row.wind_speed_10m = 9
    row.wind_gusts_10m = 18
    row.boundary_layer_height = 220
    row.data_source = OPEN_METEO_SOURCE

    async def query(lat, lon, start, end):
        assert (lat, lon) == (34, 113.75)
        assert start == datetime(2026, 9, 4, 16, tzinfo=timezone.utc)
        assert end == datetime(2026, 9, 7, 1, tzinfo=timezone.utc)
        return [row]

    class Context:
        saved = None

        def save_data(self, data, schema):
            self.saved = data
            return "/tmp/weather-contract.json"

    monkeypatch.setattr(tool.repo, "get_weather_data", query)
    context = Context()
    result = await tool.execute(context, "era5", "2026-09-05T00:00:00", "2026-09-07T09:00:00", lat=34, lon=113.75, city=city)
    assert result["success"]
    output = result["data"][0]
    assert output["timestamp"].replace(" ", "T") == "2026-09-05T08:00:00+08:00"
    assert output["measurements"]["wind_speed_10m"] == 2.5
    assert output["wind_gusts_10m"] == 5
    assert output["boundary_layer_height"] == 220
    assert output["units"]["wind_speed_10m"] == "m/s"
    assert output["data_source"] == OPEN_METEO_SOURCE
    assert context.saved == result["data"]
    assert result["metadata"]["source"] == OPEN_METEO_SOURCE
    assert result["metadata"]["actual_time_range"]["start"] == output["timestamp"]


@pytest.mark.asyncio
async def test_inverted_query_range_fails_before_database_access(monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail("Invalid interval reached database")

    tool = GetWeatherDataTool()
    monkeypatch.setattr(tool.repo, "get_weather_data", unexpected)
    result = await tool.execute(None, "era5", "2026-09-06T00:00+08:00", "2026-09-05T00:00+08:00", lat=34, lon=113.75)
    assert result["success"] is False


def test_repair_requires_complete_non_null_unique_hours():
    from scripts.repair_openmeteo_history import validate_records

    start = datetime(2026, 9, 5, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    records = [{"time": start + timedelta(hours=i), "boundary_layer_height": 220} for i in range(24)]
    validate_records(records, start, end)
    for invalid in [records[:-1], records + [records[0]], [{**record, "boundary_layer_height": None} for record in records]]:
        with pytest.raises(ValueError):
            validate_records(invalid, start, end)


@pytest.mark.asyncio
async def test_provider_requests_are_explicit_about_models_units_and_calendar(monkeypatch):
    from app.external_apis import openmeteo_client

    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, params):
            calls.append((url, params))
            return SimpleNamespace(status_code=200, json=lambda: {"utc_offset_seconds": 0})

    monkeypatch.setattr(openmeteo_client.httpx, "AsyncClient", Client)
    client = openmeteo_client.OpenMeteoClient()
    result = await client.fetch_era5_data(34, 113.75, "2026-09-05", "2026-09-06")
    assert result["data_source"] == OPEN_METEO_SOURCE
    assert calls[-1][1]["timezone"] == "UTC"
    assert calls[-1][1]["models"] == "best_match"
    assert calls[-1][1]["wind_speed_unit"] == "kmh"
    await client.fetch_forecast(34, 113.75, forecast_days=1, timezone="Asia/Shanghai")
    assert calls[-1][1]["timezone"] == "Asia/Shanghai"
    assert {"boundary_layer_height", "shortwave_radiation"} <= set(calls[-1][1]["hourly"].split(","))
    await client.fetch_forecast(34, 113.75)
    assert calls[-1][1]["timezone"] == "UTC"
