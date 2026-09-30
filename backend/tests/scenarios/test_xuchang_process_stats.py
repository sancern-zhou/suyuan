"""Deterministic city-day statistics for the exceedance report."""

from __future__ import annotations

from datetime import datetime

from app.scenarios.xuchang_city_exceedance.process_stats import (
    city_hourly_curve,
    compute_city_day_statistics,
    daypart_assessment,
    district_hourly_curves,
    pearson,
    pollutant_correlation,
    regional_city_comparison,
    township_daily_summary,
)


def _national_hour(nation: str, hour: int, *, pm25=80.0, co=0.8, no2=40.0,
                   so2=9.0, o3=60.0, pm10=95.0) -> dict:
    return {
        "station_id": nation, "name": nation,
        "data_time": f"2026-09-23T{hour:02d}:00:00+08:00",
        "pm25": pm25, "pm10": pm10, "o3": o3, "no2": no2, "so2": so2, "co": co,
    }


def _meteo(hour: int, *, speed=0.3, rh=95.0, direction=175.0) -> dict:
    return {"time": f"2026-09-23T{hour:02d}:00:00+08:00",
            "wind_speed_10m_ms": speed, "relative_humidity_2m": rh,
            "wind_direction_10m": direction}


def test_pearson_requires_enough_pairs_and_detects_perfect_linear():
    pairs = [(float(index), 2.0 * index + 1) for index in range(12)]
    assert pearson(pairs) == 1.0
    assert pearson(pairs[:4]) is None


def test_city_hourly_curve_aggregates_across_stations():
    rows = [_national_hour("A", 2, pm25=80.0), _national_hour("B", 2, pm25=90.0),
            _national_hour("A", 3, pm25=70.0)]
    curve = city_hourly_curve(rows, "pm25")
    assert curve[0]["mean"] == 85.0
    assert curve[0]["peak"] == 90.0
    assert curve[0]["station_count"] == 2
    assert curve[1]["time"] == datetime.fromisoformat("2026-09-23T03:00:00+08:00").isoformat()


def test_daypoint_assessment_night_calm_and_humidity():
    curve = [{"time": f"2026-09-23T{hour:02d}:00:00+08:00", "mean": 80.0 + hour}
             for hour in range(24)]
    meteo = [_meteo(hour, speed=0.3 if hour < 9 else 2.5,
                    rh=95.0 if hour < 9 else 50.0) for hour in range(24)]
    result = daypart_assessment(curve, meteo)
    assert result["night"]["city_mean"] == 84.0
    assert result["afternoon"]["city_mean"] == 94.5
    assert result["night"]["calm_hours"] == 9
    assert result["night"]["dominant_wind"]["direction_from_name"] == "南"
    assert result["night"]["humidity_mean"] == 95.0
    assert result["afternoon"]["calm_hours"] == 0


def test_district_curves_group_by_district_and_skip_missing():
    rows = [
        {"station_id": "T1", "district": "建安区", "data_time": "2026-09-23T02:00:00+08:00", "pm25": 70.0},
        {"station_id": "T2", "district": "建安区", "data_time": "2026-09-23T02:00:00+08:00", "pm25": 90.0},
        {"station_id": "T3", "district": "鄢陵县", "data_time": "2026-09-23T02:00:00+08:00", "pm25": None},
    ]
    curves = district_hourly_curves(rows, "pm25")
    assert {item["district"] for item in curves} == {"建安区"}
    assert curves[0]["points"][0]["mean"] == 80.0


def test_pollutant_correlation_median_across_stations():
    rows = []
    for station in ("A", "B"):
        for hour in range(20):
            rows.append(_national_hour(station, hour, pm25=50.0 + hour, co=0.5 + hour / 100))
    result = pollutant_correlation(rows)
    assert result["station_count"] == 2
    assert result["medians"]["pm25_co"] == 1.0


def test_regional_comparison_reports_night_afternoon_and_correlation():
    target = [{"time": f"2026-09-23T{hour:02d}:00:00+08:00", "mean": 60.0 + hour}
              for hour in range(24)]
    regional = [{"name": "郑州市", "data_time": f"2026-09-23T{hour:02d}:00:00+08:00",
                 "pm25": 50.0 + hour} for hour in range(24)]
    result = regional_city_comparison(regional, target)
    row = result[0]
    assert row["city"] == "郑州市"
    assert row["correlation_with_target"] == 1.0
    assert row["night_mean"] == 54.0
    assert row["afternoon_mean"] == 64.5
    assert row["peak_time"] == datetime.fromisoformat("2026-09-23T23:00:00+08:00").isoformat()


def test_township_summary_orders_by_daily_mean():
    rows = [
        {"station_id": "T1", "name": "甲镇", "district": "建安区", "pm25": 70.0,
         "data_time": "2026-09-23T01:00:00+08:00", "lat": 34.0, "lon": 113.8},
        {"station_id": "T2", "name": "乙镇", "district": "鄢陵县", "pm25": 90.0,
         "data_time": "2026-09-23T01:00:00+08:00", "lat": 34.1, "lon": 114.0},
    ]
    summary = township_daily_summary(rows, "pm25")
    assert summary[0]["station_name"] == "乙镇"
    assert summary[0]["daily_mean"] == 90.0


def test_compute_city_day_statistics_end_to_end():
    national = [_national_hour("A", hour, pm25=80.0 + hour) for hour in range(24)]
    township = [{"station_id": "T1", "name": "甲镇", "district": "建安区",
                 "data_time": f"2026-09-23T{hour:02d}:00:00+08:00",
                 "pm25": 85.0, "lat": 34.0, "lon": 113.8} for hour in range(24)]
    regional = [{"name": "郑州市", "data_time": f"2026-09-23T{hour:02d}:00:00+08:00",
                 "pm25": 60.0 + hour} for hour in range(24)]
    meteo = [_meteo(hour) for hour in range(24)]
    stats = compute_city_day_statistics(national, township, regional, meteo, pollutant="PM2.5")

    assert stats["status"] == "available"
    assert stats["peak_township"]["station_name"] == "甲镇"
    assert stats["coverage"] == {"national_stations": 1, "township_stations": 1,
                                 "regional_cities": 1, "meteo_hours": 24}
    assert stats["regional"][0]["correlation_with_target"] == 1.0
    assert compute_city_day_statistics(national, township, regional, meteo,
                                       pollutant="AQI")["status"] == "unsupported_pollutant"
