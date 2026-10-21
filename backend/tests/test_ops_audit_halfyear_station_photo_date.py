import json

from app.services.ops_audit.rules import attachment_ocr_rules


def _task():
    return {
        "order": {"WORKINGORDERCODE": "HY-001", "DDWORKINGORDERTYPE": "Check", "MAINTENANCETYPE": "HalfYear"},
        "forms": [("RF_HY_STATIONDEVICEMAINTAIN", {})],
        "details": [
            {
                "PROCESSSTEP": "CheckOrder",
                "PROCESSSTARTDATETIME": "2026-09-20 23:59:00",
                "PROCESSENDDATETIME": "2026-09-21 00:01:00",
            }
        ],
        "attachments": [
            {
                "filename": "站点设备维护.jpg",
                "file_url": "http://example.test/hy.jpg",
                "typecode": "RF_HY_STATIONDEVICEMAINTAIN",
            }
        ],
        "wo_commonfiles": [],
    }


def test_halfyear_station_photo_task_compares_date_only(monkeypatch):
    task_data = _task()
    tasks = attachment_ocr_rules.build_halfyear_station_photo_tasks(**task_data)
    assert len(tasks) == 1

    def fake_extract(*args, **kwargs):
        return {
            "status": "success",
            "data": {
                "watermark_date": "2026-09-20",
                "watermark_text": "2026-09-20 08:00:00",
                "watermark_confidence": 0.98,
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract)
    issues = []
    attachment_ocr_rules.run_flow_visual_task(tasks[0], issues)
    assert issues == []


def test_halfyear_station_photo_date_outside_window_adds_issue(monkeypatch):
    task_data = _task()
    tasks = attachment_ocr_rules.build_halfyear_station_photo_tasks(**task_data)

    monkeypatch.setattr(
        attachment_ocr_rules,
        "extract_attachment_json",
        lambda *args, **kwargs: {
            "status": "success",
            "data": {"watermark_date": "2026-09-22", "watermark_confidence": 0.98},
        },
    )
    issues = []
    attachment_ocr_rules.run_flow_visual_task(tasks[0], issues)
    assert [issue.rule_id for issue in issues] == ["ATTACHMENT_HY_STATION_PHOTO_DATE_OUTSIDE_MAINTENANCE"]
    evidence = json.loads(issues[0].evidence)
    assert evidence["watermark_date"] == "2026-09-22"


def test_halfyear_station_photo_task_requires_check_halfyear_station_form():
    task_data = _task()
    task_data["order"]["MAINTENANCETYPE"] = "Year"
    assert attachment_ocr_rules.build_halfyear_station_photo_tasks(**task_data) == []
