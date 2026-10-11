"""Tests for the Henan 18-city local ranking calculation (banker's rounding, non-official)."""

from datetime import datetime

import pytest

from app.fetchers.xuchang_henan_ranking_recalc import (
    CityCumulative,
    build_cumulative_ranking_rows,
    build_daily_ranking_rows,
    compute_rank,
    percentile_nearest_rank,
    round_half_even,
)


def _day(pm25=None, pm10=None, o3=None, no2=None, so2=None, co=None):
    return {
        "pm25": pm25, "pm10": pm10, "o3_8h": o3,
        "no2": no2, "so2": so2, "co": co,
    }


def test_round_half_even_bankers_rounding():
    # 四舍六入五成双：5 前奇数进位、5 前偶数舍去
    assert round_half_even(2.5, 0) == 2.0
    assert round_half_even(3.5, 0) == 4.0
    assert round_half_even(0.15, 1) == 0.2
    assert round_half_even(0.25, 1) == 0.2
    # 常规四舍六入
    assert round_half_even(22.93, 1) == 22.9
    assert round_half_even(22.96, 1) == 23.0
    assert round_half_even(41.5, 0) == 42.0
    assert round_half_even(None, 1) is None


def test_cumulative_applies_rounding_precision():
    agg = CityCumulative("许昌市", 210)
    # PM2.5 月均 = (40+43)/2 = 41.5 → 银行家修约一位小数 = 41.5（不变）
    agg.add_day(_day(pm25=40, pm10=78.5, o3=100, no2=25.4, so2=7.5, co=0.55))
    agg.add_day(_day(pm25=43, pm10=79.4, o3=110, no2=24.6, so2=8.4, co=0.61))
    metrics = agg.rounded_metrics()
    assert metrics["pm25"] == pytest.approx(41.5)  # 一位小数
    assert metrics["co"] == pytest.approx(0.6)  # (0.55+0.61)/2=0.58 → 0.6
    # PM10/SO2/NO2/O3 为整数
    assert metrics["pm10"] == float(79)  # (78.5+79.4)/2=78.95 → 79
    assert metrics["so2"] == float(8)  # 7.95 → 8
    assert metrics["no2"] == float(25)  # 25.0 → 25
    assert metrics["o3_8h"] == float(110)  # 90per=110 → 110


def test_percentile_nearest_rank():
    values = sorted([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert percentile_nearest_rank(values, 90) == 90
    assert percentile_nearest_rank(values, 95) == 100
    assert percentile_nearest_rank([], 90) is None


def test_compute_rank_ascending_with_ties():
    rows = [
        {"city": "甲市", "value": 20.0},
        {"city": "乙市", "value": 10.0},
        {"city": "丙市", "value": 10.0},
        {"city": "丁市", "value": 30.0},
    ]
    by_city = {row["city"]: row["rank"] for row in compute_rank(rows, key="value")}
    # 数值越低排名越靠前；相同值并列(standard competition: 1,1,3)
    assert by_city == {"乙市": 1, "丙市": 1, "甲市": 3, "丁市": 4}


def test_compute_rank_skips_null_values():
    rows = [
        {"city": "甲市", "value": None},
        {"city": "乙市", "value": 10.0},
    ]
    by_city = {row["city"]: row["rank"] for row in compute_rank(rows, key="value")}
    assert by_city == {"乙市": 1, "甲市": None}


def test_cumulative_ranking_based_on_rounded_values():
    aggs = {
        # 单日原值 → 修约：甲 59.6→60、乙 60.4→60（PM10 整数修约后并列第 1）
        "甲市": CityCumulative.from_days("甲市", 201, [_day(pm25=22.4, pm10=59.6, o3=100, no2=30, so2=10, co=1)]),
        "乙市": CityCumulative.from_days("乙市", 202, [_day(pm25=21.6, pm10=60.4, o3=100, no2=30, so2=10, co=1)]),
        "许昌市": CityCumulative.from_days("许昌市", 210, [_day(pm25=22.6, pm10=70, o3=120, no2=35, so2=12, co=1.2)]),
    }
    rows = build_cumulative_ranking_rows(
        "monthly", "2026-10", aggs, computed_at=datetime(2026, 10, 11, 6)
    )
    by_city = {row["city"]: row for row in rows}
    assert by_city["甲市"]["pm10"] == 60.0
    assert by_city["乙市"]["pm10"] == 60.0
    assert by_city["甲市"]["rank_pm10"] == 1
    assert by_city["乙市"]["rank_pm10"] == 1
    # PM2.5 一位小数：乙 21.6 < 甲 22.4 < 许昌 22.6，无并列
    assert by_city["乙市"]["rank_pm25"] == 1
    assert by_city["甲市"]["rank_pm25"] == 2
    assert by_city["许昌市"]["rank_pm25"] == 3
    assert by_city["许昌市"]["pm25"] == 22.6


def test_daily_ranking_keeps_official_values_unrounded():
    stats = {
        "许昌市": (210, _day(pm25=43, pm10=84, o3=120, no2=25, so2=8, co=0.5)),
        "济源市": (218, _day(pm25=38, pm10=78, o3=170, no2=24, so2=7, co=0.5)),
    }
    rows = build_daily_ranking_rows(
        "2026-10-09", stats, computed_at=datetime(2026, 10, 11, 6)
    )
    by_city = {row["city"]: row for row in rows}
    assert by_city["济源市"]["rank_pm25"] == 1
    assert by_city["许昌市"]["rank_pm25"] == 2
    assert by_city["许昌市"]["pm25"] == 43.0  # 官方原值不修约
