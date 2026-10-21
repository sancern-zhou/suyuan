from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.db.repositories.weather_repo import WeatherRepository
from app.tools.query.get_weather_data.tool import GetWeatherDataTool
from app.utils.weather_time import OPEN_METEO_SOURCE, open_meteo_time, weather_query_time


def test_legacy_history_and_forecast_merge_without_false_missing_hours():
    from app.utils.weather_time import normalize_weather_record

    start = datetime.fromisoformat("2026-09-05T00:00:00+08:00")
    history = [{"timestamp": (start + timedelta(hours=i)).isoformat(sep=" "),
                "boundary_layer_height": 0 if i == 0 else 100, "shortwave_radiation": 0,
                "data_source": OPEN_METEO_SOURCE} for i in range(56)]
    forecast = [{"timestamp": (start + timedelta(hours=i)).isoformat(),
                 "measurements": {"boundary_layer_height": 95 if i == 56 else 330, "shortwave_radiation": 190 if i == 56 else 375},
                 "metadata": {"data_source": "Open-Meteo Forecast"}} for i in range(48, 72)]
    normalized = [normalize_weather_record(record) for record in [*forecast, *history]]
    cutoff = start + timedelta(hours=57)
    merged = {datetime.fromisoformat(row["timestamp"]): row for row in normalized
              if start <= datetime.fromisoformat(row["timestamp"]) <= cutoff}
    assert len(merged) == 58
    assert set(merged) == {start + timedelta(hours=i) for i in range(58)}
    assert merged[start]["measurements"]["boundary_layer_height"] == 0
    assert merged[cutoff]["measurements"]["boundary_layer_height"] == 330
    assert merged[cutoff]["measurements"]["shortwave_radiation"] == 375
    assert merged[cutoff]["data_source"] == "Open-Meteo Forecast"
    assert merged[start]["data_source"] == OPEN_METEO_SOURCE


@pytest.mark.parametrize("timestamp", ["2026-09-07 08:00:00+08:00", "2026-09-07T08:00:00+08:00", "2026-09-07T00:00:00Z"])
def test_final_weather_contract_has_same_instant_fields_and_nulls(timestamp):
    from app.utils.weather_time import normalize_weather_record

    row = normalize_weather_record({"timestamp": timestamp, "measurements": {"wind_speed": 2.5, "boundary_layer_height": None, "shortwave_radiation": 0}})
    assert row["timestamp"] == "2026-09-07T08:00:00+08:00"
    assert row["measurements"]["wind_speed_10m"] == 2.5
    assert row["measurements"]["boundary_layer_height"] is None
    assert row["measurements"]["shortwave_radiation"] == 0
    assert row["metadata"]["data_source"] == row["data_source"]
    assert row["metadata"]["units"] == row["units"]


def test_history_preview_contract_matches_actual_context_data():
    from app.agent.context.data_result_policy import shape_data_result_for_context
    from app.utils.weather_time import weather_data_structure

    result = shape_data_result_for_context({"success": True, "data": [{"timestamp": str(i)} for i in range(58)],
        "file_path": "/tmp/weather.json", "data_structure": weather_data_structure(58, 58, False)})
    assert result["data_complete"] is result["data_structure"]["data_complete"] is False
    assert result["returned_records"] == result["data_structure"]["returned_records"] == 24
    assert result["record_count"] == result["data_structure"]["record_count"] == 58


def test_failed_persistence_is_not_retried_by_context_projection():
    from app.agent.context.data_result_policy import persist_large_inline_data

    class Context:
        def save_data(self, *args, **kwargs):
            pytest.fail("Persistence failure must remain an explicit warning with inline data")

    result = {"success": True, "data": [{}] * 58, "warnings": [{"code": "DATA_SAVE_FAILED"}]}
    assert persist_large_inline_data(result, context=Context(), tool_name="get_weather_forecast") is result


def test_weather_schemas_share_the_result_and_time_contract():
    from app.tools.query.get_weather_forecast.tool import GetWeatherForecastTool

    for tool in (GetWeatherDataTool(), GetWeatherForecastTool()):
        description = tool.get_function_schema()["description"]
        for expected in ("weather_hourly_v1", "datetime.fromisoformat", "data_complete=false", "error_code", "measurements"):
            assert expected in description


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
    assert output["timestamp"] == "2026-09-05T08:00:00+08:00"
    assert output["measurements"]["boundary_layer_height"] == 220
    assert output["measurements"]["shortwave_radiation"] == 0
    assert output["measurements"]["wind_speed_10m"] == 2.5
    assert output["wind_gusts_10m"] == 5
    assert output["boundary_layer_height"] == 220
    assert output["units"]["wind_speed_10m"] == "m/s"
    assert output["data_source"] == OPEN_METEO_SOURCE
    assert context.saved == result["data"]
    assert result["metadata"]["source"] == OPEN_METEO_SOURCE
    assert result["metadata"]["actual_time_range"]["start"] == output["timestamp"]
    assert result["data_structure"]["record_contract"] == "weather_hourly_v1"


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
