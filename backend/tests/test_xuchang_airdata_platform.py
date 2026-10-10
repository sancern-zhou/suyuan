"""许昌专属：大气环境监测数据接口中台查询工具测试"""
import asyncio
import threading

import httpx
import pytest

from app.agent.prompts.tool_registry import get_tool_order
from app.project_config.loader import load_project_context
from app.tools import create_global_tool_registry
from app.tools.xuchang.airdata_platform import client as client_module
from app.tools.xuchang.airdata_platform import tool as tool_module
from app.tools.xuchang.airdata_platform.client import (
    AirDataPlatformClient,
    AirDataPlatformError,
    normalize_filters,
    normalize_sort_config,
)
from app.tools.xuchang.airdata_platform.tool import (
    AirDataCalcReportSummaryTool,
    QueryAirDataPlatformTool,
    _round_bankers_1,
)


def _envelope(data):
    return {"success": True, "code": "0", "message": "success", "data": data}


@pytest.fixture
def captured(monkeypatch):
    state = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        state["url"] = url
        state["payload"] = json
        state["timeout"] = timeout
        return httpx.Response(200, json=state.get("response", _envelope({})))

    monkeypatch.setattr(client_module.httpx, "post", fake_post)
    return state


def _patch_post(monkeypatch, handler):
    monkeypatch.setattr(client_module.httpx, "post", handler)


def test_normalize_filters_defaults_operator_to_eq():
    assert normalize_filters([{"field": "code", "value": "411000"}]) == [
        {"field": "code", "operator": "eq", "value": "411000"}
    ]


def test_normalize_filters_between_requires_second_value():
    with pytest.raises(AirDataPlatformError, match="second_value"):
        normalize_filters(
            [{"field": "timepoint", "operator": "between", "value": "2026-08-01"}]
        )


def test_normalize_filters_rejects_unknown_operator():
    with pytest.raises(AirDataPlatformError, match="过滤谓词"):
        normalize_filters([{"field": "code", "operator": "gt", "value": "1"}])


def test_normalize_sort_config_rejects_bad_order():
    with pytest.raises(AirDataPlatformError, match="asc/desc"):
        normalize_sort_config([{"field": "timepoint", "order": "up"}])


def test_query_page_builds_payload_and_parses_envelope(captured):
    captured["response"] = _envelope(
        {
            "columns": [{"fieldCode": "code"}],
            "rows": [{"code": "411000"}],
            "total": 1,
            "page": 1,
            "size": 100,
            "executionTimeMs": 5,
        }
    )
    client = AirDataPlatformClient(base_url="http://example.test")

    result = client.query_page(
        "v_s_d_app_145",
        filters=[{"field": "code", "operator": "in", "value": ["411000"]}],
        selected_fields=["code"],
        sort_config=[{"field": "timepoint", "order": "desc"}],
    )

    assert result["rows"] == [{"code": "411000"}]
    assert result["total"] == 1
    assert result["execution_time_ms"] == 5
    assert captured["url"] == "http://example.test/openapi/v1/custom-apis/v_s_d_app_145/query"
    assert captured["payload"]["filters"] == [
        {"field": "code", "operator": "in", "value": ["411000"]}
    ]
    assert captured["payload"]["selectedFields"] == ["code"]
    assert captured["payload"]["sortConfig"] == [{"field": "timepoint", "order": "desc"}]
    assert captured["payload"]["size"] == 100


def test_query_page_clamps_size_to_api_limit(captured):
    client = AirDataPlatformClient(base_url="http://example.test")

    client.query_page("v_s_d_app_145", size=5000)

    assert captured["payload"]["size"] == 100


def test_query_page_rejects_unknown_api_code():
    client = AirDataPlatformClient(base_url="http://example.test")

    with pytest.raises(AirDataPlatformError, match="接口编码错误"):
        client.query_page("v_unknown", size=10)


