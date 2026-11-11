"""①月度特征分析证据组装纯函数与兜底通报单元测试。"""

from __future__ import annotations

from datetime import date

from app.scenarios.xuchang_monthly_review import evidence, notification
from app.scenarios.xuchang_monthly_review.evidence import (
    aggregate_city_month,
    build_rank168_section,
    month_bounds,
    normalize_province_month_rows,
    previous_month,
    same_month_last_year,
    summarize_inventory,
    summarize_month_episodes,
)


def test_previous_month_and_bounds():
    assert previous_month(date(2026, 11, 2)) == (2026, 10)
    assert previous_month(date(2026, 1, 2)) == (2025, 12)
    start, end = month_bounds(2026, 10)
    assert (start, end) == (date(2026, 10, 1), date(2026, 11, 1))
    _, end_dec = month_bounds(2026, 12)
    assert end_dec == date(2027, 1, 1)
    assert same_month_last_year(2026, 10) == (2025, 10)


def test_aggregate_city_month_ranks_and_means():
    rows = [
        {"city": "许昌市", "pm25": 90.0, "pm10": 150.0, "so2": 10.0, "no2": 30.0, "co": 1.0, "o3": 100.0},
        {"city": "许昌市", "pm25": 100.0, "pm10": 150.0, "so2": 12.0, "no2": 32.0, "co": 1.2, "o3": 110.0},
        {"city": "郑州市", "pm25": 70.0, "pm10": 120.0, "so2": 9.0, "no2": 28.0, "co": 0.9, "o3": 95.0},
        {"city": "郑州市", "pm25": None, "pm10": 130.0, "so2": 8.0, "no2": 26.0, "co": 0.8, "o3": 90.0},
    ]
    result = aggregate_city_month(rows)
    assert [item["city"] for item in result] == ["许昌市", "郑州市"]
    xuchang = result[0]
    assert xuchang["factors"]["PM25"]["mean"] == 95.0
    assert xuchang["factors"]["PM25"]["valid_days"] == 2
    assert xuchang["pm25_rank"] == 1
    zhengzhou = result[1]
    assert zhengzhou["factors"]["PM25"]["mean"] == 70.0
    assert zhengzhou["factors"]["PM25"]["valid_days"] == 1


def test_normalize_province_month_rows():
    records = [
        {"Level": "city", "Scope": "month", "DataMonth": "2026-10-01",
         "City": "许昌市", "PM25": 95.0, "PM25_YoY": -8.1, "PM10": 150.0,
         "CompositeIndex": 4.5, "GoodDays": 25},
        {"Level": "city", "Scope": "month", "DataMonth": "2026-10-01",
         "City": "郑州市", "PM25": 80.0, "PM25_YoY": -2.0, "PM10": 130.0,
         "CompositeIndex": 4.0, "GoodDays": 26},
        # 干扰行：区县级 / 累计口径 / 其他月份
        {"Level": "county", "Scope": "month", "DataMonth": "2026-10-01",
         "City": "许昌市", "RegionName": "魏都区", "PM25": 90.0},
        {"Level": "city", "Scope": "cum", "DataMonth": "2026-10-01", "City": "许昌市", "PM25": 80.0},
        {"Level": "city", "Scope": "month", "DataMonth": "2026-09-01", "City": "许昌市", "PM25": 70.0},
    ]
    section = normalize_province_month_rows(records, "2026-10")
    assert section["status"] == "available"
    assert section["city_count"] == 2
    assert section["xuchang"]["pm25_rank"] == 1
    assert section["xuchang"]["yoy"]["PM25"] == -8.1
    assert section["rows"][0]["city"] == "许昌市"


def test_normalize_province_month_rows_empty_when_not_published():
    section = normalize_province_month_rows([], "2026-10")
    assert section["status"] == "not_published"
    assert section["xuchang"] is None


def test_build_rank168_section():
    records = [
        {"City": "许昌市", "PeriodType": "monthly", "DataMonth": "2026-09-01",
         "CompositeIndexRank": 120, "Pm25Rank": 130, "Pm25": 40.0, "CompositeIndex": 4.1},
        {"City": "郑州市", "PeriodType": "monthly", "DataMonth": "2026-09-01",
         "CompositeIndexRank": 110, "Pm25Rank": 120, "Pm25": 38.0, "CompositeIndex": 4.0},
    ]
    section = build_rank168_section(records, "2026-10")
    # 目标月未发布 → 引用最新可得月份并标注
    assert section["status"] == "latest_only"
    assert section["latest_available_month"] == "2026-09"
    assert section["xuchang_latest"]["pm25_rank"] == 130

    section_ok = build_rank168_section(records, "2026-09")
    assert section_ok["status"] == "available"
    assert section_ok["xuchang_target"]["composite_index_rank"] == 120

    assert build_rank168_section([], "2026-10")["status"] == "unavailable"


