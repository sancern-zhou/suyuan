from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.fetchers.xuchang_station_daily_pollution import (
    CONFIRMED_EVENT_TYPE,
    REQUESTED_EVENT_TYPE,
    XuchangStationDailyPollutionFetcher,
    evaluate_station_daily_pollution,
)

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _rows(pm25: float | None = 80.0, o3_8h: float | None = 170.0):
    return [{
        "station_id": "XC001",
        "name": "测试站",
        "lat": 34.03,
        "lon": 113.85,
        "pm25": pm25,
        "o3_8h": o3_8h,
        "data_time": datetime(2026, 8, 5),
    }]


def test_evaluate_published_station_day_confirms_pm25_and_o3_once():
    result = evaluate_station_daily_pollution(_rows(), target_date=date(2026, 8, 5))

    assert len(result["events"]) == 2
    assert {event["target_pollutant"] for event in result["events"]} == {"PM2.5", "O3"}
    assert all(event["event_type"] == CONFIRMED_EVENT_TYPE for event in result["events"])
    assert all(event["source_granularity"] == "station_day" for event in result["events"])
    assert all("hourly_rows" not in event for event in result["events"])


def test_missing_station_day_values_do_not_trigger():
    result = evaluate_station_daily_pollution(
        _rows(pm25=None, o3_8h=None), target_date=date(2026, 8, 5)
    )

    assert result["events"] == []
    assert result["evaluations"][0]["pm25"]["status"] == "missing_daily_value"
    assert result["evaluations"][0]["o3_8h"]["status"] == "missing_daily_value"


class _AnalysisService:
    def __init__(self):
        self.events = []

    def ingest_daily_exceedance(self, event):
        self.events.append(event)
        job = {
            "job_id": f"{event['event_id']}-analysis",
            "event_id": f"{event['event_id']}-analysis",
            "analysis_id": f"analysis-{event['target_pollutant']}",
            "city": event["city"],
            "station_id": event["station_id"],
            "target_date": event["target_date"],
            "target_pollutant": event["target_pollutant"],
        }
        return {"status": "requested", "analysis": job, "job": job}


class _TaskService:
    def __init__(self):
        self.events = []

    async def publish_event(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_fetcher_publishes_confirmation_and_request(monkeypatch):
    analysis_service = _AnalysisService()
    task_service = _TaskService()
    fetcher = XuchangStationDailyPollutionFetcher(
        analysis_service=analysis_service,
        now_factory=lambda: datetime(2026, 8, 6, 2, tzinfo=TZ_SHANGHAI),
    )
    monkeypatch.setattr(fetcher, "load_rows", lambda target_date: _rows())
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: task_service)

    result = await fetcher.fetch_and_store()

    assert len(result["events"]) == 2
    assert len(analysis_service.events) == 2
    assert [event.event_type for event in task_service.events] == [
        CONFIRMED_EVENT_TYPE,
        REQUESTED_EVENT_TYPE,
        CONFIRMED_EVENT_TYPE,
        REQUESTED_EVENT_TYPE,
    ]