def test_query_all_paginates_until_total_reached(monkeypatch):
    def handler(url, json=None, headers=None, timeout=None):
        if json["page"] == 1:
            rows = [{"i": i} for i in range(100)]
        else:
            rows = [{"i": i} for i in range(50)]
        return httpx.Response(
            200,
            json=_envelope(
                {
                    "columns": [],
                    "rows": rows,
                    "total": 150,
                    "page": json["page"],
                    "size": 100,
                }
            ),
        )

    _patch_post(monkeypatch, handler)
    client = AirDataPlatformClient(base_url="http://example.test")

    result = client.query_all("v_s_d_app_145")

    assert len(result["rows"]) == 150
    assert result["pages_fetched"] == 2
    assert result["truncated"] is False


def test_query_all_marks_truncation_beyond_max_rows(monkeypatch):
    def handler(url, json=None, headers=None, timeout=None):
        return httpx.Response(
            200,
            json=_envelope(
                {
                    "columns": [],
                    "rows": [{"i": 0}] * 100,
                    "total": 500,
                    "page": json["page"],
                    "size": 100,
                }
            ),
        )

    _patch_post(monkeypatch, handler)
    client = AirDataPlatformClient(base_url="http://example.test")

    result = client.query_all("v_s_d_app_145", max_rows=250)

    assert len(result["rows"]) == 250
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_query_tool_does_not_block_event_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    class FakeClient:
        def query_all(self, *_args, **_kwargs):
            started.set()
            release.wait(timeout=2)
            return {
                "rows": [],
                "total": 0,
                "pages_fetched": 1,
                "truncated": False,
            }

    monkeypatch.setattr(
        tool_module,
        "get_airdata_platform_client",
        lambda: FakeClient(),
    )
    task = asyncio.create_task(QueryAirDataPlatformTool().execute(api_code="region"))

    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.001)

    assert started.is_set()
    assert not task.done()
    release.set()
    result = await task
    assert result["success"] is True


@pytest.mark.asyncio
async def test_report_summary_tool_does_not_block_event_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    class FakeClient:
        def calc_report_summary(self, **_kwargs):
            started.set()
            release.wait(timeout=2)
            return []

    monkeypatch.setattr(
        tool_module,
        "get_airdata_platform_client",
        lambda: FakeClient(),
    )
    task = asyncio.create_task(
        AirDataCalcReportSummaryTool().execute(
            start_time="2026-09-01",
            end_time="2026-09-30",
            input_table_name="view_dat_station_day_app_pantype155",
            year=2025,
        )
    )

    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.001)

    assert started.is_set()
    assert not task.done()
    release.set()
    result = await task
    assert result["success"] is True


def test_business_error_raises_with_platform_message(captured):
    captured["response"] = {
        "success": False,
        "code": "500",
        "message": "数据源不存在",
    }
    client = AirDataPlatformClient(base_url="http://example.test")

    with pytest.raises(AirDataPlatformError, match="数据源不存在"):
        client.query_page("region")


def test_calc_report_summary_builds_payload_with_defaults(captured):
    captured["response"] = _envelope([{"SO2_Curr": "8.2"}])
    client = AirDataPlatformClient(base_url="http://example.test")

    data = client.calc_report_summary(
        start_time="2026-08-01",
        end_time="2026-08-31",
        input_table_name="view_dat_station_day_app_pantype145",
        year=2025,
        area_type=0,
        report_time_type=8,
    )

    assert data == [{"SO2_Curr": "8.2"}]
    assert captured["url"] == "http://example.test/api/airdataplatform/calc-report/summary"
    payload = captured["payload"]
    assert payload["timeRanges"] == [
        {
            "inputDataDBSource": "DataCrawler",
            "inputTableName": "DataCrawler.view_dat_station_day_app_pantype145",
            "startTime": "2026-08-01",
            "endTime": "2026-08-31",
        }
    ]
    assert payload["baseData"] == {
        "baseDataSource": "DataCrawler",
        "stationTableName": "bsd_station",
        "regionTableName": "bsd_region",
    }
    assert payload["regionArea"] == {}
    assert payload["regionAreaName"] == {}
    assert payload["needKeys"] == []


