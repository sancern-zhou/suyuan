"""Tests for the Henan ssfb publish fetchers (cities + Xuchang county sites)."""

import base64
import json
from datetime import datetime

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from app.integrations.henan_ssfb_client import (
    SSFB_AES_IV,
    SSFB_AES_KEY,
    city_groups_from_tree,
    decrypt_payload,
    normalize_city_name,
    site_leaves_from_tree,
)
from app.fetchers.xuchang_henan_ssfb_publish import (
    HenanSsfbMySqlStorage,
    XuchangHenanSsfbCityPublishFetcher,
    XuchangHenanSsfbSitePublishFetcher,
    _city_record,
    _site_record,
)


def test_normalize_city_name_maps_jiyuan():
    assert normalize_city_name("济源示范区") == "济源市"
    assert normalize_city_name("许昌市") == "许昌市"
    assert normalize_city_name(None) == ""


def test_decrypt_payload_roundtrip():
    payload = json.dumps({"code": 1, "msg": "ok", "data": [{"lst": "2026-10-10 08:00"}]})
    cipher = AES.new(SSFB_AES_KEY.encode(), AES.MODE_CBC, SSFB_AES_IV.encode())
    ciphertext = base64.b64encode(cipher.encrypt(pad(payload.encode(), 16))).decode()
    assert decrypt_payload(ciphertext)["data"][0]["lst"] == "2026-10-10 08:00"


def test_city_groups_from_tree_supports_flat_and_nested_shapes():
    # 新版后端: 扁平城市列表 + 行政区划码
    flat = [
        {"ID": 201, "Name": "郑州市", "Code": "410100"},
        {"ID": 210, "Name": "许昌市", "Code": "411000"},
        {"ID": 218, "Name": "济源示范区", "Code": "419001"},
    ]
    groups = city_groups_from_tree(flat)
    assert groups[201] == {"name": "郑州市", "code": "410100"}
    assert groups[218] == {"name": "济源市", "code": "419001"}
    # 旧版后端: 顶层包根节点 + 区号式 ID
    nested = [{"Name": "省辖市", "Children": [
        {"ID": 21, "Name": "郑州市", "Code": "411"},
        {"ID": 218, "Name": "济源示范区", "Code": "4191"},
    ]}]
    legacy = city_groups_from_tree(nested)
    assert legacy[21] == {"name": "郑州市", "code": "411"}
    assert legacy[218] == {"name": "济源市", "code": "4191"}


def test_site_leaves_from_tree_filters_root_and_city():
    tree = [
        {"Name": "省辖市", "Children": [
            {"ID": 21, "Name": "许昌市", "Children": [
                {"ID": 100, "Name": "魏都区", "Children": [
                    {"ID": 1, "Name": "市一中(国)", "Note": "GK"},
                ]},
            ]},
        ]},
        {"Name": "县级", "Children": [
            {"ID": 21, "Name": "许昌市", "Children": [
                {"ID": 213, "Name": "鄢陵县", "Children": [
                    {"ID": 232, "Name": "鄢陵县政府", "Note": "SK"},
                    {"ID": 453, "Name": "鄢陵县胥庄监测站", "Note": "SCK"},
                ]},
            ]},
            {"ID": 22, "Name": "漯河市", "Children": [
                {"ID": 214, "Name": "舞阳县", "Children": [
                    {"ID": 24, "Name": "舞阳县环保局", "Note": "SK"},
                ]},
            ]},
        ]},
    ]
    sites = site_leaves_from_tree(
        tree, root_names={"县级"}, city_names={"许昌市"}
    )
    assert [(site["site_id"], site["county"]) for site in sites] == [
        (232, "鄢陵县"), (453, "鄢陵县"),
    ]
    assert sites[0]["root"] == "县级"
    assert sites[0]["online_type"] == "SK"


def test_city_record_normalizes_pm10_and_jiyuan():
    group_names = {218: {"name": "济源市", "code": "419001"}}
    record = _city_record(
        {
            "groupID": 218, "groupName": "济源示范区", "lst": "2026-10-09",
            "aqi": 56, "quality": "轻度污染", "grade": 3,
            "pm25": "38", "pm10": "78", "o3": None, "o3_8H": "174",
            "no2": 26, "so2": 1, "co": 1, "primary_pollutant_name": "O₃",
        },
        group_names,
        datetime(2026, 10, 10, 8, 0, 0),
        "day",
    )
    assert record["city"] == "济源市"
    assert record["city_code"] == "419001"
    assert record["data_time"] == datetime(2026, 10, 9)
    assert record["pm10"] == 78.0
    assert record["o3_8h"] == 174.0
    assert record["fetched_at"] == datetime(2026, 10, 10, 8, 0, 0)


def test_city_record_rejects_missing_time():
    assert _city_record({"groupID": 201, "groupName": "郑州市"},
                        {201: {"name": "郑州市", "code": "410100"}},
                        datetime(2026, 10, 10), "hour") is None


def test_site_record_merges_tree_metadata():
    meta = {232: {"site_name": "鄢陵县政府", "city": "许昌市", "county": "鄢陵县",
                  "online_type": "SK"}}
    record = _site_record(
        {"siteID": 232, "siteName": "鄢陵县政府", "lst": "2026-10-10 09:00:00",
         "area": "许昌市", "pm25": "40", "pm10": "66", "onlineType": "市控"},
        meta, datetime(2026, 10, 10, 10, 0, 0), "hour",
    )
    assert record["county"] == "鄢陵县"
    assert record["city"] == "许昌市"
    assert record["data_time"] == datetime(2026, 10, 10, 9, 0)
    assert record["pm10"] == 66.0


