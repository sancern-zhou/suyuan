"""Tests for the Henan ssfb county (区县) publish fetcher."""

from datetime import datetime

import pytest

from app.integrations.henan_ssfb_client import (
    JIYUAN_COUNTY_GROUP_ID,
    county_groups_from_tree,
)
from app.fetchers.xuchang_henan_county_publish import (
    HenanCountyMySqlStorage,
    XuchangHenanCountyPublishFetcher,
    _county_record,
)


def test_county_groups_from_tree_supports_wrapper_and_flat_shapes():
    # 旧版后端: 顶层"省辖市"包装根 → 城市 → 区县
    wrapped = [{"Name": "省辖市", "Children": [
        {"ID": 210, "Name": "许昌市", "Children": [
            {"ID": 21007, "Name": "开发区", "Code": "4111"},
            {"ID": 213, "Name": "鄢陵县", "Code": "4112"},
        ]},
    ]}]
    groups = county_groups_from_tree(wrapped)
    assert groups[21007] == {"name": "开发区", "city": "许昌市", "code": "4111"}
    assert groups[213]["city"] == "许昌市"
    # 新版后端: 顶层直接是城市节点
    flat = [{"ID": 203, "Name": "洛阳市", "Children": [
        {"ID": 20308, "Name": "栾川县"},
        {"ID": 20309, "Name": "嵩县"},
    ]}]
    groups = county_groups_from_tree(flat)
    assert groups[20308] == {"name": "栾川县", "city": "洛阳市", "code": None}


def test_county_record_normalizes_jiyuan_and_drops_future_hours():
    meta = {218: {"name": "济源市", "city": "济源市", "code": None}}
    record = _county_record(
        {
            "groupID": 218, "groupName": "济源示范区", "area": "济源示范区",
            "lst": "2026-10-09", "aqi": 82, "quality": "良", "grade": 2,
            "pm25": 42, "pm10": None, "o3": None, "o3_8H": 138,
            "no2": 26, "so2": 11, "co": 1, "primary_pollutant_name": "PM₁₀,O₃",
        },
        meta, datetime(2026, 10, 10, 9, 0), "day",
    )
    assert record["county"] == "济源市"
    assert record["city"] == "济源市"
    assert record["data_time"] == datetime(2026, 10, 9)
    assert record["o3_8h"] == 138.0
    # 未来时段(当日尚未发布)丢弃
    future = _county_record(
        {"groupID": 20308, "groupName": "栾川县", "lst": "2026-10-10 20:00"},
        {20308: {"name": "栾川县", "city": "洛阳市", "code": None}},
        datetime(2026, 10, 10, 9, 0), "hour",
    )
    assert future is None


class _FakeClient:
    def __init__(self):
        self.calls = []

    def county_tree(self):
        return [{"ID": 210, "Name": "许昌市", "Children": [
            {"ID": 21007, "Name": "开发区"},
            {"ID": 213, "Name": "鄢陵县"},
        ]}]

    def group_hours(self, county_ids, start, end, query_type="1"):
        self.calls.append(("hours", tuple(county_ids), start, end, query_type))
        return [{"groupID": 213, "groupName": "鄢陵县", "area": "许昌市",
                 "lst": "2026-10-09 23:00", "pm25": 44}]

    def group_days(self, county_ids, start, end, query_type="1"):
        self.calls.append(("days", tuple(county_ids), start, end, query_type))
        return [
            {"groupID": 213, "groupName": "鄢陵县", "area": "许昌市",
             "lst": start, "aqi": 66, "pm25": 26, "o3_8H": 133},
            {"groupID": JIYUAN_COUNTY_GROUP_ID, "groupName": "济源示范区",
             "area": "济源示范区", "lst": start, "aqi": 82, "pm25": 42,
             "o3_8H": 138},
        ]


def _make_fetcher(client, storage):
    return XuchangHenanCountyPublishFetcher(
        client=client, storage=storage,
        now_factory=lambda: datetime(2026, 10, 10, 9, 0, 0),
    )


