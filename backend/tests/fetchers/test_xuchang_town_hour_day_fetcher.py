"""乡镇站小时/日抓取器单元测试（许昌市空气质量管控平台替代源，回写 TownStationData 原表）。"""

from datetime import datetime

from app.fetchers.xuchang_town_hour_day import (
    XuchangTownAirDataFetcher,
    iaqi_legacy,
    record_from_row,
    records_from_rows,
)

# 历史行实测值（TownStationData 2026-10-15~20 原始行，逐因子核验旧 HJ633 折点）


def test_iaqi_legacy_hourly_matches_historical_rows():
    assert iaqi_legacy("so2", 9.3, daily=False) == 3
    assert iaqi_legacy("so2", 11.3, daily=False) == 4
    assert iaqi_legacy("no2", 31.5, daily=False) == 16
    assert iaqi_legacy("co", 0.42, daily=False) == 4
    assert iaqi_legacy("o3", 44.2, daily=False) == 14
    assert iaqi_legacy("pm10", 36.4, daily=False) == 36
    assert iaqi_legacy("pm25", 23.6, daily=False) == 34
    assert iaqi_legacy("pm25", 39.8, daily=False) == 56


def test_iaqi_legacy_daily_matches_historical_rows():
    # 2026-10-15/16/17 日值行：气态用 24h 表、O3 用 8h 表、PM 用 24h 表
    assert iaqi_legacy("so2", 9, daily=True) == 9
    assert iaqi_legacy("no2", 22, daily=True) == 28
    assert iaqi_legacy("no2", 24, daily=True) == 30
    assert iaqi_legacy("co", 0.5, daily=True) == 13
    assert iaqi_legacy("o3", 95, daily=True) == 48
    assert iaqi_legacy("o3", 151, daily=True) == 93
    assert iaqi_legacy("o3", 60, daily=True) == 30
    assert iaqi_legacy("pm10", 105, daily=True) == 78
    assert iaqi_legacy("pm10", 108, daily=True) == 79
    assert iaqi_legacy("pm25", 73, daily=True) == 98
    assert iaqi_legacy("pm25", 53, daily=True) == 73
    assert iaqi_legacy("pm25", 32, daily=True) == 46


def test_iaqi_legacy_handles_invalid_values():
    assert iaqi_legacy("pm25", None, daily=True) is None
    assert iaqi_legacy("pm25", "-", daily=True) is None
    assert iaqi_legacy("pm25", 600, daily=True) == 500


def test_record_from_row_maps_platform_fields_hour():
    station_tsno = {"建安区小召乡": "411023108"}
    record = record_from_row({
        "name": "建安区小召乡", "countyId": "411023", "countyIdStr": "建安区",
        "collectionTime": "2026-10-28 23:00:00",
        "pm10": 62.4, "pm25": 40.6, "so2": 3.3, "no2": 13.0, "co": 0.44, "o3": 55.8,
        "aqi": 58, "chiefPollutant": "PM2.5", "pollutionLevel": "2",
        "pollutionLevelStr": "良",
    }, station_tsno, is_hour=True, is_audit=0)
    assert record is not None
    assert record["tsno"] == "411023108"
    assert record["collection_time"] == datetime(2026, 10, 28, 23, 0)
    assert record["is_hour"] == 1
    assert record["is_audit"] == 0
    assert record["aqi"] == 58
    assert record["pollution_level"] == "良"
    assert record["chief_pollutant"] == "PM2.5"
    assert record["pm25"] == 40.6
    assert record["pm25_iaqi"] == iaqi_legacy("pm25", 40.6, daily=False)


def test_record_from_row_maps_platform_fields_day():
    station_tsno = {"建安区小召乡": "411023108"}
    record = record_from_row({
        "name": "建安区小召乡",
        "collectionTime": "2026-10-28 00:00:00",
        "pm10": 66.0, "pm25": 40.0, "so2": 4.0, "no2": 24.0, "co": 0.5, "o3": 87.0,
        "aqi": 58, "chiefPollutant": "PM10", "pollutionLevelStr": "良",
    }, station_tsno, is_hour=False, is_audit=1)
    assert record is not None
    assert record["is_hour"] == 0
    assert record["is_audit"] == 1
    assert record["pm25_iaqi"] == iaqi_legacy("pm25", 40.0, daily=True)
    assert record["no2_iaqi"] == 30


