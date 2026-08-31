from datetime import datetime

import pytest

from app.scenarios.xuchang_station_deviation.service import (
    XuchangStationDeviationAlertService,
    StationDeviationConfig,
    detect_station_deviations,
)


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
    assert alert["peer_baseline_method"] == "leave_one_out_median"
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
