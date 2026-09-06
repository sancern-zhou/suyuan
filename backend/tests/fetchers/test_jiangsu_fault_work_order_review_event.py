import json
from datetime import datetime
from pathlib import Path

import pytest

from app.fetchers import jiangsu_fault_work_order_review_event as module
from app.fetchers.jiangsu_fault_work_order_review_event import (
    EVENT_TYPE,
    JiangsuFaultWorkOrderReviewEventFetcher,
    _evidence_window,
)

NOW = datetime.fromisoformat("2026-09-02T08:30:00+08:00")


class FakeWorkOrderTool:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "data": [
                {
                    "workingOrderCode": "FA260902001",
                    "stationCodeStr": "3001A",
                    "stationName": "江宁九龙湖",
                    "uniqueCode": "UNIQUE-3001",
                    "city": "南京市",
                    "orderTitle": "NO 跨度质控不合格",
                    "currentPointName": "省中心审核",
                    "workFlowStatus": "ToAssign",
                    "orderStatus": "Doing",
                    "createTime": "2026-09-01 23:50:00",
                    "updateTime": "2026-09-02 07:50:00",
                },
                {
                    "workingOrderCode": "FA260902002",
                    "stationCodeStr": "3002A",
                    "stationName": "江宁大学城",
                    "orderTitle": "门禁异常",
                    "currentPointName": "省中心审核",
                },
            ],
        }


class FakeEnvWorkOrderTool:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "data": [{
                "workingOrderCode": "FA260903ENV",
                "stationCodeStr": "3003A",
                "stationName": "江阴虹桥邮政",
                "uniqueCode": "UNIQUE-3003",
                "city": "无锡市",
                "deviceId": "1762",
                "deviceTypeName": "PM10 分析仪",
                "orderTitle": "PM10 偏低，平台抬放异常",
                "currentPointName": "省中心审核",
                "workFlowStatus": "ToAssign",
                "orderStatus": "Doing",
                "createTime": "2026-09-03 08:40:00",
                "updateTime": "2026-09-03 10:30:00",
            }],
        }


class FakeTransmissionWorkOrderTool:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "data": [{
                "workingOrderCode": "FA260903TRAN",
                "stationCodeStr": "3008A",
                "stationName": "盱眙泵站路",
                "uniqueCode": "UNIQUE-3008",
                "city": "淮安市",
                "deviceId": "2395",
                "deviceTypeName": "SO2 分析仪",
                "orderTitle": "SO2 无数据上传，平台未更新",
                "currentPointName": "省中心审核",
                "workFlowStatus": "ToAssign",
                "orderStatus": "Doing",
                "createTime": "2026-09-03 08:40:00",
                "updateTime": "2026-09-03 10:30:00",
            }],
        }


