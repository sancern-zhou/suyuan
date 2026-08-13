import pytest

from app.tools.jiangsu.query_tools import JiangsuCityDataTool


@pytest.mark.asyncio
async def test_city_data_resolves_jiangsu_name_inside_the_query_tool(monkeypatch):
    tool = JiangsuCityDataTool()

    async def request(path, params):
        if path != "AirCityProductBase/GetBSDRegionAsync":
            return {"result": {"items": [], "totalCount": 0}}
        assert params == []
        return {"result": [
            {"areaCode": "320000", "areaName": "江苏省", "parentID": "0", "level": 1},
            {"areaCode": "320100", "areaName": "南京市", "parentID": "320000", "level": 2},
            {"areaCode": "320200", "areaName": "无锡市", "parentID": "320000", "level": 2},
            {"areaCode": "320101001", "areaName": "玄武区", "parentID": "320100", "level": 3},
        ]}

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        data_kind="city_hour", area_names=["江苏省"],
        start_time="2026-08-12 00:00:00", end_time="2026-08-12 23:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["codes"] == ["320100", "320200"]


@pytest.mark.asyncio
async def test_city_data_accepts_city_name_without_a_code(monkeypatch):
    tool = JiangsuCityDataTool()

    async def request(path, params):
        if path == "AirCityProductBase/GetBSDRegionAsync":
            return {"result": [{"areaCode": "320100", "areaName": "南京市", "parentID": "320000", "level": 2}]}
        return {"result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        data_kind="city_hour", area_names=["南京"],
        start_time="2026-08-12 00:00:00", end_time="2026-08-12 23:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["codes"] == ["320100"]
