import pytest

from app.tools.jiangsu.station_data import JiangsuStationDataTool


def test_station_tool_schema_only_exposes_city_selector():
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")
    parameters = tool.function_schema["parameters"]

    assert "city_names" in parameters["required"]
    assert "city_names" in parameters["properties"]
    assert "station_codes" not in parameters["properties"]
    assert "station_names" not in parameters["properties"]
    assert "district_names" not in parameters["properties"]
    assert parameters["properties"]["data_type"]["default"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("province_name", ["江苏省", "江苏", "全省", "江苏全省"])
async def test_station_tool_rejects_province_selector_before_directory_request(monkeypatch, province_name):
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")

    async def unexpected_directory_request():
        pytest.fail("省级查询不应访问站点目录或外部接口")

    monkeypatch.setattr(tool, "_get_station_directory", unexpected_directory_request)
    result = await tool.execute(
        data_kind="station_day",
        city_names=[province_name],
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-12 00:00:00",
    )

    assert result["success"] is False
    assert "不支持全省查询" in result["summary"]


@pytest.mark.asyncio
async def test_station_tool_rejects_non_city_selector():
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")
    result = await tool.execute(
        data_kind="station_hour",
        station_names=["玄武湖"],
        start_time="2026-08-12 00:00:00",
        end_time="2026-08-12 01:00:00",
    )

    assert result["success"] is False
    assert "只允许通过 city_names 按城市查询" in result["summary"]


@pytest.mark.asyncio
async def test_station_tool_resolves_city_and_batches_station_requests(monkeypatch):
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")
    directory = [
        {"stationCode": f"S{i}", "positionName": f"站点{i}", "cityName": "南京市", "districtName": "鼓楼区", "provinceName": "江苏省"}
        for i in range(101)
    ]
    requests = []

    async def get_directory():
        return directory

    async def request(data_kind, payload):
        assert payload["dataType"] == 1
        requests.append(payload["codes"])
        return {"result": [{"stationCode": code} for code in payload["codes"]]}

    monkeypatch.setattr(tool, "_get_station_directory", get_directory)
    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(
        data_kind="station_hour", city_names=["南京"],
        start_time="2026-08-12 00:00:00", end_time="2026-08-12 01:00:00",
    )

    assert result["success"] is True
    assert len(result["metadata"]["station_codes"]) == 101
    assert [len(item) for item in requests] == [100, 1]