def test_calc_report_summary_rejects_invalid_area_type():
    client = AirDataPlatformClient(base_url="http://example.test")

    with pytest.raises(AirDataPlatformError, match="area_type"):
        client.calc_report_summary(
            start_time="2026-08-01",
            end_time="2026-08-31",
            input_table_name="view_dat_town_day_app",
            year=2025,
            area_type=9,
            report_time_type=8,
        )


def test_tool_schemas():
    query_tool = QueryAirDataPlatformTool()
    report_tool = AirDataCalcReportSummaryTool()

    assert query_tool.name == "query_airdata_platform"
    assert query_tool.function_schema["parameters"]["required"] == ["api_code"]
    # 乡镇视图已下线（数据走本地语义层 TownHour/TownDay），不在工具 enum 中
    town_views = {"v_t_d_app", "v_t_d_src", "v_t_h_app", "v_t_h_src"}
    enum_codes = set(query_tool.function_schema["parameters"]["properties"]["api_code"]["enum"])
    assert enum_codes.isdisjoint(town_views)

    assert report_tool.name == "airdata_calc_report_summary"
    assert set(report_tool.function_schema["parameters"]["required"]) == {
        "start_time",
        "end_time",
        "input_table_name",
        "year",
        "area_type",
        "report_time_type",
    }
    assert "include_compare" in report_tool.function_schema["parameters"]["properties"]


def test_query_tool_schema_documents_data_source_priority_and_new_standard_default():
    description = QueryAirDataPlatformTool().function_schema["description"]

    assert "中大平台审核后数据" in description
    assert "长历史采集库" in description
    assert "大气监测接口中台" in description
    assert "中大国发平台" in description
    assert "第一优先级" in description
    assert "国标2（新国标）" in description
    assert "2026-01-01 及以后用 v_c_d_sb_155" in description
    assert "2021-07-01~2025-12-31 用 v_c_d_sb_145" in description
    assert "不要用 v_c_d_src_155" in description
    assert "数据源声明" in description


def test_query_tool_schema_forbids_aggregating_hourly_daily_into_monthly_annual():
    description = QueryAirDataPlatformTool().function_schema["description"]

    assert "禁止用小时数据、日数据自行汇总或计算月度、季度、半年、年度统计值" in description
    assert "airdata_calc_report_summary" in description
    assert "不得自行汇总代替报表" in description


def test_report_tool_schema_states_official_caliber_no_cross_check():
    description = QueryAirDataPlatformTool().function_schema["description"]

    assert "官方口径" in description
    assert "唯一权威来源" in description
    assert "交叉比对" in description
    assert "交叉校验" not in description


def test_report_tool_schema_forbids_aggregating_hourly_daily_into_monthly_annual():
    tool = AirDataCalcReportSummaryTool()
    description = tool.function_schema["description"]

    assert "本接口是许昌月度及以上统计的唯一来源" in description
    assert "禁止用小时数据、日数据自行汇总或计算月度、季度、半年、年度统计值" in description
    assert "不得用自行汇总的结果代替或修正平台报表" in description
    assert "不得改用明细数据自行计算" in description
    assert (
        "月报用 4、年报用 7"
        in tool.function_schema["parameters"]["properties"]["report_time_type"]["description"]
    )


def test_report_tool_schema_documents_data_source_priority_and_new_standard_default():
    tool = AirDataCalcReportSummaryTool()
    description = tool.function_schema["description"]

    assert "中大平台审核后数据" in description
    assert "长历史采集库" in description
    assert "中大国发平台" in description
    assert "第一优先级" in description
    assert "ns_type 默认 2（国标二/新国标）" in description
    assert "数据源声明" in description
    assert "唯一权威来源" in description
    assert (
        "默认 2，不要改为 1"
        in tool.function_schema["parameters"]["properties"]["ns_type"]["description"]
    )


