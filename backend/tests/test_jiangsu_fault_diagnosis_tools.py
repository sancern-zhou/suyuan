import pytest

from app.agent.prompts.tool_registry import get_tool_order
from app.tools.jiangsu.fault_diagnosis import (
    JiangsuAutoInspectionTool,
    JiangsuFaultWorkOrdersTool,
    JiangsuQcMonitoringCurveTool,
    JiangsuQcRunLogTool,
    JiangsuQcTaskHistoryTool,
    JiangsuStationAlarmLogsTool,
)
from app.tools.jiangsu.alarm_records import JiangsuAlarmRecordsTool


def test_station_fault_diagnosis_exposes_only_read_only_evidence_and_knowledge_tools():
    assert get_tool_order("station_fault_diagnosis") == [
        "knowledge_qa_workflow",
        "knowledge_document_reader",
        "jiangsu_fetch_station_data",
        "jiangsu_fetch_station_directory",
        "jiangsu_fetch_alarm_records",
        "jiangsu_fetch_station_alarm_logs",
        "jiangsu_fetch_fault_work_orders",
        "jiangsu_fetch_auto_inspection",
        "jiangsu_fetch_qc_task_history",
        "jiangsu_fetch_qc_task_status",
        "jiangsu_fetch_qc_run_logs",
        "jiangsu_fetch_qc_monitoring_curve",
        "jiangsu_query_operations_graph",
        "knowledge_graph_query",
    ]


