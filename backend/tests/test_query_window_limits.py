"""API 查询时间窗限制的回归测试。

护栏在多源监测接口客户端层生效，覆盖所有走 VOCs / PM2.5 组分接口的问数工具。
"""

from __future__ import annotations

import logging

import pytest

from app.utils.query_window_limits import (
    check_query_window,
    normalize_granularity,
)
from app.utils.particulate_api_client import ParticulateAPIClient
from app.utils.vocs_api_client import VocApiClient


def _allows(start: str, end: str, granularity) -> bool:
    return check_query_window(start, end, granularity) is None


def test_hourly_window_allows_one_month_and_rejects_longer():
    assert _allows("2026-01-01 00:00:00", "2026-01-31 00:00:00", 1)
    assert not _allows("2026-01-01 00:00:00", "2026-02-02 00:00:00", 1)

    message = check_query_window("2026-01-01 00:00:00", "2026-04-01 00:00:00", "hour")
    assert "上限 31 天" in message
    assert "接口超时或拥堵" in message
    assert "谨慎全量获取长时间细粒度数据" in message
    assert "重点时段" in message
    assert "分段查询" in message


def test_daily_window_allows_three_months_and_rejects_longer():
    assert _allows("2026-01-01 00:00:00", "2026-04-02 00:00:00", 2)
    assert not _allows("2026-01-01 00:00:00", "2026-04-10 00:00:00", 2)

    message = check_query_window("2026-01-01", "2026-07-01", "day")
    assert "上限 92 天" in message


def test_monthly_and_yearly_windows_have_coarse_limits():
    assert _allows("2024-01-01", "2024-12-31", 3)
    assert not _allows("2024-01-01", "2025-06-01", 3)
    assert _allows("2016-01-01", "2025-12-31", 5)


def test_unparseable_or_reversed_times_are_left_to_existing_validators():
    assert check_query_window("", "2026-01-01", 1) is None
    assert check_query_window("not-a-date", "2026-01-01", 1) is None
    assert check_query_window("2026-02-01", "2026-01-01", 1) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "hour"),
        (1, "hour"),
        ("1", "hour"),
        ("hour", "hour"),
        ("小时", "hour"),
        (2, "day"),
        ("daily", "day"),
        (3, "month"),
        (5, "year"),
        ("unknown", "hour"),
    ],
)
def test_normalize_granularity(value, expected):
    assert normalize_granularity(value) == expected


def _bare_particulate_client() -> ParticulateAPIClient:
    client = object.__new__(ParticulateAPIClient)
    client.logger = logging.getLogger("test.particulate")
    client.ionic_endpoint = "/test/ionic"
    client.carbon_endpoint = "/test/carbon"
    client.recovery_endpoint = "/test/recovery"
    return client


def test_particulate_client_rejects_oversized_hourly_window_before_network():
    client = _bare_particulate_client()

    result = client.get_ionic_analysis(
        station="技师学院",
        code="1036b",
        start_time="2026-01-01 00:00:00",
        end_time="2026-04-01 00:00:00",
        time_type=1,
        data_type=0,
    )

    assert result["success"] is False
    assert result["error_code"] == "query_range_too_large"
    assert "水溶性离子查询" in result["error"]


def test_particulate_client_valid_window_reaches_api_layer():
    client = _bare_particulate_client()
    calls = []

    def fake_call_api(endpoint, payload):
        calls.append((endpoint, payload))
        return {"success": True, "api_response": {"ok": True}}

    client._call_api = fake_call_api

    result = client.get_carbon_components(
        station="技师学院",
        code="1036b",
        start_time="2026-10-01 00:00:00",
        end_time="2026-10-10 00:00:00",
        table_type=1,
    )

    assert result["success"] is True
    assert len(calls) == 1


def _bare_voc_client() -> VocApiClient:
    client = object.__new__(VocApiClient)
    client.logger = logging.getLogger("test.voc")
    client.voc_category_endpoint = "/test/voc-category"
    client.voc_species_endpoint = "/test/voc-species"
    client.ofp_timeseries_endpoint = "/test/ofp-timeseries"
    client.ofp_top10_endpoint = "/test/ofp-top10"
    return client


def test_voc_client_rejects_oversized_hourly_window_before_network():
    client = _bare_voc_client()

    result = client.get_voc_categories(
        station_code="1036b",
        start_time="2026-01-01 00:00:00",
        end_time="2026-04-01 00:00:00",
        table_type=1,
        data_type=0,
    )

    assert result["success"] is False
    assert result["error_code"] == "query_range_too_large"
    assert "VOCs 类别查询" in result["error"]


def test_voc_ofp_client_valid_window_reaches_api_layer():
    client = _bare_voc_client()
    calls = []

    def fake_get_json(endpoint, params, op):
        calls.append((endpoint, params, op))
        return {"success": True, "api_response": {"ok": True}}

    client._get_json = fake_get_json

    result = client.get_ofp_top10(
        station_code="1036b",
        start_time="2026-10-01 00:00:00",
        end_time="2026-10-10 00:00:00",
        table_type=1,
        data_type=0,
    )

    assert result["success"] is True
    assert len(calls) == 1
