"""Tests for the Henan 18-city daily ranking (official day values, no aggregation)."""

from datetime import datetime

from app.fetchers.xuchang_henan_ranking_recalc import (
    _fill_pm10_from_hours,
    build_daily_ranking_rows,
    compute_rank,
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
    assert all(row["period_type"] == "daily" for row in rows)


def test_fill_pm10_from_hours_only_fills_missing():
    from datetime import date

    day_rows = [
        {"city": "许昌市", "data_time": datetime(2026, 10, 9), "pm10": None},
        {"city": "济源市", "data_time": datetime(2026, 10, 9), "pm10": 78.0},
    ]
    filled = _fill_pm10_from_hours(
        day_rows, {("许昌市", date(2026, 10, 9)): 84.0}
    )
    assert filled == 1
    assert day_rows[0]["pm10"] == 84.0
    assert day_rows[1]["pm10"] == 78.0
