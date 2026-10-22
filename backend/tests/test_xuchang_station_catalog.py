"""许昌站点目录工具与知识库同步测试"""
import json

import pytest

from app.tools.xuchang.airdata_platform.client import AirDataPlatformClient
from app.tools.xuchang.station_catalog import catalog as catalog_module
from app.tools.xuchang.station_catalog.catalog import (
    build_catalog,
    load_catalog,
    resolve_stations,
    split_township_name,
)
from app.tools.xuchang.station_catalog.graph_seed import render_station_directory
from app.tools.xuchang.station_catalog.tool import XuchangStationCatalogTool

DISTRICT_NAMES = ["建安区", "襄城县", "禹州市", "长葛市", "鄢陵县", "示范区"]

REGION_ROWS = [
    {"areacode": "410000", "areaname": "河南省", "level": 1},
    {"areacode": "411000", "areaname": "许昌市", "level": 2},
    {"areacode": "411002", "areaname": "魏都区", "level": 3},
    {"areacode": "411003", "areaname": "建安区", "level": 3},
    {"areacode": "411024", "areaname": "鄢陵县", "level": 3},
    {"areacode": "411025", "areaname": "襄城县", "level": 3},
    {"areacode": "411081", "areaname": "禹州市", "level": 3},
    {"areacode": "411082", "areaname": "长葛市", "level": 3},
    {"areacode": "411071", "areaname": "开发区", "level": 3},
]

TOWNSHIP_ROWS = [
    {"code": "1107B", "name": "长葛市和尚桥镇", "timepoint": "2026-09-18"},
    {"code": "1107B", "name": "长葛市和尚桥镇", "timepoint": "2026-09-17"},
    {"code": "1037B", "name": "示范区尚集镇", "timepoint": "2026-09-18"},
    {"code": "1050B", "name": "襄城县麦岭镇", "timepoint": "2026-09-18"},
]

STATION_ROWS = [
    {
        "positionname": "芙蓉广场",
        "areacode": "411000",
        "uniquecode": "411000408",
        "stationcode": "1009A",
        "longitude": None,
        "latitude": None,
        "address": "",
        "stationtypeid": 1,
        "status": True,
    },
    {
        "positionname": "新元大道996号",
        "areacode": "411003",
        "uniquecode": "411003002",
        "stationcode": "1011A",
        "longitude": "113.80348",
        "latitude": "34.1424",
        "address": "新元大道996号",
        "stationtypeid": 1,
        "status": True,
    },
    {
        "positionname": "建安区昌盛街道办事处",
        "areacode": "411003",
        "uniquecode": "411003002",
        "stationcode": "1015B",
        "longitude": None,
        "latitude": None,
        "address": "",
        "stationtypeid": 4,
        "status": True,
    },
]

STATION_COORDINATES = {
    "芙蓉广场": {
        "station_id": "3338A",
        "name": "芙蓉广场",
        "longitude": 113.8428,
        "latitude": 34.0825,
        "source": "sqlserver:dat_station_hour",
    },
}

FIELDS_RESPONSE = {
    "columns": [],
    "rows": [],
    "total": 0,
    "page": 1,
    "size": 100,
}


class FakeClient:
    def query_page(self, api_code, filters=None, selected_fields=None, sort_config=None, page=1, size=None):
        if api_code == "region":
            return {**FIELDS_RESPONSE, "rows": REGION_ROWS, "total": len(REGION_ROWS)}
        if api_code == "station":
            return {**FIELDS_RESPONSE, "rows": STATION_ROWS, "total": len(STATION_ROWS)}
        return {**FIELDS_RESPONSE}

    def query_all(self, api_code, filters=None, selected_fields=None, sort_config=None, max_rows=2000, page_size=None):
        if api_code == "v_t_d_src":
            return {
                "columns": [],
                "rows": TOWNSHIP_ROWS,
                "total": len(TOWNSHIP_ROWS),
                "pages_fetched": 1,
                "truncated": False,
            }
        return {"columns": [], "rows": [], "total": 0, "pages_fetched": 0, "truncated": False}


