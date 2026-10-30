"""广东站点目录工具与共享 provider 契约测试（离线 mock，不连 mart 库）。"""
import pytest

from app.tools.guangdong.station_catalog import catalog as catalog_module
from app.tools.guangdong.station_catalog.catalog import (
    StationCatalogError,
    build_catalog,
    load_catalog,
    resolve_stations,
)
from app.tools.guangdong.station_catalog.provider import GuangdongStationCatalogProvider
from app.tools.guangdong.station_catalog.tool import GuangdongStationCatalogTool

STATION_ROWS = [
    {
        "station_id": "1001",
        "station_code": "GZ0101",
        "station_name": "从化天湖",
        "unique_code": "8001A",
        "city_code": "440100",
        "city_name": "广州",
        "station_type_name": "省控站",
        "operation_unit_id": "12",
        "operation_unit_name": "广州南的环境检测有限公司",
        "department_name": "运维一部",
        "manager_name": "",
        "longitude": 113.589,
        "latitude": 23.742,
        "address": "从化区温泉镇天湖路 1 号",
        "status": 1,
        "operation_type": "",
        "refreshed_at": "2026-10-28 06:00:00",
    },
    {
        "station_id": "1002",
        "station_code": "GZ0102",
        "station_name": "花城广场",
        "unique_code": "8002A",
        "city_code": "440100",
        "city_name": "广州",
        "station_type_name": "国控站",
        "operation_unit_id": "12",
        "operation_unit_name": "广州南的环境检测有限公司",
        "department_name": "运维二部",
        "manager_name": "赵六",
        "longitude": 113.321,
        "latitude": 23.119,
        "address": "天河区珠江东路",
        "status": 1,
        "operation_type": "",
        "refreshed_at": "2026-10-28 06:00:00",
    },
    {
        "station_id": "5",
        "station_code": "SC005",
        "station_name": "南沙湿组分站",
        "unique_code": "",
        "city_code": "440100",
        "city_name": "广州",
        "station_type_name": "组分站",
        "operation_unit_id": None,
        "operation_unit_name": None,
        "department_name": None,
        "manager_name": None,
        "longitude": None,
        "latitude": None,
        "address": None,
        "status": 1,
        "operation_type": "组分网",
        "refreshed_at": "2026-10-28 06:00:00",
    },
    {
        "station_id": "2001",
        "station_code": "FS0201",
        "station_name": "顺德苏岗",
        "unique_code": "9001A",
        "city_code": "440600",
        "city_name": "佛山",
        "station_type_name": "乡镇站",
        "operation_unit_id": "15",
        "operation_unit_name": "佛山环监运维站",
        "department_name": "运维一部",
        "manager_name": "",
        "longitude": 113.25,
        "latitude": 22.98,
        "address": "顺德区苏岗村",
        "status": 1,
        "operation_type": "",
        "refreshed_at": "2026-10-28 06:00:00",
    },
]

MANAGER_ROWS = [
    {"station_id": "1001", "user_id": "201", "user_name": "张三", "user_status": "Enabled"},
    {"station_id": "1001", "user_id": "202", "user_name": "李四", "user_status": "Enabled"},
    {"station_id": "1001", "user_id": "202", "user_name": "李四", "user_status": "Enabled"},
    {"station_id": "1002", "user_id": "203", "user_name": "王五", "user_status": "Disabled"},
    {"station_id": "5", "user_id": "204", "user_name": "孙七", "user_status": "Enabled"},
]


def _built_catalog() -> dict:
    return build_catalog(STATION_ROWS, MANAGER_ROWS)


def _fake_loader(catalog=None):
    payload = catalog if catalog is not None else _built_catalog()

    async def _loader(refresh: bool = False) -> dict:
        return {**payload, "from_cache": not refresh}

    return _loader


# ---------------------------------------------------------------- 目录构建

