import pytest

from app.agent.prompts.tool_registry import get_tool_order
from app.tools.jiangsu.fault_diagnosis import (
    JiangsuFaultWorkOrdersTool,
    JiangsuQcMonitoringCurveTool,
    JiangsuQcRunLogTool,
    JiangsuQcTaskHistoryTool,
    JiangsuStationAlarmLogsTool,
)


def test_station_fault_diagnosis_exposes_only_read_only_evidence_and_knowledge_tools():
    assert get_tool_order("station_fault_diagnosis") == [
        "knowledge_qa_workflow",
        "knowledge_document_reader",
        "jiangsu_fetch_station_data",
        "jiangsu_fetch_alarm_records",
        "jiangsu_fetch_station_alarm_logs",
        "jiangsu_fetch_fault_work_orders",
        "jiangsu_fetch_auto_inspection",
        "jiangsu_fetch_qc_task_history",
        "jiangsu_fetch_qc_task_status",
        "jiangsu_fetch_qc_run_logs",
        "jiangsu_fetch_qc_monitoring_curve",
        "knowledge_graph_query",
    ]


@pytest.mark.asyncio
async def test_station_alarm_logs_exposes_structured_station_result(monkeypatch):
    async def fake_get(self, path, params):
        assert path.endswith("GetAlarmLogsAsync")
        assert params == [("StationCode", "1002A")]
        return {"success": True, "result": {"alarmLogs": [{"id": 1}], "alarmStatistics": [], "alarmState": {}}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuStationAlarmLogsTool().execute(station_code="1002A")

    assert result["success"] is True
    assert result["metadata"]["record_count"] == 1


@pytest.mark.asyncio
async def test_fault_work_orders_resolves_geographic_station_before_request(monkeypatch):
    async def fake_get(self, path, params):
        if path.endswith("GetAllEnabledBSDStationAsync"):
            assert params == []
            return {"success": True, "result": [{
                "positionName": "南京玄武湖站", "cityName": "南京市", "districtName": "玄武区",
                "uniqueCode": "2073201150070002",
            }]}
        assert path.endswith("GetWorkingOrderInfoByUniqueCode")
        assert params == [("uniqueCode", "2073201150070002"), ("take", "3")]
        return {"success": True, "result": [{"workingOrderCode": "WO-1"}]}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute(
        station_name="南京玄武湖站", city_name="南京", district_name="玄武", take=3
    )

    assert result["success"] is True
    assert result["data"][0]["workingOrderCode"] == "WO-1"
    assert result["metadata"]["station"]["station_name"] == "南京玄武湖站"
    assert "station_id" not in result["metadata"]


@pytest.mark.asyncio
async def test_qc_history_and_curve_use_repeated_time_range_parameters(monkeypatch):
    seen = []

    async def fake_get(self, path, params):
        seen.append((path, params))
        return {"success": True, "result": [{"rId": "task-1", "rStart": "2026-08-12 10:00:00"}]}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    history = await JiangsuQcTaskHistoryTool().execute(
        station_code="1002A", start_time="2026-08-12 00:00:00", end_time="2026-08-12 23:59:59", pollutant="SO2"
    )
    curve = await JiangsuQcMonitoringCurveTool().execute(
        station_code="1002A", pollutant="SO2", qc_type="零点校准",
        start_time="2026-08-12 10:00:00", end_time="2026-08-12 10:10:00"
    )

    assert history["success"] is True
    assert curve["success"] is True
    assert seen[0][0].endswith("GetNewQCHisResultListAsync")
    assert seen[0][1][1:3] == [("sStart", "2026-08-12 00:00:00"), ("sStart", "2026-08-12 23:59:59")]
    assert seen[1][0].endswith("GetNewQCAirDataResultListAsync")
    assert seen[1][1][-2:] == [("timePoint", "2026-08-12 10:00:00"), ("timePoint", "2026-08-12 10:10:00")]


@pytest.mark.asyncio
async def test_qc_run_log_uses_task_identifiers(monkeypatch):
    async def fake_get(self, path, params):
        assert path.endswith("GetNewQCHisRunLogResultListAsync")
        assert params == [("rStart", "2026-08-12 10:00:00"), ("rId", "task-1")]
        return {"success": True, "result": [{"recordTime": "2026-08-12 10:01:00"}]}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuQcRunLogTool().execute(r_start="2026-08-12 10:00:00", r_id="task-1")
    assert result["metadata"]["record_count"] == 1