class FakeDetailTool:
    async def execute(self, **kwargs):
        code = kwargs["working_order_code"]
        if code == "FA260902002":
            return {
                "success": True,
                "data": [{
                    "wo": {
                        "workingOrderCode": code,
                        "stationCodeStr": "3002A",
                        "stationName": "江宁大学城",
                        "orderContent": "门禁异常，现场检查门禁控制器。",
                    },
                    "details": [{
                        "processStep": "FaultProcess",
                        "processStepName": "故障处理",
                        "processTimeStr": "2026-09-02 01:00:00",
                    }],
                }],
                "metadata": {"record_count": 1},
                "summary": "详单查询完成",
            }
        if code == "FA260903ENV":
            return {
                "success": True,
                "data": [{
                    "wo": {
                        "workingOrderCode": code,
                        "stationCodeStr": "3003A",
                        "stationName": "江阴虹桥邮政",
                        "cityName": "无锡市",
                        "uniqueCode": "UNIQUE-3003",
                        "deviceId": "1762",
                        "deviceTypeName": "PM10 分析仪",
                        "orderContent": "PM10 偏低，现场核查平台抬放动作异常，重新调整后重启进入稳定期。",
                    },
                    "details": [{
                        "processStep": "CreateOrder",
                        "processStepName": "创建工单",
                        "processTimeStr": "2026-09-03 08:40:00",
                    }, {
                        "processStep": "FaultProcess",
                        "processStepName": "故障处理",
                        "processTimeStr": "2026-09-03 10:20:00",
                    }],
                    "attachments": [{"fileName": "现场照片.jpg"}],
                }],
                "metadata": {"record_count": 1},
                "summary": "详单查询完成",
            }
        if code == "FA260903TRAN":
            return {
                "success": True,
                "data": [{
                    "wo": {
                        "workingOrderCode": code,
                        "stationCodeStr": "3008A",
                        "stationName": "盱眙泵站路",
                        "cityName": "淮安市",
                        "uniqueCode": "UNIQUE-3008",
                        "deviceId": "2395",
                        "deviceTypeName": "SO2 分析仪",
                        "orderContent": "SO2 无数据上传，平台未更新，现场检查网络通信后恢复。",
                    },
                    "details": [{
                        "processStep": "CreateOrder",
                        "processStepName": "创建工单",
                        "processTimeStr": "2026-09-03 08:40:00",
                    }, {
                        "processStep": "FaultProcess",
                        "processStepName": "故障处理",
                        "processTimeStr": "2026-09-03 10:20:00",
                    }],
                    "attachments": [{"fileName": "通信检查截图.jpg"}],
                }],
                "metadata": {"record_count": 1},
                "summary": "详单查询完成",
            }
        return {
            "success": True,
            "data": [{
                "wo": {
                    "workingOrderCode": code,
                    "stationCodeStr": "3001A",
                    "stationName": "江宁九龙湖",
                    "orderContent": "NO 跨度质控不合格，现场校准后复测。",
                },
                "details": [{
                    "processStep": "CreateOrder",
                    "processStepName": "创建工单",
                    "processTimeStr": "2026-09-02 00:10:00",
                }, {
                    "processStep": "FaultProcess",
                    "processStepName": "故障处理",
                    "processTimeStr": "2026-09-02 01:00:00",
                    "processEdtTime": "2026-09-02 01:05:00",
                }, {
                    "processStep": "FaultReview",
                    "processStepName": "运维单位复核",
                    "processTimeStr": "2026-09-02 07:00:00",
                }],
            }],
            "metadata": {"record_count": 1},
            "summary": "详单查询完成",
        }


class FakeStationDataTool:
    def __init__(self):
        self.calls = []

    async def fetch_raw_records(self, **kwargs):
        self.calls.append(kwargs)
        query_time = kwargs.get("start_time")
        data_type = kwargs.get("data_type")
        if kwargs.get("station_codes"):
            code = kwargs["station_codes"][0]
            return [{
                "code": code,
                "timePoint": query_time,
                "nO2": 12 if data_type == 0 else 14,
                "no": 5 if data_type == 0 else 6,
                "PM10": 38 if data_type == 0 else 36,
            }], {"codes": kwargs["station_codes"]}
        city_name = kwargs.get("city_names", ["city"])[0]
        return [
            {
                "code": "3003A",
                "name": "江阴虹桥邮政",
                "timePoint": query_time,
                "nO2": 12 if data_type == 0 else 13,
                "no": 5 if data_type == 0 else 6,
                "PM10": 38 if data_type == 0 else 37,
            },
            {
                "code": "3004A",
                "name": f"{city_name}对比站",
                "timePoint": query_time,
                "nO2": 18 if data_type == 0 else 19,
                "no": 7 if data_type == 0 else 8,
                "PM10": 44 if data_type == 0 else 43,
            },
        ], {"codes": ["3003A", "3004A"]}


class FakeSimpleTool:
    def __init__(self, data=None):
        self.data = data if data is not None else []

    async def execute(self, **kwargs):
        return {"success": True, "status": "success", "data": self.data, "summary": "ok"}


class FakeCurveTool:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "status": "success",
            "data": [
                {"timePoint": kwargs["start_time"], "value": 90},
                {"timePoint": kwargs["end_time"], "value": 86},
            ],
            "summary": "质控监测曲线查询完成",
        }