def test_build_catalog_normalizes_rows_and_aggregates_managers():
    catalog = _built_catalog()

    assert catalog["station_count"] == 4
    assert catalog["main_net_count"] == 3
    assert catalog["component_count"] == 1

    stations = {item["station_id"]: item for item in catalog["stations"]}
    conghua = stations["1001"]
    assert conghua["station_type"] == "省控"
    assert conghua["station_category"] == "regular"
    assert conghua["managers"] == ["张三", "李四"]

    component = stations["5"]
    assert component["station_category"] == "component"
    assert component["station_type_name"] == "组分站"
    assert component["operation_unit_name"] == ""
    assert component["longitude"] is None
    assert component["managers"] == ["孙七"]

    huacheng = stations["1002"]
    # 停用账号（Disabled）不入名册
    assert huacheng["managers"] == []

    town = stations["2001"]
    assert town["station_type"] == "乡镇控"
    assert town["station_category"] == "township"


def test_build_catalog_dedups_duplicate_manager_rows():
    catalog = build_catalog(STATION_ROWS[:1], MANAGER_ROWS[:3])
    assert catalog["station_count"] == 1
    assert catalog["stations"][0]["managers"] == ["张三", "李四"]


# ---------------------------------------------------------------- 停用站屏蔽

def _rows_with_disabled_stations() -> list[dict]:
    disabled_numeric = {
        **STATION_ROWS[0],
        "station_id": "1099",
        "station_code": "GZ0999",
        "station_name": "旧火车站监测点",
        "unique_code": "8099A",
        "status": 0,
    }
    disabled_text = {
        **STATION_ROWS[0],
        "station_id": "1098",
        "station_code": "GZ0998",
        "station_name": "文本停用站",
        "unique_code": "8098A",
        "status": "0",
    }
    unknown_status = {
        **STATION_ROWS[0],
        "station_id": "1097",
        "station_code": "GZ0997",
        "station_name": "状态未知站",
        "unique_code": "8097A",
        "status": None,
    }
    return STATION_ROWS + [disabled_numeric, disabled_text, unknown_status]


def test_build_catalog_masks_disabled_stations():
    catalog = build_catalog(_rows_with_disabled_stations(), [])

    # status=0（数值与文本）视为停用并剔除；status 为空的未知值保留（宁多勿漏）
    assert catalog["masked_inactive_count"] == 2
    ids = {item["station_id"] for item in catalog["stations"]}
    assert "1099" not in ids
    assert "1098" not in ids
    assert "1097" in ids
    assert catalog["station_count"] == 5


def test_disabled_stations_invisible_to_resolve_and_provider():
    catalog = build_catalog(_rows_with_disabled_stations(), [])

    assert resolve_stations(catalog, keyword="旧火车站") == []
    assert resolve_stations(catalog, station_codes=["8099A", "GZ0999"]) == []
    active = resolve_stations(catalog, cities=["广州"])
    assert "1099" not in {item["station_id"] for item in active}


@pytest.mark.asyncio
async def test_disabled_stations_hidden_from_provider_and_tool():
    from app.services.station_directory import StationQuery

    catalog = build_catalog(_rows_with_disabled_stations(), [])
    provider = GuangdongStationCatalogProvider(catalog_loader=_fake_loader(catalog))
    tool = GuangdongStationCatalogTool(provider=provider)

    records = await provider.list_stations(StationQuery())
    assert "GZ0999" not in {record.station_code for record in records}

    result = await tool.execute(keyword="停用")
    assert result["status"] == "empty"
    assert result["metadata"]["masked_inactive_count"] == 2

    refresh = await tool.execute(action="refresh")
    assert refresh["metadata"]["masked_inactive_count"] == 2


# ---------------------------------------------------------------- 解析逻辑

def test_resolve_stations_by_fuzzy_name_and_codes():
    catalog = _built_catalog()

    by_name = resolve_stations(catalog, station_names=["天湖"])
    assert [item["station_id"] for item in by_name] == ["1001"]

    by_unique_code = resolve_stations(catalog, station_codes=["8001A"])
    assert [item["station_name"] for item in by_unique_code] == ["从化天湖"]

    by_station_id = resolve_stations(catalog, station_codes=["1002"])
    assert [item["station_name"] for item in by_station_id] == ["花城广场"]

    assert resolve_stations(catalog, station_codes=["不存在"]) == []


