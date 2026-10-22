"""City-day report builder: schema gate, seven-section layout, screening gate."""

from __future__ import annotations

import json
from pathlib import Path

from app.scenarios.xuchang_city_exceedance.qmd_report import (
    build_city_day_qmd_report,
    write_city_day_qmd_report,
)

SCHEMA = "xuchang_station_daily_source_analysis/v3"


def _evidence() -> dict:
    return {
        "schema_version": SCHEMA,
        "analysis_id": "xuchang-daily-20260923-1003A-pm25",
        "target_date": "2026-09-23",
        "station_name": "市一中",
        "station_id": "1003A",
        "target_pollutant": "PM2.5",
        "generated_at": "2026-09-24T02:20:00+08:00",
        "daily_evaluation": {"value": 105.0, "limit": 75.0},
        "data_quality": {"meteorology_hours": 24},
        "city_day_statistics": {
            "status": "available",
            "pollutant": "PM2.5",
            "city_hourly": [
                {"time": "2026-09-23T02:00:00+08:00", "mean": 84.2, "peak": 105.0,
                 "min": 60.0, "station_count": 6},
            ],
            "district_hourly": [{"district": "建安区", "points": []}],
            "daypart": {
                "night_label": "0-8时", "afternoon_label": "12-17时",
                "night": {"city_mean": 84.2, "wind_speed_mean_ms": 0.19,
                          "humidity_mean": 97.0, "calm_hours": 9, "meteo_hours": 9,
                          "dominant_wind": {"status": "available",
                                            "direction_from_name": "南"}},
                "afternoon": {"city_mean": 46.2, "wind_speed_mean_ms": 0.82,
                              "humidity_mean": 48.0, "calm_hours": 0, "meteo_hours": 6,
                              "dominant_wind": {"status": "available",
                                                "direction_from_name": "东"}},
                "night_to_afternoon_ratio": 1.82,
                "calm_wind_definition": "风速<0.5 m/s",
            },
            "pollutant_correlation": {
                "fields": ["pm25", "co"], "labels": {"pm25": "PM2.5", "co": "CO"},
                "medians": {"pm25_co": 0.7},
            },
            "regional": [
                {"city": "郑州市", "daily_mean": 60.6, "peak": 76.0,
                 "peak_time": "2026-09-23T07:00:00+08:00", "night_mean": 73.3,
                 "afternoon_mean": 40.8, "night_to_afternoon_ratio": 1.8,
                 "correlation_with_target": 0.91},
            ],
            "township_daily_top": [
                {"station_id": "T1", "station_name": "马栏镇", "district": "鄢陵县",
                 "lat": 34.1, "lon": 114.1, "daily_mean": 92.0, "valid_hours": 24},
            ],
            "peak_township": {"station_id": "T1", "station_name": "马栏镇",
                              "district": "鄢陵县", "lat": 34.1, "lon": 114.1,
                              "daily_mean": 92.0},
            "coverage": {"national_stations": 6, "township_stations": 76,
                         "regional_cities": 6, "meteo_hours": 24},
        },
        "enterprise_screening": {"status": "screened", "enterprises": [
            {"enterprise_name": "测试化工", "industry_category": "石化与化工",
             "district": "建安区", "screening_score": 1774.5,
             "distance_to_high_value_km": 4.07, "in_upwind_sector": True},
        ]},
        "visualizations": [],
    }


def test_city_day_report_renders_seven_fixed_sections_and_boundaries():
    report = build_city_day_qmd_report(_evidence(), {"conclusion": "夜间重点巡查化工园区。"})

    for heading in ("## 一、分析摘要", "## 二、污染过程与多点小时变化", "## 三、气象扩散条件",
                    "## 四、本地排放与外来传输", "## 五、污染源类型指示",
                    "## 六、空间分布与嫌疑企业", "## 七、结论与建议"):
        assert heading in report
    assert 'title: "许昌市 2026-09-23 轻度污染溯源分析报告"' in report
    assert "数据时段：2026-09-23 00:00—23:00" in report
    assert "乡镇站" in report and "76" in report
    assert "测试化工" in report
    assert "筛查得分" in report and "不构成贡献率或责任认定" in report
    assert "夜间重点巡查化工园区。" in report
    assert "0-8时" in report and "12-17时" in report


def test_city_day_report_gates_unscreened_enterprises_and_missing_stats():
    evidence = _evidence()
    evidence["enterprise_screening"] = {"status": "not_run",
                                        "reason": "inventory_unavailable:KeyError",
                                        "enterprises": [
                                            {"enterprise_name": "不应出现企业"}]}
    evidence["city_day_statistics"] = {"status": "insufficient_data"}
    evidence["daily_evaluation"] = {"value": None}
    report = build_city_day_qmd_report(evidence, {})

    assert "不应出现企业" not in report
    assert "inventory_unavailable" in report
    assert "许昌市 2026-09-23 PM2.5超标污染溯源分析报告" in report
    assert "有效小时样本不足" in report


def test_city_day_report_references_visualizations_when_present(tmp_path: Path):
    evidence = _evidence()
    image = tmp_path / "x.png"
    image.write_bytes(b"png")
    evidence["visualizations"] = [
        {"role": "pollutant_correlation_heatmap", "path": str(image),
         "title": "相关性热力图", "chart_type": "image"},
    ]
    report = build_city_day_qmd_report(evidence, {})
    assert "![图6 污染物相关性热力图（Pearson 相关系数，逐站中位数）](assets/charts/x.png)" in report
    missing = build_city_day_qmd_report(_evidence(), {})
    assert "本次证据包未生成该图" in missing


def test_write_city_day_qmd_report_enforces_schema(tmp_path: Path):
    evidence = _evidence()
    evidence["schema_version"] = "xuchang_city_source_analysis/v1"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")

    import pytest

    with pytest.raises(ValueError, match="schema"):
        write_city_day_qmd_report(str(path), {}, str(tmp_path / "r.qmd"))

    evidence["schema_version"] = SCHEMA
    path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    result = write_city_day_qmd_report(str(path), {"conclusion": "结论。"},
                                       str(tmp_path / "r.qmd"))
    assert result["report_id"] == "xuchang-daily-20260923-1003A-pm25-report"
    assert "## 七、结论与建议" in (tmp_path / "r.qmd").read_text(encoding="utf-8")
