"""办事处 5 分钟 / 省控小时抓取器单元测试（许昌市空气质量管控平台 tstype=9/3）。

协议要点（2026-11-23 实测定版）：airData/page 必须携带 tsno 逐站查询，
不带 tsno 时 tstype 参数被平台忽略、恒返回乡镇站全集行。
"""

from datetime import datetime

from app.fetchers.xuchang_oldcloud_extra_stations import (
    XuchangOfficeFiveMinuteFetcher,
    XuchangOfficeHourFetcher,
    XuchangShengkongStationFetcher,
    office_record_from_row,
    shengkong_record_from_row,
)
from app.fetchers.xuchang_town_high_value_alert import XuchangTownHighValueAlertFetcher


def test_office_record_from_row_maps_two_factors_only():
    record = office_record_from_row({
        "name": "魏都区东大街道办事处", "collectionTime": "2026-11-23 16:55:00",
        "pm25": 42.1, "pm10": 98.7,
        # 办事处因子集其余因子平台恒返回 null
        "so2": None, "no2": None, "co": None, "o3": None,
    }, "411002003", "魏都区")
    assert record is not None
    assert record["tsno"] == "411002003"
    assert record["station_name"] == "魏都区东大街道办事处"
    assert record["county_name"] == "魏都区"
    assert record["collection_time"] == datetime(2026, 11, 23, 16, 55)
    assert record["pm25"] == 42.1
    assert record["pm10"] == 98.7
    assert record["is_audit"] == 0
    assert set(record) == {
        "tsno", "station_name", "county_name", "collection_time",
        "is_audit", "is_hour", "pm25", "pm10",
    }


def test_office_record_from_row_drops_invalid_rows():
    assert office_record_from_row({
        "name": "魏都区东大街道办事处", "collectionTime": None,
    }, "411002003", None) is None
    assert office_record_from_row({
        "name": "魏都区东大街道办事处", "collectionTime": "bad",
    }, "411002003", None) is None


def test_shengkong_record_from_row_maps_six_factors():
    record = shengkong_record_from_row({
        "name": "鄢陵县梅园", "collectionTime": "2026-11-22 18:00:00",
        "pm25": 94.0, "pm10": 135.0, "so2": 10.0, "no2": 32.0,
        "co": 1.1, "o3": 76.0,
        # 省控因子集不返回 NO/NOX
        "no": None, "nox": None,
    }, "41102403", "鄢陵县")
    assert record is not None
    assert record["tsno"] == "41102403"
    assert record["station_name"] == "鄢陵县梅园"
    assert record["collection_time"] == datetime(2026, 11, 22, 18, 0)
    assert record["pm25"] == 94.0
    assert record["so2"] == 10.0
    assert record["co"] == 1.1
    assert record["no_val"] is None
    assert record["nox"] is None
    assert record["is_audit"] == 0


def test_shengkong_record_from_row_drops_invalid_rows():
    assert shengkong_record_from_row({
        "name": "鄢陵县梅园", "collectionTime": None,
    }, "41102403", None) is None


def test_fetcher_protocol_and_windows():
    office = XuchangOfficeFiveMinuteFetcher()
    office_hour = XuchangOfficeHourFetcher()
    shengkong = XuchangShengkongStationFetcher()
    assert (office_hour.platform_tstype, office_hour.factor_type, office_hour.time_step) == ("9", "5", 2)
    assert office_hour.schedule == "3 * * * *"
    assert office_hour.is_hour is True and office.is_hour is False
    # 平台协议：办事处 tstype=9&type=5&timeStep=1；省控 tstype=3&type=4&timeStep=2
    assert (office.platform_tstype, office.factor_type, office.time_step) == ("9", "5", 1)
    assert (shengkong.platform_tstype, shengkong.factor_type, shengkong.time_step) == ("3", "4", 2)
    assert office.schedule == "4,9,15,25,35,45 * * * *"
    assert shengkong.schedule == "17 * * * *"
    start, end = office._window(datetime(2026, 11, 23, 15, 0))
    assert (end - start).total_seconds() == 180 * 60
    start, end = shengkong._window(datetime(2026, 11, 23, 15, 0))
    assert (end - start).total_seconds() == 30 * 3600


def test_fetchers_are_registered_in_scheduler_factory():
    from app.fetchers import create_scheduler

    scheduler = create_scheduler()
    for name, schedule in (
        ("xuchang_office_five_minute_fetcher", "4,9,15,25,35,45 * * * *"),
        ("xuchang_shengkong_station_fetcher", "17 * * * *"),
        ("xuchang_office_hour_fetcher", "3 * * * *"),
    ):
        fetcher = scheduler.get_fetcher(name)
        assert fetcher is not None, name
        assert fetcher.schedule == schedule


def test_new_fetcher_schedule_does_not_collide_with_crawler_mysql_writers():
    """与 ssfb 三波 / 乡镇 5 分钟 / 乡镇小时 / transport / 大屏快照错开（并发保护）。

    transport 单轮 3~4 分钟需带拖尾；其余抓取器秒级完成，按同分钟判。
    """
    def cron_minutes(spec):
        if "/" not in spec:
            return {int(part) for part in spec.split(",")}
        start, step = spec.split("/")
        first = int(start.split("-")[0])
        return set(range(first, 60, int(step)))

    occupied = set()
    for spec in (
        "14,20,55", "16,22,57", "18,24,59",  # ssfb 城市/站点/区县
    ):
        occupied.update(int(part) for part in spec.split(","))
    occupied.update({7, 37})                 # 乡镇 5 分钟
    for minute in [int(part) for part in "26,31,40,50".split(",")]:
        occupied.update(range(minute, minute + 4))  # transport 单轮拖尾
    occupied.update({5})                     # 乡镇小时
    occupied.update(cron_minutes("6-56/5"))  # 大屏快照
    for fetcher in (
        XuchangOfficeFiveMinuteFetcher(),
        XuchangOfficeHourFetcher(),
        XuchangShengkongStationFetcher(),
        XuchangTownHighValueAlertFetcher(),
    ):
        minutes = cron_minutes(fetcher.schedule.split(" ")[0])
        for minute in minutes:
            assert minute not in occupied, (fetcher.name, minute)
            occupied.add(minute)
