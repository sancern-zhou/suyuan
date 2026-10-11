"""Tests for the Henan daily city ranking fetcher (official values only, no aggregation)."""

from datetime import datetime

import pytest

from app.fetchers.xuchang_henan_ranking_recalc import (
    compute_rank,
    build_ranking_rows,
)


def _day(pm25=None, pm10=None, o3=None, no2=None, so2=None, co=None):
    return {
        "pm25": pm25, "pm10": pm10, "o3_8h": o3,
        "no2": no2, "so2": so2, "co": co,
    }


def test_compute_rank_ascending_with_ties():
    rows = [
        {"city": "甲市", "value": 20.0},
        {"city": "乙市", "value": 10.0},
        {"city": "丙市", "value": 10.0},
        {"city": "丁市", "value": 30.0},
    ]
    ranks = compute_rank(rows, key="value")
    by_city = {row["city"]: row["rank"] for row in ranks}
    # 数值越低排名越靠前；相同值并列(standard competition: 1,1,3)
    assert by_city == {"乙市": 1, "丙市": 1, "甲市": 3, "丁市": 4}


def test_compute_rank_skips_null_values():
    rows = [
        {"city": "甲市", "value": None},
        {"city": "乙市", "value": 10.0},
    ]
    ranks = compute_rank(rows, key="value")
    by_city = {row["city"]: row["rank"] for row in ranks}
    assert by_city == {"乙市": 1, "甲市": None}


def test_daily_ranking_sorts_official_values_without_aggregation():
    """单日排名仅对官方发布日值排序；period 为日期；无聚合统计字段。"""
    stats = {
        "许昌市": (210, _day(pm25=43, pm10=84, o3=120, no2=25, so2=8, co=0.5)),
        "济源市": (218, _day(pm25=38, pm10=78, o3=170, no2=24, so2=7, co=0.5)),
    }
    rows = build_ranking_rows(
        "2026-10-09", stats, computed_at=datetime(2026, 10, 11, 6)
    )
    assert len(rows) == 2
    assert {row["period_type"] for row in rows} == {"daily"}
    assert {row["period"] for row in rows} == {"2026-10-09"}
    by_city = {row["city"]: row for row in rows}
    assert by_city["济源市"]["rank_pm25"] == 1
    assert by_city["许昌市"]["rank_pm25"] == 2
    # 值为官方发布原值（未做任何聚合变换）
    assert by_city["许昌市"]["pm25"] == 43.0
    forbidden = {"zong", "o3_8h_90", "co_95", "valid_days",
                 "official_zong", "official_rank"}
    assert forbidden.isdisjoint(by_city["济源市"])


def test_missing_pollutant_value_excluded_from_its_rank():
    stats = {
        "许昌市": (210, _day(pm25=43, pm10=None, o3=120, no2=25, so2=8, co=0.5)),
        "济源市": (218, _day(pm25=38, pm10=78, o3=170, no2=24, so2=7, co=0.5)),
    }
    rows = build_ranking_rows(
        "2026-10-09", stats, computed_at=datetime(2026, 10, 11, 6)
    )
    by_city = {row["city"]: row for row in rows}
    # 许昌 PM10 缺失 → 不参与 PM10 排名（不做补齐/估算）
    assert by_city["许昌市"]["rank_pm10"] is None
    assert by_city["济源市"]["rank_pm10"] == 1
    # PM2.5 排名不受影响
    assert by_city["济源市"]["rank_pm25"] == 1
    assert by_city["许昌市"]["rank_pm25"] == 2
