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


def test_fetcher_defaults_to_minute_queue_tick():
    fetcher = JiangsuSmartEventAlarmSyncFetcher()
    assert fetcher.name == "jiangsu_smart_event_alarm_sync"
    assert fetcher.schedule == "* * * * *"


@pytest.mark.asyncio
async def test_fetcher_runs_automation_tick(monkeypatch):
    calls = []
    sentinel_service = object()
    class FakeAutomation:
        def __init__(self, service):
            assert service is sentinel_service
        async def tick(self):
            calls.append("tick")
            return {"status": "success", "ai_queue": {"dispatched": 1}}
    monkeypatch.setattr("app.services.jiangsu_smart_event_automation.JiangsuSmartEventAutomation", FakeAutomation)
    result = await JiangsuSmartEventAlarmSyncFetcher(service=sentinel_service).fetch_and_store()
    assert calls == ["tick"]
    assert result["ai_queue"]["dispatched"] == 1