@pytest.fixture
def fake_catalog(monkeypatch, tmp_path):
    monkeypatch.setattr(catalog_module, "get_data_registry", lambda: tmp_path)
    monkeypatch.setattr(
        "app.tools.xuchang.airdata_platform.client.get_airdata_platform_client",
        lambda: FakeClient(),
        raising=False,
    )
    monkeypatch.setattr(catalog_module, "get_airdata_platform_client", lambda: FakeClient())
    monkeypatch.setattr(
        catalog_module, "load_station_coordinates", lambda: STATION_COORDINATES
    )
    return tmp_path


def test_split_township_name_prefers_longest_district():
    assert split_township_name("长葛市和尚桥镇", DISTRICT_NAMES) == ("长葛市", "和尚桥镇")
    assert split_township_name("襄城县麦岭镇", DISTRICT_NAMES) == ("襄城县", "麦岭镇")


def test_split_township_name_supports_zone_alias():
    assert split_township_name("示范区尚集镇", DISTRICT_NAMES) == ("示范区", "尚集镇")
    assert split_township_name("未知站点", DISTRICT_NAMES) == ("", "未知站点")


def test_hidden_stations_manifest_has_september_street_stations():
    hidden = catalog_module.load_hidden_stations()

    assert len(hidden) == 31
    assert all(code.upper().endswith("B") for code in hidden)
    assert hidden["1015B"] == "建安区昌盛街道办事处"
    assert hidden["1001B"] == "魏都区丁庄街道办事处"


def test_build_catalog_excludes_hidden_townships(fake_catalog, monkeypatch):
    monkeypatch.setattr(
        catalog_module,
        "load_hidden_stations",
        lambda: {"1107B": "长葛市和尚桥镇"},
    )

    catalog = build_catalog()

    codes = {item["station_code"] for item in catalog["townships"]}
    assert "1107B" not in codes
    assert {"1037B", "1050B"} <= codes
    assert catalog["hidden_station_count"] == 1


def test_resolve_stations_skips_hidden_township(fake_catalog, monkeypatch):
    monkeypatch.setattr(
        catalog_module,
        "load_hidden_stations",
        lambda: {"1037B": "示范区尚集镇"},
    )
    catalog = load_catalog(force_refresh=True)

    assert resolve_stations(catalog, station_names=["尚集"]) == []
    assert resolve_stations(catalog, station_codes=["1037B"]) == []


def test_render_station_directory_notes_hidden_stations(fake_catalog):
    catalog = load_catalog()
    catalog["hidden_station_count"] = 31

    markdown = render_station_directory(catalog)

    assert "31 个已登记但长期无数据上报的街道站" in markdown
    assert "暂未列入本目录" in markdown


def test_build_catalog_with_fake_client(fake_catalog):
    catalog = build_catalog()

    assert catalog["city"] == {"name": "许昌市", "areacode": "411000"}
    assert [d["name"] for d in catalog["districts"]] == [
        "魏都区", "建安区", "鄢陵县", "襄城县", "开发区", "禹州市", "长葛市",
    ]
    townships = {t["station_code"]: t for t in catalog["townships"]}
    assert townships["1107B"]["district"] == "长葛市"
    assert townships["1037B"]["district"] == "示范区"
    assert townships["1050B"]["district"] == "襄城县"


def test_township_coordinates_are_joined_by_station_name(fake_catalog):
    catalog = build_catalog()

    township = {item["station_code"]: item for item in catalog["townships"]}["1107B"]
    assert township["station_name"] == "长葛市和尚桥镇"
    assert township["longitude"] == pytest.approx(113.8019)
    assert township["latitude"] == pytest.approx(34.2052)
    assert township["address"]
    assert township["coordinate_source"] == "township_coordinates.xlsx"

    regular = catalog["regular_stations"]
    assert [item["station_code"] for item in regular] == ["1009A", "1011A"]
    assert regular[0]["unique_code"] == "411000408"
    assert regular[0]["type_name"] == "国控"
    assert regular[1]["district"] == "建安区"


