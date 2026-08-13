import pytest

from app.tools.jiangsu.station_data import JiangsuStationDataTool


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
