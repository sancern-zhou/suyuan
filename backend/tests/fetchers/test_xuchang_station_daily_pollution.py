from datetime import date, datetime
from zoneinfo import ZoneInfo
import base64
import json

import pytest

from app.fetchers.xuchang_station_daily_pollution import (
    CONFIRMED_EVENT_TYPE,
    DAILY_REVIEW_EVENT_TYPE,
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


def test_daily_values_alone_do_not_trigger_events():
    result = evaluate_station_daily_pollution(_rows(), target_date=date(2026, 8, 5))

    assert result["events"] == []
    assert result["evaluations"][0]["pm25"]["daily_value"] == 80.0
    assert result["evaluations"][0]["pm25"]["exceeded"] is True


def test_missing_station_day_values_do_not_trigger():
    result = evaluate_station_daily_pollution(
        _rows(pm25=None, o3_8h=None), target_date=date(2026, 8, 5)
    )

    assert result["events"] == []
    assert result["evaluations"][0]["pm25"]["status"] == "missing_daily_value"
    assert result["evaluations"][0]["o3_8h"]["status"] == "missing_daily_value"


def test_hourly_change_classification_is_deterministic():
    day = date(2026, 8, 5)
    rows = [
        {"station_id": "XC001", "name": "目标站", "lat": 34.0, "lon": 113.8,
         "pm25": 45, "o3": 90, "data_time": datetime(2026, 8, 5, 10), "data_source": "hour"},
        {"station_id": "XC001", "name": "目标站", "lat": 34.0, "lon": 113.8,
         "pm25": 30, "o3": 70, "data_time": datetime(2026, 8, 5, 11), "data_source": "hour"},
        {"station_id": "XC002", "name": "参照站", "lat": 34.1, "lon": 113.9,
         "pm25": 20, "o3": 70, "data_time": datetime(2026, 8, 5, 11), "data_source": "hour"},
        {"station_id": "XC003", "name": "参照站2", "lat": 34.2, "lon": 114.0,
         "pm25": 20, "o3": 70, "data_time": datetime(2026, 8, 5, 11), "data_source": "hour"},
        {"station_id": "XC001", "name": "目标站", "lat": 34.0, "lon": 113.8,
         "pm25": 50, "o3": 80, "data_time": datetime(2026, 8, 5, 12), "data_source": "hour"},
        {"station_id": "XC002", "name": "参照站", "lat": 34.1, "lon": 113.9,
         "pm25": 20, "o3": 70, "data_time": datetime(2026, 8, 5, 12), "data_source": "hour"},
        {"station_id": "XC003", "name": "参照站2", "lat": 34.2, "lon": 114.0,
         "pm25": 20, "o3": 70, "data_time": datetime(2026, 8, 5, 12), "data_source": "hour"},
        {"station_id": "XC001", "name": "目标站", "lat": 34.0, "lon": 113.8,
         "pm25": 80, "o3_8h": 170, "data_time": datetime(2026, 8, 5), "data_source": "day"},
    ]
    result = evaluate_station_daily_pollution(rows, target_date=day)
    event = next(item for item in result["events"] if item["target_pollutant"] == "PM2.5")
    classification = event["pollutant_change_classifications"][0]
    assert classification["classification"] == "multi_pollutant_sync"
    assert "O3" in classification["synchronized_pollutants"]


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


def _hourly_rows_with_one_pm25_alert():
    return [
        {"station_id": "XC001", "name": "目标站", "lat": 34.0, "lon": 113.8,
         "pm25": 45, "o3": 90, "data_time": datetime(2026, 8, 5, 10), "data_source": "hour"},
        {"station_id": "XC001", "name": "目标站", "lat": 34.0, "lon": 113.8,
         "pm25": 80, "o3": 90, "data_time": datetime(2026, 8, 5, 11), "data_source": "hour"},
        {"station_id": "XC002", "name": "参照站", "lat": 34.1, "lon": 113.9,
         "pm25": 20, "o3": 70, "data_time": datetime(2026, 8, 5, 11), "data_source": "hour"},
        {"station_id": "XC003", "name": "参照站2", "lat": 34.2, "lon": 114.0,
         "pm25": 20, "o3": 70, "data_time": datetime(2026, 8, 5, 11), "data_source": "hour"},
    ]


@pytest.mark.asyncio
async def test_fetcher_publishes_review_summary_confirmation_and_request(monkeypatch, tmp_path):
    analysis_service = _AnalysisService()
    task_service = _TaskService()
    fetcher = XuchangStationDailyPollutionFetcher(
        analysis_service=analysis_service,
        now_factory=lambda: datetime(2026, 8, 6, 2, tzinfo=TZ_SHANGHAI),
    )
    monkeypatch.setattr(fetcher, "load_rows", lambda target_date: _hourly_rows_with_one_pm25_alert())
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.get_data_registry", lambda: tmp_path
    )
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: task_service)

    result = await fetcher.fetch_and_store()

    assert len(result["events"]) == 1
    assert len(analysis_service.events) == 1
    assert [event.event_type for event in task_service.events] == [
        DAILY_REVIEW_EVENT_TYPE,
        CONFIRMED_EVENT_TYPE,
        REQUESTED_EVENT_TYPE,
    ]

    review_event = task_service.events[0]
    assert review_event.payload["event_count"] == 1
    assert "xuchang_station_daily_reviews" in review_event.payload["evidence_package_path"]
    evidence_path = tmp_path / "xuchang_station_daily_reviews" / "20260805.json"
    assert evidence_path.exists()
    assert "station_hourly" in evidence_path.read_text(encoding="utf-8")
    # 事件 payload 只携带摘要与路径，不内嵌全量事件数据。
    assert "events" not in review_event.payload
    assert len(review_event.model_dump_json()) < 2000


