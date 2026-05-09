from datetime import datetime, timedelta

from app.services.air_quality_data_quality_monitor import (
    AirQualityDataQualityMonitorService,
    DataQualityMonitorConfig,
)


def _record(station: str, ts: datetime, pm25: float, pm10: float, no2: float = 30.0, o3: float = 80.0):
    return {
        "station_name": station,
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "measurements": {
            "PM2_5": pm25,
            "PM10": pm10,
            "NO2": no2,
            "O3_8h": o3,
        },
    }


def test_detects_persistent_station_bias():
    start = datetime(2026, 5, 1, 0)
    records = []
    for i in range(8):
        ts = start + timedelta(hours=i)
        records.extend([
            _record("异常站", ts, pm25=80, pm10=120),
            _record("对照站1", ts, pm25=40, pm10=70),
            _record("对照站2", ts, pm25=42, pm10=72),
        ])

    service = AirQualityDataQualityMonitorService(
        DataQualityMonitorConfig(cities=["广州"], hours=8, min_aggregate_points=6, min_trend_points=6)
    )
    issues = service.evaluate_records("广州", records)

    rule_ids = {issue["rule_id"] for issue in issues}
    assert "pm2_5_daily_peer_deviation" in rule_ids
    assert "pm10_persistent_peer_bias" in rule_ids
    assert any(issue.get("station") == "异常站" for issue in issues)


def test_clean_peer_consistent_data_has_no_issue():
    start = datetime(2026, 5, 1, 0)
    records = []
    for i in range(8):
        ts = start + timedelta(hours=i)
        records.extend([
            _record("站点A", ts, pm25=30 + i, pm10=55 + i),
            _record("站点B", ts, pm25=31 + i, pm10=56 + i),
            _record("站点C", ts, pm25=29 + i, pm10=54 + i),
        ])

    service = AirQualityDataQualityMonitorService(
        DataQualityMonitorConfig(cities=["广州"], hours=8, min_aggregate_points=6, min_trend_points=6)
    )
    issues = service.evaluate_records("广州", records)

    assert issues == []