def test_xuchang_registers_airdata_tools():
    context = load_project_context("xuchang")

    registry = create_global_tool_registry(context=context)

    assert "query_airdata_platform" in registry.list_tools()
    assert "airdata_calc_report_summary" in registry.list_tools()


def test_other_projects_do_not_register_airdata_tools():
    context = load_project_context("jiangxi")

    registry = create_global_tool_registry(context=context)

    assert "query_airdata_platform" not in registry.list_tools()
    assert "airdata_calc_report_summary" not in registry.list_tools()


def test_airdata_tools_exposed_in_query_mode_order():
    order = get_tool_order("query")

    assert "query_airdata_platform" in order
    assert "airdata_calc_report_summary" in order


def _report_row():
    return {
        "TimePoint": "2025年",
        "CityName": "许昌市",
        "CityCode": "411000",
        "StationName": "许昌市监测站",
        "StationCode": "1048A",
        "PM2_5_Curr": "46",
        "PM2_5_Curr_ForNow": "45.5650890000",
        "PM2_5_Curr_ForNow_Compare": "49.3",
        "PM2_5_Curr_ForNow_Increase": "-7.3",
        "PM2_5_Curr_ForNow_ChangeType": "Rate",
        "CompositeIndex": "9.445",
        "CompositeIndex_Compare": "10.064",
        "CompositeIndex_Increase": "-6.2",
        "CompositeIndex_ChangeType": "Rate",
        "FineDays": "234",
        "FineDays_Compare": "207",
        "FineDays_Increase": "+27",
        "FineDays_ChangeType": "Difference",
        "PM25ExcessDays": "92",
    }


def _report_response(data):
    def handler(url, json=None, headers=None, timeout=None):
        return httpx.Response(200, json=_envelope(data))

    return handler


@pytest.mark.asyncio
async def test_report_tool_strips_compare_fields_and_projects_by_default(monkeypatch):
    _patch_post(monkeypatch, _report_response([_report_row()]))

    result = await AirDataCalcReportSummaryTool().execute(
        start_time="2025-01-01",
        end_time="2025-12-31",
        input_table_name="view_dat_station_day_app_pantype145",
        year=2024,
        area_type=0,
        report_time_type=7,
    )

    assert result["success"] is True
    row = result["data"][0]
    assert row["PM2_5_Curr_ForNow_R1"] == "45.6"  # 45.5650890000 银行家算法保留一位小数
    assert "PM2_5_Curr" not in row
    assert "PM2_5_Curr_ForNow" not in row
    assert "CompositeIndex" in row
    assert not any(k.endswith(("_Compare", "_Increase", "_ChangeType")) for k in row)
    assert "PM25ExcessDays" not in row  # 白名单外字段被投影掉
    metadata = result["metadata"]
    assert metadata["include_compare"] is False
    assert metadata["total_fields"] > metadata["preview_fields"]


def test_round_bankers_1_half_to_even():
    assert _round_bankers_1("45.5650890000") == "45.6"
    assert _round_bankers_1("45.55") == "45.6"  # 半分位向偶数舍入：5→6
    assert _round_bankers_1("45.45") == "45.4"  # 半分位向偶数舍入：5→4
    assert _round_bankers_1("45.85") == "45.8"
    assert _round_bankers_1("46") == "46.0"
    assert _round_bankers_1("0.05") == "0.0"
    assert _round_bankers_1("—") is None
    assert _round_bankers_1("") is None
    assert _round_bankers_1(None) is None
    assert _round_bankers_1("abc") is None


