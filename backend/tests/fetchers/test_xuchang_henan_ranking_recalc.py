"""Tests for the Henan city ranking recalculation fetcher (SsfbCityDay -> SsfbCityRanking)."""

from datetime import date, datetime

import pytest

from app.fetchers.xuchang_henan_ranking_recalc import (
    AggregationResult,
    compute_rank,
    percentile_nearest_rank,
)


def _day(pm25=None, pm10=None, o3=None, no2=None, so2=None, co=None):
    return {
        "pm25": pm25, "pm10": pm10, "o3_8h": o3,
        "no2": no2, "so2": so2, "co": co,
    }


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


def test_aggregation_single_pollutant_cumulative_means():
    days = [
        _day(pm25=35, pm10=70, o3=160, no2=40, so2=60, co=4),
        _day(pm25=35, pm10=70, o3=160, no2=40, so2=60, co=4),
    ]
    result = AggregationResult.from_days("许昌市", 210, days)
    assert result.pm25 == pytest.approx(35.0)
    assert result.o3_8h_90 == pytest.approx(160.0)
    assert result.co_95 == pytest.approx(4.0)
    assert result.days == 2
    assert result.valid_days == 2


def test_aggregation_ignores_days_with_missing_pollutant_for_valid_days():
    days = [
        _day(pm25=35, pm10=70, o3=160, no2=40, so2=60, co=4),
        _day(pm25=35, pm10=70, o3=None, no2=40, so2=60, co=4),
    ]
    result = AggregationResult.from_days("许昌市", 210, days)
    assert result.days == 2
    assert result.valid_days == 1
    assert result.pm_valid_days == 2


def test_aggregation_empty_days_returns_none_metrics():
    result = AggregationResult.from_days("许昌市", 210, [])
    assert result.pm25 is None
    assert result.o3_8h_90 is None
    assert result.valid_days == 0


def test_rank_cities_assigns_all_metrics():
    from app.fetchers.xuchang_henan_ranking_recalc import build_ranking_rows

    stats = {
        "许昌市": (210, [
            _day(pm25=40, pm10=80, o3=150, no2=30, so2=10, co=1),
            _day(pm25=30, pm10=70, o3=140, no2=20, so2=9, co=0.8),
        ]),
        "济源市": (218, [
            _day(pm25=20, pm10=60, o3=120, no2=15, so2=5, co=0.6),
            _day(pm25=22, pm10=62, o3=130, no2=16, so2=6, co=0.7),
        ]),
    }
    rows = build_ranking_rows("monthly", "2026-10", stats, official={}, computed_at=datetime(2026, 10, 11, 6))
    by_city = {row["city"]: row for row in rows}
    # 济源各项浓度更低 → 排名 1（单项浓度排名，不做综合指数）
    assert by_city["济源市"]["rank_pm25"] == 1
    assert by_city["许昌市"]["rank_pm25"] == 2
    assert "rank_zong" not in by_city["济源市"]
    assert "zong" not in by_city["济源市"]
    assert by_city["济源市"]["period_type"] == "monthly"
    assert by_city["济源市"]["computed_at"] == datetime(2026, 10, 11, 6)


def test_ranking_maps_official_reference():
    from app.fetchers.xuchang_henan_ranking_recalc import build_ranking_rows

    stats = {"许昌市": (210, [_day(pm25=35, pm10=70, o3=160, no2=40, so2=60, co=4)])}
    rows = build_ranking_rows(
        "monthly", "2026-08", stats,
        official={"许昌": {"zong": 5.169, "rank": 10}},
        computed_at=datetime(2026, 10, 11, 6),
    )
    assert rows[0]["official_zong"] == 5.169
    assert rows[0]["official_rank"] == 10


def test_daily_ranking_period_is_iso_date():
    from app.fetchers.xuchang_henan_ranking_recalc import build_ranking_rows

    stats = {
        "许昌市": (210, [_day(pm25=43, pm10=84, o3=120, no2=25, so2=8, co=0.5)]),
        "济源市": (218, [_day(pm25=38, pm10=78, o3=170, no2=24, so2=7, co=0.5)]),
    }
    rows = build_ranking_rows(
        "daily", "2026-10-09", stats, official={}, computed_at=datetime(2026, 10, 11, 6)
    )
    assert len(rows) == 2
    assert {row["period_type"] for row in rows} == {"daily"}
    assert {row["period"] for row in rows} == {"2026-10-09"}
    by_city = {row["city"]: row for row in rows}
    # 单日单项浓度排名：济源 38 < 许昌 43 → 济源第 1
    assert by_city["济源市"]["rank_pm25"] == 1
    assert by_city["许昌市"]["rank_pm25"] == 2
