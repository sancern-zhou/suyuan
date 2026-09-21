import json
import types
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.fetchers.xuchang_station_daily_pollution import (
    DAILY_REVIEW_EVENT_TYPE,
    XuchangStationDailyPollutionFetcher,
    build_city_daily_ranking,
)

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
TARGET_DAY = date(2026, 8, 5)


def test_city_daily_ranking_uses_parallel_ranks_for_equal_values():
    result = build_city_daily_ranking([
        {"city": "许昌市", "pm25": 50, "pm10": 80},
        {"city": "郑州市", "pm25": 50, "pm10": 90},
        {"city": "洛阳市", "pm25": 30, "pm10": 80},
        {"city": "开封市", "pm25": 20, "pm10": 70},
    ], TARGET_DAY)
    assert result["xuchang"]["pm25_rank"] == 1
    assert result["xuchang"]["pm10_rank"] == 2


class _FakeCursor:
    def __init__(self, result_sets):
        self._result_sets = result_sets
        self._index = -1
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append(" ".join(sql.split()))
        self._index += 1

    def fetchall(self):
        return self._result_sets[self._index]


class _FakeConnection:
    def __init__(self, result_sets):
        self._cursor = _FakeCursor(result_sets)

    def cursor(self):
        return self._cursor

    def close(self):
        pass


def test_load_city_daily_rows_merges_zhongda_and_publish_history(monkeypatch):
    result_sets = [
        [("许昌市", "411000", date(2026, 9, 19), 42.0, 72.0)],
        [
            ("郑州市", "410100", datetime(2026, 9, 19), "51", "75"),
            ("开封市", "410200", datetime(2026, 9, 19), "52", "100"),
        ],
    ]
    connection = _FakeConnection(result_sets)

    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.xcai_connection_string", lambda: "dsn=fake"
    )
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.pyodbc",
        types.SimpleNamespace(connect=lambda dsn, timeout=30: connection),
    )
    fetcher = XuchangStationDailyPollutionFetcher()

    rows = fetcher.load_city_daily_rows(date(2026, 9, 19))

    zhongda_sql, publish_sql = connection._cursor.executed
    assert "dat_zhongda_city_day" in zhongda_sql
    assert "CityDayAQIPublishHistory" in publish_sql
    assert [row["city"] for row in rows] == ["许昌市", "郑州市", "开封市"]
    assert rows[0]["data_source"] == "zhongda_city_day"
    assert rows[0]["pm25"] == 42.0
    peers = rows[1:]
    assert all(row["data_source"] == "city_day_publish_history" for row in peers)
    assert peers[0]["pm25"] == 51.0 and peers[1]["pm10"] == 100.0

    ranking = build_city_daily_ranking(rows, date(2026, 9, 19))
    assert ranking["city_count"] == 3
    assert ranking["xuchang"]["pm25"] == 42.0
    assert ranking["xuchang"]["pm25_rank"] == 3
    assert ranking["xuchang"]["pm25_median"] == 51.0
    assert "CityDayAQIPublishHistory" in ranking["source"]


@pytest.fixture(autouse=True)
def _use_file_episode_state(monkeypatch):
    monkeypatch.setenv("XUCHANG_STATION_EPISODE_STORAGE", "file")


def _hourly_rows():
    rows = []
    profiles = {
        "XC001": (34.03, 113.85, {8: 20, 9: 20, 10: 20, 11: 60, 12: 55, 13: 50, 14: 45}),
        "XC002": (34.10, 113.90, {8: 20, 9: 20, 10: 40, 11: 50, 12: 45, 13: 40, 14: 35}),
        "XC003": (34.20, 114.00, {8: 20, 9: 20, 10: 40, 11: 45, 12: 40, 13: 35, 14: 30}),
        "XC004": (34.05, 113.70, {8: 20, 9: 20, 10: 20, 11: 25, 12: 22, 13: 20, 14: 20}),
    }
    for station_id, (lat, lon, values) in profiles.items():
        for hour, value in values.items():
            rows.append({
                "station_id": station_id, "name": f"站点{station_id}", "pm25": value,
                "data_time": datetime(2026, 8, 5, hour), "lat": lat, "lon": lon,
                "station_type": "regular", "data_source": "hour",
            })
    return rows


def _township_rows():
    rows = []
    profiles = {
        "1107B": ("长葛市和尚桥镇", "长葛市", {8: 22, 9: 22, 10: 24, 11: 45, 12: 40, 13: 35, 14: 30}),
        "1108B": ("长葛市南席镇", "长葛市", {8: 20, 9: 20, 10: 20, 11: 25, 12: 22, 13: 20, 14: 20}),
    }
    for station_id, (name, district, values) in profiles.items():
        for hour, value in values.items():
            rows.append({
                "station_id": station_id, "name": name, "district": district,
                "data_time": datetime(2026, 8, 5, hour), "pm25": value,
                "station_type": "township", "lat": None, "lon": None,
            })
    return rows


