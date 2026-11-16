"""乡镇站 5 分钟抓取器单元测试（旧云平台替代源）。"""

from datetime import datetime

from app.fetchers.xuchang_town_five_minute import (
    XuchangTownFiveMinuteFetcher,
    record_from_row,
)
from app.integrations.town_cloud_client import eval_captcha_expression


def test_eval_captcha_expression_supports_four_operators():
    assert eval_captcha_expression("5+1=?") == "6"
    assert eval_captcha_expression("8-2=?") == "6"
    assert eval_captcha_expression("1*6=?") == "6"
    assert eval_captcha_expression("3/1=?") == "3"
    assert eval_captcha_expression("9+8=?") == "17"


def test_eval_captcha_expression_handles_dirty_ocr_text():
    assert eval_captcha_expression("识别: 7+6=? 请看图") == "13"
    assert eval_captcha_expression("7+0") == "7"
    assert eval_captcha_expression("无法识别") is None
    assert eval_captcha_expression("") is None
    assert eval_captcha_expression("5/0=?") is None


def test_record_from_row_maps_platform_fields():
    station_tsno = {"襄城县库庄镇": "411025111"}
    record = record_from_row({
        "tsno": "411025111", "name": "襄城县库庄镇",
        "countyId": "411025", "countyIdStr": "襄城县",
        "collectionTime": "2026-10-27 12:05:00",
        "pm25": "47.42", "pm10": 58.81, "so2": "4.34",
        "no2": None, "co": None, "o3": None, "no": "0.5", "nox": "15.8",
        "aqi": None, "chiefPollutant": None, "pollutionLevel": None,
    }, station_tsno)
    assert record is not None
    assert record["tsno"] == "411025111"
    assert record["station_name"] == "襄城县库庄镇"
    assert record["collection_time"] == datetime(2026, 10, 27, 12, 5)
    assert record["pm25"] == 47.42
    assert record["no_val"] == 0.5
    assert record["is_audit"] == 0


def test_record_from_row_drops_invalid_rows():
    station_tsno = {"襄城县库庄镇": "411025111"}
    # 缺时间戳
    assert record_from_row({
        "countyId": "411025", "name": "襄城县库庄镇", "collectionTime": None,
    }, station_tsno) is None
    # 目录未命中（站名不在目录里）
    assert record_from_row({
        "countyId": "411025", "name": "未知站",
        "collectionTime": "2026-10-27 12:05:00",
    }, station_tsno) is None
    # 时间戳格式非法
    assert record_from_row({
        "countyId": "411025", "name": "襄城县库庄镇", "collectionTime": "bad",
    }, station_tsno) is None


def test_fetcher_schedule_and_window():
    fetcher = XuchangTownFiveMinuteFetcher()
    assert fetcher.schedule == "7,37 * * * *"
    start, end = fetcher._window(datetime(2026, 10, 27, 15, 0))
    assert (end - start).total_seconds() == 180 * 60


def test_town_five_minute_fetcher_is_registered_in_scheduler_factory():
    from app.fetchers import create_scheduler

    scheduler = create_scheduler()
    fetcher = scheduler.get_fetcher("xuchang_town_five_minute_fetcher")
    assert fetcher is not None
    assert fetcher.schedule == "7,37 * * * *"
