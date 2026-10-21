import json
from datetime import datetime

from app.scenarios.yuncheng_trial.fetch_and_alert import (
    evaluate_alert_rules,
    fetch_target_city_hourly_rows,
    write_latest_alert,
)


def test_o3_three_hour_rise_triggers_medium_alert():
    rows = [
        {"time": "2026-07-07 06:00:00", "O3": 110, "PM2.5": 20, "PM10": 50, "NO2": 18, "CO": 0.6},
        {"time": "2026-07-07 07:00:00", "O3": 125, "PM2.5": 21, "PM10": 51, "NO2": 18, "CO": 0.6},
        {"time": "2026-07-07 08:00:00", "O3": 138, "PM2.5": 22, "PM10": 51, "NO2": 19, "CO": 0.6},
        {"time": "2026-07-07 09:00:00", "O3": 153, "PM2.5": 22, "PM10": 52, "NO2": 19, "CO": 0.6},
    ]

    result = evaluate_alert_rules(rows)

    assert result["has_alert"] is True
    assert result["alert_type"] == "pollutant_rise"
    assert result["target_pollutant"] == "O3"
    assert result["alert_level"] == "medium"
    assert result["rule_hits"][0]["rule_id"] == "o3_3h_rising"
    assert "rule_basis" in result["rule_hits"][0]


def test_pm25_pm10_co_rise_adds_supporting_rule_hits():
    rows = [
        {"time": "2026-07-07 06:00:00", "O3": 80, "PM2.5": 40, "PM10": 80, "NO2": 30, "CO": 0.6},
        {"time": "2026-07-07 07:00:00", "O3": 82, "PM2.5": 48, "PM10": 95, "NO2": 31, "CO": 0.7},
        {"time": "2026-07-07 08:00:00", "O3": 83, "PM2.5": 58, "PM10": 112, "NO2": 32, "CO": 0.8},
        {"time": "2026-07-07 09:00:00", "O3": 84, "PM2.5": 68, "PM10": 123, "NO2": 34, "CO": 0.9},
    ]

    result = evaluate_alert_rules(rows)

    rule_ids = {item["rule_id"] for item in result["rule_hits"]}
    supporting_ids = {item["rule_id"] for item in result["supporting_rule_hits"]}
    assert result["has_alert"] is True
    assert result["target_pollutant"] == "PM2.5"
    assert "pm25_3h_rising" in rule_ids
    assert "pm10_3h_rising" in rule_ids
    assert "pm25_pm10_co_rising" in supporting_ids
    assert "pm25_co_combustion_clue" in supporting_ids


def test_no2_o3_inverse_pattern_is_supporting_only():
    rows = [
        {"time": "2026-07-07 06:00:00", "O3": 120, "PM2.5": 20, "PM10": 50, "NO2": 35, "CO": 0.6},
        {"time": "2026-07-07 07:00:00", "O3": 114, "PM2.5": 21, "PM10": 51, "NO2": 42, "CO": 0.6},
        {"time": "2026-07-07 08:00:00", "O3": 108, "PM2.5": 21, "PM10": 51, "NO2": 49, "CO": 0.6},
        {"time": "2026-07-07 09:00:00", "O3": 102, "PM2.5": 22, "PM10": 52, "NO2": 57, "CO": 0.6},
    ]

    result = evaluate_alert_rules(rows)

    assert result["has_alert"] is False
    assert result["status"] == "silent"
    assert result["supporting_rule_hits"][0]["rule_id"] == "no2_rise_o3_drop_titration_clue"


def test_stable_pollutants_remain_silent():
    rows = [
        {"time": "2026-07-07 06:00:00", "O3": 100, "PM2.5": 20, "PM10": 50, "NO2": 18, "CO": 0.6},
        {"time": "2026-07-07 07:00:00", "O3": 104, "PM2.5": 20, "PM10": 51, "NO2": 18, "CO": 0.6},
        {"time": "2026-07-07 08:00:00", "O3": 106, "PM2.5": 21, "PM10": 51, "NO2": 19, "CO": 0.6},
        {"time": "2026-07-07 09:00:00", "O3": 108, "PM2.5": 21, "PM10": 52, "NO2": 19, "CO": 0.6},
    ]

    result = evaluate_alert_rules(rows)

    assert result["has_alert"] is False
    assert result["status"] == "silent"
    assert result["rule_hits"] == []
    assert result["supporting_rule_hits"] == []


def test_latest_aqi_over_100_triggers_watch_alert():
    rows = [
        {"time": "2026-07-07 06:00:00", "AQI": 72, "O3": 100, "PM2.5": 20, "PM10": 50, "NO2": 18, "CO": 0.6},
        {"time": "2026-07-07 07:00:00", "AQI": 83, "O3": 104, "PM2.5": 20, "PM10": 51, "NO2": 18, "CO": 0.6},
        {"time": "2026-07-07 08:00:00", "AQI": 95, "O3": 106, "PM2.5": 21, "PM10": 51, "NO2": 19, "CO": 0.6},
        {"time": "2026-07-07 09:00:00", "AQI": 101, "O3": 108, "PM2.5": 21, "PM10": 52, "NO2": 19, "CO": 0.6},
    ]

    result = evaluate_alert_rules(rows)

    assert result["has_alert"] is True
    assert result["alert_type"] == "aqi_watch"
    assert result["target_pollutant"] == "AQI"
    assert result["rule_hits"][0]["rule_id"] == "aqi_hourly_over_100"


def test_write_latest_alert_creates_file(tmp_path):
    state = {
        "city": "运城市",
        "checked_at": "2026-07-07T09:00:00+08:00",
        "has_alert": False,
        "summary": "未发现需要推送的告警。",
        "rule_hits": [],
        "supporting_rule_hits": [],
        "status": "silent",
    }

    path = write_latest_alert(tmp_path, state)

    assert path == tmp_path / "scenarios" / "yuncheng_trial" / "latest_alert.json"
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "silent"


def test_fetch_target_city_hourly_rows_uses_city_table_only():
    calls = []

    class FakeClient:
        def query(self, **kwargs):
            calls.append(kwargs)
            return [
                {
                    "TimePoint": datetime(2026, 7, 7, 9),
                    "Area": "运城市",
                    "PM2_5": 22,
                    "PM10": 52,
                    "O3": 153,
                    "NO2": 19,
                    "SO2": 6,
                    "CO": 0.6,
                    "AQI": 80,
                    "PrimaryPollutant": "O3",
                    "Quality": "良",
                }
            ]

    rows = fetch_target_city_hourly_rows(
        city="运城市",
        end_time=datetime(2026, 7, 7, 9),
        hours=6,
        sql_client=FakeClient(),
    )

    assert calls[0]["cities"] == ["运城市"]
    assert calls[0]["table"] == "CityAQIPublishHistory"
    assert rows[0]["time"] == "2026-07-07 09:00:00"
    assert rows[0]["PM2.5"] == 22
