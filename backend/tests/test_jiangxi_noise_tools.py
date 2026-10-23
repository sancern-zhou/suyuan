# -*- coding: utf-8 -*-
"""江西噪声数据获取工具测试：客户端请求编码 + 工具参数语义校验。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
import pytest

from app.external_apis.jiangxi_noise_api_client import JiangxiNoiseDataClient
from app.tools.query.query_jiangxi_noise.directory_tool import (
    GetJiangxiNoiseDirectoryTool,
)
from app.tools.query.query_jiangxi_noise.events_tool import GetJiangxiNoiseEventsTool
from app.tools.query.query_jiangxi_noise.runtime_tool import (
    GetJiangxiNoiseRuntimeStatusTool,
)
from app.tools.query.query_jiangxi_noise.stats_tool import (
    GetJiangxiNoiseStatisticsTool,
)
from app.tools.query.query_jiangxi_noise.tool import GetJiangxiNoiseDataTool
from app.tools.query.query_jiangxi_noise.trends_tool import GetJiangxiNoiseTrendsTool

pytestmark = pytest.mark.asyncio

TOKEN_PATH = "/api/noiseproduct/AirCityBaseCommon/GetExternalApiToken"
START = "2026-07-01T00:00:00+08:00"
END = "2026-07-02T00:00:00+08:00"


class FakePlatform:
    """记录请求并按路由返回固定结果的平台替身。"""

    def __init__(self, results: dict[str, Any] | None = None) -> None:
        self.results = results or {}
        self.requests: list[tuple[str, httpx.Request]] = []
        self.responses: list[int] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json={"success": True, "result": "token-1"})
        route = self._match_route(request.url.path)
        if route is None:
            return httpx.Response(404, json={"success": False})
        self.requests.append((route, request))
        if self.responses:
            return httpx.Response(self.responses.pop(0), json={})
        payload = self.results.get(route, {"items": [], "totalCount": 0})
        return httpx.Response(200, json={"success": True, "result": payload})

    @staticmethod
    def _match_route(path: str) -> str | None:
        for route, (_, endpoint) in JiangxiNoiseDataClient.API_ROUTES.items():
            if path == endpoint:
                return route
        for route, endpoint in JiangxiNoiseDataClient.API_ENDPOINTS.items():
            if path == endpoint:
                return route
        return None

    def last(self) -> tuple[str, httpx.Request]:
        assert self.requests, "没有发出任何平台请求"
        return self.requests[-1]


def make_client(fake: FakePlatform) -> JiangxiNoiseDataClient:
    return JiangxiNoiseDataClient(
        base_url="http://platform",
        username="user",
        secret_key="secret",
        transport=httpx.MockTransport(fake),
    )


def query_of(request: httpx.Request) -> dict[str, str]:
    return {key: value for key, value in request.url.params.items()}


def body_of(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


# ---------------------------------------------------------------------------
# 工具 schema 语义治理约束
# ---------------------------------------------------------------------------


def test_tool_schema_names_and_variants():
    tools = (
        GetJiangxiNoiseDataTool(),
        GetJiangxiNoiseStatisticsTool(),
        GetJiangxiNoiseTrendsTool(),
        GetJiangxiNoiseEventsTool(),
        GetJiangxiNoiseRuntimeStatusTool(),
        GetJiangxiNoiseDirectoryTool(),
    )
    for tool in tools:
        schema = tool.function_schema
        assert schema["name"] == tool.name
        for variant in schema["parameters"]["oneOf"]:
            assert variant.get("title"), f"{tool.name} 缺少变体中文标题"
            assert variant.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# 监测数据工具
# ---------------------------------------------------------------------------


async def test_monitor_station_hour_params():
    fake = FakePlatform({"station_hour": {"items": [{"code": "1737A"}], "totalCount": 1}})
    tool = GetJiangxiNoiseDataTool(client=make_client(fake))
    result = await tool.execute(
        scope="station",
        granularity="hour",
        station_codes=["1737A"],
        start_time=START,
        end_time=END,
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "station_hour"
    params = query_of(request)
    assert params["codes[0]"] == "1737A"
    assert params["dataType"] == "0"
    assert params["timePoint[0]"] == "2026-07-01 00:00:00"
    assert result["total_count"] == 1


async def test_monitor_month_report_params():
    fake = FakePlatform({"station_period_report": {"items": [], "totalCount": 0}})
    tool = GetJiangxiNoiseDataTool(client=make_client(fake))
    result = await tool.execute(
        scope="station",
        granularity="month",
        station_codes=["1737A"],
        start_time=START,
        end_time="2026-12-31T00:00:00+08:00",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "station_period_report"
    params = query_of(request)
    assert params["timeType"] == "40"
    assert params["timepoint[0]"] == "2026-07-01 00:00:00"
    assert params["codes[0]"] == "1737A"


async def test_monitor_second_uses_station_codes_param():
    fake = FakePlatform({"station_second": {"items": [], "totalCount": 0}})
    tool = GetJiangxiNoiseDataTool(client=make_client(fake))
    result = await tool.execute(
        scope="station",
        granularity="second",
        station_codes=["1737A"],
        start_time=START,
        end_time="2026-07-01T01:00:00+08:00",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "station_second"
    assert query_of(request)["stationCodes[0]"] == "1737A"


async def test_monitor_minute_range_limit():
    tool = GetJiangxiNoiseDataTool(client=make_client(FakePlatform()))
    result = await tool.execute(
        scope="station",
        granularity="minute",
        station_codes=["1737A"],
        start_time=START,
        end_time="2026-07-20T00:00:00+08:00",
    )
    assert result["success"] is False
    assert result["error_code"] == "time_range_too_large"


async def test_monitor_district_day_params():
    fake = FakePlatform({"district_day": {"items": [], "totalCount": 0}})
    tool = GetJiangxiNoiseDataTool(client=make_client(fake))
    result = await tool.execute(
        scope="district",
        granularity="day",
        district_codes=["360102"],
        start_time=START,
        end_time=END,
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "district_day"
    assert query_of(request)["codes[0]"] == "360102"


async def test_monitor_conflicting_locations():
    tool = GetJiangxiNoiseDataTool(client=make_client(FakePlatform()))
    result = await tool.execute(
        scope="station",
        granularity="hour",
        station_codes=["1737A"],
        city_names=["南昌市"],
        start_time=START,
        end_time=END,
    )
    assert result["success"] is False
    assert result["error_code"] == "conflicting_locations"


# ---------------------------------------------------------------------------
# 统计评价工具
# ---------------------------------------------------------------------------


async def test_stats_station_period_stats_body():
    fake = FakePlatform({"station_period_stats": [{"stationCode": "1737A"}]})
    tool = GetJiangxiNoiseStatisticsTool(client=make_client(fake))
    result = await tool.execute(
        report="station_period_stats",
        period="month",
        station_codes=["1737A"],
        start_time=START,
        end_time="2026-09-30T00:00:00+08:00",
        review_status="audited",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "station_period_stats"
    body = body_of(request)
    assert body["timeType"] == 40
    assert body["dataType"] == 1
    assert body["codes"] == ["1737A"]
    assert body["timePoint"] == ["2026-07-01 00:00:00", "2026-09-30 00:00:00"]
    assert result["data"] == [{"stationCode": "1737A"}]


async def test_stats_region_period_stats_body():
    fake = FakePlatform({"region_period_stats": []})
    tool = GetJiangxiNoiseStatisticsTool(client=make_client(fake))
    result = await tool.execute(
        report="region_period_stats",
        period="year",
        region_type="city",
        codes=["360100"],
        start_time=START,
        end_time="2026-12-31T00:00:00+08:00",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "region_period_stats"
    body = body_of(request)
    assert body["regionType"] == 2
    assert body["timeType"] == 55


async def test_stats_quality_summary_object_result():
    fake = FakePlatform(
        {"quality_summary": {"stationCount": 3, "overallQualifiedRate": 90.0}}
    )
    tool = GetJiangxiNoiseStatisticsTool(client=make_client(fake))
    result = await tool.execute(
        report="quality_summary",
        station_codes=["1737A"],
        start_time=START,
        end_time=END,
    )
    assert result["success"] is True
    assert result["data"]["stationCount"] == 3


async def test_stats_fun_evaluation_body():
    fake = FakePlatform({"fun_evaluation": []})
    tool = GetJiangxiNoiseStatisticsTool(client=make_client(fake))
    result = await tool.execute(
        report="fun_evaluation",
        period="quarter",
        area_type="city",
        codes=["360100"],
        start_time=START,
        end_time="2026-09-30T00:00:00+08:00",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "fun_evaluation"
    body = body_of(request)
    assert body["timeType"] == 5
    assert body["areaType"] == 1
    assert body["codes"] == ["360100"]


async def test_stats_district_month_rate_params():
    fake = FakePlatform({"district_month_rate": []})
    tool = GetJiangxiNoiseStatisticsTool(client=make_client(fake))
    result = await tool.execute(
        report="district_month_rate",
        month_time="2026-09-15T00:00:00+08:00",
        district_codes=["360102"],
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "district_month_rate"
    params = query_of(request)
    assert params["areaCodes[0]"] == "360102"
    assert params["timePoint[0]"] == "2026-09-15 00:00:00"


async def test_stats_region_ranking_yesterday_params():
    fake = FakePlatform({"region_noise_ranking": {"areaName": "南昌市"}})
    tool = GetJiangxiNoiseStatisticsTool(client=make_client(fake))
    result = await tool.execute(
        report="region_noise_ranking",
        period="yesterday",
        time_point="2026-10-22T00:00:00+08:00",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "region_noise_ranking"
    params = query_of(request)
    assert params["timeType"] == "昨日"
    assert params["timePoint[0]"] == "2026-10-22 00:00:00"


async def test_stats_invalid_report():
    tool = GetJiangxiNoiseStatisticsTool(client=make_client(FakePlatform()))
    result = await tool.execute(report="unknown")
    assert result["success"] is False
    assert result["error_code"] == "invalid_report"


async def test_stats_fun_period_must_be_quarter_or_year():
    tool = GetJiangxiNoiseStatisticsTool(client=make_client(FakePlatform()))
    result = await tool.execute(
        report="fun_evaluation",
        period="month",
        start_time=START,
        end_time=END,
    )
    assert result["success"] is False
    assert result["error_code"] == "invalid_period"


# ---------------------------------------------------------------------------
# 趋势对比工具
# ---------------------------------------------------------------------------


async def test_trends_year_on_year_body():
    fake = FakePlatform({"year_on_year": {"baseYear": 2025}})
    tool = GetJiangxiNoiseTrendsTool(client=make_client(fake))
    result = await tool.execute(
        trend="year_on_year",
        base_year=2025,
        compare_years=[2023, 2024],
        dimension="city",
        indicator="ld",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "year_on_year"
    body = body_of(request)
    assert body["baseYear"] == 2025
    assert body["compareYears"] == [2023, 2024]
    assert body["dimension"] == 1
    assert body["indicator"] == 1


async def test_trends_year_on_year_rejects_bad_years():
    tool = GetJiangxiNoiseTrendsTool(client=make_client(FakePlatform()))
    result = await tool.execute(
        trend="year_on_year",
        base_year=2025,
        compare_years=[2025, 2024],
        dimension="city",
        indicator="ld",
    )
    assert result["success"] is False
    assert result["error_code"] == "invalid_compare_years"


async def test_trends_24h_body():
    fake = FakePlatform({"trend_24h": {"stationCode": "1737A"}})
    tool = GetJiangxiNoiseTrendsTool(client=make_client(fake))
    result = await tool.execute(
        trend="trend_24h",
        station_code="1737A",
        monitor_date="2026-10-20T00:00:00+08:00",
        compare_date="2026-10-13T00:00:00+08:00",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "trend_24h"
    body = body_of(request)
    assert body["stationCode"] == "1737A"
    assert body["monitorDate"] == "2026-10-20 00:00:00"
    assert body["compareDate"] == "2026-10-13 00:00:00"


async def test_trends_compare_requires_codes():
    tool = GetJiangxiNoiseTrendsTool(client=make_client(FakePlatform()))
    result = await tool.execute(
        trend="compare",
        dimension="station",
        granularity="day",
        start_time=START,
        end_time=END,
    )
    assert result["success"] is False
    assert result["error_code"] == "missing_station_codes"


# ---------------------------------------------------------------------------
# 噪声源与事件工具
# ---------------------------------------------------------------------------


async def test_events_source_analysis_params():
    fake = FakePlatform(
        {"source_analysis": {"tableData": {"items": [], "totalCount": 0}}}
    )
    tool = GetJiangxiNoiseEventsTool(client=make_client(fake))
    result = await tool.execute(
        report="source_analysis",
        dimension="station",
        codes=["1737A"],
        start_time=START,
        end_time=END,
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "source_analysis"
    params = query_of(request)
    assert params["areaType"] == "3"
    assert params["codes[0]"] == "1737A"


async def test_events_event_list_params():
    fake = FakePlatform({"event_list": {"items": [{"leq": "60.1"}], "totalCount": 1}})
    tool = GetJiangxiNoiseEventsTool(client=make_client(fake))
    result = await tool.execute(
        report="event_list",
        station_codes=["1737A"],
        start_time=START,
        end_time=END,
        is_exceed=True,
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "event_list"
    params = query_of(request)
    assert params["dataTime[0]"] == "2026-07-01 00:00:00"
    assert params["isExceed"] == "true"
    assert result["total_count"] == 1


async def test_events_daily_summary_body():
    fake = FakePlatform({"event_daily_summary": {"xData": [], "ldData": []}})
    tool = GetJiangxiNoiseEventsTool(client=make_client(fake))
    result = await tool.execute(
        report="event_daily_summary",
        station_codes=["1737A"],
        start_time=START,
        end_time=END,
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "event_daily_summary"
    body = body_of(request)
    assert body["codes"] == ["1737A"]
    assert body["timePoint"] == ["2026-07-01 00:00:00", "2026-07-02 00:00:00"]


# ---------------------------------------------------------------------------
# 运行状态工具
# ---------------------------------------------------------------------------


async def test_runtime_network_overview_params():
    fake = FakePlatform(
        {"network_overview": {"totalCount": 10, "onlineCount": 8, "offlineCount": 2}}
    )
    tool = GetJiangxiNoiseRuntimeStatusTool(client=make_client(fake))
    result = await tool.execute(
        report="network_overview", city_code="360100", status_filter="offline"
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "network_overview"
    params = query_of(request)
    assert params["cityCode"] == "360100"
    assert params["stationStatus"] == "1"
    assert params["dataType"] == "2"


async def test_runtime_station_status_comma_joined():
    fake = FakePlatform({"station_network_status": []})
    tool = GetJiangxiNoiseRuntimeStatusTool(client=make_client(fake))
    result = await tool.execute(
        report="station_network_status",
        station_codes=["1737A", "1738B"],
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "station_network_status"
    assert query_of(request)["stationCode"] == "1737A,1738B"


async def test_runtime_receiving_rate_params():
    fake = FakePlatform({"data_receiving_rate": []})
    tool = GetJiangxiNoiseRuntimeStatusTool(client=make_client(fake))
    result = await tool.execute(
        report="data_receiving_rate",
        station_codes=["1737A"],
        start_time=START,
        end_time=END,
        rate_type="effective",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "data_receiving_rate"
    params = query_of(request)
    assert params["rateType"] == "1"
    assert params["startTime"] == "2026-07-01 00:00:00"


async def test_runtime_alarm_records_optional_filters():
    fake = FakePlatform({"alarm_records": {"items": [], "totalCount": 0}})
    tool = GetJiangxiNoiseRuntimeStatusTool(client=make_client(fake))
    result = await tool.execute(
        report="alarm_records", station_name="八一公园", max_results=10
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "alarm_records"
    params = query_of(request)
    assert params["stationName"] == "八一公园"
    assert "phone" not in params


# ---------------------------------------------------------------------------
# 目录工具
# ---------------------------------------------------------------------------


async def test_directory_station_filter_by_city():
    fake = FakePlatform(
        {
            "station_directory": [
                {"stationCode": "1737A", "positionName": "八一公园", "cityCode": "360100"},
                {"stationCode": "1738B", "positionName": "某站点", "cityCode": "360700"},
            ]
        }
    )
    tool = GetJiangxiNoiseDirectoryTool(client=make_client(fake))
    result = await tool.execute(target="station", city_names=["南昌市"])
    assert result["success"] is True
    route, _ = fake.last()
    assert route == "station_directory"
    assert result["total_count"] == 1
    assert result["data"][0]["stationCode"] == "1737A"


async def test_directory_region():
    fake = FakePlatform(
        {"region_directory": [{"areaCode": "360102", "areaName": "东湖区"}]}
    )
    tool = GetJiangxiNoiseDirectoryTool(client=make_client(fake))
    result = await tool.execute(target="region")
    assert result["success"] is True
    assert result["data"][0]["areaCode"] == "360102"


# ---------------------------------------------------------------------------
# 客户端行为
# ---------------------------------------------------------------------------


async def test_client_token_retry_on_401():
    fake = FakePlatform({"station_hour": {"items": [], "totalCount": 0}})
    fake.responses.append(401)
    client = make_client(fake)
    result = await client.query_station_hour_data(
        station_codes=["1737A"],
        start_time=datetime(2026, 7, 1),
        end_time=datetime(2026, 7, 2),
    )
    assert result["success"] is True
    data_requests = [r for route, r in fake.requests if route == "station_hour"]
    assert len(data_requests) == 2
    assert data_requests[0].headers["Authorization"] == "Bearer token-1"
    assert data_requests[1].headers["Authorization"] == "Bearer token-1"


async def test_client_unknown_route():
    client = make_client(FakePlatform())
    with pytest.raises(Exception):
        await client.query_platform_api("no_such_route")