def test_regular_station_coordinates_filled_from_sqlserver(fake_catalog):
    catalog = build_catalog()

    regular = catalog["regular_stations"][0]
    assert regular["longitude"] == pytest.approx(113.8428)
    assert regular["latitude"] == pytest.approx(34.0825)
    assert regular["coordinate_source"] == "sqlserver:dat_station_hour"


@pytest.mark.asyncio
async def test_provider_returns_canonical_records(fake_catalog):
    from app.services.station_directory import StationQuery
    from app.tools.xuchang.station_catalog.provider import (
        XuchangStationCatalogProvider,
    )

    provider = XuchangStationCatalogProvider()
    records = await provider.list_stations(StationQuery(station_types=("国控",)))

    assert [record.station_code for record in records] == ["1009A", "1011A"]
    assert records[0].station_category == "regular"
    assert records[0].station_type == "国控"
    assert records[0].longitude == pytest.approx(113.8428)
    assert records[0].latitude == pytest.approx(34.0825)

    township_records = await provider.list_stations(
        StationQuery(station_categories=("township",))
    )
    assert township_records
    assert all(
        record.station_category == "township" for record in township_records
    )


def test_load_catalog_uses_cache_within_ttl(fake_catalog):
    first = load_catalog()
    assert first["from_cache"] is False

    second = load_catalog()
    assert second["from_cache"] is True

    cached = json.loads((fake_catalog / "xuchang_station_catalog" / "catalog_cache.json").read_text())
    assert cached["townships"][0]["station_code"]


def test_resolve_stations_by_fuzzy_name_and_code(fake_catalog):
    catalog = load_catalog()

    by_name = resolve_stations(catalog, station_names=["和尚桥镇"])
    assert [item["station_code"] for item in by_name] == ["1107B"]

    by_code = resolve_stations(catalog, station_codes=["411000408"])
    assert [item["station_name"] for item in by_code] == ["芙蓉广场"]

    by_district = resolve_stations(catalog, districts=["襄城"])
    assert [item["station_code"] for item in by_district] == ["1050B"]


def test_resolve_stations_type_filter(fake_catalog):
    catalog = load_catalog()

    townships_only = resolve_stations(catalog, districts=["长葛"], station_type="township")
    assert [item["station_code"] for item in townships_only] == ["1107B"]

    regular_only = resolve_stations(catalog, station_type="regular")
    assert [item["station_code"] for item in regular_only] == ["1009A", "1011A"]


@pytest.mark.asyncio
async def test_catalog_tool_lookup(fake_catalog):
    tool = XuchangStationCatalogTool()

    result = await tool.execute(stations=["尚集"])

    assert result["success"] is True
    assert result["data"][0]["station_code"] == "1037B"
    assert result["data"][0]["district"] == "示范区"


@pytest.mark.asyncio
async def test_catalog_tool_lookup_empty_gives_hint(fake_catalog):
    tool = XuchangStationCatalogTool()

    result = await tool.execute(stations=["不存在站"])

    assert result["status"] == "empty"
    assert "可用区县" in result["summary"]


def test_render_station_directory_contains_relations(fake_catalog):
    markdown = render_station_directory(load_catalog())

    assert "# 许昌市空气监测站点目录" in markdown
    assert "长葛市和尚桥镇" in markdown
    assert "1107B" in markdown
    assert "隶属于长葛市" in markdown
    assert "芙蓉广场" in markdown


def test_xuchang_registers_station_catalog_tool():
    from app.project_config.loader import load_project_context
    from app.tools import create_global_tool_registry

    xuchang_registry = create_global_tool_registry(
        context=load_project_context("xuchang")
    )
    assert "xuchang_station_catalog" in xuchang_registry.list_tools()

    jiangxi_registry = create_global_tool_registry(
        context=load_project_context("jiangxi")
    )
    assert "xuchang_station_catalog" not in jiangxi_registry.list_tools()


def test_query_payload_auto_fields_for_township_views():
    payload = AirDataPlatformClient._build_query_payload("v_t_h_src", None, None, None, 1, 100)
    assert payload["selectedFields"][0] == "id"
    assert len(payload["selectedFields"]) == 32

    payload_region = AirDataPlatformClient._build_query_payload("region", None, None, None, 1, 100)
    assert "selectedFields" not in payload_region