def _township_loader_ok(start, end):
    return {
        "status": "available",
        "reason": None,
        "source": "airdata_platform:v_t_h_src",
        "query_window": {"start": start.isoformat(), "end": end.isoformat()},
        "station_count": 2,
        "rows": _township_rows(),
    }


def _township_loader_failed(start, end):
    return {
        "status": "not_available",
        "reason": "township_hourly_query_failed: AirDataPlatformError: boom",
        "source": "airdata_platform:v_t_h_src",
        "query_window": {"start": start.isoformat(), "end": end.isoformat()},
        "station_count": 0,
        "rows": [],
    }


def _write_scenario_one_fixtures(registry):
    alerts_dir = registry / "xuchang_station_deviation_alerts"
    day_dir = alerts_dir / "20260805"
    day_dir.mkdir(parents=True)
    (day_dir / "xuchang-station-episode-202608051100-XC001-abc.evidence.json").write_text(
        json.dumps({
            "schema_version": "xuchang_station_deviation_evidence/v3",
            "alerts": [{
                "alert": {"event_id": "ev-11", "occurred_at": "2026-08-05T11:00:00+08:00",
                          "station_value": 60.0, "target_pollutant": "PM2.5",
                          "pollutant_source_features": {
                              "status": "calculated", "sample_count": 12,
                              "classification": "biomass_burning",
                          }},
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (alerts_dir / "episode_state.json").write_text(
        json.dumps({
            "schema_version": "xuchang_station_deviation_episodes/v1",
            "active": {},
            "history": [{
                "episode_id": "xuchang-station-deviation-episode-2026080511-XC001-pm2.5",
                "status": "closed",
                "city": "许昌市",
                "station_id": "XC001",
                "station_name": "目标站",
                "target_pollutant": "PM2.5",
                "measurement_granularity": "hour",
                "alert_type": "hourly_deviation",
                "started_at": "2026-08-05T11:00:00+08:00",
                "last_seen_at": "2026-08-05T11:00:00+08:00",
                "event_ids": ["ev-11"],
                "hour_count": 1,
                "notification_count": 1,
                "peak_station_value": 60.0,
                "peak_deviation_ratio": 1.2,
                "closed_at": "2026-08-05T12:00:00+08:00",
                "closed_reason": "inactivity",
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_load_city_daily_rows_falls_back_to_publish_history_for_xuchang(monkeypatch):
    result_sets = [
        [],
        [("许昌市", "411000", datetime(2026, 9, 19), "59", "92")],
        [
            ("郑州市", "410100", datetime(2026, 9, 19), "51", "75"),
        ],
    ]
    connection = _FakeConnection(result_sets)
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.xcai_connection_string", lambda: "dsn=fake"
    )
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.pyodbc",
        types.SimpleNamespace(connect=lambda dsn, timeout=30: connection),
    )
    fetcher = XuchangStationDailyPollutionFetcher()

    rows = fetcher.load_city_daily_rows(date(2026, 9, 19))

    assert len(connection._cursor.executed) == 3
    assert rows[0]["city"] == "许昌市"
    assert rows[0]["data_source"] == "city_day_publish_history_xuchang_fallback"
    assert rows[0]["pm25"] == 59.0

    ranking = build_city_daily_ranking(rows, date(2026, 9, 19))
    assert ranking["xuchang"]["pm25"] == 59.0
    assert ranking["xuchang"]["value_source"] == "city_day_publish_history_xuchang_fallback"
    assert ranking["xuchang"]["pm25_rank"] == 1


class _TaskService:
    def __init__(self):
        self.events = []

    async def publish_event(self, event):
        self.events.append(event)


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


def _build_fetcher(monkeypatch, tmp_path, task_service, township_loader=_township_loader_ok):
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.get_data_registry", lambda: tmp_path
    )
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.WeatherRepository", _WeatherRepository
    )
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: task_service)
    fetcher = XuchangStationDailyPollutionFetcher(
        now_factory=lambda: datetime(2026, 8, 6, 2, 5, tzinfo=TZ_SHANGHAI),
        township_loader=township_loader,
    )
    monkeypatch.setattr(fetcher, "load_rows", lambda start, end, codes: _hourly_rows())
    monkeypatch.setattr(fetcher, "load_regional_hourly_rows", lambda target_date: [])
    monkeypatch.setattr(fetcher, "load_city_daily_rows", lambda target_date: [
        {"city": "许昌市", "pm25": 35, "pm10": 58},
        {"city": "郑州市", "pm25": 55, "pm10": 75},
        {"city": "洛阳市", "pm25": 20, "pm10": 40},
    ])
    return fetcher


@pytest.mark.asyncio
async def test_fetcher_consumes_scenario_one_episodes(monkeypatch, tmp_path):
    _write_scenario_one_fixtures(tmp_path)
    task_service = _TaskService()
    fetcher = _build_fetcher(monkeypatch, tmp_path, task_service)

    await fetcher.fetch_and_store()

    assert [event.event_type for event in task_service.events] == [DAILY_REVIEW_EVENT_TYPE]
    payload = task_service.events[0].payload
    assert payload["alert_source_status"] == "found"
    assert payload["episode_count"] == 1
    assert "XC001(PM2.5" in payload["alert_episode_anchors"][0]
    # 事件 payload 只携带摘要与路径，不内嵌全量证据数据。
    assert len(task_service.events[0].model_dump_json()) < 2000

    evidence = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805" / "manifest.json").read_text(encoding="utf-8")
    )
    assert evidence["schema_version"] == "xuchang_station_daily_review/v5"
    assert evidence["alert_source"]["status"] == "found"
    assert "cities" not in evidence
    assert "meteorology_chart_paths" not in evidence
    assert "city_mean_meteorology_chart_path" not in evidence
    assert "city_daily_rankings" in evidence["evidence_files"]
    city_daily = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805" / "city_daily_rankings.json").read_text(encoding="utf-8")
    )
    assert city_daily["city_daily_ranking"]["xuchang"]["pm25_rank"] == 2
    assert city_daily["city_daily_ranking"]["xuchang"]["pm10_rank"] == 2
    assert "cities" not in city_daily["city_daily_ranking"]
    episode = evidence["episodes"][0]
    assert episode["analysis_status"] == "new"
    assert episode["episode_id"].startswith("xuchang-station-deviation-episode-")
    assert episode["regional_co_rise"]["classification"] == "regional_co_rise"
    assert episode["transport_consistency"]["conclusion"] == "neighbor_lead_rise"
    assert episode["source_features"] == [{
        "status": "calculated", "sample_count": 12, "classification": "biomass_burning",
    }]
    township_responses = [
        item for item in episode["station_response_by_window"]
        if item["station_type"] == "township"
    ]
    assert township_responses
    assert all(item["coordinate_status"] == "missing_coordinates" for item in township_responses)
    assert episode["spatial_gradient"]["coordinate_coverage"]["township"] == "missing_coordinates"
    assert episode["alert_anchor"]["peak_value"] == 60.0
    assert "source_evidence_package_path" not in episode
    meteorology = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805" / "meteorology.json").read_text(encoding="utf-8")
    )
    assert meteorology["meteorology"]
    assert "meteorology_chart_paths" not in meteorology
    assert "city_mean_meteorology_chart_path" not in meteorology
    source_features = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805" / "source_features.json").read_text(encoding="utf-8")
    )
    assert source_features["source_features_summary"]["record_count"] == 1
    assert source_features["source_features_summary"]["classification_counts"] == {
        "biomass_burning": 1,
    }


@pytest.mark.asyncio
async def test_fetcher_without_scenario_one_events_records_not_found(monkeypatch, tmp_path):
    task_service = _TaskService()
    fetcher = _build_fetcher(monkeypatch, tmp_path, task_service)

    result = await fetcher.fetch_and_store()

    assert [event.event_type for event in task_service.events] == [DAILY_REVIEW_EVENT_TYPE]
    payload = task_service.events[0].payload
    assert payload["alert_source_status"] == "not_found"
    assert payload["episode_count"] == 0
    assert result["episodes"] == []
    evidence = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805" / "manifest.json").read_text(encoding="utf-8")
    )
    assert evidence["episodes"] == []
    assert evidence["report_summary"]["alert_source_status"] == "not_found"
    assert "meteorology_chart_paths" not in evidence
    assert "city_mean_meteorology_chart_path" not in evidence


