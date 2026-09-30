"""Report chart rendering smoke tests (Agg backend, deterministic fixtures)."""

from __future__ import annotations

from pathlib import Path

from app.scenarios.xuchang_city_exceedance.process_stats import compute_city_day_statistics
from app.scenarios.xuchang_city_exceedance.report_charts import generate_city_report_charts


def _national_hourly() -> list[dict]:
    return [
        {
            "station_id": "1003A", "name": "市一中", "lat": 34.03, "lon": 113.85,
            "data_time": f"2026-09-23T{hour:02d}:00:00+08:00",
            "pm25": 80.0 + hour % 6, "pm10": 95.0, "o3": 70.0,
            "no2": 40.0 + hour % 3, "so2": 9.0, "co": 0.8,
        }
        for hour in range(24)
    ]


def _township_hourly() -> list[dict]:
    return [
        {
            "station_id": "T1", "name": "马栏镇", "district": "鄢陵县",
            "lat": 34.1, "lon": 114.1,
            "data_time": f"2026-09-23T{hour:02d}:00:00+08:00",
            "pm25": 85.0 + hour % 4, "pm10": 100.0, "o3": 65.0,
        }
        for hour in range(24)
    ]


def _regional_hourly() -> list[dict]:
    return [
        {
            "station_id": "郑州市", "name": "郑州市",
            "data_time": f"2026-09-23T{hour:02d}:00:00+08:00",
            "pm25": 70.0 + hour % 5, "pm10": 90.0, "o3": 60.0,
        }
        for hour in range(24)
    ]


def _meteo_rows() -> list[dict]:
    return [
        {
            "time": f"2026-09-23T{hour:02d}:00:00+08:00",
            "relative_humidity_2m": 95.0 if hour < 9 else 50.0,
            "wind_speed_10m_ms": 0.3 if hour < 9 else 2.5,
            "wind_direction_10m": 175.0,
        }
        for hour in range(24)
    ]


def test_generate_city_report_charts_renders_all_template_roles(tmp_path: Path):
    national = _national_hourly()
    stats = compute_city_day_statistics(
        national, _township_hourly(), _regional_hourly(), _meteo_rows(),
        pollutant="PM2.5")
    artifacts = generate_city_report_charts(
        output_dir=tmp_path, job_id="job-1", pollutant="PM2.5",
        national_hourly=national, city_day_statistics=stats,
        meteorology_rows=_meteo_rows(), regional_hourly=_regional_hourly(),
        enterprise_screening={"enterprises": [
            {"enterprise_name": "测试化工", "industry_category": "石化与化工",
             "screening_score": 1774.5, "distance_km": 4.07,
             "distance_to_high_value_km": 4.07},
        ]})

    roles = {item["role"] for item in artifacts}
    assert roles == {
        "national_station_hourly_curves", "urban_district_hourly_comparison",
        "meteorology_hourly_panel", "regional_city_hourly_comparison",
        "regional_city_daypart_comparison", "pollutant_correlation_heatmap",
        "township_daily_spatial_distribution", "enterprise_screening_top10",
    }
    assert all(Path(item["path"]).exists() and Path(item["path"]).stat().st_size > 0
               for item in artifacts)
    assert all(item["path"].startswith(str(tmp_path)) for item in artifacts)


def test_generate_city_report_charts_survives_empty_evidence(tmp_path: Path):
    artifacts = generate_city_report_charts(
        output_dir=tmp_path, job_id="job-2", pollutant="PM2.5",
        national_hourly=[], city_day_statistics={}, meteorology_rows=[],
        regional_hourly=[], enterprise_screening={"enterprises": []})
    assert artifacts == []
