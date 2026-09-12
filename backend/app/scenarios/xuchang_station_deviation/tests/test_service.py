from datetime import datetime

import pytest

from app.scenarios.xuchang_station_deviation.service import (
    XuchangStationDeviationAlertService,
    StationDeviationConfig,
    air_quality_level_from_aqi,
    detect_station_deviations,
    evaluate_adverse_meteorology,
)


def test_aqi_is_mapped_to_dynamic_threshold_level():
    assert air_quality_level_from_aqi(50) == "优"
    assert air_quality_level_from_aqi(100) == "良"
    assert air_quality_level_from_aqi(150) == "轻度污染"
    assert air_quality_level_from_aqi(999) == "严重污染"
    assert air_quality_level_from_aqi(None) is None


def test_adverse_meteorology_lowers_sensitivity_without_humidity_only_trigger():
    decision = evaluate_adverse_meteorology({"wind_speed": 1.2, "stability": "stable", "humidity": 70})
    assert decision["adverse"] is True
    assert decision["sensitivity"] == 0.75
    humid_only = evaluate_adverse_meteorology({"wind_speed": 3, "stability": "neutral", "humidity": 85})
    assert humid_only["adverse"] is False
    assert "高湿辅助" in humid_only["reasons"]


def _row(station_id: str, value: float) -> dict:
    return {
        "station_id": station_id,
        "name": station_id,
        "lat": 34.0,
        "lon": 113.0,
        "pm25": value,
        "pm10": value,
        "o3": value,
        "no2": value,
        "so2": value,
        "co": value,
        "data_time": datetime(2026, 8, 4, 8),
    }


def test_detects_leave_one_out_station_deviation():
    result = detect_station_deviations(
        [_row("a", 100), _row("b", 40), _row("c", 40)],
        expected_station_count=3,
        config=StationDeviationConfig(pollutants=("PM2.5",)),
    )

    assert len(result["alerts"]) == 1
    alert = result["alerts"][0]
    assert alert["station_id"] == "a"
    assert alert["peer_mean"] == 40.0
    assert alert["peer_baseline_method"] == "leave_one_out_mean"
    assert alert["absolute_delta"] == 60.0
    assert alert["deviation_ratio"] == 1.5


def test_does_not_check_when_coverage_is_below_required_rate():
    result = detect_station_deviations(
        [_row("a", 100), _row("b", 40), _row("c", 40)],
        expected_station_count=4,
        config=StationDeviationConfig(pollutants=("PM2.5",)),
    )

    assert result["alerts"] == []
    assert result["checks"][0]["status"] == "insufficient_data_rate"


def test_relative_spike_below_absolute_delta_does_not_alert():
    result = detect_station_deviations(
        [_row("a", 5), _row("b", 2), _row("c", 2)],
        expected_station_count=3,
        config=StationDeviationConfig(pollutants=("PM2.5",)),
    )

    assert result["alerts"] == []


def test_coverage_is_checked_per_pollutant():
    rows = [_row("a", 100), _row("b", 40), _row("c", 40), _row("d", 40)]
    rows[-1]["pm25"] = -99

    result = detect_station_deviations(
        rows,
        expected_station_count=4,
        config=StationDeviationConfig(pollutants=("PM2.5",)),
    )

    assert result["alerts"] == []
    assert result["checks"][0]["available_station_count"] == 3
    assert result["checks"][0]["status"] == "insufficient_data_rate"


def test_one_pollutant_event_keeps_primary_and_secondary_stations():
    result = detect_station_deviations(
        [_row("a", 100), _row("b", 90), _row("c", 10), _row("d", 10)],
        expected_station_count=4,
        config=StationDeviationConfig(pollutants=("PM2.5",)),
    )

    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["station_id"] == "a"
    assert [item["station_id"] for item in result["alerts"][0]["secondary_stations"]] == ["b"]


def test_nox_uses_no2_as_an_explicit_proxy():
    rows = [_row("a", 100), _row("b", 40), _row("c", 40)]
    for row in rows:
        row["data_source"] = "minute"
    result = detect_station_deviations(
        rows,
        expected_station_count=3,
        expected_station_counts={"minute": 3},
        config=StationDeviationConfig(pollutants=("NOX",)),
    )

    alert = result["alerts"][0]
    assert alert["target_pollutant"] == "NOX"
    assert alert["observed_indicator"] == "NO2"
    assert "代理" in alert["nox_proxy_note"]


def test_minute_rows_are_grouped_in_five_minute_slots():
    rows = [_row("a", 100), _row("b", 40), _row("c", 40)]
    for row in rows:
        row["data_source"] = "minute"
        row["data_time"] = datetime(2026, 8, 4, 8, 7)
    result = detect_station_deviations(
        rows,
        expected_station_count=3,
        expected_station_counts={"minute": 3},
        config=StationDeviationConfig(pollutants=("O3",)),
    )

    assert result["alerts"][0]["occurred_at"].endswith("08:05:00+08:00")


def test_marked_minute_value_is_exempt_from_alert_calculation():
    rows = [_row("a", 100), _row("b", 40), _row("c", 40)]
    for row in rows:
        row["data_source"] = "minute"
        row["data_time"] = datetime(2026, 8, 4, 8, 5)
    rows[0]["o3_mark"] = "质控"
    result = detect_station_deviations(
        rows,
        expected_station_count=3,
        expected_station_counts={"minute": 3},
        config=StationDeviationConfig(pollutants=("O3",)),
    )

    assert result["alerts"] == []
    assert result["checks"][0]["available_station_count"] == 2


