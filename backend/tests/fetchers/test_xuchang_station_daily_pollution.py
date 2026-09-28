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


def test_load_city_daily_rows_uses_publish_history_for_all_cities(monkeypatch):
    result_sets = [
        [
            ("许昌市", "411000", datetime(2026, 9, 19), "42", "72"),
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

    (publish_sql,) = connection._cursor.executed
    assert "CityDayAQIPublishHistory" in publish_sql
    assert "dat_zhongda_city_day" not in publish_sql
    assert [row["city"] for row in rows] == ["许昌市", "郑州市", "开封市"]
    assert all(row["data_source"] == "city_day_publish_history" for row in rows)
    assert rows[0]["pm25"] == 42.0
    assert rows[1]["pm25"] == 51.0 and rows[2]["pm10"] == 100.0

    ranking = build_city_daily_ranking(rows, date(2026, 9, 19))
    assert ranking["city_count"] == 3
    assert ranking["xuchang"]["pm25"] == 42.0
    assert ranking["xuchang"]["value_source"] == "city_day_publish_history"
    assert ranking["xuchang"]["pm25_rank"] == 3
    assert ranking["xuchang"]["pm25_median"] == 51.0
    assert "CityDayAQIPublishHistory" in ranking["source"]
    assert "dat_zhongda_city_day" not in ranking["source"]


def test_load_hourly_rows_normalizes_legacy_station_id(monkeypatch):
    connection = _FakeConnection([[
        ("2398A", "旧站名", 20, 30, 40, 15, 5, 0.4, datetime(2026, 9, 25, 9)),
    ]])
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.xcai_connection_string", lambda: "dsn=fake"
    )
    monkeypatch.setattr(
        "app.fetchers.xuchang_station_daily_pollution.pyodbc",
        types.SimpleNamespace(connect=lambda dsn, timeout=30: connection),
    )
    fetcher = XuchangStationDailyPollutionFetcher()
    rows = fetcher.load_rows(datetime(2026, 9, 25, 8), datetime(2026, 9, 25, 10), {"2398A"})
    assert rows[0]["station_id"] == "1003A"
    assert rows[0]["source_station_id"] == "2398A"
    assert rows[0]["name"] == "开发区"


@pytest.fixture(autouse=True)
def _use_file_episode_state(monkeypatch):
    monkeypatch.setenv("XUCHANG_STATION_EPISODE_STORAGE", "file")


def _hourly_rows():
    rows = []
    profiles = {
        "XC001": (34.03, 113.85, {8: 20, 9: 20, 10: 35, 11: 60, 12: 55, 13: 50, 14: 45}),
        "XC002": (34.10, 113.90, {8: 20, 9: 20, 10: 20, 11: 50, 12: 45, 13: 40, 14: 35}),
        "XC003": (34.20, 114.00, {8: 20, 9: 20, 10: 20, 11: 45, 12: 40, 13: 35, 14: 30}),
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


def _make_scenario_one_minute_pm10(registry):
    _write_scenario_one_fixtures(registry)
    alerts_dir = registry / "xuchang_station_deviation_alerts"
    state_path = alerts_dir / "episode_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    source = state["history"][0]
    source.update({
        "target_pollutant": "PM10", "measurement_granularity": "5min",
        "alert_type": "station_deviation", "started_at": "2026-08-05T10:35:00+08:00",
        "last_seen_at": "2026-08-05T10:35:00+08:00",
    })
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    evidence_path = next((alerts_dir / "20260805").glob("*.evidence.json"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["alerts"][0]["alert"].update({
        "target_pollutant": "PM10", "occurred_at": "2026-08-05T10:35:00+08:00",
    })
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")


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
async def test_fetcher_selects_hourly_rise_without_scenario_one_clue(monkeypatch, tmp_path):
    _write_scenario_one_fixtures(tmp_path)
    monkeypatch.setattr("app.fetchers.xuchang_station_daily_pollution.settings.amap_public_key", "public-test-key")
    task_service = _TaskService()
    fetcher = _build_fetcher(monkeypatch, tmp_path, task_service)

    await fetcher.fetch_and_store()

    assert [event.event_type for event in task_service.events] == [DAILY_REVIEW_EVENT_TYPE]
    payload = task_service.events[0].payload
    assert payload["alert_source_status"] == "found"
    assert payload["episode_count"] == 1
    assert "XC001(PM2.5" in payload["alert_event_anchors"][0]
    # 事件 payload 只携带摘要与路径，不内嵌全量证据数据。
    assert len(task_service.events[0].model_dump_json()) < 2000

    evidence = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805" / "manifest.json").read_text(encoding="utf-8")
    )
    assert evidence["schema_version"] == "xuchang_station_daily_review/v8"
    assert evidence["alert_source"]["status"] == "found"
    assert "cities" not in evidence
    assert "meteorology_chart_paths" not in evidence
    assert "city_mean_meteorology_chart_path" not in evidence
    assert "city_daily_rankings" in evidence["evidence_files"]
    render_config = json.loads((tmp_path / "xuchang_station_daily_reviews" / "20260805" / "render_config.json").read_text(encoding="utf-8"))
    assert render_config == {"map_provider": "amap", "public_key": "public-test-key"}
    assert evidence["render_config_path"].endswith("/render_config.json")
    city_daily = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805" / "city_daily_rankings.json").read_text(encoding="utf-8")
    )
    assert city_daily["city_daily_ranking"]["xuchang"]["pm25_rank"] == 2
    assert city_daily["city_daily_ranking"]["xuchang"]["pm10_rank"] == 2
    assert "cities" not in city_daily["city_daily_ranking"]
    assert "episodes" not in evidence
    assert evidence["episode_count"] == 1
    files = evidence["evidence_files"]
    assert {"hourly_rise_detection", "report_brief", "event_brief", "stage_brief", "episodes", "station_responses", "regional_responses", "temporal_responses", "spatial_responses", "transport_responses", "report_facts", "pollutant_maps"} <= files.keys()
    assert "map_hourly" not in files
    day_dir = tmp_path / "xuchang_station_daily_reviews" / "20260805"
    brief_path = day_dir / "report_brief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    assert brief["episode_count"] == 1
    assert brief["alert_list"][0]["station_name"] == "站点XC001"
    assert brief["hourly_data_coverage"]["PM2.5"]["stations_with_data"] == 4
    assert "质控" in brief["hourly_quality_note"]
    assert brief["meteorology_intervals"]["nmc"]["record_count"] == 2
    assert "event_brief.json" in brief["field_guide"]["merged_alert_events"]
    assert brief_path.stat().st_size < 20_000
    stage_path = day_dir / "stage_brief.json"
    stage_brief = json.loads(stage_path.read_text(encoding="utf-8"))
    assert stage_brief["episode_count"] == 1
    assert isinstance(stage_brief["episodes"][0]["nearby_township_examples"], list)
    assert stage_brief["episodes"][0]["target_response"]["during"]["mean"] == 47.5
    assert stage_path.stat().st_size < 100_000
    episode = json.loads((day_dir / "episodes.json").read_text(encoding="utf-8"))["episodes"][0]
    assert episode["analysis_status"] == "new"
    assert episode["episode_id"].startswith("hourly-rise-")
    assert "spatial_map" not in episode
    regional = json.loads((day_dir / "regional_responses.json").read_text(encoding="utf-8"))["episodes"][0]
    transport = json.loads((day_dir / "transport_responses.json").read_text(encoding="utf-8"))["episodes"][0]
    assert regional["regional_co_rise"]["classification"] == "regional_co_rise"
    assert transport["transport_consistency"]["conclusion"] == "regional_co_rise"
    source_detail = json.loads((day_dir / "source_features.json").read_text(encoding="utf-8"))["episodes"][0]
    assert source_detail["source_features"] == []
    station_response = json.loads((day_dir / "station_responses.json").read_text(encoding="utf-8"))["episodes"][0]
    township_responses = [
        item for item in station_response["stations"]
        if item["station_type"] == "township"
    ]
    assert township_responses
    assert all(item["coordinate_status"] == "missing_coordinates" for item in township_responses)
    spatial = json.loads((day_dir / "spatial_responses.json").read_text(encoding="utf-8"))["episodes"][0]
    assert "spatial_map" in spatial
    assert spatial["spatial_gradient"]["coordinate_coverage"]["township"] == "missing_coordinates"
    assert episode["alert_anchor"]["peak_value"] == 60.0
    assert "source_evidence_package_path" not in episode
    facts = json.loads((day_dir / "report_facts.json").read_text(encoding="utf-8"))
    assert facts["episode_count"] == 1
    assert facts["episodes"][0]["transport_conclusion"] == "regional_co_rise"
    event_data = json.loads((day_dir / "event_brief.json").read_text(encoding="utf-8"))
    assert event_data["event_count"] == 1
    assert event_data["events"][0]["source_episode_ids"] == []
    assert event_data["events"][0]["minute_clue_count"] == 0
    assert event_data["events"][0]["hourly_observations"] == [
        {"time": "2026-08-05T09:00:00", "concentration": 20.0},
        {"time": "2026-08-05T10:00:00", "concentration": 35.0},
        {"time": "2026-08-05T11:00:00", "concentration": 60.0},
    ]
    assert event_data["events"][0]["peak_rise_absolute"] == 40
    assert event_data["events"][0]["reference_time"] == "2026-08-05T09:00:00"
    selection = json.loads((day_dir / "hourly_rise_detection.json").read_text(encoding="utf-8"))
    assert selection["event_count"] == 1
    assert selection["events"][0]["qualified_windows"]
    assert len(selection["events"][0]["hourly_observations"]) == 3
    assert "full_day_rows" not in selection
    from app.scenarios.xuchang_daily_review.qmd_report import write_qmd_report_from_evidence

    built = write_qmd_report_from_evidence(
        str(day_dir / "manifest.json"),
        {"summary_text": "昨日发现一次小时抬升。", "conclusion": "继续观察。",
         "event_analysis": {event_data["events"][0]["event_id"]: "结合区域事实继续核查。"}},
        str(tmp_path / "actual_review.qmd"),
    )
    qmd = (tmp_path / "actual_review.qmd").read_text(encoding="utf-8")
    assert built["event_count"] == 1
    assert "小时抬升时段" in qmd and "结合区域事实继续核查" in qmd
    map_data = json.loads((day_dir / "pollutant_maps.json").read_text(encoding="utf-8"))
    assert map_data["pollutant_count"] == 1
    assert map_data["maps"][0]["pollutant"] == "PM2.5"
    assert map_data["maps"][0]["frames"]
    meteorology = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805" / "meteorology.json").read_text(encoding="utf-8")
    )
    assert meteorology["meteorology"]
    assert "meteorology_chart_paths" not in meteorology
    assert "city_mean_meteorology_chart_path" not in meteorology
    source_features = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805" / "source_features.json").read_text(encoding="utf-8")
    )
    assert source_features["source_features_summary"]["record_count"] == 0
    assert source_features["source_features_summary"]["classification_counts"] == {}


