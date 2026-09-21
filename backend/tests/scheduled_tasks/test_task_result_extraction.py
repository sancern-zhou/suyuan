from datetime import datetime

from app.scheduled_tasks.models import ExecutionStatus, StepExecution, TaskExecution
from app.scheduled_tasks.result_extraction import extract_task_result


def _execution(**overrides) -> TaskExecution:
    payload = dict(
        execution_id="exec-1",
        task_id="task-1",
        task_name="日报",
        status=ExecutionStatus.SUCCESS,
        started_at=datetime(2026, 9, 18, 8, 0, 0),
        completed_at=datetime(2026, 9, 18, 8, 5, 0),
        total_steps=1,
        completed_steps=1,
        steps=[
            StepExecution(
                step_id="task",
                status=ExecutionStatus.SUCCESS,
                agent_prompt="prompt",
                agent_response="结论：昨日 PM2.5 未超标。报告：/tmp/report.docx",
            )
        ],
    )
    payload.update(overrides)
    return TaskExecution(**payload)


class _Event:
    def __init__(self, attributes):
        self.event_id = "evt-1"
        self.event_type = "xuchang.station_deviation.alert_created"
        self.attributes = attributes
        self.payload = {}


def test_extraction_prefers_distilled_case():
    case = {
        "city": "许昌市",
        "station": "许昌ymc",
        "pollutant": "PM2.5",
        "conclusion": "站点连续3小时抬升，已通知",
        "distilled": {
            "cities": ["许昌市"],
            "stations": ["许昌ymc"],
            "pollutants": ["PM2.5"],
            "findings": ["峰值偏差 0.4", "持续 3 小时"],
        },
    }
    result = extract_task_result(
        execution=_execution(),
        event=None,
        agent_result={"summary": "fallback"},
        case=case,
    )
    assert result.city == "许昌市"
    assert result.station_name == "许昌ymc"
    assert result.pollutant == "PM2.5"
    assert result.conclusion == "站点连续3小时抬升，已通知"
    assert result.conclusion_source == "distilled"
    assert result.findings == ["峰值偏差 0.4", "持续 3 小时"]


def test_extraction_falls_back_to_event_attributes():
    result = extract_task_result(
        execution=_execution(),
        event=_Event({
            "city": "郑州市",
            "station_id": "station-42",
            "station_name": "测试站",
            "target_pollutant": "O3",
        }),
        agent_result=None,
        case=None,
    )
    assert result.city == "郑州市"
    assert result.station_id == "station-42"
    assert result.station_name == "测试站"
    assert result.pollutant == "O3"
    assert result.conclusion == "结论：昨日 PM2.5 未超标。报告：/tmp/report.docx"
    assert result.conclusion_source == "agent_response"
    assert result.document_paths == ["/tmp/report.docx"]


def test_extraction_collects_images_and_documents():
    agent_result = {
        "visuals": [
            {"local_path": "/data/charts/pm25.png", "title": "PM2.5"},
            {"path": "/data/charts/ignored.svg"},
            {"local_path": "/data/charts/pm25.png"},
        ],
        "tool_calls": [
            {
                "tool": "create_report_package",
                "result": {
                    "data": {
                        "report_id": "report-1",
                        "file_path": "/data/reports/report-1/report.qmd",
                        "resources": [
                            {"path": "/data/reports/report-1/report.docx", "format": "docx"},
                            {"path": "/data/reports/report-1/report.html", "format": "html"},
                        ],
                    }
                },
            },
            {"tool": "other", "media": ["/data/photo.jpg", "/data/notes.md"]},
        ],
    }
    result = extract_task_result(
        execution=_execution(),
        event=None,
        agent_result=agent_result,
        case=None,
    )
    assert result.image_paths == ["/data/charts/pm25.png", "/data/photo.jpg"]
    assert set(result.document_paths) == {
        "/data/reports/report-1/report.docx",
        "/tmp/report.docx",
    }
    assert {"kind": "report", "ref": "report-1", "title": "report-1"} in result.report_refs


def test_extraction_collects_evidence_package_paths():
    event = _Event({"station_id": "station-42"})
    event.payload = {
        "evidence_package_path": "/data/evidence/20260918/xuchang-station-episode-1.evidence.json"
    }
    agent_result = {
        "tool_calls": [
            {
                "tool": "analyze",
                "result": {
                    "data": {"source_evidence_package_path": "/data/evidence/episode/source.json"}
                },
            }
        ]
    }
    case = {
        "trigger": {
            "type": "event",
            "attributes": {"evidence_path": "/data/evidence/legacy.json"},
        }
    }
    result = extract_task_result(
        execution=_execution(trigger_type="event"),
        event=event,
        agent_result=agent_result,
        case=case,
    )
    assert result.evidence_package_paths == [
        "/data/evidence/20260918/xuchang-station-episode-1.evidence.json",
        "/data/evidence/legacy.json",
        "/data/evidence/episode/source.json",
    ]


def test_extraction_dedupes_evidence_package_paths():
    event = _Event({"evidence_package_path": "/data/evidence/same.json"})
    event.payload = {"evidence_package_path": "/data/evidence/same.json"}
    result = extract_task_result(
        execution=_execution(trigger_type="event"),
        event=event,
        agent_result=None,
        case=None,
    )
    assert result.evidence_package_paths == ["/data/evidence/same.json"]


def test_extraction_carries_trigger_metadata():
    execution = _execution(
        trigger_type="event",
        event_id="evt-9",
        event_type="daily_report",
    )
    result = extract_task_result(execution=execution, event=None, agent_result=None, case=None)
    assert result.trigger_type == "event"
    assert result.event_id == "evt-9"
    assert result.event_type == "daily_report"
    assert result.status == "success"
