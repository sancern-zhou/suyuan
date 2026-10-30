"""广东三套站点体系的站点地理工具守卫。

体系划分（共用 station_directory 底座，互不混用）：
- monitoring_station_catalog：监测平台站点地理快照（query / 监测问数子模式）
- component_station_catalog：组分接口 38 站清单 + 城市归属 + 组分监测能力（query_component，及监测子流程的名录解析）
- guangdong_station_catalog：运维台账 dim_station（运维模式）
"""

import json
from pathlib import Path

import pytest

from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.workflow.mode_workflows import current_phase, get_mode_workflow
from app.services.station_directory import StationQuery
from app.tools.guangdong.component_station_catalog.provider import (
    ComponentStationCatalogProvider,
)
from app.tools.guangdong.component_station_catalog.tool import (
    _normalize_component_types,
)
from app.tools.guangdong.monitoring_station_catalog.provider import (
    MonitoringStationCatalogProvider,
)


def _geo_mappings() -> dict:
    path = Path(__file__).resolve().parents[1] / "app" / "config" / "geo_mappings.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_component_station_geo_is_complete_and_city_attributed():
    data = _geo_mappings()
    stations = data["stations"]
    geo = data["station_geo"]
    capabilities = data["station_capabilities"]
    assert set(geo) == set(stations)
    assert all(item["city"] for item in geo.values())
    # 每站必须有组分监测能力标注（vocs/pm25；无任何监测能力的对比方站允许
    # 为空列表），VOCs 属性站与颗粒物组分站不是同一批站
    # （2026-07~09 接口原始数据实测：vocs 31 站、pm25 离子 13 站）
    assert set(capabilities) == set(stations)
    for domains in capabilities.values():
        assert set(domains) <= {"vocs", "pm25"}
    vocs_count = sum(1 for domains in capabilities.values() if "vocs" in domains)
    pm25_count = sum(1 for domains in capabilities.values() if "pm25" in domains)
    assert vocs_count == 31
    assert pm25_count == 13
    # 深圳莲花山：有 VOCs 原始监测、无水溶性离子——两类能力不可混为一谈
    assert capabilities["莲花山"] == ["vocs"]


@pytest.mark.asyncio
async def test_component_catalog_resolves_guangzhou_component_stations():
    provider = ComponentStationCatalogProvider()
    records = await provider.list_stations(None)
    assert len(records) == 38
    assert all(record.city for record in records)
    assert all(record.station_code.endswith("b") for record in records)
    # 能力标注随目录透传到 data_domains（无能力的对比方站为空元组）
    assert all(isinstance(record.data_domains, tuple) for record in records)

    guangzhou = await provider.list_stations(StationQuery.create(cities=["广州"]))
    assert sorted((r.station_name, r.station_code) for r in guangzhou) == [
        ("从化天湖", "1004b"),
        ("公园前", "1006b"),
        ("南沙科大", "1007b"),
    ]
    # 派生对比方站随母站归属，且无 VOCs 监测能力
    derived = await provider.list_stations(StationQuery.create(cities=["江门"]))
    names = {record.station_name for record in derived}
    assert {"鹤山花果山 3", "鹤山花果山 (对比方 1)"} <= names
    by_name = {record.station_name: record for record in derived}
    assert "vocs" not in by_name["鹤山花果山 3"].data_domains
    assert "vocs" in by_name["鹤山花果山"].data_domains


@pytest.mark.asyncio
async def test_monitoring_catalog_uses_admin_code_city():
    provider = MonitoringStationCatalogProvider()
    records = await provider.list_stations(None)
    assert len(records) >= 400
    # 仅流动监测车无固定城市归属，其余站点城市字段必须可解析
    missing_city = [record for record in records if not record.city]
    assert all("监测车" in record.station_name for record in missing_city)

    guangzhou = await provider.list_stations(StationQuery.create(cities=["广州"]))
    assert guangzhou
    # 快照城市字段有少量错误，行政区划码校正后区域站不再错归广州
    assert all(record.station_name != "广东南岭" for record in guangzhou)

    national = await provider.list_stations(StationQuery.create(station_types=["国控"]))
    assert national
    assert {record.station_type for record in national} == {"国控"}