class _FakeClient:
    def __init__(self):
        self.calls = []

    def city_tree(self):
        return [
            {"ID": 201, "Name": "许昌市", "Code": "411000"},
            {"ID": 218, "Name": "济源示范区", "Code": "419001"},
        ]

    def group_hours(self, city_ids, start, end):
        self.calls.append(("hours", tuple(city_ids), start, end))
        return [{"groupID": 218, "groupName": "济源示范区", "lst": "2026-10-09 23:00",
                 "pm25": 44, "pm10": 91}]

    def group_days(self, city_ids, start, end):
        self.calls.append(("days", tuple(city_ids), start, end))
        return [{"groupID": 218, "groupName": "济源示范区", "lst": "2026-10-09",
                 "pm25": 38, "pm10": 78}]

    def station_tree(self):
        return [{"Name": "县级", "Children": [
            {"ID": 210, "Name": "许昌市", "Code": "411000", "Children": [
                {"ID": 213, "Name": "鄢陵县", "Children": [
                    {"ID": 232, "Name": "鄢陵县政府", "Note": "SK"},
                    {"ID": 453, "Name": "鄢陵县胥庄监测站", "Note": "SCK"},
                ]},
                {"ID": 999, "Name": "魏都区", "Children": [
                    {"ID": 86, "Name": "市一中(国)", "Note": "GK"},
                ]},
            ]},
            {"ID": 211, "Name": "漯河市", "Code": "411100", "Children": [
                {"ID": 214, "Name": "舞阳县", "Children": [
                    {"ID": 24, "Name": "舞阳县环保局", "Note": "SK"},
                ]},
            ]},
        ]}]

    def site_hours(self, site_ids, start, end):
        self.calls.append(("site_hours", tuple(site_ids), start, end))
        return [{"siteID": 232, "siteName": "鄢陵县政府", "lst": "2026-10-09 22:00",
                 "pm25": 41, "pm10": 70}]

    def site_days(self, site_ids, start, end):
        self.calls.append(("site_days", tuple(site_ids), start, end))
        return [{"siteID": 232, "siteName": "鄢陵县政府", "lst": "2026-10-09",
                 "pm25": 39, "pm10": 72}]


def test_city_fetcher_collect_uses_full_city_list_and_window():
    client = _FakeClient()
    fetcher = XuchangHenanSsfbCityPublishFetcher(
        client=client,
        storage=HenanSsfbMySqlStorage(url="mysql+aiomysql://u:p@127.0.0.1:13307/DataCrawler"),
        now_factory=lambda: datetime(2026, 10, 10, 9, 0, 0),
    )
    collected = fetcher._collect(datetime(2026, 10, 10, 9, 0, 0))
    kinds = [call[0] for call in client.calls]
    assert kinds == ["hours", "days"]
    assert client.calls[0][1] == (201, 218)
    assert client.calls[0][2] == "2026-10-09 00:00:00"
    assert client.calls[0][3] == "2026-10-10 23:00:00"
    assert client.calls[1][2] == "2026-10-08"
    assert client.calls[1][3] == "2026-10-09"
    assert [row["city"] for row in collected["hour"]] == ["济源市"]
    assert collected["hour"][0]["city_code"] == "419001"
    assert collected["day"][0]["data_time"] == datetime(2026, 10, 9)


def test_site_fetcher_collect_excludes_gk_and_other_cities():
    client = _FakeClient()
    fetcher = XuchangHenanSsfbSitePublishFetcher(
        client=client,
        storage=HenanSsfbMySqlStorage(url="mysql+aiomysql://u:p@127.0.0.1:13307/DataCrawler"),
        now_factory=lambda: datetime(2026, 10, 10, 9, 0, 0),
    )
    collected = fetcher._collect(datetime(2026, 10, 10, 9, 0, 0))
    site_calls = [call for call in client.calls if call[0].startswith("site_")]
    # 1 次小时(范围) + 2 次日值(单日, 站点日接口不支持跨日范围)
    assert len(site_calls) == 3
    assert site_calls[0][0] == "site_hours"
    assert site_calls[0][2] == "2026-10-09 00:00:00"
    assert site_calls[0][3] == "2026-10-10 23:00:00"
    assert [(call[2], call[3]) for call in site_calls[1:]] == [
        ("2026-10-08", "2026-10-08"), ("2026-10-09", "2026-10-09"),
    ]
    assert all(call[1] == (232, 453) for call in site_calls)
    assert collected["hour"][0]["county"] == "鄢陵县"
    assert collected["day"][0]["data_time"] == datetime(2026, 10, 9)


@pytest.mark.asyncio
async def test_city_fetcher_store_and_result(monkeypatch):
    client = _FakeClient()
    saved = []

    class _FakeStorage:
        async def save(self, records, kind):
            saved.append((len(records), kind))
            return len(records)

        async def upsert_dim_city(self, groups):
            dim.append(len(groups))
            return len(groups)

    saved = []
    dim = []
    fetcher = XuchangHenanSsfbCityPublishFetcher(
        client=client, storage=_FakeStorage(),
        now_factory=lambda: datetime(2026, 10, 10, 9, 0, 0),
    )
    result = await fetcher.fetch_and_store()
    assert saved == [(1, "hour"), (1, "day")]
    assert dim == [2]
    assert result["saved_hour_rows"] == 1
    assert result["cities"] == ["济源市"]


def test_storage_connection_kwargs_parse():
    storage = HenanSsfbMySqlStorage(
        url="mysql+aiomysql://root:secret@127.0.0.1:13307/DataCrawler?charset=utf8mb4"
    )
    kwargs = storage._connection_kwargs()
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 13307
    assert kwargs["user"] == "root"
    assert kwargs["password"] == "secret"
    assert kwargs["db"] == "DataCrawler"