@pytest.mark.asyncio
async def test_station_alarm_logs_exposes_structured_station_result(monkeypatch):
    async def fake_get(self, path, params):
        assert path.endswith("GetAlarmLogsAsync")
        assert params == [("StationCode", "1002A")]
        return {"success": True, "result": {"alarmLogs": [{"id": 1}], "alarmStatistics": [], "alarmState": {}}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuStationAlarmLogsTool().execute(station_codes=["1002A"])

    assert result["success"] is True
    assert result["metadata"]["record_count"] == 1


@pytest.mark.asyncio
async def test_station_alarm_logs_schema_only_supports_direct_station_lists():
    schema = JiangsuStationAlarmLogsTool().function_schema
    properties = schema["parameters"]["properties"]
    assert set(properties) == {"station_names", "station_codes", "unique_codes"}
    for parameter in properties.values():
        assert parameter["type"] == "array"
        assert parameter["maxItems"] == JiangsuStationAlarmLogsTool._MAX_STATIONS


@pytest.mark.asyncio
async def test_station_alarm_logs_rejects_city_scope():
    result = await JiangsuStationAlarmLogsTool().execute(city_name="南京市")

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "不支持城市/区县批量" in result["summary"]
    assert "jiangsu_fetch_alarm_records" in result["summary"]


@pytest.mark.asyncio
async def test_station_alarm_logs_queries_direct_station_list_concurrently(monkeypatch):
    import asyncio

    active = 0
    max_active = 0
    requested_codes = []

    async def fake_get(self, path, params):
        nonlocal active, max_active
        assert path.endswith("GetAlarmLogsAsync")
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        requested_codes.append(params[0][1])
        return {"success": True, "result": {"alarmLogs": [{"id": 1}]}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuStationAlarmLogsTool().execute(station_codes=["1001A", "1002A"])

    assert result["success"] is True
    assert result["metadata"]["station_count"] == 2
    assert result["metadata"]["record_count"] == 2
    assert sorted(requested_codes) == ["1001A", "1002A"]
    assert max_active == 2
    assert "并发查询 2 个站点" in result["summary"]


@pytest.mark.asyncio
async def test_station_alarm_logs_keeps_partial_results_when_one_station_fails(monkeypatch):
    async def fake_get(self, path, params):
        assert path.endswith("GetAlarmLogsAsync")
        if params == [("StationCode", "1002A")]:
            raise ValueError("站房告警接口 result 无效")
        return {"success": True, "result": {"alarmLogs": [{"id": 1}]}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuStationAlarmLogsTool().execute(station_codes=["1001A", "1002A"])

    assert result["success"] is True
    assert result["metadata"]["failed_station_count"] == 1
    assert result["metadata"]["record_count"] == 1


@pytest.mark.asyncio
async def test_station_alarm_logs_rejects_more_stations_than_limit():
    result = await JiangsuStationAlarmLogsTool().execute(
        station_codes=[f"1000{index}A" for index in range(JiangsuStationAlarmLogsTool._MAX_STATIONS + 1)]
    )

    assert result["success"] is False
    assert f"一次最多并发查询 {JiangsuStationAlarmLogsTool._MAX_STATIONS} 个站点" in result["summary"]


@pytest.mark.asyncio
async def test_fault_work_orders_resolves_station_name_before_request(monkeypatch):
    async def fake_get(self, path, params):
        if path.endswith("GetAllEnabledBSDStationAsync"):
            assert params == []
            return {"success": True, "result": [{
                "positionName": "南京玄武湖站", "cityName": "南京市", "districtName": "玄武区",
                "uniqueCode": "2073201150070002", "stationCode": "5006A",
            }]}
        assert path.endswith("GetWorkingOrderInfoByUniqueCode")
        assert params == [("uniqueCode", "2073201150070002"), ("take", "3")]
        return {"success": True, "result": [{"workingOrderCode": "WO-1"}]}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute(station_names=["南京玄武湖站"], take=3)

    assert result["success"] is True
    assert result["data"][0]["workingOrderCode"] == "WO-1"
    assert result["metadata"]["station_count"] == 1
    assert result["metadata"]["failed_station_count"] == 0


@pytest.mark.asyncio
async def test_fault_work_orders_rejects_city_scope():
    result = await JiangsuFaultWorkOrdersTool().execute(city_name="南京市", take=2)

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "不支持城市/区县批量" in result["summary"]


@pytest.mark.asyncio
async def test_fault_work_orders_queries_direct_station_list_concurrently(monkeypatch):
    import asyncio

    active = 0
    max_active = 0
    requested = []

    async def fake_get(self, path, params):
        nonlocal active, max_active
        if path.endswith("GetAllEnabledBSDStationAsync"):
            return {"success": True, "result": [
                {"positionName": "站点甲", "cityName": "南京市", "stationCode": "1001A", "uniqueCode": "U1"},
                {"positionName": "站点乙", "cityName": "南京市", "stationCode": "1002A", "uniqueCode": "U2"},
            ]}
        assert path.endswith("GetWorkingOrderInfoByUniqueCode")
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        requested.append(params[0][1])
        return {"success": True, "result": [{"workingOrderCode": params[0][1]}]}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute(station_codes=["1001A", "1002A"], take=2)

    assert result["success"] is True
    assert result["metadata"]["station_count"] == 2
    assert sorted(requested) == ["U1", "U2"]
    assert max_active == 2
    assert "并发查询 2 个站点" in result["summary"]


@pytest.mark.asyncio
async def test_fault_work_orders_rejects_more_stations_than_limit():
    result = await JiangsuFaultWorkOrdersTool().execute(
        station_codes=[f"1000{index}A" for index in range(JiangsuFaultWorkOrdersTool._MAX_STATIONS + 1)]
    )

    assert result["success"] is False
    assert f"一次最多并发查询 {JiangsuFaultWorkOrdersTool._MAX_STATIONS} 个站点" in result["summary"]


@pytest.mark.asyncio
async def test_alarm_records_resolves_province_selector_without_station_codes(monkeypatch):
    requested = []

    async def fake_directory(self, path, params):
        assert path.endswith("GetAllEnabledBSDStationAsync")
        return {"success": True, "result": [
            {"positionName": "站点甲", "provinceName": "江苏省", "cityName": "南京市",
             "stationCode": "1001A", "uniqueCode": "U1"},
            {"positionName": "站点乙", "provinceName": "江苏省", "cityName": "无锡市",
             "stationCode": "1002A", "uniqueCode": "U2"},
        ]}

    async def fake_alarm(self, params):
        requested.append(params)
        return {"success": True, "result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_directory)
    monkeypatch.setattr(JiangsuAlarmRecordsTool, "_request", fake_alarm)
    tool = JiangsuAlarmRecordsTool(base_url="http://ops", token_url="http://token", username="u", password="p")
    result = await tool.execute(city_name="江苏省", start_time="2026-08-01 00:00:00", end_time="2026-08-01 01:00:00")

    assert result["success"] is True
    assert result["metadata"]["station_codes"] == ["1001A", "1002A"]


@pytest.mark.asyncio
async def test_qc_history_and_curve_use_repeated_time_range_parameters(monkeypatch):
    seen = []

    async def fake_get(self, path, params):
        seen.append((path, params))
        return {"success": True, "result": [{"rId": "task-1", "rStart": "2026-08-12 10:00:00"}]}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    history = await JiangsuQcTaskHistoryTool().execute(
        station_codes=["1002A"], start_time="2026-08-12 00:00:00", end_time="2026-08-12 23:59:59", pollutant="SO2"
    )
    curve = await JiangsuQcMonitoringCurveTool().execute(
        station_codes=["1002A"], pollutant="SO2", qc_type="零点校准",
        start_time="2026-08-12 10:00:00", end_time="2026-08-12 10:10:00"
    )

    assert history["success"] is True
    assert curve["success"] is True
    assert seen[0][0].endswith("GetNewQCHisResultListAsync")
    assert seen[0][1][1:3] == [("sStart", "2026-08-12 00:00:00"), ("sStart", "2026-08-12 23:59:59")]
    assert seen[1][0].endswith("GetNewQCAirDataResultListAsync")
    assert seen[1][1][-2:] == [("timePoint", "2026-08-12 10:00:00"), ("timePoint", "2026-08-12 10:10:00")]


@pytest.mark.asyncio
async def test_qc_history_rejects_city_scope():
    result = await JiangsuQcTaskHistoryTool().execute(
        city_name="南京市", start_time="2026-08-12 00:00:00", end_time="2026-08-12 23:59:59"
    )

    assert result["success"] is False
    assert "不支持城市/区县批量" in result["summary"]


@pytest.mark.asyncio
async def test_qc_curve_rejects_city_scope():
    result = await JiangsuQcMonitoringCurveTool().execute(
        city_name="南京市", pollutant="SO2", qc_type="零点校准",
        start_time="2026-08-12 10:00:00", end_time="2026-08-12 10:10:00",
    )

    assert result["success"] is False
    assert "不支持城市/区县批量" in result["summary"]


@pytest.mark.asyncio
async def test_qc_history_queries_direct_station_list_concurrently(monkeypatch):
    import asyncio

    active = 0
    max_active = 0
    requested_codes = []

    async def fake_get(self, path, params):
        nonlocal active, max_active
        assert path.endswith("GetNewQCHisResultListAsync")
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        requested_codes.append(params[0][1])
        return {"success": True, "result": [{"rId": "task-1"}]}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuQcTaskHistoryTool().execute(
        station_codes=["1001A", "1002A"], start_time="2026-08-12 00:00:00", end_time="2026-08-12 23:59:59"
    )

    assert result["success"] is True
    assert result["metadata"]["station_count"] == 2
    assert result["metadata"]["record_count"] == 2
    assert sorted(requested_codes) == ["1001A", "1002A"]
    assert max_active == 2
    assert "并发查询 2 个站点" in result["summary"]


@pytest.mark.asyncio
async def test_qc_run_log_uses_task_identifiers(monkeypatch):
    async def fake_get(self, path, params):
        assert path.endswith("GetNewQCHisRunLogResultListAsync")
        assert params == [("rStart", "2026-08-12 10:00:00"), ("rId", "task-1")]
        return {"success": True, "result": [{"recordTime": "2026-08-12 10:01:00"}]}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuQcRunLogTool().execute(r_start="2026-08-12 10:00:00", r_id="task-1")
    assert result["metadata"]["record_count"] == 1


@pytest.mark.asyncio
async def test_auto_inspection_schema_only_supports_direct_station_lists():
    schema = JiangsuAutoInspectionTool().function_schema
    properties = schema["parameters"]["properties"]
    assert set(properties) == {"station_names", "station_codes", "unique_codes"}
    for parameter in properties.values():
        assert parameter["type"] == "array"
        assert parameter["maxItems"] == JiangsuAutoInspectionTool._MAX_STATIONS


@pytest.mark.asyncio
async def test_auto_inspection_rejects_city_scope_without_partial_results():
    result = await JiangsuAutoInspectionTool().execute(city_name="南京市")

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "不支持城市/区县批量" in result["summary"]
    assert "network_inspection_summary" in result["summary"]


@pytest.mark.asyncio
async def test_auto_inspection_queries_direct_station_list_concurrently(monkeypatch):
    import asyncio

    active = 0
    max_active = 0
    inspected_station_ids = []

    async def fake_get(self, path, params):
        assert path.endswith("GetAllEnabledBSDStationAsync")
        return {"success": True, "result": [
            {"positionName": "站点甲", "cityName": "南京市", "stationCode": "1001A", "uniqueCode": "U1"},
            {"positionName": "站点乙", "cityName": "南京市", "stationCode": "1002A", "uniqueCode": "U2"},
        ]}

    async def fake_post(self, path, payload):
        nonlocal active, max_active
        assert path.endswith("QcSvcAgent")
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        inspected_station_ids.append(payload["data"].split("&", 1)[0].removeprefix("StationId="))
        return {"success": True, "result": {"DevDtls": []}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.post", fake_post)
    result = await JiangsuAutoInspectionTool().execute(station_codes=["1001A", "1002A"])

    assert result["success"] is True
    assert result["metadata"]["station_count"] == 2
    assert sorted(inspected_station_ids) == ["U1", "U2"]
    assert max_active == 2
    assert "并发巡检 2 个站点" in result["summary"]


@pytest.mark.asyncio
async def test_auto_inspection_rejects_more_stations_than_limit():
    result = await JiangsuAutoInspectionTool().execute(
        station_codes=[f"1000{index}A" for index in range(JiangsuAutoInspectionTool._MAX_STATIONS + 1)]
    )

    assert result["success"] is False
    assert f"最多并发巡检 {JiangsuAutoInspectionTool._MAX_STATIONS} 个站点" in result["summary"]
