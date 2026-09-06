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
    JiangsuStationAlarmLogsTool,
)


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