@pytest.mark.asyncio
async def test_catalog_tools_return_stable_payload():
    from app.tools.guangdong.component_station_catalog.tool import (
        ComponentStationCatalogTool,
    )
    from app.tools.guangdong.monitoring_station_catalog.tool import (
        MonitoringStationCatalogTool,
    )

    component = await ComponentStationCatalogTool().execute(cities=["广州市"])
    assert component["success"] is True
    assert component["status"] == "success"
    assert component["metadata"]["station_count"] == 3
    assert component["data"][0]["station_code"].endswith("b")
    assert {"station_name", "city", "district", "station_category"} <= set(component["data"][0])
    # 能力标注进 payload：data_domains 为规范域，component_capabilities 为中文标签
    assert {"data_domains", "component_capabilities"} <= set(component["data"][0])

    # 深圳有组分站（莲花山，VOCs）但无水溶性离子——按"颗粒物组分"过滤必须
    # 得到带解释的 empty，而不是把"没有这类组分站"误报成"没有组分站"。
    shenzhen_vocs = await ComponentStationCatalogTool().execute(
        cities=["深圳市"], component_types=["VOCs"]
    )
    assert shenzhen_vocs["status"] == "success"
    assert [(item["station_name"], item["station_code"]) for item in shenzhen_vocs["data"]] == [
        ("莲花山", "1011b")
    ]
    assert shenzhen_vocs["data"][0]["data_domains"] == ["vocs"]

    shenzhen_pm25 = await ComponentStationCatalogTool().execute(
        cities=["深圳市"], component_types=["颗粒物组分"]
    )
    assert shenzhen_pm25["status"] == "empty"
    assert shenzhen_pm25["success"] is True
    assert "莲花山" in shenzhen_pm25["summary"]
    assert "不具备" in shenzhen_pm25["summary"]

    # 全省 VOCs 能力站过滤（31 站）与无法识别的类型别名
    all_vocs = await ComponentStationCatalogTool().execute(component_types=["VOCs"])
    assert all_vocs["metadata"]["station_count"] == 31
    assert _normalize_component_types(["VOCs", "颗粒物组分"]) == ("vocs", "pm25")
    assert _normalize_component_types(["胡话"]) == ()

    empty = await ComponentStationCatalogTool().execute(cities=["云浮"])
    assert empty["status"] == "empty"
    assert empty["success"] is True

    monitoring = await MonitoringStationCatalogTool().execute(cities=["广州市"], limit=5)
    assert monitoring["success"] is True
    assert len(monitoring["data"]) <= 5
    assert monitoring["metadata"]["directory_total"] >= 400


def test_guangdong_whitelists_use_system_matched_geo_tools():
    query_tools = get_tools_by_mode("query")
    assert "monitoring_station_catalog" in query_tools
    # 组分站名录/组分能力问题在综合问数主链路就地可答（目录带能力标注）
    assert "component_station_catalog" in query_tools
    # 运维台账目录不进监测问数（两套体系不混用）
    assert "guangdong_station_catalog" not in query_tools

    for mode in ("query_monitoring", "query_monitoring_station", "query_forecast"):
        tools = set(get_tools_by_mode(mode))
        phase_tools = set(current_phase(get_mode_workflow(mode), {}).allowed_tools)
        assert "monitoring_station_catalog" in tools & phase_tools
        assert "guangdong_station_catalog" not in tools & phase_tools

    # 监测/站点子流程携带组分目录（名录与能力问题就地可答）；预报子流程不带
    for mode in ("query_monitoring", "query_monitoring_station"):
        tools = set(get_tools_by_mode(mode))
        phase_tools = set(current_phase(get_mode_workflow(mode), {}).allowed_tools)
        assert "component_station_catalog" in tools & phase_tools
    forecast_phase = set(current_phase(get_mode_workflow("query_forecast"), {}).allowed_tools)
    assert "component_station_catalog" not in forecast_phase

    component_tools = set(get_tools_by_mode("query_component"))
    component_phase = set(current_phase(get_mode_workflow("query_component"), {}).allowed_tools)
    assert "component_station_catalog" in component_tools & component_phase

    # 城市层级子模式不携带任何站点目录（站点任务归 station 子模式）
    for mode in ("query_monitoring_city",):
        tools = set(get_tools_by_mode(mode))
        phase_tools = set(current_phase(get_mode_workflow(mode), {}).allowed_tools)
        visible = tools & phase_tools
        assert not visible & {
            "monitoring_station_catalog",
            "component_station_catalog",
            "guangdong_station_catalog",
        }


@pytest.mark.asyncio
async def test_component_resolver_blocks_uncapable_stations_for_vocs():
    from app.tools.query.component_station_resolver import resolve_component_station

    # 深圳莲花山有 VOCs：正常放行并解析编码
    station, code, error = resolve_component_station(
        locations=None, station="莲花山", code=None, require_domain="vocs"
    )
    assert error is None
    assert (station, code) == ("莲花山", "1011b")

    # 牛牯岭无 VOCs 监测：拦截并给出有能力站点清单，避免拿占位空值当数据
    station, code, error = resolve_component_station(
        locations=None, station="牛牯岭", code=None, require_domain="vocs"
    )
    assert station is None and code is None
    assert error is not None
    assert "牛牯岭" in error["error"]
    assert "鹤山花果山=1001b" in error["error"]

    # 无 require_domain 时不拦截（保持原语义）
    station, code, error = resolve_component_station(
        locations=None, station="牛牯岭", code=None
    )
    assert error is None
    assert station == "牛牯岭"