class _MetItem:
    def __init__(self, hour: int):
        self.time = datetime(2026, 8, 5, hour, tzinfo=TZ_SHANGHAI)
        self.temperature_2m = 25.0
        self.relative_humidity_2m = 70.0
        self.wind_speed_10m = 1.5
        self.wind_direction_10m = 180.0
        self.precipitation = 0.0


class _WeatherRepository:
    async def get_observed_data(self, station_id, start, end):
        return [_MetItem(10), _MetItem(11)]


@pytest.mark.asyncio
async def test_fetcher_without_alerts_renders_city_mean_meteorology_chart(monkeypatch, tmp_path):
    task_service = _TaskService()
    fetcher = XuchangStationDailyPollutionFetcher(
        analysis_service=_AnalysisService(),
        now_factory=lambda: datetime(2026, 8, 6, 2, tzinfo=TZ_SHANGHAI),
    )
    rows = [
        {"station_id": "XC001", "name": "站点一", "lat": 34.0, "lon": 113.8,
         "pm25": 20, "o3": 60, "data_time": datetime(2026, 8, 5, 10), "data_source": "hour"},
        {"station_id": "XC002", "name": "站点二", "lat": 34.1, "lon": 113.9,
         "pm25": 22, "o3": 60, "data_time": datetime(2026, 8, 5, 10), "data_source": "hour"},
        {"station_id": "XC001", "name": "站点一", "lat": 34.0, "lon": 113.8,
         "pm25": 24, "o3": 55, "data_time": datetime(2026, 8, 5, 11), "data_source": "hour"},
        {"station_id": "XC002", "name": "站点二", "lat": 34.1, "lon": 113.9,
         "pm25": 26, "o3": 55, "data_time": datetime(2026, 8, 5, 11), "data_source": "hour"},
        {"station_id": "XC001", "name": "站点一", "lat": 34.0, "lon": 113.8,
         "pm25": 22, "o3_8h": 60, "data_time": datetime(2026, 8, 5), "data_source": "day"},
        {"station_id": "XC002", "name": "站点二", "lat": 34.1, "lon": 113.9,
         "pm25": 24, "o3_8h": 60, "data_time": datetime(2026, 8, 5), "data_source": "day"},
    ]
    monkeypatch.setattr(fetcher, "load_rows", lambda target_date: rows)
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.get_data_registry", lambda: tmp_path
    )
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.get_images_dir", lambda: images_dir
    )
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.WeatherRepository", _WeatherRepository
    )
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: task_service)

    render_calls = []

    def fake_render_wind_timeseries(*, title, data, options, output_context, style_profile):
        render_calls.append({"title": title, "records": data["records"]})
        return base64.b64encode(b"png-bytes").decode(), None, None

    monkeypatch.setattr(
        "app.tools.visualization.create_report_chart.domain.wind_timeseries.render_wind_timeseries",
        fake_render_wind_timeseries,
    )

    result = await fetcher.fetch_and_store()

    assert result["events"] == []
    assert "meteorology_chart_paths" not in result
    city_chart = result["city_mean_meteorology_chart_path"]
    assert "许昌市全市均值_气象与PM2_5时序变化_2026-08-05.png" in city_chart
    assert (tmp_path / "images" / "许昌市全市均值_气象与PM2_5时序变化_2026-08-05.png").read_bytes() == b"png-bytes"
    assert len(render_calls) == 1
    assert "全市站点均值" in render_calls[0]["title"]
    concentrations = {row["time"].hour: row["concentration"] for row in render_calls[0]["records"]}
    assert concentrations == {10: 21.0, 11: 25.0}
    evidence = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805.json").read_text(encoding="utf-8")
    )
    assert evidence["city_mean_meteorology_chart_path"] == city_chart
