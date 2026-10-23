"""XuchangZhongdaCityFetcher 查询窗口回归测试。

背景：2026-09 起平台审核后城市小时数据可查前沿滞后约 2 天（此前 <1 天）。
窗口若只回看 1 天，每天仅 D-1 00:00 边界点已过审核，导致库里每天只落
1 条。窗口必须覆盖足够长的历史（3 天前 00:00 起），让迟到的小时数据在
后续轮次被 upsert 补齐。
"""

from datetime import datetime, timedelta

from app.fetchers.xuchang_zhongda_station import (
    XuchangZhongdaCityFetcher,
    XuchangZhongdaStationFetcher,
    plan_for_date,
    split_window_by_plan,
)


def test_city_hour_window_looks_back_three_days():
    fetcher = XuchangZhongdaCityFetcher()
    start, end = fetcher._window(datetime(2026, 10, 9, 15, 21))
    assert start == datetime(2026, 10, 6, 0, 0)
    assert end == datetime(2026, 10, 9, 16, 0)


def test_city_hour_window_backfills_across_audit_lag():
    # 审核前沿滞后 ~2 天时，昨天同一时刻起算的窗口必须仍能覆盖
    # D-3 的小时数据（正是此前每天丢 23 条的故障窗口）。
    fetcher = XuchangZhongdaCityFetcher()
    start, end = fetcher._window(datetime(2026, 10, 9, 15, 21))
    assert start <= datetime(2026, 10, 8, 0, 0) - timedelta(days=1)


def test_station_hour_window_keeps_26h_backfill():
    fetcher = XuchangZhongdaStationFetcher(data_kind="hour")
    start, end = fetcher._window(datetime(2026, 10, 9, 15, 10))
    assert start == datetime(2026, 10, 8, 13, 0)
    assert end == datetime(2026, 10, 9, 15, 0)


def test_plan_period_split_across_boundary():
    plans = {
        plan
        for plan, _, _ in split_window_by_plan(
            datetime(2025, 12, 30, 0), datetime(2026, 1, 2, 0)
        )
    }
    assert plans == {"145th", "155th"}
    assert plan_for_date(datetime(2026, 10, 9)) == "155th"
    assert plan_for_date(datetime(2025, 12, 31)) == "145th"
