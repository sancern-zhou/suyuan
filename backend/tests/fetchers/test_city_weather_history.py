import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.project_config.models import WeatherHistoryConfig
from app.services import weather_history
from app.services.weather_history import (
    HistoryJobs, WeatherHistoryService, coverage, grid_point,
)
from app.utils.weather_time import BEIJING, OPEN_METEO_SOURCE

START = datetime(2026, 8, 1, tzinfo=timezone.utc)


def configuration():
    return WeatherHistoryConfig(points=[{"city": "Example", "province": "Example", "lat": 34.036, "lon": 113.852}])


def row(hour, value=100, source=OPEN_METEO_SOURCE):
    return SimpleNamespace(time=START + timedelta(hours=hour), boundary_layer_height=value, data_source=source)


def test_coverage_detects_null_nonfinite_legacy_and_missing_hours():
    result = coverage([row(0, 0), row(1, None), row(2, float("nan")), row(3, -1), row(4, source="ERA5")], START, START + timedelta(hours=5))
    assert result["expected_hours"] == 6
    assert result["valid_hours"] == 1
    assert result["missing_hours"] == 5


def test_coverage_counts_beijing_hours_without_double_shift():
    result = coverage([row(0)], "2026-08-01T08:00:00+08:00", "2026-08-01T08:59:59+08:00")
    assert result["expected_hours"] == result["valid_hours"] == 1


@pytest.mark.asyncio
async def test_repair_fetches_only_incomplete_days(tmp_path):
    cached = [row(i) for i in range(72) if i != 35]
    repo = SimpleNamespace(get_weather_data=AsyncMock(side_effect=[cached, [row(i) for i in range(72)]]), save_era5_data=AsyncMock())
    client = SimpleNamespace(fetch_era5_data=AsyncMock(return_value={"hourly": {}}))
    service = WeatherHistoryService(configuration(), project_id="test", root=tmp_path, repo=repo, client=client)
    result = await service.repair(34, 113.75, START, START + timedelta(hours=71))
    client.fetch_era5_data.assert_awaited_once_with(34, 113.75, "2026-08-02", "2026-08-02")
    assert repo.save_era5_data.call_args.kwargs == {"preserve_valid": True}
    assert result["missing_hours"] == 0


@pytest.mark.asyncio
async def test_durable_jobs_resume_and_deduplicate(tmp_path):
    service = WeatherHistoryService(configuration(), project_id="test", root=tmp_path)
    service.repair = AsyncMock(return_value={"missing_hours": 0})
    job = service.jobs.submit(service.points(), START.date(), (START + timedelta(days=59)).date())
    await service.run_pending(max_chunks=1)
    assert service.jobs.get(job["id"])["cursor"] == 1
    resumed = WeatherHistoryService(configuration(), project_id="test", root=tmp_path)
    resumed.repair = AsyncMock(return_value={"missing_hours": 0})
    await resumed.run_pending()
    assert resumed.jobs.get(job["id"])["state"] == "complete"
    assert resumed.repair.await_count == 1
    assert resumed.jobs.submit(service.points(), START.date(), (START + timedelta(days=59)).date())["id"] == job["id"]


@pytest.mark.asyncio
async def test_failures_are_not_reported_as_complete(tmp_path):
    service = WeatherHistoryService(configuration(), project_id="test", root=tmp_path)
    service.repair = AsyncMock(side_effect=RuntimeError("upstream unavailable"))
    job = service.jobs.submit(service.points(), START.date(), START.date())
    await service.run_pending()
    result = service.jobs.get(job["id"])
    assert result["state"] == "partial"
    assert result["failed"] == 1


def test_schedule_limits_points_and_bootstraps_once(tmp_path):
    service = WeatherHistoryService(configuration(), project_id="test", root=tmp_path)
    service.schedule_collection()
    service.schedule_collection()
    jobs = service.jobs.pending()
    assert len(jobs) == 2
    assert sorted(job["total"] for job in jobs) == [1, 3]
    assert grid_point(34.036, 113.852) == (34, 113.75)


def test_invalid_config_and_oversized_job_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        WeatherHistoryConfig(points=[{"city": "A", "province": "B", "lat": 100, "lon": 0}])
    with pytest.raises(ValueError):
        HistoryJobs(tmp_path).submit([], START.date(), (START + timedelta(days=366)).date())


@pytest.mark.asyncio
async def test_jobs_use_beijing_day_windows(tmp_path, monkeypatch):
    fixed = datetime(2026, 9, 29, 2, 5, tzinfo=BEIJING)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(weather_history, "datetime", FixedDatetime)
    service = WeatherHistoryService(configuration(), project_id="test", root=tmp_path)
    service.repair = AsyncMock(return_value={"missing_hours": 0})
    service.submit(
        service.points(),
        datetime(2026, 9, 22, tzinfo=BEIJING),
        datetime(2026, 9, 29, 10, tzinfo=BEIJING),
    )
    payload = json.loads(service.jobs.pending()[0]["payload"])
    # 北京 9/29 凌晨请求“昨日”：clamp 到北京 9/28 整日，而不是 UTC 9/27（丢昨日白天）。
    assert payload["end"] == "2026-09-28"
    await service.run_pending()
    service.repair.assert_awaited_once_with(
        34.0, 113.75,
        datetime(2026, 9, 22, 0, 0, tzinfo=BEIJING),
        datetime(2026, 9, 28, 23, 0, tzinfo=BEIJING),
    )
