from datetime import datetime
from typing import Any

import pytest

from app.external_apis.jiangxi_noise_api_client import JiangxiNoiseDataClient
from app.tools.query.query_jiangxi_noise import (
    QueryJiangxiNoiseCityHourTool,
    QueryJiangxiNoiseStationDayTool,
    QueryJiangxiNoiseStationHourTool,
    QueryJiangxiNoiseStationMinuteTool,
    QueryJiangxiNoiseStationStatisticsTool,
)

START = "2026-07-30T00:00:00+08:00"
END = "2026-07-30T01:00:00+08:00"


class FakeNoiseClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def _result(self, method: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, kwargs))
        if method == "city_hour":
            record = {
                "cityCode": "360100",
                "cityName": "南昌市",
                "timePointStr": "2026-07-30 00:00:00",
                "leq_1": "52.1",
            }
        else:
            record = {
                "code": kwargs["station_codes"][0],
                "timePoint": "2026-07-30 00:00:00",
                "leq": "55.1",
                "ldn": "54.2",
            }
        return {"data": [record], "total_count": 1}

    async def query_city_hour_data(self, **kwargs: Any) -> dict[str, Any]:
        return await self._result("city_hour", kwargs)

    async def query_station_minute_data(self, **kwargs: Any) -> dict[str, Any]:
        return await self._result("station_minute", kwargs)

    async def query_station_hour_data(self, **kwargs: Any) -> dict[str, Any]:
        return await self._result("station_hour", kwargs)

    async def query_station_day_data(self, **kwargs: Any) -> dict[str, Any]:
        return await self._result("station_day", kwargs)

    async def query_station_statistics_data(self, **kwargs: Any) -> dict[str, Any]:
        return await self._result("station_statistics", kwargs)


@pytest.mark.asyncio
async def test_split_noise_tools_route_to_dedicated_client_methods() -> None:
    client = FakeNoiseClient()
    tools = [
        QueryJiangxiNoiseCityHourTool(client),
        QueryJiangxiNoiseStationMinuteTool(client),
        QueryJiangxiNoiseStationHourTool(client),
        QueryJiangxiNoiseStationDayTool(client),
        QueryJiangxiNoiseStationStatisticsTool(client),
    ]

    city_result = await tools[0].execute(
        cities=["南昌"],
        start_time=START,
        end_time=END,
    )
    station_results = [
        await tool.execute(
            station_codes=["1737A"],
            start_time=START,
            end_time=END,
        )
        for tool in tools[1:]
    ]

    assert city_result["status"] == "success"
    assert all(result["status"] == "success" for result in station_results)
    assert [name for name, _ in client.calls] == [
        "city_hour",
        "station_minute",
        "station_hour",
        "station_day",
        "station_statistics",
    ]
    assert client.calls[0][1]["data_type"] == 1
    assert client.calls[1][1]["data_type"] == 0
    assert client.calls[2][1]["data_type"] == 1
    assert client.calls[3][1]["data_type"] == 1
    assert client.calls[4][1]["data_type"] == 0

    station_metadata = station_results[1]["metadata"]["stations"]["1737A"]
    assert station_metadata == {
        "station_name": "东湖区大院街道",
        "city_name": "南昌市",
        "longitude": "115.9128",
        "latitude": "28.6816",
        "functional_area": {"type": "2", "name": "2类功能区"},
    }
    assert "longitude" not in station_results[1]["data"][0]
    assert "latitude" not in station_results[1]["data"][0]


@pytest.mark.asyncio
async def test_client_uses_recovered_minute_and_statistics_endpoints() -> None:
    client = object.__new__(JiangxiNoiseDataClient)
    captured: list[tuple[str, dict[str, Any]]] = []

    async def request(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        captured.append((endpoint, params))
        return {"items": [], "totalCount": 0}

    client._request_result = request

    common = {
        "station_codes": ["1737A"],
        "start_time": datetime.fromisoformat(START),
        "end_time": datetime.fromisoformat(END),
        "data_type": 1,
        "max_result_count": 25,
        "skip_count": 50,
    }
    await client.query_station_minute_data(**common)
    await client.query_station_statistics_data(**common)

    assert captured[0][0].endswith(
        "/DATStationMinute/GetDATStationMinuteDisplayPagedListAsync"
    )
    assert captured[1][0].endswith(
        "/DATStationDay/GetNoiseStationAnyDateDisplayPagedListAsync"
    )
    for _, params in captured:
        assert params["codes[0]"] == "1737A"
        assert params["dataType"] == 1
        assert params["maxResultCount"] == 25
        assert params["skipCount"] == 50
