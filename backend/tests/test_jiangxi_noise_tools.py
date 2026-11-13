# -*- coding: utf-8 -*-
"""江西噪声数据获取工具测试：客户端请求编码 + 工具参数语义校验。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
import pytest

from app.external_apis.jiangxi_noise_api_client import JiangxiNoiseDataClient
from app.tools.query.query_jiangxi_noise.alarm_analysis_tool import (
    GetJiangxiNoiseAlarmAnalysisTool,
)
from app.tools.query.query_jiangxi_noise.api_catalog import API_CATALOG
from app.tools.query.query_jiangxi_noise.api_discovery_tool import (
    CallJiangxiNoiseApiTool,
    DescribeJiangxiNoiseApiTool,
    SearchJiangxiNoiseApisTool,
    build_call_payload,
    encode_query_params,
)
from app.tools.query.query_jiangxi_noise.compliance_tool import (
    GetJiangxiNoiseComplianceTool,
    resolve_period_range,
)
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


# ---------------------------------------------------------------------------
# 超标事件分析工具
# ---------------------------------------------------------------------------


def alarm_analysis_payload(records: int = 1) -> dict[str, Any]:
    return {
        "startTime": "2026-07-15T00:00:00+08:00",
        "endTime": "2026-07-15T23:59:59.99+08:00",
        "periodText": "2026-07-15",
        "regionLevel": "城市",
        "totalAlarmCount": 42,
        "unprocessedCount": 7,
        "processedCount": 35,
        "alarmStationCount": 9,
        "levelSummary": {"lightCount": 30, "moderateCount": 8, "severeCount": 4},
        "regionStats": [{"rank": 1, "regionName": "南昌市", "alarmCount": 12, "alarmRate": 0.8}],
        "stationStats": [
            {"rank": 1, "stationCode": "1737A", "stationName": "监测一站", "alarmCount": 5}
        ],
        "alarmRecords": [
            {
                "id": index + 1,
                "stationCode": "1737A",
                "stationName": "监测一站",
                "alarmName": "昼间超标",
                "level": "轻微",
                "status": "已处理",
            }
            for index in range(records)
        ],
    }


async def test_alarm_analysis_defaults_and_params():
    fake = FakePlatform({"alarm_analysis": alarm_analysis_payload()})
    tool = GetJiangxiNoiseAlarmAnalysisTool(client=make_client(fake))
    result = await tool.execute()
    assert result["success"] is True
    route, request = fake.last()
    assert route == "alarm_analysis"
    assert request.method == "GET"
    params = query_of(request)
    assert params["TimeType"] == "today"
    assert "CityCode" not in params
    assert result["record_total"] == 1
    assert result["data"]["totalAlarmCount"] == 42
    assert result["truncated"] is False


async def test_alarm_analysis_resolves_city_and_filters():
    fake = FakePlatform({"alarm_analysis": alarm_analysis_payload()})
    tool = GetJiangxiNoiseAlarmAnalysisTool(client=make_client(fake))
    result = await tool.execute(
        time_type="month", city="南昌市", district_code="360102"
    )
    assert result["success"] is True
    params = query_of(fake.last()[1])
    assert params["TimeType"] == "month"
    assert params["CityCode"] == "360100"
    assert params["DistrictCode"] == "360102"
    assert result["city_code"] == "360100"


async def test_alarm_analysis_province_code():
    fake = FakePlatform({"alarm_analysis": alarm_analysis_payload()})
    tool = GetJiangxiNoiseAlarmAnalysisTool(client=make_client(fake))
    await tool.execute(city="江西省")
    assert query_of(fake.last()[1])["CityCode"] == "360000"


async def test_alarm_analysis_truncates_records():
    fake = FakePlatform({"alarm_analysis": alarm_analysis_payload(records=5)})
    tool = GetJiangxiNoiseAlarmAnalysisTool(client=make_client(fake))
    result = await tool.execute(max_records=2)
    assert result["success"] is True
    assert result["truncated"] is True
    assert result["record_count"] == 2
    assert result["record_total"] == 5
    assert len(result["data"]["alarmRecords"]) == 2
    assert "已截断" in result["hint"]


async def test_alarm_analysis_invalid_inputs():
    tool = GetJiangxiNoiseAlarmAnalysisTool(client=make_client(FakePlatform()))
    result = await tool.execute(time_type="week")
    assert result["success"] is False
    assert result["error_code"] == "invalid_time_type"
    result = await tool.execute(city="北京市")
    assert result["success"] is False
    assert result["error_code"] == "invalid_city"


# ---------------------------------------------------------------------------
# 达标统计工具
# ---------------------------------------------------------------------------


def compliance_statistics_payload(stations: int = 2) -> dict[str, Any]:
    return {
        "summary": {
            "stationCount": 20,
            "cityCount": 2,
            "unqualifiedStationCount": 3,
            "averageDayRate": 0.95,
            "averageNightRate": 0.9,
        },
        "cities": [{"rowId": "360100", "city": "南昌市", "dayRate": 0.96, "nightRate": 0.91}],
        "zones": [{"rowId": "2", "zone": "2类区", "dayRate": 0.94}],
        "stations": [
            {"rowId": f"ST{index}", "name": f"站点{index}", "dayRate": 0.9}
            for index in range(stations)
        ],
    }


def test_period_range_expansion_matches_platform_periods():
    # 平台 CreatePeriods 要求起止落在同一自然周期内（EndDate 闭区间）
    cases = {
        "day": ("2026-07-15T09:00:00+08:00", "2026-07-15", "2026-07-15", "2026-07-15"),
        "month": ("2026-07-15T00:00:00+08:00", "2026-07-01", "2026-07-31", "2026-07"),
        "quarter": ("2026-07-15T00:00:00+08:00", "2026-07-01", "2026-09-30", "2026Q3"),
        "year": ("2026-07-15T00:00:00+08:00", "2026-01-01", "2026-12-31", "2026"),
    }
    for period, (period_date, expected_start, expected_end, label) in cases.items():
        start, end, period_label = resolve_period_range(
            period, datetime.fromisoformat(period_date)
        )
        assert start.strftime("%Y-%m-%d") == expected_start
        assert end.strftime("%Y-%m-%d") == expected_end
        assert period_label == label


async def test_compliance_statistics_body():
    fake = FakePlatform({"compliance_statistics": compliance_statistics_payload()})
    tool = GetJiangxiNoiseComplianceTool(client=make_client(fake))
    result = await tool.execute(
        report="statistics",
        city_names=["南昌市"],
        period="month",
        period_date="2026-07-15T00:00:00+08:00",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "compliance_statistics"
    assert request.method == "POST"
    body = body_of(request)
    assert body["CityCodes"] == ["360100"]
    assert body["DataType"] == 1
    assert body["TimeType"] == 40
    assert body["StartDate"] == "2026-07-01 00:00:00"
    assert body["EndDate"] == "2026-07-31 00:00:00"
    assert result["period_label"] == "2026-07"
    assert result["station_total"] == 2
    assert result["truncated"] is False


async def test_compliance_statistics_truncates_stations():
    fake = FakePlatform(
        {"compliance_statistics": compliance_statistics_payload(stations=5)}
    )
    tool = GetJiangxiNoiseComplianceTool(client=make_client(fake))
    result = await tool.execute(
        report="statistics",
        city_names=["360100"],
        period="quarter",
        period_date="2026-07-15T00:00:00+08:00",
        max_records=2,
    )
    assert result["truncated"] is True
    assert result["station_count"] == 2
    assert len(result["data"]["stations"]) == 2
    body = body_of(fake.last()[1])
    assert body["StartDate"] == "2026-07-01 00:00:00"
    assert body["EndDate"] == "2026-09-30 00:00:00"


async def test_compliance_statistics_invalid_inputs():
    tool = GetJiangxiNoiseComplianceTool(client=make_client(FakePlatform()))
    result = await tool.execute(report="statistics", period="month", period_date=START)
    assert result["success"] is False
    assert result["error_code"] == "missing_city_names"
    result = await tool.execute(
        report="statistics",
        city_names=["南昌市"],
        period="week",
        period_date=START,
    )
    assert result["error_code"] == "invalid_period"
    result = await tool.execute(
        report="statistics",
        city_names=["北京市"],
        period="month",
        period_date=START,
    )
    assert result["error_code"] == "invalid_city"


async def test_compliance_comparison_body():
    fake = FakePlatform(
        {
            "compliance_comparison": {
                "totalCount": 2,
                "items": [
                    {"districtName": "东湖区", "dayQualifiedBefore": 20, "dayQualifiedAfter": 18},
                    {"districtName": "西湖区", "dayQualifiedBefore": 22, "dayQualifiedAfter": 22},
                ],
            }
        }
    )
    tool = GetJiangxiNoiseComplianceTool(client=make_client(fake))
    result = await tool.execute(
        report="comparison",
        city_names=["南昌市", "九江市"],
        district_codes=["360102"],
        start_date="2026-01-01T00:00:00+08:00",
        end_date="2026-01-31T00:00:00+08:00",
        review_status="raw",
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "compliance_comparison"
    assert request.method == "POST"
    body = body_of(request)
    assert body["CityCodes"] == ["360100", "360400"]
    assert body["DistrictCodes"] == ["360102"]
    assert body["DataType"] == 0
    assert body["SkipCount"] == 0
    assert body["MaxResultCount"] == 20
    assert body["StartDate"] == "2026-01-01 00:00:00"
    assert body["EndDate"] == "2026-01-31 00:00:00"
    assert result["total_count"] == 2
    assert len(result["data"]) == 2


async def test_compliance_comparison_requires_region():
    tool = GetJiangxiNoiseComplianceTool(client=make_client(FakePlatform()))
    result = await tool.execute(
        report="comparison",
        start_date=START,
        end_date=END,
    )
    assert result["success"] is False
    assert result["error_code"] == "missing_region"


async def test_compliance_comparison_range_limit():
    tool = GetJiangxiNoiseComplianceTool(client=make_client(FakePlatform()))
    result = await tool.execute(
        report="comparison",
        city_names=["南昌市"],
        start_date="2024-01-01T00:00:00+08:00",
        end_date="2026-01-31T00:00:00+08:00",
    )
    assert result["success"] is False
    assert result["error_code"] == "time_range_too_large"


async def test_compliance_invalid_report():
    tool = GetJiangxiNoiseComplianceTool(client=make_client(FakePlatform()))
    result = await tool.execute(report="unknown")
    assert result["success"] is False
    assert result["error_code"] == "invalid_report"


# ---------------------------------------------------------------------------
# 接口目录发现工具（search / describe / call）
# ---------------------------------------------------------------------------


def test_catalog_routes_consistent_with_client():
    """目录守门：每条目录项的 route 必须已注册到客户端且动词一致。"""
    for api, entry in API_CATALOG.items():
        assert entry["route"] in JiangxiNoiseDataClient.API_ROUTES, api
        method, endpoint = JiangxiNoiseDataClient.API_ROUTES[entry["route"]]
        assert endpoint.startswith("/api/noiseproduct/"), api
        describe_payload = {
            "route": entry["route"],
            "method": method,
        }
        assert describe_payload["route"] == entry["route"]
        for field, rule in entry["params"].items():
            assert rule.get("type"), f"{api}.{field} 缺少 type"
            assert rule.get("desc"), f"{api}.{field} 缺少 desc"


async def test_search_finds_exceed_apis():
    tool = SearchJiangxiNoiseApisTool()
    result = await tool.execute(query="超标 统计")
    assert result["success"] is True
    names = [item["api"] for item in result["results"]]
    assert "exceed_statistics" in names
    assert "overlimit_analysis" in names
    assert "alarm_analysis" in names


async def test_search_requires_query():
    tool = SearchJiangxiNoiseApisTool()
    result = await tool.execute(query="  ")
    assert result["success"] is False
    assert result["error_code"] == "invalid_query"


async def test_describe_returns_contract():
    tool = DescribeJiangxiNoiseApiTool()
    result = await tool.execute(api="season_comparison")
    assert result["success"] is True
    assert result["method"] == "GET"
    assert result["params"]["StationCode"]["required"] is True
    assert "example" in result
    result = await tool.execute(api="no_such_api")
    assert result["success"] is False
    assert result["error_code"] == "unknown_api"


def test_build_call_payload_enum_and_datetime():
    payload = build_call_payload(
        "assessment_ranking",
        {
            "DataType": "audited",
            "Dimension": "city",
            "StartDate": "2026-07-01T00:00:00+08:00",
            "EndDate": "2026-07-31T00:00:00+08:00",
        },
    )
    assert payload["DataType"] == 1
    assert payload["Dimension"] == "city"
    assert payload["StartDate"] == "2026-07-01 00:00:00"
    assert payload["EndDate"] == "2026-07-31 00:00:00"


def test_build_call_payload_defaults_and_omissions():
    payload = build_call_payload(
        "area_average_report",
        {
            "Codes": ["360100"],
            "TimePoint": ["2026-07-01T00:00:00+08:00", "2026-07-31T00:00:00+08:00"],
            "TimeType": "month",
        },
    )
    assert payload["TimeType"] == 40
    assert payload["SandType"] == 0  # 有默认值，缺省时补齐
    assert "SamplingType" not in payload  # 无默认值，缺省时省略
    assert payload["TimePoint"] == ["2026-07-01 00:00:00", "2026-07-31 00:00:00"]


def test_build_call_payload_validation_errors():
    with pytest.raises(Exception) as exc_info:
        build_call_payload("no_such_api", {})
    assert "unknown_api" in str(getattr(exc_info.value, "code", "")) or "目录中没有接口" in str(
        exc_info.value
    )
    with pytest.raises(Exception) as exc_info:
        build_call_payload("season_comparison", {"StationCode": "1737A"})  # 缺 Date
    assert getattr(exc_info.value, "code", "") == "missing_Date"
    with pytest.raises(Exception) as exc_info:
        build_call_payload("season_comparison", {"StationCode": "1737A", "Date": START,
                                                 "Bogus": 1})
    assert getattr(exc_info.value, "code", "") == "unknown_param"
    with pytest.raises(Exception) as exc_info:
        build_call_payload("assessment_ranking", {"DataType": True})
    assert getattr(exc_info.value, "code", "") == "invalid_DataType"
    with pytest.raises(Exception) as exc_info:
        build_call_payload(
            "sound_calendar_day",
            {"AnalysisDimension": 3, "StationCode": "1737A", "StartDay": "abc",
             "EndDay": 2026},
        )
    assert getattr(exc_info.value, "code", "") == "invalid_StartDay"


def test_encode_query_params_expands_lists():
    query = encode_query_params(
        {"Codes": ["360100", "360400"], "AreaType": 2, "TimePoint": ["2026-07-01 00:00:00"]}
    )
    assert query["Codes[0]"] == "360100"
    assert query["Codes[1]"] == "360400"
    assert query["TimePoint[0]"] == "2026-07-01 00:00:00"
    assert query["AreaType"] == 2


async def test_call_get_encodes_query_params():
    fake = FakePlatform({"season_comparison": {"seasons": []}})
    tool = CallJiangxiNoiseApiTool(client=make_client(fake))
    result = await tool.execute(
        api="season_comparison",
        params={"StationCode": "1737A", "Date": "2026-07-15T00:00:00+08:00", "DataType": "raw"},
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "season_comparison"
    assert request.method == "GET"
    params = query_of(request)
    assert params["StationCode"] == "1737A"
    assert params["Date"] == "2026-07-15 00:00:00"
    assert params["DataType"] == "0"
    assert result["params_sent"]["DataType"] == 0


async def test_call_post_sends_json_body():
    fake = FakePlatform({"exceed_statistics": {"total": 3}})
    tool = CallJiangxiNoiseApiTool(client=make_client(fake))
    result = await tool.execute(
        api="exceed_statistics",
        params={
            "Dimension": "quarter",
            "Period": "day",
            "TimePoint": "2026-07-15T00:00:00+08:00",
            "StationCodes": ["1737A"],
            "DataType": "audited",
        },
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "exceed_statistics"
    assert request.method == "POST"
    body = body_of(request)
    assert body["Dimension"] == "quarter"
    assert body["Period"] == "day"
    assert body["TimePoint"] == "2026-07-15 00:00:00"
    assert body["StationCodes"] == ["1737A"]
    assert body["DataType"] == 1


async def test_call_rejects_unknown_api():
    tool = CallJiangxiNoiseApiTool(client=make_client(FakePlatform()))
    result = await tool.execute(api="not_in_catalog", params={})
    assert result["success"] is False
    assert result["error_code"] == "unknown_api"


async def test_call_truncates_long_lists():
    fake = FakePlatform(
        {
            "source_identification_detail": {
                "items": [{"id": index} for index in range(300)],
                "totalCount": 300,
            }
        }
    )
    tool = CallJiangxiNoiseApiTool(client=make_client(fake))
    result = await tool.execute(
        api="source_identification_detail",
        params={
            "TimePoint": ["2026-07-01T00:00:00+08:00", "2026-07-31T00:00:00+08:00"],
            "AreaType": 3,
        },
    )
    assert result["success"] is True
    assert result["count"] == 200
    assert result["total_count"] == 300
    assert result["truncated"] is True


def test_build_call_payload_int_list_resolves_enum_labels():
    payload = build_call_payload(
        "work_order_paged",
        {
            "TimePoint": ["2026-07-01T00:00:00+08:00", "2026-07-31T00:00:00+08:00"],
            "OrderStatus": ["待处理", 2],
            "StatisticsType": [8, "故障排查"],
        },
    )
    assert payload["OrderStatus"] == [1, 2]
    assert payload["StatisticsType"] == [8, 8]


async def test_call_ops_get_encodes_paged_query():
    fake = FakePlatform({"substation_power_status": {"items": [], "totalCount": 0}})
    tool = CallJiangxiNoiseApiTool(client=make_client(fake))
    result = await tool.execute(
        api="substation_power_status",
        params={
            "StationCode": "1737A,1738A",
            "StartTime": "2026-07-01T00:00:00+08:00",
            "maxResultCount": 20,
        },
    )
    assert result["success"] is True
    route, request = fake.last()
    assert route == "substation_power_status"
    assert request.method == "GET"
    params = query_of(request)
    assert params["StationCode"] == "1737A,1738A"
    assert params["StartTime"] == "2026-07-01 00:00:00"
    assert params["skipCount"] == "0"  # 默认分页参数补齐
    assert params["maxResultCount"] == "20"


async def test_call_qc_arrange_requires_time_range():
    fake = FakePlatform({"qc_arrange_list": {"items": [], "totalCount": 0}})
    tool = CallJiangxiNoiseApiTool(client=make_client(fake))
    result = await tool.execute(api="qc_arrange_list", params={"StationCode": "1737A"})
    assert result["success"] is False
    assert result["error_code"] == "missing_StartTime"
    result = await tool.execute(
        api="qc_arrange_list",
        params={
            "StartTime": "2026-07-01T00:00:00+08:00",
            "EndTime": "2026-07-02T00:00:00+08:00",
        },
    )
    assert result["success"] is True
    assert result["params_sent"]["EndTime"] == "2026-07-02 00:00:00"