def test_record_from_row_drops_invalid_rows():
    station_tsno = {"建安区小召乡": "411023108"}
    assert record_from_row({
        "name": "建安区小召乡", "collectionTime": None,
    }, station_tsno, is_hour=True, is_audit=0) is None
    assert record_from_row({
        "name": "未知站", "collectionTime": "2026-10-28 23:00:00",
    }, station_tsno, is_hour=True, is_audit=0) is None


def test_records_from_rows_dual_writes_audit_0_and_1():
    station_tsno = {"建安区小召乡": "411023108"}
    row = {
        "name": "建安区小召乡", "collectionTime": "2026-10-28 08:00:00",
        "pm25": 40.6, "aqi": 58,
    }
    records, unmatched = records_from_rows([row], station_tsno, is_hour=True)
    assert unmatched == 0
    assert len(records) == 2
    audits = sorted(record["is_audit"] for record in records)
    assert audits == [0, 1]
    # 同值双写：除 IsAudit 外其余字段一致
    assert records[0]["pm25"] == records[1]["pm25"]
    assert records[0]["collection_time"] == records[1]["collection_time"]


def test_records_from_rows_counts_unmatched():
    records, unmatched = records_from_rows(
        [{"name": "未知站", "collectionTime": "2026-10-28 08:00:00"}],
        {}, is_hour=True,
    )
    assert records == []
    assert unmatched == 1


def test_fetcher_schedule_and_window():
    hour_fetcher = XuchangTownAirDataFetcher(data_kind="hour")
    assert hour_fetcher.name == "xuchang_town_hour_fetcher"
    assert hour_fetcher.schedule == "5 * * * *"
    start, end = hour_fetcher._window(datetime(2026, 10, 29, 15, 0))
    assert (end - start).total_seconds() == 30 * 3600

    day_fetcher = XuchangTownAirDataFetcher(data_kind="day")
    assert day_fetcher.name == "xuchang_town_day_fetcher"
    assert day_fetcher.schedule == "5 8 * * *"
    start, end = day_fetcher._window(datetime(2026, 10, 29, 8, 5))
    assert (end - start).days == 16


def test_fetcher_rejects_unknown_data_kind():
    import pytest

    with pytest.raises(ValueError):
        XuchangTownAirDataFetcher(data_kind="minute")


def test_fetchers_are_registered_in_scheduler_factory():
    from app.fetchers import create_scheduler

    scheduler = create_scheduler()
    for name, schedule in (
        ("xuchang_town_hour_fetcher", "5 * * * *"),
        ("xuchang_town_day_fetcher", "5 8 * * *"),
    ):
        fetcher = scheduler.get_fetcher(name)
        assert fetcher is not None, name
        assert fetcher.schedule == schedule


def test_new_fetcher_schedule_does_not_collide_with_crawler_mysql_writers():
    """与 ssfb 三波 / 乡镇5分钟 / transport 错开（Crawler MySQL 并发保护）。

    ssfb 各波与乡镇 5 分钟单轮数十秒内完成，按同分钟互斥建模；只有
    transport_analysis 单轮 3~4 分钟，按分钟+3 拖尾建模（历史上其 :15 轮
    拖到 :18:26 与区县波并发触发过 Packet sequence number wrong）。
    """
    exact_minutes = set()
    for spec in (
        "14,20,55", "16,22,57", "18,24,59",  # ssfb 城市/站点/区县
        "7,37",                              # 乡镇 5 分钟
        "4,9,15,25,35,45",                   # 办事处 5 分钟
    ):
        exact_minutes.update(int(part) for part in spec.split(","))
    occupied = set(exact_minutes)
    for minute in (26, 31, 40, 50):  # transport_analysis（单轮拖尾 3~4 分钟）
        occupied.update(minute + offset for offset in range(4))
    from app.fetchers.xuchang_oldcloud_extra_stations import (
        XuchangOfficeHourFetcher,
        XuchangShengkongStationFetcher,
    )
    from app.fetchers.xuchang_town_high_value_alert import (
        XuchangTownHighValueAlertFetcher,
    )

    hour_fetcher = XuchangTownAirDataFetcher(data_kind="hour")
    day_fetcher = XuchangTownAirDataFetcher(data_kind="day")
    fetchers = (
        hour_fetcher,
        day_fetcher,
        XuchangOfficeHourFetcher(),
        XuchangShengkongStationFetcher(),
        XuchangTownHighValueAlertFetcher(),
    )
    for fetcher in fetchers:
        for spec in fetcher.schedule.split(" ")[0].split(","):
            assert int(spec) not in occupied, (fetcher.name, fetcher.schedule)