def test_resolve_stations_by_city_type_unit_manager_keyword():
    catalog = _built_catalog()

    by_city = resolve_stations(catalog, cities=["广州市"])
    assert {item["station_id"] for item in by_city} == {"1001", "1002", "5"}

    by_type_label = resolve_stations(catalog, station_types=["组分站"])
    assert [item["station_id"] for item in by_type_label] == ["5"]

    by_type_canonical = resolve_stations(catalog, station_types=["国控"])
    assert [item["station_id"] for item in by_type_canonical] == ["1002"]

    by_type_all = resolve_stations(catalog, station_types=["全部"])
    assert len(by_type_all) == 4

    by_unit = resolve_stations(catalog, operation_units=["佛山环监"])
    assert [item["station_id"] for item in by_unit] == ["2001"]

    by_manager = resolve_stations(catalog, managers=["张三"])
    assert [item["station_id"] for item in by_manager] == ["1001"]

    # alm_home 管理人（manager_name）也参与人员匹配
    by_manager_name = resolve_stations(catalog, managers=["赵六"])
    assert [item["station_id"] for item in by_manager_name] == ["1002"]

    by_keyword = resolve_stations(catalog, keyword="温泉镇")
    assert [item["station_id"] for item in by_keyword] == ["1001"]

    limited = resolve_stations(catalog, cities=["广州"], limit=2)
    assert len(limited) == 2


def test_resolve_stations_combined_filters_are_anded():
    catalog = _built_catalog()

    combined = resolve_stations(
        catalog, cities=["广州"], station_types=["省控站"], managers=["李四"]
    )
    assert [item["station_id"] for item in combined] == ["1001"]

    empty = resolve_stations(
        catalog, cities=["广州"], station_types=["组分站"], operation_units=["南的环境"]
    )
    assert empty == []


# ---------------------------------------------------------------- provider 契约

@pytest.mark.asyncio
async def test_provider_returns_canonical_records():
    from app.services.station_directory import StationQuery

    provider = GuangdongStationCatalogProvider(catalog_loader=_fake_loader())

    records = await provider.list_stations(StationQuery(station_types=("省控",)))
    assert [record.station_code for record in records] == ["GZ0101"]
    assert records[0].station_name == "从化天湖"
    assert records[0].city == "广州"
    assert records[0].unique_code == "8001A"
    assert records[0].station_category == "regular"
    assert records[0].longitude == pytest.approx(113.589)

    component_records = await provider.list_stations(
        StationQuery(station_categories=("component",))
    )
    assert [record.station_code for record in component_records] == ["SC005"]
    assert component_records[0].station_category == "component"

    township_records = await provider.list_stations(
        StationQuery(station_categories=("township",))
    )
    assert [record.station_code for record in township_records] == ["FS0201"]


@pytest.mark.asyncio
async def test_provider_get_station_by_code():
    from app.services.station_directory import StationQuery

    provider = GuangdongStationCatalogProvider(catalog_loader=_fake_loader())

    station = await provider.get_station("8001A")
    assert station is not None and station.station_name == "从化天湖"

    resolution = await provider.resolve(
        StationQuery(station_names=["花城"], station_codes=["不存在"])
    )
    assert [record.station_code for record in resolution.stations] == ["GZ0102"]
    assert resolution.unresolved_codes == ["不存在"]
    assert resolution.metadata["provider"] == "guangdong_station_catalog"


# ---------------------------------------------------------------- 工具三态

@pytest.mark.asyncio
async def test_catalog_tool_lookup_success():
    provider = GuangdongStationCatalogProvider(catalog_loader=_fake_loader())
    tool = GuangdongStationCatalogTool(provider=provider)

    result = await tool.execute(stations=["天湖"])

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["data"][0]["station_id"] == "1001"
    assert result["data"][0]["operation_unit_name"] == "广州南的环境检测有限公司"
    assert result["data"][0]["managers"] == ["张三", "李四"]
    assert result["metadata"]["directory_total"] == 4
    assert "源系统未提供" not in result["summary"]