def test_summarize_month_episodes_distribution():
    episodes = [
        {"station_name": "许昌学院", "target_pollutant": "PM10", "alert_type": "sudden_rise",
         "started_at": "2026-10-09T10:00:00", "peak_station_value": 200.0},
        {"station_name": "许昌学院", "target_pollutant": "PM10", "alert_type": "sudden_rise",
         "started_at": "2026-10-10T11:00:00", "peak_station_value": 210.0},
        {"station_name": "开发区", "target_pollutant": "SO2", "alert_type": "spatial_outlier",
         "started_at": "2026-10-11T12:00:00", "peak_station_value": 150.0},
    ]
    summary = summarize_month_episodes(episodes)
    assert summary["episode_count"] == 3
    assert summary["station_count"] == 2
    assert summary["by_station"][0] == {"name": "许昌学院", "count": 2}
    assert summary["by_pollutant"][0] == {"name": "PM10", "count": 2}
    assert summary["peak_episode"]["peak_value"] == 210.0
    assert [row["date"] for row in summary["by_day"]] == [
        "2026-10-09", "2026-10-10", "2026-10-11"
    ]


def test_summarize_inventory_static_context():
    dataset = [
        {"enterprise_name": "企业A", "district": "魏都区",
         "inventory_sectors": ["工业涂装", "铸造"],
         "inventory_emissions": {"emission_pm25": 12.5, "emission_so2": 3.0}},
        {"enterprise_name": "企业B", "district": "建安区",
         "inventory_sectors": ["工业涂装"],
         "inventory_emissions": {"emission_pm25": 7.5}},
        {"enterprise_name": "", "district": "魏都区"},
    ]
    summary = summarize_inventory(dataset)
    assert summary["status"] == "available"
    assert summary["enterprise_count"] == 2
    assert summary["top_districts"][0] == {"name": "魏都区", "count": 1}
    assert {"name": "工业涂装", "count": 2} in summary["top_sectors"]
    assert summary["annual_emission_totals"]["emission_pm25"] == 20.0


def test_compose_fallback_message_contains_sections_and_calibers():
    evidence = {
        "month": "2026-10",
        "city_comparison": {
            "official": {
                "status": "available", "city_count": 19,
                "xuchang": {"pm25_rank": 3, "factors": {"PM25": 95.0, "PM10": 150.0},
                            "yoy": {"PM25": -8.1}},
                "rows": [],
            },
            "realtime": {"city_count": 18, "xuchang": {"pm25_rank": 1}, "rows": []},
        },
        "rank168": {"xuchang_target": None, "xuchang_latest": {
            "composite_index_rank": 120, "pm25_rank": 130}, "latest_available_month": "2026-09"},
        "meteorology": {"temperature": {"mean": 18.5}, "relative_humidity": {"mean": 70},
                        "wind_speed": {"mean": 2.3}, "precipitation_sum": 12.0,
                        "boundary_layer_height": {"mean": 900}},
        "meteorology_last_year": {},
        "station_alerts": {"episode_count": 5, "station_count": 3,
                           "by_station": [{"name": "许昌学院", "count": 3}],
                           "peak_episode": {"station": "许昌学院", "peak_value": 210.0}},
        "enterprise_context": {"status": "available", "enterprise_count": 2305,
                               "top_districts": [{"name": "魏都区", "count": 400}]},
    }
    message = notification.compose_fallback_message(evidence)
    assert message.startswith("【月度特征分析】")
    for section in ("一、全市浓度概况", "二、地市对比与排名", "三、气象因素",
                    "四、站点告警情况", "五、企业排放背景", "六、说明"):
        assert section in message
    assert "第3位" in message
    assert "120" in message  # 168 城综合指数排名
    assert "5个" in message
    assert "2305" in message
    assert "不认定" in message


def test_compose_fallback_message_realtime_caliber_noted():
    evidence = {
        "month": "2026-10",
        "city_comparison": {
            "official": {"status": "not_published", "xuchang": None, "rows": []},
            "realtime": {"city_count": 18, "xuchang": {"pm25_rank": 1}, "rows": []},
        },
        "rank168": {},
        "meteorology": {},
        "station_alerts": {"episode_count": 0},
        "enterprise_context": {"status": "unavailable"},
    }
    message = notification.compose_fallback_message(evidence)
    assert "实时参考口径" in message
    assert "无站点快速告警记录" in message
    assert "气象观测数据暂缺" in message


def test_aggregate_weather_month_stats():
    observed = [
        {"temperature_2m": 20.0, "relative_humidity_2m": 60.0,
         "wind_speed_10m_ms": 2.0, "precipitation": 1.0},
        {"temperature_2m": 22.0, "relative_humidity_2m": 80.0,
         "wind_speed_10m_ms": 4.0, "precipitation": 0.5},
        {"temperature_2m": None, "relative_humidity_2m": 70.0,
         "wind_speed_10m_ms": 3.0, "precipitation": 0.0},
    ]
    era5 = [{"boundary_layer_height": 800.0}, {"boundary_layer_height": 1000.0}]
    summary = evidence.aggregate_weather_month(observed, era5)
    assert summary["temperature"]["mean"] == 21.0
    assert summary["temperature"]["valid_hours"] == 2
    assert summary["relative_humidity"]["mean"] == 70.0
    assert summary["precipitation_sum"] == 1.5
    assert summary["boundary_layer_height"]["mean"] == 900.0