@pytest.mark.asyncio
async def test_report_tool_include_compare_keeps_yoy_fields(monkeypatch):
    _patch_post(monkeypatch, _report_response([_report_row()]))

    result = await AirDataCalcReportSummaryTool().execute(
        start_time="2025-01-01",
        end_time="2025-12-31",
        input_table_name="view_dat_station_day_app_pantype145",
        year=2024,
        area_type=0,
        report_time_type=7,
        include_compare=True,
    )

    row = result["data"][0]
    assert "PM2_5_Curr_ForNow_Compare" not in row  # PM2.5 双口径同比字段只进落盘视图，不进上下文
    assert "PM2_5_Curr_ForNow_Increase" not in row
    assert "PM2_5_Curr_ForNow_ChangeType" not in row
    assert row["PM2_5_Curr_ForNow_R1"] == "45.6"
    assert "CompositeIndex_Compare" in row
    # 非浓度列只带 _Compare，不带变幅与变幅类型
    assert "FineDays_Compare" in row
    assert "FineDays_Increase" not in row
    assert "FineDays_ChangeType" not in row
    assert result["metadata"]["include_compare"] is True


@pytest.mark.asyncio
async def test_report_tool_cross_caliber_auto_fills_compare(monkeypatch):
    current_row = {
        "TimePoint": "2026-08",
        "CityCode": "411000",
        "UniqueCode": "411000",
        "PM2_5_Curr": "21",
        "PM2_5_Curr_Compare": "—",
        "PM2_5_Curr_Increase": "—",
        "PM2_5_Curr_ChangeType": "Rate",
        "PM2_5_Curr_ForNow": "20.7741940000",
        "PM2_5_Curr_ForNow_Compare": "—",
        "PM2_5_Curr_ForNow_Increase": "—",
        "PM2_5_Curr_ForNow_ChangeType": "Rate",
    }
    compare_row = {
        "TimePoint": "2025-08",
        "CityCode": "411000",
        "UniqueCode": "411000",
        "PM2_5_Curr": "15",
        "PM2_5_Curr_ForNow": "17.4000000000",
    }
    queried_tables = []

    def handler(url, json=None, headers=None, timeout=None):
        table = json["timeRanges"][0]["inputTableName"]
        queried_tables.append(table)
        data = [compare_row] if table.endswith("145") else [current_row]
        return httpx.Response(200, json=_envelope(data))

    _patch_post(monkeypatch, handler)

    result = await AirDataCalcReportSummaryTool().execute(
        start_time="2026-08-01",
        end_time="2026-08-31",
        input_table_name="view_dat_city_day_substitutionback_pantype155",
        year=2025,
        area_type=2,
        report_time_type=4,
        include_compare=True,
    )

    assert any(t.endswith("145") for t in queried_tables)
    row = result["data"][0]
    # 上下文 PM2.5 统一为 R1 口径：原始双口径同比不进上下文，R1 同比由全精度值换算
    assert "PM2_5_Curr_Compare" not in row
    assert "PM2_5_Curr_ForNow_Compare" not in row
    assert row["PM2_5_Curr_ForNow_R1"] == "20.8"
    assert row["PM2_5_Curr_ForNow_R1_Compare"] == "17.4"
    assert row["PM2_5_Curr_ForNow_R1_Increase"] == "19.5"
    assert row["PM2_5_Curr_ForNow_R1_ChangeType"] == "Rate"
    metadata = result["metadata"]
    assert metadata["compare_source"] == "auto_cross_caliber_145"
    assert metadata["compare_table_name"].endswith("145")
    assert metadata["compare_time_range"] == "2025-08-01 ~ 2025-08-31"
    assert "145" in result["summary"]


@pytest.mark.asyncio
async def test_report_tool_cross_caliber_skips_when_platform_has_compare(monkeypatch):
    row = _report_row()
    row["TimePoint"] = "2026-08"
    queried_tables = []

    def handler(url, json=None, headers=None, timeout=None):
        queried_tables.append(json["timeRanges"][0]["inputTableName"])
        return httpx.Response(200, json=_envelope([row]))

    _patch_post(monkeypatch, handler)

    result = await AirDataCalcReportSummaryTool().execute(
        start_time="2026-08-01",
        end_time="2026-08-31",
        input_table_name="view_dat_city_day_substitutionback_pantype155",
        year=2025,
        area_type=2,
        report_time_type=4,
        include_compare=True,
    )

    assert len(queried_tables) == 1  # 平台已给出同比，不再补查
    assert "compare_source" not in result["metadata"]