@pytest.mark.asyncio
async def test_fetcher_without_scenario_one_events_still_selects_hourly_rise(monkeypatch, tmp_path):
    task_service = _TaskService()
    fetcher = _build_fetcher(monkeypatch, tmp_path, task_service)

    result = await fetcher.fetch_and_store()

    assert [event.event_type for event in task_service.events] == [DAILY_REVIEW_EVENT_TYPE]
    payload = task_service.events[0].payload
    assert payload["alert_source_status"] == "found"
    assert payload["episode_count"] == 1
    assert result["episodes"]
    evidence = json.loads(
        (tmp_path / "xuchang_station_daily_reviews" / "20260805" / "manifest.json").read_text(encoding="utf-8")
    )
    assert evidence["episode_count"] == 1
    assert "episodes" not in evidence
    summary = json.loads((tmp_path / "xuchang_station_daily_reviews" / "20260805" / "summary.json").read_text(encoding="utf-8"))
    assert summary["report_summary"]["alert_source_status"] == "found"
    assert "meteorology_chart_paths" not in evidence
    assert "city_mean_meteorology_chart_path" not in evidence


@pytest.mark.asyncio
async def test_minute_only_alert_does_not_trigger_daily_process(monkeypatch, tmp_path):
    _make_scenario_one_minute_pm10(tmp_path)
    task_service = _TaskService()
    fetcher = _build_fetcher(monkeypatch, tmp_path, task_service)
    monkeypatch.setattr(fetcher, "load_rows", lambda start, end, codes: [
        {**row, "pm25": 20, "pm10": 20} for row in _hourly_rows()
    ])
    result = await fetcher.fetch_and_store()
    assert result["alert_source"]["scenario_one_status"] == "found"
    assert result["report_events"]["event_count"] == 0
    assert task_service.events[0].payload["alert_source_status"] == "not_found"
    day_dir = tmp_path / "xuchang_station_daily_reviews" / "20260805"
    assert json.loads((day_dir / "event_brief.json").read_text())["events"] == []