@pytest.mark.asyncio
async def test_fetcher_publishes_qc_review_event_and_evidence_pack(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(module, "has_active_review", lambda code: False)
    monkeypatch.setattr(
        JiangsuFaultWorkOrderReviewEventFetcher,
        "_ensure_feedback_case",
        staticmethod(lambda event: None),
    )

    async def publish(event):
        events.append(event)

    work_order_tool = FakeWorkOrderTool()
    status_payload = {
        "Steps": [
            {"stepName": "读取参数", "recordTime": "2026-09-02 00:45:02", "message": "参数检查完成"},
            {"stepName": "开始质控任务", "recordTime": "2026-09-02 00:46:00", "message": "开始零点检查"},
            {"stepName": "质控进行中检查", "recordTime": "2026-09-02 00:50:00", "message": "进行中检查通过"},
            {"stepName": "稳定后读数", "recordTime": "2026-09-02 00:55:00", "message": "稳定后读取"},
            {"stepName": "结束质控任务", "recordTime": "2026-09-02 01:05:30", "message": "结束零点检查"},
        ],
        "HistoryDetail": {
            "TargetValue": 0.0,
            "RelevantValue": -0.75,
            "Inaccuracy": -0.002,
            "QCResult": "合格",
        },
        "DataValues": [1.2, 1.1, 1.0],
        "ResultValues": [0.9, 1.0],
    }
    curve_tool = FakeCurveTool()
    fetcher = JiangsuFaultWorkOrderReviewEventFetcher(
        registry_root=tmp_path,
        event_publisher=publish,
        clock=lambda: NOW,
        work_order_tool=work_order_tool,
        detail_tool=FakeDetailTool(),
        station_data_tool=FakeStationDataTool(),
        station_alarm_tool=FakeSimpleTool(),
        environment_tool=FakeSimpleTool({"tableData": []}),
        qc_history_tool=FakeSimpleTool([{
            "rId": "RID-1",
            "rStart": "2026-09-02 00:00:00",
            "endTime": "2026-09-02 01:05:30",
            "qcType": "span",
            "poll": "NO",
            "qcResult": "合格",
            "HistoryDetail": {
                "TargetValue": 0.0,
                "RelevantValue": -0.75,
                "Inaccuracy": -0.002,
                "QCResult": "合格",
            },
            "DataValues": [1.2, 1.1, 1.0],
            "ResultValues": [0.9, 1.0],
        }]),
        qc_status_tool=FakeSimpleTool({"jsonStr": json.dumps(status_payload, ensure_ascii=False)}),
        qc_run_log_tool=FakeSimpleTool([{"step": "span", "result": "failed"}]),
        qc_curve_tool=curve_tool,
    )

    result = await fetcher.fetch_and_store()

    assert result["queried_orders"] == 2
    assert "start_time" not in work_order_tool.calls[0]
    assert work_order_tool.calls[0]["current_points"] == ["省中心审核"]
    assert result["sop01_candidates"] == 1
    assert result["published_events"] == 1
    assert events[0].event_type == EVENT_TYPE
    assert events[0].attributes["work_order_code"] == "FA260902001"
    evidence_path = Path(events[0].payload["evidence_pack_path"])
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["sop_id"] == "SOP-01"
    assert evidence["work_order_code"] == "FA260902001"
    assert evidence["evidence_time_window"]["start"] == "2026-08-31 00:00:00"
    assert evidence["evidence_time_window"]["end"] == "2026-09-02 23:59:59"
    assert evidence["evidence_time_window"]["fault_start_anchor"]["time"] == "2026-09-01 23:50:00"
    assert evidence["evidence_time_window"]["fault_start_anchor"]["boundary_time"] == "2026-08-31 00:00:00"
    assert evidence["evidence_time_window"]["processing_end_anchor"]["step_name"] == "故障处理"
    assert evidence["evidence_time_window"]["processing_end_anchor"]["boundary_time"] == "2026-09-02 23:59:59"
    assert evidence["evidence_time_window"]["boundary_warning"]
    assert evidence["monitoring"]["station_hour_raw"]["metadata"]["chunk_count"] == 1
    assert fetcher.station_data_tool.calls[0]["start_time"] == "2026-08-31 00:00:00"
    assert fetcher.station_data_tool.calls[0]["end_time"] == "2026-09-02 23:59:59"
    assert evidence["quality_control"]["task_statuses"]
    assert evidence["quality_control"]["task_details"][0]["curve_window"]["start"] == "2026-09-02 00:00:00"
    assert evidence["quality_control"]["task_details"][0]["curve_window"]["end"] == "2026-09-02 01:05:30"
    assert evidence["quality_control"]["task_details"][0]["status_detail"]["step_count"] == 5
    assert evidence["quality_control"]["task_details"][0]["status_detail"]["steps"][0]["phase"] == "参数检查"
    assert evidence["quality_control"]["task_details"][0]["status_detail"]["history_detail"]["QCResult"] == "合格"
    assert curve_tool.calls[0]["start_time"] == "2026-09-02 00:00:00"
    assert curve_tool.calls[0]["end_time"] == "2026-09-02 01:05:30"


@pytest.mark.asyncio
async def test_fetcher_routes_sop02_data_anomaly_event_and_slims_same_city_series(tmp_path, monkeypatch):
    events = []
    weather_calls = []

    async def weather(**kwargs):
        weather_calls.append(kwargs)
        return {"status": "success", "data": [{"timePoint": "2026-09-02T00:00:00", "temperature": 25}]}

    monkeypatch.setattr(module, "fetch_city_weather", weather)
    station_data_tool = FakeStationDataTool()
    monkeypatch.setattr(module, "has_active_review", lambda code: False)
    monkeypatch.setattr(
        JiangsuFaultWorkOrderReviewEventFetcher,
        "_ensure_feedback_case",
        staticmethod(lambda event: None),
    )

    async def publish(event):
        events.append(event)

    fetcher = JiangsuFaultWorkOrderReviewEventFetcher(
        registry_root=tmp_path,
        event_publisher=publish,
        clock=lambda: NOW,
        work_order_tool=FakeEnvWorkOrderTool(),
        detail_tool=FakeDetailTool(),
        station_data_tool=station_data_tool,
        station_alarm_tool=FakeSimpleTool([{"alarm": "platform lift"}]),
        environment_tool=FakeSimpleTool({"tableData": [{"StationTemp": 25, "time": "2026-09-03 09:00:00"}]}),
        qc_history_tool=FakeSimpleTool([]),
        qc_status_tool=FakeSimpleTool(),
        qc_run_log_tool=FakeSimpleTool(),
        qc_curve_tool=FakeSimpleTool(),
    )

    result = await fetcher.fetch_and_store()

    assert result["queried_orders"] == 1
    assert result["sop01_candidates"] == 0
    assert result["sop02_candidates"] == 1
    assert result["published_events"] == 1
    assert events[0].event_type == EVENT_TYPE
    assert events[0].attributes["sop_id"] == "SOP-02"
    assert "env_category" not in events[0].attributes
    assert events[0].payload["review_submit_tool"] == "jiangsu_submit_fault_work_order_review"
    evidence_path = Path(events[0].payload["evidence_pack_path"])
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["sop_id"] == "SOP-02"
    assert evidence["review_type"] == "fault_work_order_env_sop02"
    assert weather_calls == [{"city_name": "无锡市", "start_time": evidence["evidence_time_window"]["start"], "end_time": evidence["evidence_time_window"]["end"]}]
    assert evidence["city_weather"]["data"][0]["temperature"] == 25
    assert evidence["input_profile"] == "agent_slim_v1"
    assert evidence["pollutants_detected_from_text"] == ["PM10"]
    assert "env_category" not in evidence["environmental_fault"]
    assert evidence["environmental_fault"]["event_type"] == "low"
    assert evidence["same_city_monitoring"]["comparison_scope"] == "same_city"
    assert evidence["same_city_monitoring"]["summary_mode"] == "deterministic_summary_with_raw_resource"
    assert evidence["same_city_monitoring"]["station_hour_raw"]["metadata"]["time_point_count"] == 48
    assert evidence["same_city_monitoring"]["station_hour_raw"]["record_count"] == 96
    assert "data" not in evidence["same_city_monitoring"]["station_hour_raw"]
    same_city_pm10 = evidence["same_city_monitoring"]["station_hour_raw"]["pollutant_summaries"][0]
    assert same_city_pm10["pollutant"] == "PM10"
    assert same_city_pm10["target_hour_count"] == 48
    assert same_city_pm10["classification_counts"]["target_below_same_city_min"] == 48
    assert same_city_pm10["timeline"][0]["target"]["value"] == 38
    assert same_city_pm10["timeline"][0]["same_city"]["median"] == 44
    raw_resource = evidence["same_city_monitoring"]["raw_resource"]
    assert raw_resource["name"] == "same_city_monitoring_raw"
    assert raw_resource["record_counts"]["station_hour_raw"] == 96
    assert evidence["raw_resources"][0]["path"] == raw_resource["path"]
    raw_same_city = json.loads(Path(raw_resource["path"]).read_text(encoding="utf-8"))
    assert raw_same_city["station_hour_raw"]["data"][0]["timePoint"] == "2026-09-02 00:00:00"
    assert raw_same_city["station_hour_raw"]["data"][-1]["timePoint"] == "2026-09-03 23:00:00"
    assert "auto_inspection" not in evidence
    assert any(gap["item"] == "流量/泵/制冷等专用历史参数" for gap in evidence["evidence_gaps"])
    five_minute_calls = [
        call for call in station_data_tool.calls
        if call["data_kind"] == "station_5minute" and call.get("station_codes") == ["3003A"]
    ]
    assert five_minute_calls
    assert all("pollutant_codes" not in call for call in five_minute_calls)
    same_city_calls = [call for call in station_data_tool.calls if call.get("city_names") == ["无锡市"]]
    assert same_city_calls
    assert len({call["start_time"] for call in same_city_calls}) == 48
    assert same_city_calls[0]["start_time"] == "2026-09-02 00:00:00"
    assert same_city_calls[-1]["start_time"] == "2026-09-03 23:00:00"
    assert all(call["data_kind"] == "station_hour" for call in same_city_calls)


@pytest.mark.asyncio
async def test_fetcher_routes_sop03_transmission_event_and_exposes_missing_evidence(tmp_path, monkeypatch):
    events = []
    station_data_tool = FakeStationDataTool()
    monkeypatch.setattr(module, "has_active_review", lambda code: False)
    monkeypatch.setattr(
        JiangsuFaultWorkOrderReviewEventFetcher,
        "_ensure_feedback_case",
        staticmethod(lambda event: None),
    )

    async def publish(event):
        events.append(event)

    fetcher = JiangsuFaultWorkOrderReviewEventFetcher(
        registry_root=tmp_path,
        event_publisher=publish,
        clock=lambda: NOW,
        work_order_tool=FakeTransmissionWorkOrderTool(),
        detail_tool=FakeDetailTool(),
        station_data_tool=station_data_tool,
        station_alarm_tool=FakeSimpleTool([{"alarm": "通信中断"}]),
        environment_tool=FakeSimpleTool({"tableData": []}),
        qc_history_tool=FakeSimpleTool([]),
        qc_status_tool=FakeSimpleTool(),
        qc_run_log_tool=FakeSimpleTool(),
        qc_curve_tool=FakeSimpleTool(),
    )

    result = await fetcher.fetch_and_store()

    assert result["queried_orders"] == 1
    assert result["sop03_candidates"] == 1
    assert result["published_events"] == 1
    assert events[0].attributes["sop_id"] == "SOP-03"
    assert "transmission_category" not in events[0].attributes
    assert "transmission_category" not in events[0].payload
    evidence_path = Path(events[0].payload["evidence_pack_path"])
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["sop_id"] == "SOP-03"
    assert evidence["review_type"] == "fault_work_order_transmission_sop03"
    assert "transmission_category" not in evidence["transmission_fault"]
    assert evidence["transmission_fault"]["event_type"] == "not_uploaded"
    assert evidence["transmission_evidence"]["platform_monitoring"]["station_hour_raw"]["record_count"] >= 1
    assert evidence["transmission_evidence"]["local_data"]["status"] == "unavailable"
    assert any(gap["item"] == "设备本地数据和缓存状态" for gap in evidence["evidence_gaps"])
    assert any(gap["item"] == "补传起止、成功/失败数量和回执" for gap in evidence["evidence_gaps"])
    assert evidence["same_city_monitoring"] is None
    same_city_calls = [call for call in station_data_tool.calls if call.get("city_names") == ["淮安市"]]
    assert same_city_calls == []


def test_fetcher_runs_once_each_morning_by_default():
    fetcher = JiangsuFaultWorkOrderReviewEventFetcher(
        work_order_tool=FakeWorkOrderTool(),
        detail_tool=FakeDetailTool(),
        station_data_tool=FakeStationDataTool(),
        station_alarm_tool=FakeSimpleTool(),
        environment_tool=FakeSimpleTool(),
        qc_history_tool=FakeSimpleTool(),
        qc_status_tool=FakeSimpleTool(),
        qc_run_log_tool=FakeSimpleTool(),
        qc_curve_tool=FakeSimpleTool(),
    )

    assert fetcher.schedule == "30 8 * * *"


def test_sop02_evidence_gaps_expose_failed_five_minute_when_hour_data_exists():
    gaps = module._sop02_evidence_gaps(
        route={"sop_id": "SOP-02"},
        station={"station_code": "3003A", "city_name": "无锡市"},
        pollutants=["PM10"],
        work_order_detail={"success": True, "record_count": 1, "data": [{}]},
        monitoring={
            "station_5minute_raw": {
                "success": False,
                "status": "failed",
                "summary": "江苏站点station_5minute分片查询全部失败：1 个分片失败。",
                "record_count": 0,
                "data": [],
            },
            "station_5minute_audited": {
                "success": False,
                "status": "failed",
                "summary": "江苏站点station_5minute分片查询全部失败：1 个分片失败。",
                "record_count": 0,
                "data": [],
            },
            "station_hour_raw": {"success": True, "record_count": 2, "data": [{}, {}]},
            "station_hour_audited": {"success": True, "record_count": 2, "data": [{}, {}]},
        },
        station_alarm={"success": True, "record_count": 1, "data": [{}]},
        environment={"success": True, "record_count": 1, "data": {"tableData": [{}]}},
        same_city_monitoring={
            "station_hour_raw": {"success": True, "record_count": 2, "data": [{}, {}]},
            "station_hour_audited": {"success": True, "record_count": 2, "data": [{}, {}]},
        },
    )

    assert any(gap["item"] == "本站 5 分钟原始数据" for gap in gaps)
    assert any(gap["item"] == "本站 5 分钟审核数据" for gap in gaps)
    assert not any(gap["item"] == "本站 5 分钟/小时数据" for gap in gaps)


@pytest.mark.asyncio
async def test_fetch_monitoring_does_not_filter_five_minute_pm25():
    station_data_tool = FakeStationDataTool()
    fetcher = JiangsuFaultWorkOrderReviewEventFetcher(
        station_data_tool=station_data_tool,
    )

    result = await fetcher._fetch_monitoring(
        station_code="3101A",
        start_time="2026-09-01 00:00:00",
        end_time="2026-09-01 01:00:00",
        pollutants=["PM2.5"],
    )

    assert result["station_5minute_raw"]["success"] is True
    five_minute_calls = [
        call for call in station_data_tool.calls
        if call["data_kind"] == "station_5minute"
    ]
    assert five_minute_calls
    assert all("pollutant_codes" not in call for call in five_minute_calls)


def test_evidence_window_ignores_workflow_template_times():
    order = {
        "createTime": "2026-09-03 08:46:42",
        "updateTime": "2026-09-03T13:37:21.507",
    }
    detail = {
        "wo": {"createTime": "2026-09-03 08:46:42"},
        "details": [
            {"processStep": "CreateOrder", "processStepName": "创建工单", "processTimeStr": "2026-09-03 08:46:42"},
            {"processStep": "FaultProcess", "processStepName": "故障处理", "processTimeStr": "2026-09-03 10:30:00"},
            {"processStep": "FaultReview", "processStepName": "运维单位复核", "processTimeStr": "2022-11-03T17:39:10.607"},
        ],
        "workFlowInfo": {
            "stepList": [
                {"taskName": "省中心审核", "createTime": "2022-11-03T17:39:10.607"},
            ],
        },
    }

    now = datetime.fromisoformat("2026-09-03T13:47:53+08:00")
    window = _evidence_window(order, detail, now)

    assert window["start"].year == 2026
    assert window["start"].strftime("%Y-%m-%d %H:%M:%S") == "2026-09-02 00:00:00"
    assert window["end"].strftime("%Y-%m-%d %H:%M:%S") == "2026-09-03 23:59:59"
    assert window["processing_end_anchor"]["step_name"] == "故障处理"
    assert window["query_window_truncated"] is False


def test_evidence_window_requires_fault_process_anchor():
    order = {"createTime": "2026-09-03 08:46:42"}
    detail = {
        "details": [
            {"processStep": "FaultReview", "processStepName": "运维单位复核", "processTimeStr": "2026-09-03 13:37:21"},
        ],
    }

    now = datetime.fromisoformat("2026-09-03T13:47:53+08:00")

    with pytest.raises(ValueError, match="未找到故障处理流转记录"):
        _evidence_window(order, detail, now)


def test_evidence_window_requires_create_time():
    order = {}
    detail = {
        "details": [
            {"processStep": "FaultProcess", "processStepName": "故障处理", "processTimeStr": "2026-09-03 13:37:21"},
        ],
    }

    now = datetime.fromisoformat("2026-09-03T13:47:53+08:00")

    with pytest.raises(ValueError, match="工单创建时间缺失"):
        _evidence_window(order, detail, now)
