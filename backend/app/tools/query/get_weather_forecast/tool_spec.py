import asyncio
from datetime import datetime, timedelta

from app.agent.context.data_result_policy import shape_data_result_for_context
from app.tools.query.get_weather_forecast.tool import (
    INLINE_RECORD_LIMIT,
    GetWeatherForecastTool,
)


class _FakeContext:
    def __init__(self):
        self.saved = []

    def save_data(self, *, data, schema, metadata):
        self.saved.append({"data": data, "schema": schema, "metadata": metadata})
        return "backend/backend_data_registry/sessions/test/data/weather.json"


def _forecast(point_count: int):
    start = datetime(2026, 8, 11)
    times = [(start + timedelta(hours=index)).isoformat() for index in range(point_count)]

    def values(value):
        return [value for _ in times]

    return {
        "hourly": {
            "time": times,
            "temperature_2m": values(25.0),
            "relative_humidity_2m": values(70),
            "dew_point_2m": values(19.0),
            "wind_speed_10m": values(8.0),
            "wind_direction_10m": values(30),
            "wind_gusts_10m": values(12.0),
            "surface_pressure": values(995.0),
            "precipitation": values(0.0),
            "precipitation_probability": values(10),
            "weather_code": values(1),
            "cloud_cover": values(20),
            "visibility": values(10000.0),
            "boundary_layer_height": values(500.0),
        },
        "daily": {
            "temperature_2m_max": [30.0],
            "temperature_2m_min": [22.0],
        },
    }


def _run_tool(point_count: int):
    tool = GetWeatherForecastTool()
    context = _FakeContext()

    async def fetch_forecast(**_kwargs):
        return _forecast(point_count)

    tool.client.fetch_forecast = fetch_forecast
    result = asyncio.run(
        tool.execute(
            context,
            lat=34.04,
            lon=113.85,
            location_name="测试城市",
            forecast_days=1,
        )
    )
    return result, context


def test_weather_forecast_inlines_up_to_24_records_without_persisting():
    result, context = _run_tool(INLINE_RECORD_LIMIT)

    assert len(result["data"]) == INLINE_RECORD_LIMIT
    assert result["data_complete"] is True
    assert result["record_count"] == INLINE_RECORD_LIMIT
    assert result["returned_records"] == INLINE_RECORD_LIMIT
    assert result["sample_strategy"] == "complete"
    assert result["data_structure"]["root_type"] == "array"
    assert result["data_structure"]["record_schema"]["measurements"]["wind_speed"] == "number|null"
    assert "file_path" not in result
    assert context.saved == []


def test_weather_forecast_externalizes_more_than_24_records_and_returns_shape():
    result, context = _run_tool(INLINE_RECORD_LIMIT + 1)

    assert len(result["data"]) == INLINE_RECORD_LIMIT
    assert result["data_complete"] is False
    assert result["record_count"] == INLINE_RECORD_LIMIT + 1
    assert result["returned_records"] == INLINE_RECORD_LIMIT
    assert result["sample_strategy"] == "head_tail"
    assert result["file_path"].endswith("weather.json")
    assert result["data_structure"]["file_root_type"] == "array"
    assert result["metadata"]["context_data"]["externalized"] is True

    assert len(context.saved) == 1
    assert len(context.saved[0]["data"]) == INLINE_RECORD_LIMIT + 1
    assert context.saved[0]["schema"] == "weather"
    assert context.saved[0]["metadata"]["field_mapping_applied"] is True
    assert context.saved[0]["metadata"]["root_type"] == "array"

    context_result = shape_data_result_for_context(result)
    assert len(context_result["data"]) == INLINE_RECORD_LIMIT
    assert context_result["data_structure"] == result["data_structure"]
    assert context_result["data_complete"] is False