@pytest.mark.asyncio
async def test_matching_minute_clue_is_frozen_with_hourly_process(monkeypatch, tmp_path):
    _make_scenario_one_minute_pm10(tmp_path)
    task_service = _TaskService()
    fetcher = _build_fetcher(monkeypatch, tmp_path, task_service)
    monkeypatch.setattr(fetcher, "load_rows", lambda start, end, codes: [
        {**row, "pm10": row["pm25"], "pm25": 20} for row in _hourly_rows()
    ])
    result = await fetcher.fetch_and_store()
    assert result["report_events"]["event_count"] == 1
    assert result["report_summary"]["raw_episode_count"] == 1
    day_dir = tmp_path / "xuchang_station_daily_reviews" / "20260805"
    event = json.loads((day_dir / "event_brief.json").read_text())["events"][0]
    assert event["pollutant"] == "PM10"
    assert event["minute_clue_count"] == 1
    assert event["minute_clues"][0]["matched_times"] == ["2026-08-05T10:35:00"]
    assert event["minute_clues"][0]["event_ids"] == ["ev-11"]
    assert event["source_episode_ids"] == [result["episodes"][0]["alert_anchor"]["source_episode_ids"][0]]
    assert json.loads((day_dir / "source_features.json").read_text())["source_features_summary"]["record_count"] == 1


