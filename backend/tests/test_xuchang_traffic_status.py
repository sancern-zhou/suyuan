# -*- coding: utf-8 -*-
"""许昌站点周边实时路况查询工具测试。

SN 签名回归向量以百度官方算法（quote -> 拼 SK -> quote_plus -> md5）计算，
与 2026-10 对线上接口实测通过的实现一致；网络交互全部 mock，不打真实接口。
"""
from __future__ import annotations

import pytest

from app.project_config.loader import load_project_context
from app.tools import create_global_tool_registry
from app.tools.xuchang.traffic_status.client import (
    BAIDU_TRAFFIC_BASE_URL,
    BaiduTrafficClient,
    BaiduTrafficError,
)
from app.tools.xuchang.traffic_status.signing import build_signed_url, calc_sn
from app.tools.xuchang.traffic_status.tool import XuchangTrafficStatusTool

AROUND_PARAMS = {
    "ak": "testak",
    "center": "33.998056,113.857222",
    "coord_type_input": "wgs84",
    "coord_type_output": "gcj02",
    "radius": "1000",
    "road_grade": "0",
}

AROUND_RESPONSE = {
    "status": 0,
    "message": "成功",
    "description": "该区域整体畅通。",
    "evaluation": {"status": 1, "status_desc": "畅通"},
    "road_traffic": [
        {"road_name": "京深线"},
        {
            "road_name": "学院南路",
            "congestion_sections": [
                {
                    "status": 3,
                    "speed": 12,
                    "congestion_distance": 380,
                    "congestion_trend": "加重",
                    "section_desc": "学院南路（建设路口附近）拥堵",
                }
            ],
        },
    ],
}

ROAD_RESPONSE = {
    "status": 0,
    "message": "成功",
    "description": "建安大道：双向畅通。",
    "evaluation": {"status": 1, "status_desc": "双向畅通"},
    "congestion_sections": [],
}


class StubClient:
    """替身客户端，记录请求参数并返回固定响应。"""

    def __init__(self, around=AROUND_RESPONSE, road=ROAD_RESPONSE):
        self.around_response = around
        self.road_response = road
        self.around_calls: list[dict] = []
        self.road_calls: list[dict] = []

    async def query_around(self, **kwargs):
        self.around_calls.append(kwargs)
        return self.around_response

    async def query_road(self, **kwargs):
        self.road_calls.append(kwargs)
        return self.road_response


def test_calc_sn_matches_official_algorithm_vector():
    # 用假凭证生成的回归向量，锁定官方算法行为
    assert calc_sn("/traffic/v1/around", AROUND_PARAMS, "testsk") == (
        "68ce5625cb1cbbc90686078fcccddc9c"
    )


def test_build_signed_url_sorts_params_and_appends_sn_last():
    url = build_signed_url(
        BAIDU_TRAFFIC_BASE_URL,
        "/traffic/v1/road",
        {"city": "许昌市", "road_name": "建安大道"},
        "testak",
        "testsk",
    )
    assert url.startswith(f"{BAIDU_TRAFFIC_BASE_URL}/traffic/v1/road?ak=testak&")
    # 参数按 key 字典序：ak, city, road_name；值做单次百分号编码；sn 固定在最后
    assert "city=%E8%AE%B8%E6%98%8C%E5%B8%82" in url
    assert "road_name=%E5%BB%BA%E5%AE%89%E5%A4%A7%E9%81%93" in url
    assert url.index("&sn=") > url.index("road_name=")
    assert len(url.rsplit("&sn=", 1)[1]) == 32


async def test_client_query_around_normalizes_params():
    captured: dict = {}

    async def fake_fetch(url: str) -> dict:
        captured["url"] = url
        return {"status": 0}

    client = BaiduTrafficClient(ak="testak", sk="testsk")
    client._fetch = fake_fetch  # type: ignore[method-assign]

    payload = await client.query_around(
        latitude=33.998056123,
        longitude=113.857222789,
        radius=2000,
        coord_type="wgs84",
    )

    assert payload == {"status": 0}
    # 半径截断到接口上限；坐标四舍五入到 6 位小数且为“纬度,经度”顺序（逗号属于保留字符不编码）
    assert "radius=1000" in captured["url"]
    assert "center=33.998056,113.857223" in captured["url"]
    assert "coord_type_input=wgs84" in captured["url"]
    assert "coord_type_output=gcj02" in captured["url"]


async def test_client_raises_on_business_error():
    async def fake_fetch(url: str) -> dict:
        return {"status": 211, "message": "APP SN校验失败"}

    client = BaiduTrafficClient(ak="testak", sk="testsk")
    client._fetch = fake_fetch  # type: ignore[method-assign]

    with pytest.raises(BaiduTrafficError) as excinfo:
        await client.query_around(latitude=34.0, longitude=113.8)

    assert "211" in str(excinfo.value)


async def test_client_requires_credentials(monkeypatch):
    monkeypatch.delenv("BAIDU_MAP_AK", raising=False)
    monkeypatch.delenv("BAIDU_MAP_SK", raising=False)

    client = BaiduTrafficClient()
    with pytest.raises(BaiduTrafficError):
        await client.query_road(road_name="建安大道")


async def test_tool_around_success_shape():
    stub = StubClient()
    tool = XuchangTrafficStatusTool(client=stub)  # type: ignore[arg-type]

    result = await tool.execute(latitude=33.998056, longitude=113.857222, radius=1000)

    assert result["success"] is True
    assert result["status"] == "success"
    assert stub.around_calls[0]["radius"] == 1000
    data = result["data"]
    assert data["evaluation"]["status_desc"] == "畅通"
    assert data["roads"][1]["road_name"] == "学院南路"
    assert data["roads"][1]["congestion_sections"][0]["speed"] == 12
    assert "1 个拥堵路段" in result["summary"]


async def test_tool_around_without_coordinates_fails():
    tool = XuchangTrafficStatusTool(client=StubClient())  # type: ignore[arg-type]

    result = await tool.execute()

    assert result["success"] is False
    assert "latitude" in result["error"]


async def test_tool_road_success_shape():
    stub = StubClient()
    tool = XuchangTrafficStatusTool(client=stub)  # type: ignore[arg-type]

    result = await tool.execute(query_type="road", road_name="建安大道")

    assert result["success"] is True
    assert stub.road_calls[0] == {"road_name": "建安大道", "city": "许昌市"}
    assert result["data"]["evaluation"]["status_desc"] == "双向畅通"
    assert result["summary"].startswith("许昌市 建安大道：双向畅通")


async def test_tool_reports_client_error():
    class FailingClient:
        async def query_around(self, **_):
            raise BaiduTrafficError(211, "APP SN校验失败（status=211；SN 校验失败）")

    result = await XuchangTrafficStatusTool(client=FailingClient()).execute(  # type: ignore[arg-type]
        latitude=34.0, longitude=113.8
    )

    assert result["success"] is False
    assert "211" in result["error"]


def test_xuchang_registers_traffic_status_tool():
    context = load_project_context("xuchang")

    registry = create_global_tool_registry(context=context)

    assert "query_xuchang_traffic_status" in registry.list_tools()


def test_other_projects_do_not_register_traffic_status_tool():
    context = load_project_context("jiangxi")

    registry = create_global_tool_registry(context=context)

    assert "query_xuchang_traffic_status" not in registry.list_tools()
