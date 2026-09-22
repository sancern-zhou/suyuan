import asyncio
import json
from pathlib import Path

import pytest

from app.agent.prompts.tool_registry import get_tool_order
from app.agent.resources.contracts import ResourceDeclaration
from app.tools.jiangsu.alarm_records import JiangsuAlarmRecordsTool
from app.tools.jiangsu.fault_diagnosis import (
    JiangsuAutoInspectionTool,
    JiangsuFaultWorkOrderDetailTool,
    JiangsuFaultWorkOrdersTool,
    JiangsuQcMonitoringCurveTool,
    JiangsuQcRunLogTool,
    JiangsuQcTaskHistoryTool,
    JiangsuQcTaskStatusTool,
    JiangsuReviewEvidenceTool,
    JiangsuStationAlarmLogsTool,
    JiangsuStationEnvironmentHistoryTool,
)


def test_station_fault_diagnosis_exposes_only_read_only_evidence_and_knowledge_tools():
    assert get_tool_order("station_fault_diagnosis") == [
        "jiangsu_smart_event_workspace",
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
async def test_fault_work_orders_list_mode_applies_platform_status_defaults(monkeypatch):
    requested = []

    async def fake_get(self, path, params):
        assert path.endswith("GetMtcWorkingOrderPagedListAsync")
        requested.append(params)
        return {"success": True, "result": {"items": [{"workingOrderCode": "WO-1"}], "totalCount": 1}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute()

    assert result["success"] is True
    assert result["metadata"]["query_mode"] == "filtered"
    assert result["metadata"]["total_count"] == 1
    assert ("OrderType", "Fault") in requested[0]
    assert ("WorkFlowStatus", "ToAssign") in requested[0]
    assert ("WorkFlowStatus", "ToAccept") in requested[0]
    assert ("WorkFlowStatus", "Doing") in requested[0]
    assert ("OrderStatus", "Wait") in requested[0]
    assert ("OrderStatus", "Doing") in requested[0]
    assert ("OrderStatus", "Finish") in requested[0]
    assert result["metadata"]["defaults_applied"] is True
    assert "待处理/处理中/已完成" in result["summary"]


@pytest.mark.asyncio
async def test_fault_work_orders_list_mode_supports_order_code_time_and_statuses(monkeypatch):
    requested = []

    async def fake_get(self, path, params):
        assert path.endswith("GetMtcWorkingOrderPagedListAsync")
        requested.append(params)
        return {"success": True, "result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute(
        working_order_code="GD20260801001",
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-24 23:59:59",
        workflow_statuses=["已完成", "Reject"],
        order_statuses=[],
        fetch_all=False,
        page=2,
        page_size=20,
    )

    assert result["success"] is True
    assert result["status"] == "empty"
    assert ("WorkingOrderCode", "GD20260801001") in requested[0]
    assert ("CreateTime", "2026-08-01 00:00:00") in requested[0]
    assert ("CreateTime", "2026-08-24 23:59:59") in requested[0]
    assert ("WorkFlowStatus", "Finish") in requested[0]
    assert ("WorkFlowStatus", "Reject") in requested[0]
    assert not any(key == "OrderStatus" for key, _ in requested[0])
    assert ("SkipCount", "20") in requested[0]
    assert ("MaxResultCount", "20") in requested[0]
    assert result["metadata"]["defaults_applied"] is False
    assert result["metadata"]["filters"]["order_statuses"] == []


@pytest.mark.asyncio
async def test_fault_work_orders_empty_order_types_queries_all_types(monkeypatch):
    requested = []

    async def fake_get(self, path, params):
        if path.endswith("GetAllEnabledBSDStationAsync"):
            return {"success": True, "result": [
                {"positionName": "站点甲", "cityName": "南京市", "stationCode": "1001A", "uniqueCode": "U1"},
            ]}
        assert path.endswith("GetMtcWorkingOrderPagedListAsync")
        requested.append(params)
        return {"success": True, "result": {"items": [{
            "workingOrderCode": "XJ-1", "orderType": "Check", "orderTypeStr": "巡检单",
            "ruleType": "Week", "ruleTypeName": "每周",
        }], "totalCount": 1}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute(
        station_codes=["1001A"], order_types=[], workflow_statuses=[], order_statuses=[],
    )

    assert result["success"] is True
    assert not any(key == "OrderType" for key, _ in requested[0])
    assert result["metadata"]["filters"]["order_types"] == []
    assert result["data"][0]["orderType"] == "Check"
    assert result["data"][0]["ruleTypeName"] == "每周"
    assert result["summary"].startswith("工单查询完成")


@pytest.mark.asyncio
async def test_fault_work_orders_supports_platform_qa_type(monkeypatch):
    requested = []

    async def fake_get(self, path, params):
        assert path.endswith("GetMtcWorkingOrderPagedListAsync")
        requested.append(params)
        return {"success": True, "result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute(order_types=["QA"])

    assert result["success"] is True
    assert ("OrderType", "QA") in requested[0]
    assert result["metadata"]["filters"]["order_types"] == ["QA"]


@pytest.mark.asyncio
async def test_fault_work_orders_list_mode_resolves_node_names(monkeypatch):
    requested = []

    async def fake_get(self, path, params):
        requested.append((path, params))
        if path.endswith("GetWorkFlowByUser"):
            assert params == [("Type", "Fault")]
            return {"success": True, "result": {"stepList": [
                {"guid": "guid-process", "taskName": "故障处理"},
                {"guid": "guid-review", "taskName": "故障审核"},
            ]}}
        assert path.endswith("GetMtcWorkingOrderPagedListAsync")
        return {"success": True, "result": {"items": [{"workingOrderCode": "WO-9"}], "totalCount": 1}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute(current_points=["故障审核", "guid-process"])

    assert result["success"] is True
    list_params = requested[-1][1]
    assert ("CurrentPoint", "guid-review") in list_params
    assert ("CurrentPoint", "guid-process") in list_params


@pytest.mark.asyncio
async def test_fault_work_orders_list_mode_rejects_unknown_node_and_status(monkeypatch):
    async def fake_get(self, path, params):
        if path.endswith("GetWorkFlowByUser"):
            return {"success": True, "result": {"stepList": [{"guid": "guid-1", "taskName": "故障处理"}]}}
        raise AssertionError("list endpoint should not be reached")

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    tool = JiangsuFaultWorkOrdersTool()

    unknown_node = await tool.execute(current_points=["不存在的节点"])
    assert unknown_node["success"] is False
    assert "未知工单节点" in unknown_node["summary"]

    unknown_status = await tool.execute(workflow_statuses=["Done"])
    assert unknown_status["success"] is False
    assert "无效值" in unknown_status["summary"]


@pytest.mark.asyncio
async def test_fault_work_orders_filters_with_stations_use_list_mode(monkeypatch):
    requested = []

    async def fake_get(self, path, params):
        requested.append((path, params))
        if path.endswith("GetAllEnabledBSDStationAsync"):
            return {"success": True, "result": [
                {"positionName": "站点甲", "cityName": "南京市", "stationCode": "1001A", "uniqueCode": "U1"},
            ]}
        assert path.endswith("GetMtcWorkingOrderPagedListAsync")
        return {"success": True, "result": {"items": [{"workingOrderCode": "WO-2"}], "totalCount": 1}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute(
        station_codes=["1001A"], workflow_statuses=["ToAccept"],
    )

    assert result["success"] is True
    assert result["metadata"]["query_mode"] == "filtered"
    list_params = requested[-1][1]
    assert ("StationCode", "1001A") in list_params
    assert ("WorkFlowStatus", "ToAccept") in list_params


class _FaultOrderContext:
    def __init__(self):
        self.saved = []

    def save_data(self, *, data, schema, metadata):
        self.saved.append({"data": data, "schema": schema, "metadata": metadata})
        return f"backend/backend_data_registry/sessions/test/data/{schema}.json"


@pytest.mark.asyncio
async def test_fault_work_orders_fetches_all_pages_and_externalizes_over_24(monkeypatch):
    requested = []

    async def fake_get(self, path, params):
        assert path.endswith("GetMtcWorkingOrderPagedListAsync")
        requested.append(params)
        skip = int(dict(params)["SkipCount"])
        count = 50 if skip == 0 else 5
        items = [
            {
                "workingOrderCode": f"WO-{index:03d}",
                "uniqueCode": f"U-{index:03d}",
                "orderTitle": f"故障工单 {index}",
                "orderStatusStr": "处理中",
                "btnEdit": True,
                "commonFile": {"unused": "platform ui state"},
            }
            for index in range(skip, skip + count)
        ]
        return {"success": True, "result": {"items": items, "totalCount": 55}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    context = _FaultOrderContext()
    result = await JiangsuFaultWorkOrdersTool().execute(context=context)

    assert result["success"] is True
    assert len(requested) == 2
    assert [dict(params)["SkipCount"] for params in requested] == ["0", "50"]
    assert result["record_count"] == 55
    assert result["returned_records"] == 24
    assert result["data_complete"] is False
    assert result["metadata"]["source_data_complete"] is True
    assert result["file_path"].endswith("jiangsu_fault_work_order_list.json")
    assert len(result["data"]) == 24
    assert len(context.saved) == 1
    assert len(context.saved[0]["data"]) == 55
    assert "btnEdit" not in context.saved[0]["data"][0]
    assert "commonFile" not in context.saved[0]["data"][0]


@pytest.mark.asyncio
async def test_fault_work_orders_keeps_exactly_24_compact_records_inline(monkeypatch):
    async def fake_get(self, path, params):
        items = [
            {
                "workingOrderCode": f"WO-{index:03d}",
                "uniqueCode": f"U-{index:03d}",
                "stationName": "测试站",
                "orderTitle": "颗粒物分析仪故障",
                "orderContent": "设备出现告警，请核查处置。",
                "orderStatusStr": "处理中",
                "commonFile": {"large": "x" * 1000},
                "btnEdit": True,
            }
            for index in range(24)
        ]
        return {"success": True, "result": {"items": items, "totalCount": 24}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    context = _FaultOrderContext()
    result = await JiangsuFaultWorkOrdersTool().execute(context=context)

    assert result["data_complete"] is True
    assert result["record_count"] == 24
    assert "file_path" not in result
    assert context.saved == []
    assert "commonFile" not in result["data"][0]
    assert len(json.dumps(result, ensure_ascii=False)) < 20_000


@pytest.mark.asyncio
async def test_fault_work_order_detail_locates_downloads_attachments_and_returns_exact_order(monkeypatch, tmp_path):
    requested = []
    downloaded = []

    async def fake_get(self, path, params):
        requested.append((path, params))
        if path.endswith("GetMtcWorkingOrderPagedListAsync"):
            return {"success": True, "result": {"items": [
                {"workingOrderCode": "WO-EXACT", "uniqueCode": "U-1"},
            ], "totalCount": 1}}
        assert path.endswith("GetWorkingOrderInfoByUniqueCode")
        return {"success": True, "result": [
            {"wo": {"workingOrderCode": "WO-OTHER"}, "details": []},
            {
                "wo": {
                    "workingOrderCode": "WO-EXACT",
                    "orderTitle": "分析仪故障",
                    "btnEdit": True,
                    "commonFile": [
                        {
                            "id": 7,
                            "fileName": "evidence.jpg",
                            "filePath": "/NewFiles/Fault/FaultProcess/2026/8/evidence.jpg",
                            "typeCode": "FaultProcess",
                        },
                        {
                            "id": 8,
                            "fileName": "invalid.jpg",
                            "filePath": "/outside/invalid.jpg",
                            "typeCode": "FaultProcess",
                        },
                    ],
                },
                "details": [{"processContent": "已更换备件"}],
                "faultContentItems": [{"faultName": "通讯异常"}],
                "checkItemList": [{"name": "通信检查"}],
                "faultDevice": {"deviceName": "PM2.5 分析仪"},
                "workFlowInfo": {"stepList": [{
                    "guid": "step-1", "taskName": "省中心审核", "orderDetailDto": {"large": "x" * 1000},
                }]},
                "selectDevices": [
                    {"id": index, "label": f"候选设备 {index}", "unused": "x" * 100}
                    for index in range(1682)
                ],
            },
        ]}

    async def fake_download_file(self, path, params, *, max_bytes, retry_unauthorized=True):
        downloaded.append((path, params, max_bytes, retry_unauthorized))
        return b"\xff\xd8\xff\xe0JFIF-test-image", "image/jpeg"

    attachment_dir = tmp_path / "attachments"
    attachment_dir.mkdir()
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    monkeypatch.setattr(
        "app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.download_file",
        fake_download_file,
    )
    monkeypatch.setattr(
        "app.tools.jiangsu.fault_diagnosis._fault_attachment_output_dir",
        lambda raw_resource_path, order_code: attachment_dir,
    )
    context = _FaultOrderContext()
    result = await JiangsuFaultWorkOrderDetailTool().execute(
        context=context, working_order_code="WO-EXACT",
    )

    assert result["success"] is True
    assert result["data"][0]["wo"]["workingOrderCode"] == "WO-EXACT"
    assert result["data"][0]["details"][0]["processContent"] == "已更换备件"
    assert result["data"][0]["workFlowInfo"]["stepList"][0]["taskName"] == "省中心审核"
    assert result["data"][0]["attachments"][0]["fileName"] == "evidence.jpg"
    assert result["data"][0]["attachments"][0]["download_status"] == "success"
    assert result["data"][0]["attachments"][0]["content_type"] == "image/jpeg"
    assert Path(result["data"][0]["attachments"][0]["local_path"]).is_file()
    assert result["data"][0]["attachments"][1]["download_status"] == "failed"
    assert "NewFiles" in result["data"][0]["attachments"][1]["download_error"]
    assert "commonFile" not in result["data"][0]["wo"]
    assert "btnEdit" not in result["data"][0]["wo"]
    assert "selectDevices" not in result["data"][0]
    assert result["metadata"]["process_record_count"] == 1
    assert result["metadata"]["select_devices_omitted"] == 1682
    assert result["metadata"]["attachment_count"] == 2
    assert result["metadata"]["attachments_downloaded"] == 1
    assert result["metadata"]["attachments_failed"] == 1
    assert result["metadata"]["attachments_skipped"] == 0
    assert result["metadata"]["attachment_bytes"] == len(b"\xff\xd8\xff\xe0JFIF-test-image")
    assert result["metadata"]["inline_projection"] == "fault_order_review_v1"
    assert result["resources"][0]["role"] == "attachment"
    assert result["resources"][0]["renderer"] == "image"
    assert result["resources"][0]["label"] == "evidence.jpg"
    assert ResourceDeclaration.model_validate(result["resources"][0])
    assert result["file_path"].endswith("jiangsu_fault_work_order_detail_raw.json")
    assert context.saved[0]["schema"] == "jiangsu_fault_work_order_detail_raw"
    assert len(context.saved[0]["data"][0]["selectDevices"]) == 1682
    assert len(json.dumps(result, ensure_ascii=False, indent=2)) < 20_000
    assert requested[0][1][-1] == ("WorkingOrderCode", "WO-EXACT")
    assert requested[1][1] == [("uniqueCode", "U-1"), ("take", "20")]
    assert downloaded == [(
        "basicinfo/FileCommon/DownFile",
        [("filePath", "/NewFiles/Fault/FaultProcess/2026/8/evidence.jpg")],
        20 * 1024 * 1024,
        True,
    )]


@pytest.mark.asyncio
async def test_fault_work_order_detail_downloads_attachments_without_session_context(monkeypatch, tmp_path):
    async def fake_get(self, path, params):
        if path.endswith("GetMtcWorkingOrderPagedListAsync"):
            return {"success": True, "result": {"items": [
                {"workingOrderCode": "WO-NO-CONTEXT", "uniqueCode": "U-1"},
            ], "totalCount": 1}}
        assert path.endswith("GetWorkingOrderInfoByUniqueCode")
        return {"success": True, "result": [
            {
                "wo": {
                    "workingOrderCode": "WO-NO-CONTEXT",
                    "commonFile": [{
                        "id": 9,
                        "fileName": "现场照片.jpg",
                        "filePath": "/NewFiles/Fault/FaultProcess/2026/9/photo.jpg",
                        "typeCode": "FaultProcess",
                    }],
                },
                "details": [{"processContent": "现场检查"}],
            },
        ]}

    async def fake_download_file(self, path, params, *, max_bytes, retry_unauthorized=True):
        return b"\xff\xd8\xff\xe0JFIF-from-no-context", "image/jpeg"

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.get_data_registry", lambda: tmp_path)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    monkeypatch.setattr(
        "app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.download_file",
        fake_download_file,
    )

    result = await JiangsuFaultWorkOrderDetailTool().execute(working_order_code="WO-NO-CONTEXT")

    attachment = result["data"][0]["attachments"][0]
    saved_path = Path(attachment["local_path"])
    assert result["success"] is True
    assert result["metadata"]["raw_resource_saved"] is False
    assert result["metadata"]["attachments_downloaded"] == 1
    assert result["metadata"]["attachments_skipped"] == 0
    assert attachment["download_status"] == "success"
    assert attachment["content_type"] == "image/jpeg"
    assert saved_path.is_file()
    assert saved_path.is_relative_to(tmp_path / "work_order_review_attachments" / "WO-NO-CONTEXT")
    assert saved_path.read_bytes() == b"\xff\xd8\xff\xe0JFIF-from-no-context"
    assert "file_path" not in result
    assert ResourceDeclaration.model_validate(result["resources"][0])


@pytest.mark.asyncio
async def test_fault_work_order_detail_never_substitutes_another_order(monkeypatch):
    async def fake_get(self, path, params):
        if path.endswith("GetMtcWorkingOrderPagedListAsync"):
            return {"success": True, "result": {"items": [
                {"workingOrderCode": "WO-EXACT", "uniqueCode": "U-1"},
            ], "totalCount": 1}}
        return {"success": True, "result": [
            {"wo": {"workingOrderCode": "WO-OTHER"}, "details": [{"processContent": "其他工单"}]},
        ]}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrderDetailTool().execute(working_order_code="WO-EXACT")

    assert result["success"] is False
    assert result["data"] == []
    assert "未使用其他工单替代" in result["summary"]


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
    result = await tool.execute_pipeline(city_name="江苏省", start_time="2026-08-01 00:00:00", end_time="2026-08-01 01:00:00")

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
async def test_fault_work_orders_mine_only_uses_role_step_ids(monkeypatch):
    requested = []

    async def fake_get(self, path, params):
        requested.append((path, params))
        if path.endswith("GetWorkFlowByUser"):
            assert params == [("Type", "Fault")]
            return {"success": True, "result": {
                "stepList": [{"guid": "prov", "taskName": "省中心审核"}],
                "stepIds": ["prov"],
            }}
        assert path.endswith("GetMtcWorkingOrderPagedListAsync")
        return {"success": True, "result": {"items": [
            {"workingOrderCode": "WO-1", "currentPointName": "省中心审核", "orderStatusStr": "处理中"},
            {"workingOrderCode": "WO-2", "currentPointName": "运维单位审核", "orderStatusStr": "处理中"},
        ], "totalCount": 2}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute(mine_only=True)

    assert result["success"] is True
    list_params = requested[1][1]
    assert ("CurrentPoint", "prov") in list_params
    assert result["metadata"]["filters"]["mine_only"] is True
    assert result["metadata"]["distribution"]["scope"] == "full"
    assert result["metadata"]["distribution"]["by_node"] == {"运维单位审核": 1, "省中心审核": 1}
    assert result["metadata"]["distribution"]["by_order_status"] == {"处理中": 2}
    assert "节点分布" in result["summary"]


@pytest.mark.asyncio
async def test_fault_work_orders_mine_only_conflicts_with_current_points():
    result = await JiangsuFaultWorkOrdersTool().execute(
        mine_only=True, current_points=["省中心审核"],
    )

    assert result["success"] is False
    assert "二选一" in result["summary"]


@pytest.mark.asyncio
async def test_fault_work_orders_review_finished_filters_by_finish_time(monkeypatch):
    requested = []

    async def fake_get(self, path, params):
        requested.append((path, params))
        if path.endswith("GetWorkFlowByUser"):
            return {"success": True, "result": {"stepList": [{"guid": "prov", "taskName": "省中心审核"}]}}
        assert path.endswith("GetMtcWorkingOrderPagedListAsync")
        return {"success": True, "result": {"items": [
            {"workingOrderCode": "WO-IN", "currentPointName": "省中心审核",
             "createTime": "2026-09-10 08:00:00", "finishTime": "2026-09-15 10:00:00"},
            {"workingOrderCode": "WO-EARLY", "currentPointName": "省中心审核",
             "createTime": "2026-09-01 08:00:00", "finishTime": "2026-09-02 10:00:00"},
            {"workingOrderCode": "WO-NO-FINISH", "currentPointName": "省中心审核",
             "createTime": "2026-09-11 08:00:00"},
        ], "totalCount": 3}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuFaultWorkOrdersTool().execute(
        current_points=["省中心审核"],
        review_finished_start="2026-09-14 00:00:00",
        review_finished_end="2026-09-20 23:59:59",
    )

    assert result["success"] is True
    list_params = requested[1][1]
    # 自动限定 Finish 并回溯创建时间窗口
    assert list_params.count(("WorkFlowStatus", "Finish")) == 1
    create_times = [value for name, value in list_params if name == "CreateTime"]
    assert len(create_times) == 2
    assert create_times[0] < "2026-09-14"
    assert [item["workingOrderCode"] for item in result["data"]] == ["WO-IN"]
    review = result["metadata"]["review_finished"]
    assert review["platform_matched"] == 3
    assert review["matched"] == 1
    assert review["dropped_out_of_range"] == 1
    assert review["dropped_missing_finish_time"] == 1
    assert review["forced_workflow_status_finish"] is True
    assert review["created_window_widened_days"] == JiangsuFaultWorkOrdersTool._REVIEW_FILTER_BACKFILL_DAYS
    assert result["metadata"]["distribution"]["by_node"] == {"省中心审核": 1}
    assert "窗口内完成 1 条" in result["summary"]


@pytest.mark.asyncio
async def test_fault_work_orders_review_finished_rejects_conflicting_workflow_statuses():
    result = await JiangsuFaultWorkOrdersTool().execute(
        current_points=["省中心审核"],
        workflow_statuses=["Doing"],
        review_finished_start="2026-09-14 00:00:00",
    )

    assert result["success"] is False
    assert "Finish" in result["summary"]


@pytest.mark.asyncio
async def test_fault_work_orders_review_finished_requires_start():
    result = await JiangsuFaultWorkOrdersTool().execute(review_finished_end="2026-09-20 00:00:00")

    assert result["success"] is False
    assert "review_finished_start" in result["summary"]


@pytest.mark.asyncio
async def test_review_evidence_builds_panel_visual(monkeypatch):
    async def fake_directory(self, path, params):
        assert path.endswith("GetAllEnabledBSDStationAsync")
        return {"success": True, "result": [
            {"positionName": "阜宁滨湖", "cityName": "盐城市", "districtName": "阜宁县",
             "stationCode": "7099A", "uniqueCode": "320100397"},
        ]}

    async def fake_raw_records(self, **kwargs):
        assert kwargs["data_kind"] == "station_hour"
        assert kwargs["station_codes"] == ["7099A"]
        assert "pollutant_codes" not in kwargs
        return ([
            {"timePoint": "2026-09-14 10:00:00", "pM10": 82.0},
            {"timePoint": "2026-09-14 11:00:00", "pM10": -99},
            {"timePoint": "2026-09-14 12:00:00", "pM10": 120.5},
        ], 3)

    async def fake_city_weather(*, city_name, start_time, end_time):
        assert city_name == "盐城市"
        return {"status": "success", "data": [
            {"timePoint": "2026-09-14T10:00:00", "windSpeed": 2.1, "windDirection": 120,
             "temperature": 24.0, "humidity": 60, "rain": 0, "pressure": 1008},
        ]}

    async def fake_same_city_band(station, start_time, end_time, pollutant, *, station_data_tool=None):
        assert pollutant == "PM10"
        return {"status": "success", "scope": "same_district", "station_count": 3, "band": [
            {"time": "2026-09-14 10:00:00", "target": 82.0, "min": 60.0, "median": 70.0, "max": 90.0},
            {"time": "2026-09-14 12:00:00", "target": 120.5, "min": 65.0, "median": 75.0, "max": 95.0},
        ]}

    saved_packages = []

    def fake_save_evidence(package):
        saved_packages.append(package)
        return {"working_order_code": package["working_order_code"], "status": "待审核",
                "index_path": "/nonexistent/jiangsu_work_order_reviews/index.json",
                "source_files": {}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_directory)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.JiangsuStationDataTool.fetch_raw_records", fake_raw_records)
    monkeypatch.setattr("app.fetchers.weather.jiangsu_review_weather.fetch_city_weather", fake_city_weather)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.fetch_same_city_band", fake_same_city_band)
    monkeypatch.setattr("app.services.jiangsu_work_order_review.save_evidence", fake_save_evidence)

    result = await JiangsuReviewEvidenceTool().execute(
        station_names=["阜宁滨湖"], pollutant="PM10",
        start_time="2026-09-14 00:00:00", end_time="2026-09-15 00:00:00",
        working_order_code="FA260914178938611578927",
        modules=[],
    )

    assert result["success"] is True
    # 不再向可视化面板发布图表：visuals 为空，资源只包含证据索引/分文件（此处路径不可用则降级为空）
    assert result["visuals"] == []
    assert result["resources"] == []
    # 证据索引投影：LLM 可直接读到逐时值与统计摘要
    index = result["data"]["evidence_index"]
    assert index["station_hour"]["projection"]["hourly"] == [
        {"time": "2026-09-14 10:00:00", "value": 82.0},
        {"time": "2026-09-14 12:00:00", "value": 120.5},
    ]
    assert index["band"]["projection"]["exceed_hours"] == 1
    assert index["band"]["projection"]["exceed_samples"] == [
        {"time": "2026-09-14 12:00:00", "target": 120.5, "band_max": 95.0}]
    assert index["weather"]["projection"]["windSpeed"]["max"] == 2.1
    # 证据包拆分持久化：sources 携带完整 data
    assert saved_packages[0]["working_order_code"] == "FA260914178938611578927"
    assert saved_packages[0]["sources"]["station_hour"]["data"]["points"] == [
        {"time": "2026-09-14 10:00:00", "value": 82.0},
        {"time": "2026-09-14 12:00:00", "value": 120.5},
    ]
    assert result["data"]["package"]["status"] == "待审核"
    assert result["data"]["ui_command"] == {
        "type": "open_work_order_review", "working_order_code": "FA260914178938611578927"}
    assert result["metadata"]["point_count"] == 2
    assert result["metadata"]["band_point_count"] == 2
    assert result["metadata"]["weather_status"] == "success"


@pytest.mark.asyncio
async def test_review_evidence_resolves_from_working_order_code(monkeypatch, tmp_path):
    async def fake_get(self, path, params):
        if path.endswith("GetMtcWorkingOrderPagedListAsync"):
            assert ("WorkingOrderCode", "FA260914178938611578927") in params
            return {"success": True, "result": {"items": [
                {"workingOrderCode": "FA260914178938611578927", "uniqueCode": "320100397",
                 "stationCodeStr": "7099A", "createTime": "2026-09-14 21:14:44",
                 "orderTitle": "PM10 分析仪数据偏高，疑似污染过程"},
            ], "totalCount": 1}}
        if path.endswith("GetWorkingOrderInfoByUniqueCode"):
            assert ("uniqueCode", "320100397") in params
            return {"success": True, "result": [
                {"wo": {"workingOrderCode": "FA260914178938611578927",
                        "orderTitle": "PM10 分析仪数据偏高，疑似污染过程",
                        "orderContent": "09-14 06 时起 PM10 抬升",
                        "createTime": "2026-09-14 19:41:00",
                        "commonFile": [{"id": "file-1", "fileName": "站点照片.jpg",
                                        "filePath": "/NewFiles/2026/09/站点照片.jpg"}]},
                 "details": [{"processContent": "现场检查采样已恢复", "createTime": "2026-09-14 19:42:00"}],
                 "workFlowInfo": {"stepList": [{"taskName": "省中心审核", "status": 2,
                                                "createTime": "2026-09-15 10:30:00"}]}},
            ]}
        assert path.endswith("GetAllEnabledBSDStationAsync")
        return {"success": True, "result": [
            {"positionName": "阜宁滨湖", "cityName": "盐城市", "districtName": "阜宁县",
             "stationCode": "7099A", "uniqueCode": "320100397"},
        ]}

    async def fake_download_file(self, path, params, max_bytes=None):
        assert path.endswith("DownFile")
        return b"fake-image-bytes", "image/jpeg"

    def fake_output_dir(raw_resource_path, order_code):
        folder = tmp_path / "attachments"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    async def fake_raw_records(self, **kwargs):
        assert "pollutant_codes" not in kwargs
        assert kwargs["start_time"] == "2026-09-13 21:14:44"
        assert kwargs["end_time"] == "2026-09-16 21:14:44"
        return ([{"timePoint": "2026-09-14 22:00:00", "pM10": 96.0}], 1)

    async def fake_city_weather(*, city_name, start_time, end_time):
        assert city_name == "盐城市"
        assert start_time == "2026-09-13 21:14:44"
        return {"status": "success", "data": [{"timePoint": "2026-09-14T22:00:00", "windSpeed": 1.6}]}

    async def fake_empty_same_city_band(station, start_time, end_time, pollutant, *, station_data_tool=None):
        return {"status": "empty", "scope": "same_district", "station_count": 0,
                "band": [], "message": "同区无可比较站点"}

    saved_packages = []

    def fake_save_evidence(package):
        saved_packages.append(package)
        return {"working_order_code": package["working_order_code"], "status": "待审核",
                "index_path": "/nonexistent/jiangsu_work_order_reviews/index.json",
                "source_files": {}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.download_file", fake_download_file)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._fault_attachment_output_dir", fake_output_dir)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.JiangsuStationDataTool.fetch_raw_records", fake_raw_records)
    monkeypatch.setattr("app.fetchers.weather.jiangsu_review_weather.fetch_city_weather", fake_city_weather)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.fetch_same_city_band",
                        fake_empty_same_city_band)
    monkeypatch.setattr("app.services.jiangsu_work_order_review.save_evidence", fake_save_evidence)

    result = await JiangsuReviewEvidenceTool().execute(
        working_order_code="FA260914178938611578927",
        mark_areas=[{"name": "剔除候选", "start": "2026-09-14 20:00:00", "end": "2026-09-14 23:00:00"}],
        modules=[],
    )

    assert result["success"] is True
    assert result["visuals"] == []
    # 标注区间随证据包持久化，由工单审核工作台图表渲染
    assert saved_packages[0]["mark_areas"] == [
        {"name": "剔除候选", "start": "2026-09-14 20:00:00", "end": "2026-09-14 23:00:00"}]
    index = result["data"]["evidence_index"]
    assert index["station_hour"]["projection"]["hourly"] == [{"time": "2026-09-14 22:00:00", "value": 96.0}]
    assert index["work_order"]["status"] == "success"
    assert index["work_order"]["projection"]["attachment_count"] == 1
    assert result["data"]["ui_command"]["working_order_code"] == "FA260914178938611578927"
    # 源平台详单进入证据包：清单条目 + wo 主表 + 处置过程 + 附件（含落盘路径）
    work_order_source = saved_packages[0]["sources"]["work_order"]["data"]
    assert work_order_source["order"]["orderTitle"] == "PM10 分析仪数据偏高，疑似污染过程"
    assert work_order_source["wo"]["workingOrderCode"] == "FA260914178938611578927"
    assert work_order_source["details"][0]["processContent"] == "现场检查采样已恢复"
    attachment = work_order_source["attachments"][0]
    assert attachment["download_status"] == "success"
    assert attachment["content_type"] == "image/jpeg"
    assert Path(attachment["local_path"]).is_file()
    # 附件同时发布为会话资源
    assert any(resource["role"] == "attachment" for resource in result["resources"])
    assert result["metadata"]["station_source"] == "work_order"
    assert result["metadata"]["pollutant_source"] == "inferred"
    assert result["metadata"]["window_source"] == "work_order"


def test_review_evidence_same_city_band_statistics():
    from app.tools.jiangsu.review_evidence import pollutant_points, same_city_band

    records = [
        {"timePoint": "2026-09-14 10:00:00", "stationCode": "T", "pM10": 82.0},
        {"timePoint": "2026-09-14 10:00:00", "stationCode": "A", "pM10": 60.0},
        {"timePoint": "2026-09-14 10:00:00", "stationCode": "B", "pM10": 70.0},
        {"timePoint": "2026-09-14 10:00:00", "stationCode": "C", "pM10": 90.0},
        {"timePoint": "2026-09-14 11:00:00", "stationCode": "T", "pM10": -99},
    ]

    band = same_city_band(records, target_station_code="T", pollutant="PM10")

    assert band == [{"time": "2026-09-14 10:00:00", "target": 82.0, "min": 60.0, "median": 70.0, "max": 90.0}]
    assert pollutant_points([
        {"timePoint": "2026-09-14 10:00:00", "pM10": 82.0},
        {"timePoint": "2026-09-14 11:00:00", "pM10": -99},
    ], "PM10") == [{"time": "2026-09-14 10:00:00", "value": 82.0}]


@pytest.mark.asyncio
async def test_review_evidence_requires_single_station():
    result = await JiangsuReviewEvidenceTool().execute(
        station_names=["站点甲", "站点乙"],
        start_time="2026-09-14 00:00:00", end_time="2026-09-15 00:00:00",
    )

    assert result["success"] is False
    assert "仅支持单个站点" in result["summary"]


@pytest.mark.asyncio
async def test_review_evidence_modules_gather_alarm_env_qc_in_parallel(monkeypatch):
    seen_paths = []

    async def fake_get(self, path, params):
        seen_paths.append(path)
        if path.endswith("GetAllEnabledBSDStationAsync"):
            return {"success": True, "result": [
                {"positionName": "阜宁滨湖", "cityName": "盐城市", "districtName": "阜宁县",
                 "stationCode": "7099A", "uniqueCode": "320100397"},
            ]}
        if path.endswith("GetAlarmLogsAsync"):
            # 含一条动环类告警（AlarmType=1150）触发动环抓取门控
            return {"success": True, "result": {"alarmLogs": [
                {"id": index, "AlarmType": 1150 if index == 0 else 999} for index in range(60)],
                "alarmStatistics": [{"x": 1}], "alarmState": {"a": 1}}}
        if path.endswith("GetStationEnvPowerData"):
            return {"success": True, "result": {
                "tableData": [{"timePoint": f"h{index}", "StationTemp": 26 if index else 88}
                              for index in range(60)],
                "chartData": [{"timePoint": "t", "StationTemp": 26, "SmokeState": 0}]}}
        if path.endswith("GetNewQCHisResultListAsync"):
            return {"success": True, "result": [
                {"rId": "task-1", "rStart": "2026-09-14 10:00:00", "poll": "PM10", "qcType": "零气检查"},
            ]}
        if path.endswith("GetNewQCHisTaskStatusResultAsync"):
            return {"success": True, "result": {
                "rStart": "2026-09-14 10:00:00", "rId": "task-1",
                "stationCode": "7099A", "poll": "PM10", "qcType": "零气检查",
                "jsonStr": "{}"}}
        if path.endswith("GetNewQCHisRunLogResultListAsync"):
            return {"success": True, "result": []}
        if path.endswith("GetNewQCAirDataResultListAsync"):
            return {"success": True, "result": [
                {"dataValue": 1.2, "timePoint": "2026-09-14 10:00:00", "unit": "μg/m³", "isQCing": True},
            ]}
        raise AssertionError(f"unexpected path {path}")

    async def fake_raw_records(self, **kwargs):
        return ([{"timePoint": "2026-09-14 10:00:00", "pM10": 82.0}], 1)

    async def fake_city_weather(*, city_name, start_time, end_time):
        return {"status": "success", "data": []}

    async def fake_same_city_band(station, start_time, end_time, pollutant, *, station_data_tool=None):
        return {"status": "empty", "station_count": 0, "band": []}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.JiangsuStationDataTool.fetch_raw_records", fake_raw_records)
    monkeypatch.setattr("app.fetchers.weather.jiangsu_review_weather.fetch_city_weather", fake_city_weather)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.fetch_same_city_band", fake_same_city_band)

    result = await JiangsuReviewEvidenceTool().execute(
        station_codes=["7099A"], pollutant="PM10",
        start_time="2026-09-14 00:00:00", end_time="2026-09-15 00:00:00",
    )

    assert result["success"] is True
    assert any(path.endswith("GetAlarmLogsAsync") for path in seen_paths)
    assert any(path.endswith("GetStationEnvPowerData") for path in seen_paths)
    assert any(path.endswith("GetNewQCHisResultListAsync") for path in seen_paths)
    # 质控任务带动合格结果与质控曲线
    assert any(path.endswith("GetNewQCHisTaskStatusResultAsync") for path in seen_paths)
    assert any(path.endswith("GetNewQCAirDataResultListAsync") for path in seen_paths)

    # 模块明细只进证据包分文件；tool_result 中是投影索引
    index = result["data"]["evidence_index"]
    alarms = index["alarms"]
    assert alarms["status"] == "success"
    assert alarms["record_count"] == 60
    assert len(alarms["projection"]["recent"]) == 5

    # 动环只保留异常行（60 行中仅 1 行 StationTemp=88 超范围）
    env = index["env_power"]
    assert env["status"] == "success"
    assert env["record_count"] == 1

    # 质控只抓目标污染物，并带合格结果/曲线
    qc = index["qc"]
    assert qc["record_count"] == 1
    assert qc["projection"]["tasks"][0]["rId"] == "task-1"
    assert qc["projection"]["tasks"][0]["curve_points"] == 1

    assert "补充取证" in result["summary"]
    module_briefs = result["metadata"]["modules"]
    assert {"module": "qc", "status": "success", "record_count": 1, "truncated": False} in module_briefs


@pytest.mark.asyncio
async def test_review_evidence_module_failure_degrades_without_breaking_chart(monkeypatch):
    async def fake_get(self, path, params):
        if path.endswith("GetAllEnabledBSDStationAsync"):
            return {"success": True, "result": [
                {"positionName": "阜宁滨湖", "cityName": "盐城市", "districtName": "阜宁县",
                 "stationCode": "7099A", "uniqueCode": "320100397"},
            ]}
        if path.endswith("GetAlarmLogsAsync"):
            raise ValueError("站房告警接口 result 无效")
        if path.endswith("GetNewQCHisResultListAsync"):
            return {"success": True, "result": []}
        raise AssertionError(f"unexpected path {path}")

    async def fake_raw_records(self, **kwargs):
        return ([{"timePoint": "2026-09-14 10:00:00", "pM10": 82.0}], 1)

    async def fake_city_weather(*, city_name, start_time, end_time):
        return {"status": "success", "data": []}

    async def fake_same_city_band(station, start_time, end_time, pollutant, *, station_data_tool=None):
        return {"status": "empty", "station_count": 0, "band": []}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.JiangsuStationDataTool.fetch_raw_records", fake_raw_records)
    monkeypatch.setattr("app.fetchers.weather.jiangsu_review_weather.fetch_city_weather", fake_city_weather)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.fetch_same_city_band", fake_same_city_band)

    result = await JiangsuReviewEvidenceTool().execute(
        station_codes=["7099A"], pollutant="PM10",
        start_time="2026-09-14 00:00:00", end_time="2026-09-15 00:00:00",
        modules=["alarms", "qc"],
    )

    assert result["success"] is True
    assert result["visuals"] == []
    index = result["data"]["evidence_index"]
    assert index["alarms"]["status"] == "failed"
    assert index["alarms"]["record_count"] == 0
    assert index["qc"]["status"] == "success"
    assert "告警不可用" in result["summary"]


@pytest.mark.asyncio
async def test_review_evidence_qc_detail_timeout_degrades_to_summary(monkeypatch):
    """质控详情超时应降级为任务概要，不拖挂整次取证。"""
    import app.tools.jiangsu.fault_diagnosis as module

    async def fake_get(self, path, params):
        if path.endswith("GetAllEnabledBSDStationAsync"):
            return {"success": True, "result": [
                {"positionName": "阜宁滨湖", "cityName": "盐城市", "districtName": "阜宁县",
                 "stationCode": "7099A", "uniqueCode": "320100397"}]}
        if path.endswith("GetNewQCHisResultListAsync"):
            return {"success": True, "result": [
                {"rId": "task-1", "rStart": "2026-09-14 10:00:00", "poll": "PM10", "qcType": "零气检查"}]}
        raise AssertionError(f"unexpected path {path}")

    async def fake_raw_records(self, **kwargs):
        return ([{"timePoint": "2026-09-14 10:00:00", "pM10": 82.0}], 1)

    async def fake_city_weather(*, city_name, start_time, end_time):
        return {"status": "success", "data": []}

    async def fake_same_city_band(station, start_time, end_time, pollutant, *, station_data_tool=None):
        return {"status": "empty", "station_count": 0, "band": []}

    async def slow_detail(self, task, pollutant_code):
        await asyncio.sleep(5)
        return {}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.JiangsuStationDataTool.fetch_raw_records", fake_raw_records)
    monkeypatch.setattr("app.fetchers.weather.jiangsu_review_weather.fetch_city_weather", fake_city_weather)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.fetch_same_city_band", fake_same_city_band)
    monkeypatch.setattr(module.JiangsuReviewEvidenceTool, "_fetch_qc_task_detail", slow_detail)
    monkeypatch.setattr(module.JiangsuReviewEvidenceTool, "_MODULE_QC_DETAIL_TIMEOUT", 0.05)

    result = await JiangsuReviewEvidenceTool().execute(
        station_codes=["7099A"], pollutant="PM10",
        start_time="2026-09-14 00:00:00", end_time="2026-09-15 00:00:00",
        modules=["qc"],
    )

    assert result["success"] is True
    qc = result["data"]["evidence_index"]["qc"]
    assert qc["status"] == "success"
    assert qc["record_count"] == 1
    assert qc["projection"]["tasks"][0]["detail_status"] == "timeout"


def test_review_evidence_rejects_unknown_module():
    import asyncio

    result = asyncio.run(JiangsuReviewEvidenceTool().execute(
        station_codes=["7099A"], pollutant="PM10",
        start_time="2026-09-14 00:00:00", end_time="2026-09-15 00:00:00",
        modules=["weather"],
    ))

    assert result["success"] is False
    assert "modules 含无效值" in result["summary"]


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
async def test_qc_task_status_builds_detail_visual_with_logs_and_curve(monkeypatch):
    seen = []
    status_detail = {
        "StrStartTime": "2026-09-16 00:10:09",
        "StrEndTime": "2026-09-16 00:23:52",
        "PollutantCode": "O3",
        "HistoryDetail": {
            "QCResult": "合格", "TaskStatus": 0, "RelevantValue": 1.58, "Inaccuracy": 0.0158,
        },
        "Steps": [{
            "StepName": "准备", "Status": 2,
            "Actions": [{"ActionName": "检查", "ActionParameter": "正常", "Status": 2}],
        }],
        "ResultValues": [{"DataName": "零点响应", "DataValue": "1.58"}],
        "DataValues": [{"DataName": "漂移", "DataValue": "0.01"}],
    }

    async def fake_get(self, path, params):
        seen.append((path, params))
        if path.endswith("GetNewQCHisTaskStatusResultAsync"):
            return {"success": True, "result": {
                "rId": "task-1", "rStart": "2026-09-16 00:10:09",
                "stationCode": "7099A", "uniqueCode": "320100397",
                "stationName": "江苏省环境监测中心超站",
                "poll": "O3", "qcType": "零点检查",
                "jsonStr": json.dumps(status_detail, ensure_ascii=False),
            }}
        if path.endswith("GetNewQCHisRunLogResultListAsync"):
            return {"success": True, "result": [
                {"recordTime": "2026-09-16 00:11:00", "target": "质控", "message": "开始零点检查"},
            ]}
        assert path.endswith("GetNewQCAirDataResultListAsync")
        return {"success": True, "result": [
            {"timePoint": "2026-09-16 00:10:00", "dataValue": 1.2, "unit": "ppb", "isQCing": True, "flag": 0},
            {"timePoint": "2026-09-16 00:20:00", "dataValue": 1.6, "unit": "ppb", "isQCing": True, "flag": 0},
        ]}

    captured = {}

    def fake_resources_for_visuals(visuals, *, tool_name):
        captured["visuals"] = list(visuals)
        captured["tool_name"] = tool_name
        return [{
            "kind": "visual", "group_key": "visual:qc_task_detail_task-1",
            "resource_key": "chart-spec", "relation": "primary", "role": "output",
            "label": "质控详情", "locator": {"visual_id": "qc_task_detail_task-1"},
            "format": "json", "media_type": "application/json", "renderer": "chart",
            "capabilities": ["preview"], "tool_name": tool_name,
        }]

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis.resources_for_visuals", fake_resources_for_visuals)
    result = await JiangsuQcTaskStatusTool().execute(r_start="2026-09-16 00:10:09", r_id="task-1")

    assert result["success"] is True
    visual = result["visuals"][0]
    assert visual["type"] == "qc_task_detail"
    assert visual["id"] == "qc_task_detail_task-1"
    detail = visual["data"]["qc_task_detail"]
    assert detail["task"]["qc_result"] == "合格"
    assert detail["task"]["task_status_label"] == "结束"
    assert detail["steps"][0]["name"] == "准备"
    assert detail["result_values"][0]["name"] == "零点响应"
    assert detail["run_logs"][0]["message"] == "开始零点检查"
    assert len(detail["curve"]) == 2
    assert result["metadata"]["curve_point_count"] == 2
    assert result["resources"][0]["renderer"] == "chart"
    assert captured["tool_name"] == "jiangsu_fetch_qc_task_status"
    assert seen[1][1] == [("rStart", "2026-09-16 00:10:09"), ("rId", "task-1")]
    curve_params = seen[2][1]
    assert ("stationCode", "7099A") in curve_params
    assert ("poll", "O3") in curve_params
    assert ("qcType", "零点检查") in curve_params
    assert curve_params[-2][1] == "2026-09-16 00:08:09"
    assert curve_params[-1][1] == "2026-09-16 00:25:52"



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

    async def fake_air_snapshot(station_code):
        return {}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.post", fake_post)
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._fetch_station_air_snapshot", fake_air_snapshot)
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


def _visual_values(data):
    from app.tools.jiangsu.fault_diagnosis import _stationhouse_visual

    station = {"station_name": "高淳淳溪", "station_code": "1001A", "unique_code": "U1",
               "city_name": "南京市", "district_name": "高淳区"}
    visual = _stationhouse_visual(station, data, [], {})
    return visual["data"]["stationhouse"]["values"]


def test_stationhouse_visual_prefers_qc_value_over_monitoring_snapshot():
    values = _visual_values({
        "DevDtls": [{"DevPollCode": "SO2", "HourDataDtsls": [{"Value": 5.0}]}],
        "MonitoringSnapshot": {"SO2": {"Value": 6.0, "DataAlarm": 0},
                               "NO": {"Value": 3.0, "DataAlarm": 0}},
    })

    assert values["SO2"]["value"] == "5"
    assert values["NO"]["value"] == "3"


def test_stationhouse_visual_fills_missing_instruments_from_monitoring_snapshot():
    values = _visual_values({
        "DevDtls": [{"DevPollCode": "CO", "DevAlarm": 0}],
        "MonitoringSnapshot": {"CO": {"Value": 1.2, "DataAlarm": 0},
                               "PM2.5": {"Value": 10.0, "DataAlarm": 0},
                               "NO": {"Value": "-99", "DataAlarm": 0}},
    })

    assert values["CO"]["value"] == "1.2"
    assert values["PM2.5"]["value"] == "10"
    assert "NO" not in values


@pytest.mark.asyncio
async def test_station_environment_history_rejects_city_scope():
    result = await JiangsuStationEnvironmentHistoryTool().execute(
        city_name="南京市", start_time="2026-08-01 00:00:00", end_time="2026-08-01 06:00:00"
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "不支持城市/区县批量" in result["summary"]
    assert "jiangsu_fetch_station_alarm_logs" in result["summary"]


@pytest.mark.asyncio
async def test_station_environment_history_requires_codes_for_multiple_stations(monkeypatch):
    async def fake_get(self, path, params):
        if path.endswith("GetAllEnabledBSDStationAsync"):
            return {"result": [
                {"stationCode": "1001A", "uniqueCode": "U1", "positionName": "站1"},
                {"stationCode": "1002A", "uniqueCode": "U2", "positionName": "站2"},
            ]}
        raise AssertionError("多站点未指定 pollutant_codes 时不应请求动环接口")

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuStationEnvironmentHistoryTool().execute(
        station_codes=["1001A", "1002A"], start_time="2026-08-01 00:00:00", end_time="2026-08-01 06:00:00"
    )

    assert result["success"] is False
    assert "pollutant_codes" in result["summary"]


@pytest.mark.asyncio
async def test_station_environment_history_queries_only_requested_codes(monkeypatch):
    captured = {}

    async def fake_get(self, path, params):
        if path.endswith("GetAllEnabledBSDStationAsync"):
            return {"result": [{"stationCode": "1001A", "uniqueCode": "U1", "positionName": "站1"}]}
        assert path.endswith("GetStationEnvPowerData")
        captured["params"] = params
        return {"result": {"tableData": [{"time": "2026-08-01 01:00:00", "StationTemp": 99}], "chartData": []}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi.get", fake_get)
    result = await JiangsuStationEnvironmentHistoryTool().execute(
        station_codes=["1001A"], start_time="2026-08-01 00:00:00", end_time="2026-08-01 06:00:00",
        pollutant_codes=["StationTemp", "VA"],
    )

    assert result["success"] is True
    params = dict(captured["params"])
    assert params["Uniquecode"] == "U1"
    assert params["PollutantCode"] == "StationTemp,VA"
    assert result["metadata"]["pollutant_codes"] == ["StationTemp", "VA"]