@pytest.mark.asyncio
async def test_duplicate_episode_not_recomputed_on_rerun(monkeypatch, tmp_path):
    _write_scenario_one_fixtures(tmp_path)
    task_service = _TaskService()
    fetcher = _build_fetcher(monkeypatch, tmp_path, task_service)

    first = await fetcher.fetch_and_store()
    second = await fetcher.fetch_and_store()

    assert first["episodes"][0]["analysis_status"] == "new"
    assert second["episodes"][0]["analysis_status"] == "duplicate"
    assert second["episodes"][0]["calculation_status"] == "skipped_duplicate"
    assert second["episodes"][0]["regional_co_rise"]["classification"] == "regional_co_rise"
    assert second["report_summary"]["episode_count"] == 1
    assert second["report_summary"]["alert_source_status"] == "found"
    state = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "analysis_state.json").read_text(encoding="utf-8")
    )
    versions = state["episodes"][first["episodes"][0]["episode_id"]]["versions"]
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_township_failure_degrades_without_breaking_review(monkeypatch, tmp_path):
    _write_scenario_one_fixtures(tmp_path)
    task_service = _TaskService()
    fetcher = _build_fetcher(monkeypatch, tmp_path, task_service, township_loader=_township_loader_failed)

    result = await fetcher.fetch_and_store()

    assert result["township_data"]["status"] == "not_available"
    episode = result["episodes"][0]
    assert episode["calculation_status"] == "calculated"
    assert episode["regional_co_rise"]["classification"] in {
        "regional_co_rise", "local_target_only", "insufficient_evidence",
    }
