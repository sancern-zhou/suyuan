from datetime import datetime, timedelta

from app.services.pollution_event_monitor import MonitorConfig, PollutionEventMonitorService, TZ_SHANGHAI


def _service():
    return PollutionEventMonitorService(MonitorConfig(cities=["测试"], include_components=False))


def _record(ts, pm25=20, pm10=45, no2=25, aqi=None, wind=1.0):
    if aqi is None:
        aqi = max(pm25, no2)
    return {
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "measurements": {
            "AQI": aqi,
            "PM2_5": pm25,
            "PM10": pm10,
            "NO2": no2,
            "wind_speed_10m": wind,
            "wind_direction_10m": 220,
            "relative_humidity_2m": 70,
        },
    }


def test_detects_sustained_pm25_process():
    service = _service()
    start = datetime(2026, 5, 8, 0, tzinfo=TZ_SHANGHAI)
    records = []
    for i in range(24):
        pm25 = 20
        no2 = 25
        if 9 <= i <= 13:
            pm25 = 20 + (i - 8) * 18
            no2 = 25 + (i - 8) * 12
        records.append(_record(start + timedelta(hours=i), pm25=pm25, pm10=pm25 + 20, no2=no2))

    quality = service._quality_report("测试", records, start, start + timedelta(hours=23))
    events = service._detect_events("测试", records, quality)

    assert events
    assert events[0]["main_pollutant"] == "PM2_5"
    assert events[0]["severity"] in {"medium", "high"}
    assert "sustained" in events[0]["event_type"]


def test_quality_flags_pm25_greater_than_pm10():
    service = _service()
    start = datetime(2026, 5, 8, 0, tzinfo=TZ_SHANGHAI)
    records = [_record(start + timedelta(hours=i), pm25=60, pm10=45) for i in range(6)]

    quality = service._quality_report("测试", records, start, start + timedelta(hours=5))

    issue_types = {issue["issue_type"] for issue in quality["issues"]}
    assert "pm25_gt_pm10" in issue_types
    assert quality["status"] in {"usable_with_caution", "poor"}


def test_component_fetch_window_extends_backward_for_24_hour_points():
    service = PollutionEventMonitorService(
        MonitorConfig(
            cities=["测试"],
            include_components=True,
            event_context_hours=2,
            component_min_hours=24,
        )
    )
    event_start = datetime(2026, 5, 8, 20, tzinfo=TZ_SHANGHAI)
    event_end = datetime(2026, 5, 8, 21, tzinfo=TZ_SHANGHAI)
    full_end = datetime(2026, 5, 8, 23, tzinfo=TZ_SHANGHAI)

    start, end = service._component_fetch_window(
        event_start=event_start,
        event_end=event_end,
        full_end=full_end,
    )

    assert start == datetime(2026, 5, 8, 0, tzinfo=TZ_SHANGHAI)
    assert end == full_end
