from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.project_config.models import WeatherHistoryConfig
from app.services.weather_history import WeatherHistoryService
from app.tools.query.get_weather_data.tool import GetWeatherDataTool
from app.utils.weather_time import OPEN_METEO_SOURCE


@pytest.fixture
def tool(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.weather_history.configured_history_service", lambda: None)
    tool = GetWeatherDataTool()
    config = WeatherHistoryConfig(points=[{"city": "示例市", "province": "示例省", "lat": 34, "lon": 113.75}])
    tool.history = WeatherHistoryService(config, project_id="test", root=tmp_path)
    tool.repo = SimpleNamespace(get_weather_data=AsyncMock(return_value=[]))
    tool.history.repair = AsyncMock(return_value={"missing_hours": 0})
    return tool


@pytest.mark.asyncio
async def test_small_query_repairs_online_and_uses_project_point(tool):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    report = await tool._prepare_history(["示例市"], None, None, start, start + timedelta(hours=23))
    assert not report["jobs"]
    tool.history.repair.assert_awaited_once_with(34, 113.75, start, start + timedelta(hours=23))
    assert tool._resolve_city("示例").era5_point == {"lat": 34, "lon": 113.75}


@pytest.mark.asyncio
async def test_large_query_queues_and_repeat_reports_progress(tool):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    report = await tool._prepare_history(["示例市"], None, None, start, start + timedelta(days=30))
    assert report["jobs"][0]["state"] == "pending"
    assert report["warnings"][0]["code"] == "HISTORY_BACKFILL_PENDING"
    tool.history.repair.assert_not_awaited()


@pytest.mark.asyncio
async def test_online_error_queues_without_claiming_success(tool):
    tool.history.repair.side_effect = TimeoutError()
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    report = await tool._prepare_history(["示例市"], None, None, start, start)
    assert report["jobs"]
    assert report["warnings"][0]["code"] == "ONLINE_HISTORY_INCOMPLETE"


@pytest.mark.asyncio
async def test_today_never_calls_archive(tool):
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    report = await tool._prepare_history(["示例市"], None, None, start, start + timedelta(hours=10))
    assert report == {"jobs": [], "warnings": []}
    tool.history.repair.assert_not_awaited()


def test_comparison_requires_common_hours_and_sources():
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    result = {"success": True, "summary": "", "data": [
        {"city": city, "timestamp": (start + timedelta(hours=hour)).isoformat(), "boundary_layer_height": value, "data_source": source}
        for city, hour, value, source in [("A", 0, 0, OPEN_METEO_SOURCE), ("B", 0, 50, OPEN_METEO_SOURCE),
                                          ("A", 1, 100, OPEN_METEO_SOURCE), ("B", 1, 50, "other")]
    ]}
    result = GetWeatherDataTool._finish_history(result, {"jobs": [], "warnings": []}, ["A", "B"], start, start + timedelta(hours=2))
    assert result["status"] == "partial"
    assert result["metadata"]["comparison_coverage"]["common_valid_hours"] == 1
    assert result["metadata"]["comparison_coverage"]["cities"]["A"]["missing_hours"] == 1
