from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.fetchers.xuchang_station_daily_exceedance import (
    CONFIRMED_EVENT_TYPE,
    REQUESTED_EVENT_TYPE,
    XuchangStationDailyExceedanceFetcher,
    analyze_boundary_layer,
    analyze_cloud_cover,
    analyze_high_humidity_conversion,
    analyze_temperature_inversion,
    evaluate_station_daily_pollution,
    merge_meteo_rows,
    normalize_station_name,
    resolve_hourly_station_codes,
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


def _meteo_rows(*, rh=70.0, cooling=True, calm=True, clear=True, blh=600.0):
    """Build 24 hourly ERA5-style rows with controllable drivers."""
    rows = []
    for hour in range(24):
        if cooling:
            temperature = 24.0 if hour <= 18 else 24.0 - (hour - 18) * 0.8
            if hour < 7:
                temperature = 24.0 - (24 - 18 + hour) * 0.8
        else:
            temperature = 20.0
        rows.append({
            "time": datetime(2026, 8, 5, hour, tzinfo=TZ_SHANGHAI).isoformat(),
            "temperature_2m": round(temperature, 1),
            "relative_humidity_2m": rh,
            "wind_speed_10m_kmh": 3.0 if calm else 20.0,
            "wind_speed_10m_ms": round((3.0 if calm else 20.0) / 3.6, 2),
            "wind_direction_10m": 180.0,
            "precipitation": 0.0,
            "cloud_cover": 10.0 if clear else 90.0,
            "boundary_layer_height": blh,
        })
    return rows


def _station_hourly(station_id="XC001", *, pm25=60.0, pm10=80.0, so2=8.0, no2=30.0):
    return [
        {
            "station_id": station_id,
            "name": "测试站",
            "pm25": pm25,
            "pm10": pm10,
            "o3": 90.0,
            "no2": no2,
            "so2": so2,
            "co": 0.6,
            "data_time": datetime(2026, 8, 5, hour),
            "data_source": "hour",
        }
        for hour in range(24)
    ]


def test_daily_exceedance_triggers_one_event_per_pollutant():
    result = evaluate_station_daily_pollution(_rows(), target_date=date(2026, 8, 5))

    assert [event["target_pollutant"] for event in result["events"]] == ["PM2.5", "O3"]
    event = result["events"][0]
    assert event["event_type"] == CONFIRMED_EVENT_TYPE
    assert event["trigger"] == "confirmed_station_daily_exceedance"
    assert event["source_granularity"] == "station_day"
    assert event["daily_value"] == 80.0
    assert event["limit"] == 75.0
    assert event["event_id"] == "xuchang-station-daily-pollution-20260805-XC001-pm25"


def test_below_limit_or_missing_values_do_not_trigger():
    compliant = evaluate_station_daily_pollution(
        _rows(pm25=60.0, o3_8h=150.0), target_date=date(2026, 8, 5)
    )
    missing = evaluate_station_daily_pollution(
        _rows(pm25=None, o3_8h=None), target_date=date(2026, 8, 5)
    )

    assert compliant["events"] == []
    assert missing["events"] == []
    assert missing["evaluations"][0]["pm25"]["status"] == "missing_daily_value"


def test_peer_station_daily_context_attached():
    rows = _rows() + [{
        "station_id": "XC002",
        "name": "参照站",
        "lat": 34.08,
        "lon": 113.84,
        "pm25": 50.0,
        "o3_8h": 120.0,
        "data_time": datetime(2026, 8, 5),
    }]
    result = evaluate_station_daily_pollution(rows, target_date=date(2026, 8, 5))

    peers = result["events"][0]["peer_station_daily"]
    assert [peer["station_id"] for peer in peers] == ["XC002"]
    assert peers[0]["exceeded"] is False


# ---- 气象机理分析 ----------------------------------------------------------


def test_boundary_layer_classification_rules():
    shallow = analyze_boundary_layer(_meteo_rows(blh=120.0))
    nocturnal_stable = analyze_boundary_layer(_meteo_rows(blh=400.0))
    normal = analyze_boundary_layer(_meteo_rows(blh=1200.0))

    assert shallow["classification"] == "persistently_shallow_boundary_layer"
    assert shallow["low_boundary_layer_hours"] == 24
    # blh=400：夜间均值400不满足<200，白天max400<500 → 持续浅边界层
    assert nocturnal_stable["classification"] == "persistently_shallow_boundary_layer"
    assert normal["classification"] == "normal_boundary_layer"
    assert normal["daily_amplitude"] == 0.0
    assert analyze_boundary_layer(_meteo_rows()[:3])["status"] == "insufficient_data"


def test_cloud_cover_classification_rules():
    clear = analyze_cloud_cover(_meteo_rows(clear=True))
    cloudy = analyze_cloud_cover(_meteo_rows(clear=False))

    assert clear["nocturnal_mean"] == 10.0
    assert clear["classification"] == "clear_night_favoring_radiative_cooling"
    assert cloudy["classification"] == "cloudy_night_suppressing_radiative_cooling"


def test_high_humidity_conversion_classification_rules():
    humid = _meteo_rows(rh=90.0)
    dry = _meteo_rows(rh=40.0)

    likely = analyze_high_humidity_conversion(
        humid, _station_hourly(pm25=72.0, pm10=90.0), "XC001"
    )
    assert likely["classification"] == "high_humidity_secondary_conversion_likely"
    assert likely["high_humidity_ratio"] == 1.0
    assert likely["fine_particle_ratio_mean_in_humid_hours"] == 0.8

    coarse = analyze_high_humidity_conversion(
        humid, _station_hourly(pm25=30.0, pm10=90.0), "XC001"
    )
    assert coarse["classification"] == "high_humidity_without_fine_particle_evidence"

    possible = analyze_high_humidity_conversion(
        dry, _station_hourly(), "XC001"
    )
    assert possible["classification"] == "unlikely_high_humidity_secondary_conversion"


def test_temperature_inversion_classification_rules():
    likely = analyze_temperature_inversion(_meteo_rows(calm=True, clear=True))
    # 18时24°C，夜间最低约 24-9.6*0.8≈16.3°C，降温>5°C + 静稳 + 晴夜
    assert likely["nocturnal_cooling_c"] >= 5.0
    assert likely["criteria"]["strong_nocturnal_cooling"] is True
    assert likely["classification"] == "radiation_inversion_likely"

    windy = analyze_temperature_inversion(_meteo_rows(calm=False, clear=True))
    assert windy["criteria"]["calm_nocturnal_wind"] is False
    assert windy["classification"] == "radiation_inversion_possible"

    none = analyze_temperature_inversion(_meteo_rows(calm=False, clear=False, cooling=False))
    assert none["classification"] == "radiation_inversion_unlikely"
    assert "非探空实测" in none["proxy_note"]


def test_merge_prefers_observed_surface_variables_and_keeps_era5_vertical():
    observed = [{
        "time": datetime(2026, 8, 5, 10, tzinfo=TZ_SHANGHAI).isoformat(),
        "temperature_2m": 21.5,
        "relative_humidity_2m": 85.0,
        "wind_speed_10m_ms": 1.2,
        "wind_direction_10m": 200.0,
        "precipitation": 0.4,
    }]
    era5 = _meteo_rows()

    merged, coverage = merge_meteo_rows(observed, era5)

    hour10 = next(row for row in merged if "T10:" in row["time"])
    assert hour10["temperature_2m"] == 21.5
    assert hour10["wind_speed_10m_ms"] == 1.2
    assert hour10["precipitation"] == 0.4
    assert hour10["cloud_cover"] == 10.0
    assert hour10["boundary_layer_height"] == 600.0
    hour11 = next(row for row in merged if "T11:" in row["time"])
    assert hour11["temperature_2m"] != 21.5
    assert coverage["observed_hours"] == 1
    assert coverage["merged_hours"] == 24


def test_station_code_mapping_by_name():
    daily_names = {
        "2398A": "开发区",
        "3134A": "市一中",
        "3337A": "许昌学院",
        "3338A": "芙蓉广场",
        "4180A": "新元大道996号",
        "4259A": "望田路111号",
    }
    hourly_names = {
        "1003A": "开发区",
        "1005A": "市一中（启用170929）",
        "1008A": "许昌学院",
        "1009A": "芙蓉广场",
        "1011A": "新元大道996号",
        "1012A": "望田路111号（启用20250213）",
        "9999A": "其它站",
    }

    mapping = resolve_hourly_station_codes(daily_names, hourly_names)

    assert mapping == {
        "2398A": "1003A", "3134A": "1005A", "3337A": "1008A",
        "3338A": "1009A", "4180A": "1011A", "4259A": "1012A",
    }
    assert normalize_station_name("市一中（启用170929）") == "市一中"


# ---- Fetcher 集成 ----------------------------------------------------------


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
async def test_fetcher_publishes_confirmation_and_request_with_evidence(monkeypatch):
    analysis_service = _AnalysisService()
    task_service = _TaskService()
    fetcher = XuchangStationDailyExceedanceFetcher(
        analysis_service=analysis_service,
        now_factory=lambda: datetime(2026, 8, 6, 2, tzinfo=TZ_SHANGHAI),
    )
    monkeypatch.setattr(fetcher, "load_rows", lambda target_date: _rows())
    monkeypatch.setattr(fetcher, "load_station_hourly", lambda d, ids: _station_hourly())
    monkeypatch.setattr(
        fetcher, "load_era5_hourly", lambda d: _async_value(_meteo_rows(rh=90.0))
    )
    monkeypatch.setattr(
        fetcher,
        "load_observed_hourly",
        lambda d: _async_value([]),
    )
    monkeypatch.setattr(
        "app.scheduled_tasks.get_scheduled_task_service", lambda: task_service
    )

    result = await fetcher.fetch_and_store()

    assert len(result["events"]) == 2
    assert len(analysis_service.events) == 2
    published = [event.event_type for event in task_service.events]
    assert published == [
        CONFIRMED_EVENT_TYPE,
        REQUESTED_EVENT_TYPE,
        CONFIRMED_EVENT_TYPE,
        REQUESTED_EVENT_TYPE,
    ]

    pm25_event = next(
        event for event in result["events"] if event["target_pollutant"] == "PM2.5"
    )
    meteo = pm25_event["meteorology_evidence"]
    assert meteo["status"] == "available"
    assert len(meteo["rows"]) == 24
    assert meteo["boundary_layer_analysis"]["status"] == "calculated"
    assert meteo["temperature_inversion_analysis"]["classification"] == "radiation_inversion_likely"
    assert (
        meteo["high_humidity_conversion_analysis"]["classification"]
        == "high_humidity_secondary_conversion_likely"
    )
    assert pm25_event["pollutant_source_features"]["status"] == "calculated"
    assert pm25_event["pollutant_source_features"]["classification"] in {
        "偏综合型", "偏二次型", "偏机动车型", "偏燃煤型", "偏扬尘型", "其他类型",
    }
    assert len(pm25_event["hourly_rows"]) == 24
    assert pm25_event["hourly_rows"][0]["concentration"] == 60.0
    assert pm25_event["data_quality"]["hourly_completeness_ratio"] == 1.0
    assert all(
        payload["scenario_2"]["status"] == "requested"
        for payload in (
            event.payload for event in task_service.events
            if event.event_type == CONFIRMED_EVENT_TYPE
        )
    )


def _async_value(value):
    async def _wrapper():
        return value
    return _wrapper()


@pytest.mark.asyncio
async def test_fetcher_without_exceedance_publishes_nothing(monkeypatch):
    task_service = _TaskService()
    fetcher = XuchangStationDailyExceedanceFetcher(
        analysis_service=_AnalysisService(),
        now_factory=lambda: datetime(2026, 8, 6, 2, tzinfo=TZ_SHANGHAI),
    )
    monkeypatch.setattr(
        fetcher, "load_rows", lambda target_date: _rows(pm25=60.0, o3_8h=150.0)
    )
    monkeypatch.setattr(
        "app.scheduled_tasks.get_scheduled_task_service", lambda: task_service
    )

    result = await fetcher.fetch_and_store()

    assert result["events"] == []
    assert task_service.events == []