@pytest.mark.asyncio
async def test_run_attaches_daily_pollution_source_features(tmp_path):
    rows = [
        {**_row("a", 40), "data_source": "hour", "data_time": datetime(2026, 8, 4, 7),
         "pm10": 50, "so2": 2, "no2": 10, "co": 0.3},
        {**_row("b", 10), "data_source": "hour", "data_time": datetime(2026, 8, 4, 7),
         "pm10": 20, "so2": 2, "no2": 10, "co": 0.3},
        {**_row("c", 10), "data_source": "hour", "data_time": datetime(2026, 8, 4, 7),
         "pm10": 20, "so2": 2, "no2": 10, "co": 0.3},
        {**_row("a", 100), "data_source": "hour", "data_time": datetime(2026, 8, 4, 7),
         "pm10": 120, "so2": 2, "no2": 10, "co": 0.3},
        {**_row("a", 100), "data_source": "minute", "data_time": datetime(2026, 8, 4, 8, 5),
         "pm10": 120, "so2": 2, "no2": 10, "co": 0.3},
    ]
    service = XuchangStationDeviationAlertService(output_root=tmp_path)
    service.load_station_rows = lambda timestamp: (rows, {"hour": 3, "minute": 3})

    result = await service.run(datetime(2026, 8, 4, 8, 6))

    alert = next(item for item in result["alerts"] if item["station_id"] == "a")
    features = alert["pollutant_source_features"]
    assert features["status"] == "calculated"
    assert features["sample_count"] == 3
    assert "classification" in features
    assert "minute pollutants" in features["granularity"]


def _alert(station_id: str, pollutant: str) -> dict:
    return {
        "event_id": f"test-{station_id}-{pollutant.lower().replace('.', '')}",
        "station_id": station_id,
        "station_name": station_id,
        "target_pollutant": pollutant,
        "occurred_at": "2026-09-12T21:35:00+08:00",
    }


def test_no2_nox_pair_does_not_trigger_multifactor_table(tmp_path):
    service = XuchangStationDeviationAlertService(output_root=tmp_path)
    rows = [_row("a", 100), _row("b", 40), _row("c", 40)]

    assert service.write_multifactor_table(
        [_alert("a", "NO2"), _alert("a", "NOX")], rows) is None


def test_distinct_pollutants_still_trigger_multifactor_table(tmp_path):
    service = XuchangStationDeviationAlertService(output_root=tmp_path)
    rows = [
        {**_row("a", 41), "data_source": "hour", "data_time": datetime(2026, 9, 12, 20)},
        {**_row("a", 40), "data_source": "minute", "data_time": datetime(2026, 9, 12, 21, 35)},
        {**_row("b", 40), "data_source": "minute", "data_time": datetime(2026, 9, 12, 21, 35)},
        {**_row("c", 40), "data_source": "minute", "data_time": datetime(2026, 9, 12, 21, 35)},
    ]

    path = service.write_multifactor_table(
        [_alert("a", "NO2"), _alert("a", "SO2")], rows)

    assert path is not None and path.exists()


def test_multifactor_snapshot_pins_values_to_alert_slot():
    rows = [
        # 21:30 旧槽的 SO2 不应回退到告警槽 21:35 的表格里。
        {**_row("a", 40), "data_source": "minute", "data_time": datetime(2026, 9, 12, 21, 30),
         "so2": 5, "no2": 80},
        # 告警槽内 SO2 与 PM2.5 无效（负值），NO2 正常。
        {**_row("a", 40), "data_source": "minute", "data_time": datetime(2026, 9, 12, 21, 35),
         "so2": -99, "pm25": -99, "no2": 100},
        # PM2.5 只有小时源，取上一完整小时。
        {**_row("a", 41), "data_source": "hour", "data_time": datetime(2026, 9, 12, 20)},
    ]

    snapshot = XuchangStationDeviationAlertService._multifactor_snapshot(
        [_alert("a", "NO2"), _alert("a", "SO2")], rows)

    slot_key, station_ids, names, latest, marked = snapshot
    assert slot_key == datetime(2026, 9, 12, 21, 35)
    assert "SO2" not in latest["a"]
    assert latest["a"]["NO2"] == (datetime(2026, 9, 12, 21, 35), 100.0)
    assert latest["a"]["PM2.5"] == (datetime(2026, 9, 12, 20), 41.0)


def test_multifactor_snapshot_prefers_slot_pm25_over_previous_hour():
    rows = [
        {**_row("a", 41), "data_source": "hour", "data_time": datetime(2026, 9, 12, 20)},
        {**_row("a", 52), "data_source": "minute", "data_time": datetime(2026, 9, 12, 21, 35)},
    ]

    _, _, _, latest, _ = XuchangStationDeviationAlertService._multifactor_snapshot(
        [_alert("a", "NO2"), _alert("a", "SO2")], rows)

    assert latest["a"]["PM2.5"] == (datetime(2026, 9, 12, 21, 35), 52.0)


@pytest.mark.asyncio
async def test_run_no2_nox_episode_has_no_multifactor_table(tmp_path):
    rows = []
    for sid, no2_value in (("a", 100), ("b", 40), ("c", 40)):
        row = {**_row(sid, 40), "data_source": "minute", "data_time": datetime(2026, 9, 12, 21, 35)}
        row["no2"] = no2_value
        rows.append(row)
    service = XuchangStationDeviationAlertService(output_root=tmp_path)
    service.load_station_rows = lambda timestamp: (rows, {"hour": 3, "minute": 3})

    result = await service.run(datetime(2026, 9, 12, 21, 36))

    pollutants = {a["target_pollutant"] for a in result["alerts"] if a["station_id"] == "a"}
    assert pollutants == {"NO2", "NOX"}
    assert all("multifactor_table_path" not in a for a in result["alerts"])