@pytest.mark.asyncio
async def test_report_tool_need_keys_passthrough_skips_projection(captured):
    captured["response"] = _envelope([{"PM25ExcessDays": "92"}])

    result = await AirDataCalcReportSummaryTool().execute(
        start_time="2025-01-01",
        end_time="2025-12-31",
        input_table_name="view_dat_station_day_app_pantype145",
        year=2024,
        area_type=0,
        report_time_type=7,
        need_keys=["PM25ExcessDays"],
    )

    assert captured["payload"]["needKeys"] == ["PM25ExcessDays"]
    assert set(result["data"][0]) == {"PM25ExcessDays"}
    assert result["metadata"]["need_keys_passthrough"] is True


@pytest.mark.asyncio
async def test_report_tool_need_keys_passthrough_computes_pm25_rounded(captured):
    captured["response"] = _envelope([_report_row()])

    result = await AirDataCalcReportSummaryTool().execute(
        start_time="2025-01-01",
        end_time="2025-12-31",
        input_table_name="view_dat_station_day_app_pantype145",
        year=2024,
        area_type=0,
        report_time_type=7,
        need_keys=["PM2_5_Curr_ForNow_R1", "PM25ExcessDays"],
    )

    assert captured["payload"]["needKeys"] == ["PM2_5_Curr_ForNow_R1", "PM25ExcessDays"]
    row = result["data"][0]
    assert row["PM2_5_Curr_ForNow_R1"] == "45.6"
    assert row["PM25ExcessDays"] == "92"
    assert result["metadata"]["need_keys_passthrough"] is True


@pytest.mark.asyncio
async def test_report_tool_saves_stripped_full_data_with_context(captured):
    captured["response"] = _envelope([_report_row()])

    class Context:
        def __init__(self):
            self.saved = None

        def save_data(self, **kwargs):
            self.saved = kwargs
            return "report-data-id"

    context = Context()
    result = await AirDataCalcReportSummaryTool().execute(
        context=context,
        start_time="2025-01-01",
        end_time="2025-12-31",
        input_table_name="view_dat_station_day_app_pantype145",
        year=2024,
        area_type=0,
        report_time_type=7,
    )

    assert result["file_path"] == "report-data-id"
    assert result["metadata"]["file_path"] == "report-data-id"
    saved_row = context.saved["data"][0]
    # 落盘的是剥离同比后的完整当期数据：白名单外字段与 PM2.5 双口径原始值保留
    assert saved_row["PM25ExcessDays"] == "92"
    assert saved_row["PM2_5_Curr"] == "46"
    assert saved_row["PM2_5_Curr_ForNow"] == "45.5650890000"
    assert "PM2_5_Curr_ForNow_R1" not in saved_row
    assert "PM2_5_Curr_ForNow_Compare" not in saved_row
    assert "PM2_5_Curr_ForNow_Compare" not in context.saved["metadata"]["columns"]
    assert "PM25ExcessDays" in context.saved["metadata"]["columns"]


@pytest.mark.asyncio
async def test_report_tool_truncates_preview_and_externalizes(monkeypatch):
    _patch_post(monkeypatch, _report_response([_report_row() for _ in range(30)]))
    saved = {}

    class Context:
        def save_data(self, **kwargs):
            saved.update(kwargs)
            return "report-data-id"

    result = await AirDataCalcReportSummaryTool().execute(
        context=Context(),
        start_time="2025-01-01",
        end_time="2025-12-31",
        input_table_name="view_dat_station_day_app_pantype145",
        year=2024,
        area_type=0,
        report_time_type=7,
    )

    assert result["metadata"]["total_records"] == 30
    assert result["metadata"]["returned_records"] == 24
    assert result["metadata"]["truncated"] is True
    assert saved["schema"] == "airdata_calc_report_summary"
    assert len(saved["data"]) == 30
