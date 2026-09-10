from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.fetchers.jiangsu_smart_event_alarm_sync import (
    JiangsuSmartEventAlarmSyncFetcher,
    previous_hour_window,
)

TZ = ZoneInfo("Asia/Shanghai")


def test_previous_hour_window_covers_the_last_completed_hour():
    now = datetime(2026, 9, 9, 5, 10, 32, tzinfo=TZ)
    start, end = previous_hour_window(now, overlap_minutes=5)
    assert start == datetime(2026, 9, 9, 3, 55, 0, tzinfo=TZ)
    assert end == datetime(2026, 9, 9, 5, 0, 0, tzinfo=TZ)


def test_previous_hour_window_defaults_to_local_timezone():
    now = datetime(2026, 9, 9, 5, 10, tzinfo=UTC)
    start, end = previous_hour_window(now)
    assert start.tzinfo is not None
    assert end == datetime(2026, 9, 9, 5, 0, 0, tzinfo=UTC)
    assert (end - start).total_seconds() == 65 * 60


def test_fetcher_defaults_to_hourly_cron():
    fetcher = JiangsuSmartEventAlarmSyncFetcher()
    assert fetcher.name == "jiangsu_smart_event_alarm_sync"
    assert fetcher.schedule == "5 * * * *"


@pytest.mark.asyncio
async def test_fetcher_syncs_previous_hour_into_the_service():
    calls = []

    class FakeService:
        async def sync_alarm_events(self, **kwargs):
            calls.append(kwargs)
            return {"events": [], "stored_event_count": 0, "created_tasks": []}

    fetcher = JiangsuSmartEventAlarmSyncFetcher(service=FakeService())
    result = await fetcher.fetch_and_store()

    assert result["stored_event_count"] == 0
    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs["dispatch_ai"] is False
    assert kwargs["fetch_evidence"] is False
    assert kwargs["actor"] == {"user_id": "system", "username": "smart-event-sync"}
    assert "T" in kwargs["start_time"] and "T" in kwargs["end_time"]
    assert kwargs["end_time"] > kwargs["start_time"]