@pytest.mark.asyncio
async def test_catalog_tool_lookup_notes_component_gap():
    provider = GuangdongStationCatalogProvider(catalog_loader=_fake_loader())
    tool = GuangdongStationCatalogTool(provider=provider)

    result = await tool.execute(station_types=["组分站"])

    assert result["status"] == "success"
    assert result["metadata"]["component_count"] == 1
    assert "组分站无经纬度/运维单位/运维人员" in result["summary"]


@pytest.mark.asyncio
async def test_catalog_tool_lookup_empty_gives_city_hint():
    provider = GuangdongStationCatalogProvider(catalog_loader=_fake_loader())
    tool = GuangdongStationCatalogTool(provider=provider)

    result = await tool.execute(stations=["不存在的站"])

    assert result["status"] == "empty"
    assert result["success"] is True
    assert "可用城市" in result["summary"]
    assert "广州" in result["metadata"]["available_cities"]


@pytest.mark.asyncio
async def test_catalog_tool_lookup_failed_without_dsn(monkeypatch):
    monkeypatch.delenv(catalog_module.DSN_ENV, raising=False)
    monkeypatch.setattr(catalog_module, "_memory_cache", None)
    monkeypatch.setattr(catalog_module._DISK_CACHE, "load", lambda: None)
    provider = GuangdongStationCatalogProvider(
        catalog_loader=lambda refresh: load_catalog(refresh)
    )
    tool = GuangdongStationCatalogTool(provider=provider)

    result = await tool.execute(stations=["从化天湖"])

    assert result["status"] == "failed"
    assert result["success"] is False
    assert "OPS_MART_DATABASE_URL" in result["error"]


@pytest.mark.asyncio
async def test_catalog_tool_refresh_action():
    calls = []

    async def loader(refresh: bool = False) -> dict:
        calls.append(refresh)
        return {**_built_catalog(), "from_cache": not refresh}

    tool = GuangdongStationCatalogTool(
        provider=GuangdongStationCatalogProvider(catalog_loader=loader)
    )

    result = await tool.execute(action="refresh")

    assert calls == [True]
    assert result["status"] == "success"
    assert "重建" in result["summary"]

    failed = GuangdongStationCatalogTool(
        provider=GuangdongStationCatalogProvider(
            catalog_loader=_raising_loader(StationCatalogError("OPS_MART_DATABASE_URL 未配置"))
        )
    )
    result = await failed.execute(action="refresh")
    assert result["status"] == "failed"


def _raising_loader(exc: Exception):
    async def _loader(refresh: bool = False) -> dict:
        raise exc

    return _loader


@pytest.mark.asyncio
async def test_catalog_tool_limit_normalization():
    provider = GuangdongStationCatalogProvider(catalog_loader=_fake_loader())
    tool = GuangdongStationCatalogTool(provider=provider)

    result = await tool.execute(cities=["广州"], limit=2)
    assert len(result["data"]) == 2
    assert "已达返回上限" in result["summary"]


# ---------------------------------------------------------------- 注册与契约

def test_guangdong_registers_station_catalog_tool():
    from app.project_config.loader import load_project_context
    from app.services.station_directory import (
        get_station_directory_provider,
        get_station_directory_registry,
    )
    from app.tools import create_global_tool_registry

    get_station_directory_registry().clear()
    try:
        registry = create_global_tool_registry(context=load_project_context("guangdong"))
        assert "guangdong_station_catalog" in registry.list_tools()

        provider = get_station_directory_provider("guangdong")
        assert provider is not None
        assert provider.name == "guangdong_station_catalog"

        other_registry = create_global_tool_registry(
            context=load_project_context("jiangxi")
        )
        assert "guangdong_station_catalog" not in other_registry.list_tools()
    finally:
        get_station_directory_registry().clear()


def test_mart_contract_exposes_dim_station_user():
    from app.tools.query.guangdong_ops_sql_query import tool as sql_tool_module

    assert "dim_station_user" in sql_tool_module.MART_TABLES
    assert "sys_userstation" not in set(sql_tool_module.ODS_TABLES)
    assert "sys_departmentstation" in set(sql_tool_module.ODS_TABLES)
