from datetime import datetime
from types import SimpleNamespace

import pytest

from app.tools.query.get_weather_data.tool import GetWeatherDataTool


class _ExecutionContext:
    def save_data(self, *, data, schema):
        assert data
        assert schema == "weather"
        return "weather-data-id"


@pytest.mark.asyncio
async def test_query_observed_includes_sample_record(monkeypatch):
    tool = GetWeatherDataTool()
    observed_record = SimpleNamespace(
        time=datetime(2026, 8, 13, 10),
        temperature_2m=28.5,
        relative_humidity_2m=61.0,
        dew_point_2m=20.2,
        wind_speed_10m=2.4,
        wind_direction_10m=135.0,
        surface_pressure=1004.2,
        precipitation=0.0,
        cloud_cover=35.0,
        visibility=18.0,
    )

    async def get_observed_data(station_id, start_time, end_time):
        assert station_id == "57089"
        return [observed_record]

    monkeypatch.setattr(tool.repo, "get_observed_data", get_observed_data)

    result = await tool._query_observed(
        _ExecutionContext(),
        "57089",
        datetime(2026, 8, 13),
        datetime(2026, 8, 13, 20),
    )

    assert result["success"] is True
    assert result["file_path"] == "weather-data-id"
    first_record = result["data"][0]
    assert result["metadata"]["sample_record"] == {
        "timestamp": first_record.get("timestamp"),
        "station_name": first_record.get("station_name"),
        "lat": first_record.get("lat"),
        "lon": first_record.get("lon"),
        "measurements": first_record.get("measurements", {}),
    }


@pytest.mark.asyncio
async def test_query_observed_without_data_has_no_sample_record(monkeypatch):
    tool = GetWeatherDataTool()

    async def get_observed_data(station_id, start_time, end_time):
        return []

    monkeypatch.setattr(tool.repo, "get_observed_data", get_observed_data)

    result = await tool._query_observed(
        _ExecutionContext(),
        "57089",
        datetime(2026, 8, 13),
        datetime(2026, 8, 13, 20),
    )

    assert result["success"] is False
    assert result["status"] == "success"
    assert result["data"] == []
    assert result["metadata"]["sample_record"] is None