@pytest.mark.asyncio
async def test_missing_hourly_data_has_explicit_status(monkeypatch, tmp_path):
    task_service = _TaskService()
    fetcher = _build_fetcher(monkeypatch, tmp_path, task_service)
    monkeypatch.setattr(fetcher, "load_rows", lambda start, end, codes: [])
    result = await fetcher.fetch_and_store()
    assert result["report_events"]["event_count"] == 0
    assert task_service.events[0].payload["alert_source_status"] == "data_unavailable"
    day_dir = tmp_path / "xuchang_station_daily_reviews" / "20260805"
    assert json.loads((day_dir / "report_brief.json").read_text())["alert_source_status"] == "data_unavailable"


@pytest.mark.asyncio
async def test_sparse_hourly_data_is_inconclusive_not_clean_day(monkeypatch, tmp_path):
    task_service = _TaskService()
    fetcher = _build_fetcher(monkeypatch, tmp_path, task_service)
    monkeypatch.setattr(fetcher, "load_rows", lambda start, end, codes: [
        row for row in _hourly_rows() if row["data_time"].hour == 11
    ])
    result = await fetcher.fetch_and_store()
    assert result["hourly_rise_detection"]["valid_windows"] == 0
    assert result["report_events"]["event_count"] == 0
    assert task_service.events[0].payload["alert_source_status"] == "insufficient_data"


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
