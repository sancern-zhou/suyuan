import pytest

from app.tools.jiangsu.query_tools import (
    JiangsuCityDataTool,
    JiangsuDistrictDataTool,
    JiangsuStatisticsTool,
)


class _FakeContext:
    def __init__(self):
        self.saved = []

    def save_data(self, *, data, schema, metadata):
        self.saved.append({"data": data, "schema": schema, "metadata": metadata})
        return f"backend/backend_data_registry/sessions/test/data/{schema}.json"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "data_kind", "codes"),
    [
        (JiangsuCityDataTool(), "city_hour", ["320100"]),
        (JiangsuDistrictDataTool(), "district_hour", ["320102"]),
    ],
)
async def test_area_data_tools_default_to_audited_operating_conditions(monkeypatch, tool, data_kind, codes):
    async def request(path, params):
        assert ("dataType", 1) in params
        return {"result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        data_kind=data_kind,
        codes=codes,
        start_time="2026-08-12 00:00:00",
        end_time="2026-08-12 01:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["data_type"] == 1
    assert tool.function_schema["parameters"]["properties"]["data_type"]["default"] == 1


@pytest.mark.asyncio
async def test_statistics_tool_defaults_to_audited_operating_conditions(monkeypatch):
    tool = JiangsuStatisticsTool()

    async def request(path, params):
        assert ("DataType", 1) in params
        return {"result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        statistic_kind="city_rank",
        codes=["320100"],
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-12 00:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["data_type"] == 1
    assert "原始实况" in tool.function_schema["parameters"]["properties"]["data_type"]["description"]


@pytest.mark.asyncio
async def test_rate_statistics_default_to_platform_live_defaults(monkeypatch):
    tool = JiangsuStatisticsTool()
    bodies = []

    async def post_json(endpoint, body):
        bodies.append((endpoint, body))
        return {"result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr(tool, "_post_json", post_json)
    result = await tool.execute(
        statistic_kind="station_effective_rate",
        codes=["3001A"],
        start_time="2026-10-01 01:00:00",
        end_time="2026-10-14 16:00:00",
    )

    assert result["success"] is True
    endpoint, body = bodies[-1]
    assert endpoint.endswith("GetStationEffectiveRateQueryDataPage")
    # 平台统计页面默认口径：原始实况 + 新国标。
    assert body["dataType"] == 0
    assert body["nsType"] == 2
    assert result["metadata"]["data_type"] == 0
    assert result["metadata"]["ns_type"] == 2
    assert tool.function_schema["parameters"]["properties"]["ns_type"]["default"] == 2


@pytest.mark.asyncio
async def test_daily_effective_rate_uses_platform_page_defaults(monkeypatch):
    tool = JiangsuStatisticsTool()
    bodies = []

    async def post_json(endpoint, body):
        bodies.append((endpoint, body))
        return {"result": {"items": [
            {"stationCode": "3001A", "stationName": "江宁九龙湖", "sO2": "100", "aqi": "100",
             "totalReceiveRate": "100", "rank": 99999},
            {"uniqueCode": "站点平均值", "stationCode": None, "sO2": "100", "rank": 99999},
        ], "totalCount": 1}}

    monkeypatch.setattr(tool, "_post_json", post_json)
    result = await tool.execute(
        statistic_kind="station_daily_effective_rate",
        codes=["3001A"],
        start_time="2026-10-07 00:00:00",
        end_time="2026-10-13 00:00:00",
    )

    assert result["success"] is True
    endpoint, body = bodies[-1]
    # 平台「日有效率统计」页面接口与默认口径。
    assert endpoint.endswith("GetStationReceiveRateQueryDataPage")
    assert body["dataType"] == 0
    assert body["nsType"] == 2
    rows = result["data"]
    assert [r["stationCode"] for r in rows if r.get("stationCode")] == ["3001A"]
    assert not any(r.get("uniqueCode") == "站点平均值" for r in rows)
    assert result["metadata"]["data_type"] == 0
    assert result["metadata"]["ns_type"] == 2


@pytest.mark.asyncio
async def test_city_networking_summary_defaults_to_provincial_and_cleans_nan(monkeypatch):
    tool = JiangsuStatisticsTool()
    calls = []

    async def get(path, params, **kwargs):
        calls.append((path, params))
        return {"result": {"items": [
            {"cityCode": "320100", "cityName": "南京市", "totalCount": 4, "onlineCount": 4,
             "offlineCount": 0, "rate": 100.0, "remark": "", "hourAppRate": 94.83, "dayAppRate": 92.86},
            {"cityCode": "合计", "cityName": "合计", "totalCount": 101, "onlineCount": 101,
             "offlineCount": 0, "rate": "NaN", "remark": "", "hourAppRate": "NaN", "dayAppRate": "NaN"},
        ], "totalCount": 13}}

    monkeypatch.setattr(tool, "_get", get)
    result = await tool.execute(
        statistic_kind="city_networking_summary",
        start_time="2026-10-01 01:00:00",
        end_time="2026-10-14 17:00:00",
    )

    assert result["success"] is True
    path, params = calls[-1]
    assert path.endswith("GetCityTownStationNetworkingPagedListWithSummaryRecordAsync")
    # 页面缺省：省控 stationType=2。
    assert ("stationType", 2) in params
    assert ("timePoint[0]", "2026-10-01 01:00:00") in params
    assert ("timePoint[1]", "2026-10-14 17:00:00") in params
    rows = result["data"]
    city_row = next(r for r in rows if r["cityCode"] == "320100")
    total_row = next(r for r in rows if r["cityCode"] == "合计")
    assert city_row["is_summary"] is False
    assert total_row["is_summary"] is True
    assert total_row["rate"] is None and total_row["dayAppRate"] is None
    assert result["metadata"]["station_type"] == "省控"
    assert "综合数据获取率" in result["summary"]


@pytest.mark.asyncio
async def test_city_networking_summary_rejects_all_and_codes(monkeypatch):
    tool = JiangsuStatisticsTool()

    async def get(path, params):
        raise AssertionError("invalid arguments must be rejected before calling the platform")

    monkeypatch.setattr(tool, "_get", get)
    result = await tool.execute(
        statistic_kind="city_networking_summary", station_type="全部",
        start_time="2026-10-01 01:00:00", end_time="2026-10-14 17:00:00",
    )
    assert result["success"] is False
    assert "仅支持" in result["summary"]

    result = await tool.execute(
        statistic_kind="city_networking_summary", codes=["3001A"],
        start_time="2026-10-01 01:00:00", end_time="2026-10-14 17:00:00",
    )
    assert result["success"] is False
    assert "不接受 codes" in result["summary"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("station_type", "expected_id"), [
    ("国控", 1), ("省控", 2), ("市控", 3), ("区域站", 4),
    ("乡镇站", 5), ("省建站", 6), ("省乡镇站", 7),
])
async def test_city_networking_summary_maps_all_platform_station_types(monkeypatch, station_type, expected_id):
    tool = JiangsuStatisticsTool()
    calls = []

    async def get(path, params, **kwargs):
        calls.append(params)
        return {"result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr(tool, "_get", get)
    result = await tool.execute(
        statistic_kind="city_networking_summary", station_type=station_type,
        start_time="2026-10-01 01:00:00", end_time="2026-10-14 17:00:00",
    )

    assert result["success"] is True
    assert ("stationType", expected_id) in calls[-1]
    assert result["metadata"]["station_type"] == station_type


@pytest.mark.asyncio
async def test_rate_statistics_reject_unknown_ns_type(monkeypatch):
    tool = JiangsuStatisticsTool()

    async def post_json(endpoint, body):
        raise AssertionError("invalid ns_type must be rejected before calling the platform")

    monkeypatch.setattr(tool, "_post_json", post_json)
    result = await tool.execute(
        statistic_kind="station_transfer_rate",
        codes=["3001A"],
        start_time="2026-10-01 00:00:00",
        end_time="2026-10-14 23:00:00",
        ns_type=3,
    )

    assert result["success"] is False
    assert "ns_type" in result["summary"]


@pytest.mark.asyncio
async def test_station_data_rate_counts_valid_hours_per_platform_rules(monkeypatch):
    tool = JiangsuStatisticsTool()
    bodies = []

    def hour_row(hour: int, **overrides):
        row = {
            "code": "3001A", "name": "江宁九龙湖", "cityName": "南京市", "districtName": "江宁区",
            "timePoint": f"2026-10-{1 + hour // 24:02d}T{hour % 24:02d}:00:00",
            "pM2_5": "12", "nO2": "11", "sO2": "4", "pM10": "20", "co": "0.6", "o3": "53",
        }
        row.update(overrides)
        return row

    # 48 应测小时（10-01~10-02 闭区间两天）；PM2.5 一小时带 PF 标记无效，NO2 一小时 -99 无效。
    records = [
        hour_row(hour, pM2_5="2(PF)") if hour == 7 else hour_row(hour)
        for hour in range(48)
    ]
    records[20]["nO2"] = "-99"

    async def post_json(endpoint, body):
        bodies.append((endpoint, body))
        assert body["dataType"] == 0
        return {"result": records}

    monkeypatch.setattr(tool, "_post_json", post_json)
    result = await tool.execute(
        statistic_kind="station_data_rate",
        codes=["3001A"],
        start_time="2026-10-01 00:00:00",
        end_time="2026-10-02 23:59:59",
    )

    assert result["success"] is True
    endpoint, _ = bodies[-1]
    assert endpoint == "airdata/DATStationHour/GetStationHourDataListAsync"
    row = result["data"][0]
    assert row["stationCode"] == "3001A"
    assert row["expected_hours"] == 48
    assert row["pM2_5"] == 97.92
    assert row["pM2_5_valid_hours"] == 47
    assert row["nO2_valid_hours"] == 47
    assert row["sO2_valid_hours"] == 48
    assert result["metadata"]["source"] == "computed_from_platform_hour_data"
    assert result["metadata"]["expected_hours"] == 48
    assert "数据获取率" in result["summary"]


@pytest.mark.asyncio
async def test_station_statistics_filter_codes_by_station_type(monkeypatch):
    tool = JiangsuStatisticsTool()
    calls = []

    async def request(path, params):
        calls.append((path, params))
        if path == "AirCityProductBase/GetAllEnabledBSDStationAsync":
            return {"result": [
                {"stationCode": "N", "stationType": 1},
                {"stationCode": "P", "stationTypeName": "省控"},
                {"stationCode": "M", "stationType": 3},
            ]}
        return {"result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        statistic_kind="station_rank",
        codes=["N", "P", "M"],
        station_type="省控",
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-12 00:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["codes"] == ["P"]
    assert result["metadata"]["station_type"] == "省控"
    assert result["metadata"]["station_type_filter_applied"] is True
    stats_call = calls[-1]
    assert stats_call[0].endswith("GetStationRankStatisticsPagedAsync")
    assert ("StationCode[0]", "P") in stats_call[1]
    assert not any(value == "N" or value == "M" for key, value in stats_call[1] if key.startswith("StationCode"))


@pytest.mark.asyncio
async def test_area_statistics_reject_station_type_dimension(monkeypatch):
    tool = JiangsuStatisticsTool()

    async def request(path, params):
        raise AssertionError("area statistic must be rejected before calling the platform")

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        statistic_kind="city_rank",
        codes=["320100"],
        station_type="省控",
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-12 00:00:00",
    )

    assert result["success"] is False
    assert "city_rank/district_rank" in result["summary"]
    assert tool.function_schema["parameters"]["properties"]["station_type"]["default"] == "全部"


@pytest.mark.asyncio
async def test_city_data_rejects_station_type_dimension(monkeypatch):
    tool = JiangsuCityDataTool()

    async def request(path, params):
        raise AssertionError("area data must be rejected before calling the platform")

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        data_kind="city_hour",
        codes=["320100"],
        station_type="省控",
        start_time="2026-08-12 00:00:00",
        end_time="2026-08-12 01:00:00",
    )

    assert result["success"] is False
    assert "不支持 station_type" in result["summary"]


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


@pytest.mark.asyncio
async def test_city_hour_data_preserves_full_series_and_externalizes_only_inline_preview(monkeypatch):
    tool = JiangsuCityDataTool()
    records = [
        {
            "name": "南京市",
            "code": "320100",
            "timePoint": f"2026-08-{1 + hour // 24:02d}T{hour % 24:02d}:00:00",
            "dataType": 0,
            "aqi": str(20 + hour % 30),
        }
        for hour in range(288)
    ]

    async def request(path, params):
        if path == "AirCityProductBase/GetBSDRegionAsync":
            return {
                "result": [
                    {
                        "areaCode": "320100",
                        "areaName": "南京市",
                        "parentID": "320000",
                        "level": 2,
                    }
                ]
            }
        return {"result": {"items": records, "totalCount": len(records)}}

    monkeypatch.setattr(tool, "_get", request)
    context = _FakeContext()

    result = await tool.execute(
        context=context,
        data_kind="city_hour",
        area_names=["南京市"],
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-12 23:59:59",
        max_results=1000,
    )

    assert result["success"] is True
    assert result["record_count"] == 288
    assert result["returned_records"] == 24
    assert result["sample_strategy"] == "head_tail"
    assert result["data"][0]["timePoint"] == "2026-08-01T00:00:00"
    assert result["data"][-1]["timePoint"] == "2026-08-12T23:00:00"
    assert result["file_path"].endswith("jiangsu_city_city_hour_filtered.json")
    filtered = next(item for item in context.saved if item["schema"].endswith("_filtered"))
    assert len(filtered["data"]) == 288
    assert "完整时间序列 288 条" in result["summary"]