def test_county_fetcher_collect_uses_county_querytype_and_jiyuan():
    client = _FakeClient()
    fetcher = _make_fetcher(client, HenanCountyMySqlStorage(
        url="mysql+aiomysql://u:p@127.0.0.1:13307/DataCrawler"))
    collected = fetcher._collect(datetime(2026, 10, 10, 9, 0, 0))
    kinds = [call[0] for call in client.calls]
    assert kinds == ["hours", "days", "days"]
    # 区县树叶子 + 济源(218)，全部走 queryType=2（ID 升序）
    assert client.calls[0][1] == (213, JIYUAN_COUNTY_GROUP_ID, 21007)
    assert all(call[4] == "2" for call in client.calls)
    # 9:00 不属于三波调度分钟 → 手动/补数运行按全量对账窗口（回看 3 天）。
    assert client.calls[0][2] == "2026-10-07 00:00:00"
    assert client.calls[0][3] == "2026-10-10 23:00:00"
    # 站点式单日回看两日（区县日值发布偏晚，自动补齐）
    assert [(call[2], call[3]) for call in client.calls[1:]] == [
        ("2026-10-08", "2026-10-08"), ("2026-10-09", "2026-10-09"),
    ]
    assert collected["hour"][0]["county"] == "鄢陵县"
    assert {row["county"] for row in collected["day"]} == {"鄢陵县", "济源市"}
    # 排名不落表（cube 语义层实时现算）
    assert "ranking" not in collected


def test_county_fetcher_retry_wave_skips_day_fetch():
    """次波/三波只抓 2 小时窗口的小时值，不再重复拉取日值。"""
    client = _FakeClient()
    fetcher = _make_fetcher(client, HenanCountyMySqlStorage(
        url="mysql+aiomysql://u:p@127.0.0.1:13307/DataCrawler"))
    for minute in (24, 59):
        client.calls.clear()
        collected = fetcher._collect(datetime(2026, 10, 16, 10, minute, 0))
        assert [call[0] for call in client.calls] == ["hours"]
        assert client.calls[0][2] == "2026-10-16 08:00:00"
        assert client.calls[0][3] == "2026-10-16 23:00:00"
        assert collected["day"] == []


def test_county_fetcher_day_hours_follow_first_wave():
    """日值只在 07/10/13/16/19/22 时的首波（:18 分）抓取。"""
    client = _FakeClient()
    fetcher = _make_fetcher(client, HenanCountyMySqlStorage(
        url="mysql+aiomysql://u:p@127.0.0.1:13307/DataCrawler"))
    fetcher._collect(datetime(2026, 10, 16, 7, 18, 0))
    assert [call[0] for call in client.calls] == ["hours", "days", "days"]
    assert client.calls[0][2] == "2026-10-16 01:00:00"
    client.calls.clear()
    fetcher._collect(datetime(2026, 10, 16, 8, 18, 0))
    assert [call[0] for call in client.calls] == ["hours"]


def test_county_fetcher_target_counties_appends_jiyuan():
    fetcher = _make_fetcher(_FakeClient(), HenanCountyMySqlStorage(
        url="mysql+aiomysql://u:p@127.0.0.1:13307/DataCrawler"))
    counties = fetcher._target_counties(fetcher.client.county_tree())
    assert JIYUAN_COUNTY_GROUP_ID in counties
    assert counties[JIYUAN_COUNTY_GROUP_ID]["name"] == "济源市"


@pytest.mark.asyncio
async def test_county_fetcher_store_and_result():
    client = _FakeClient()
    saved, dims = [], []

    class _FakeStorage:
        async def save(self, records, kind):
            saved.append((len(records), kind))
            return len(records)

        async def upsert_dim_county(self, counties):
            dims.append(len(counties))
            return len(counties)

    fetcher = _make_fetcher(client, _FakeStorage())
    result = await fetcher.fetch_and_store()
    assert saved == [(1, "hour"), (4, "day")]
    assert dims == [3]
    assert "saved_ranking_rows" not in result
