import json

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules import attachment_ocr_rules
from app.services.ops_audit.rules.attachment_ocr_rules import build_flow_visual_tasks, run_flow_visual_task


def _order():
    return {"WORKINGORDERCODE": "CH2605251779692955875"}


def test_pm_membrane_visual_tasks_include_quarterly_pm_run_status_photos():
    forms = [
        (
            "RF_Q_PM25RUNSTATUSCHECK",
            {
                "WORKINGORDERCODE": "CH2605251779692955875",
                "PM25CHECKTEMP1VALUE": "0.806",
                "PM25CHECKTEMP2VALUE": "0.804",
                "PM25CHECKTEMP3VALUE": "0.2",
            },
        )
    ]
    attachments = [
        {
            "REFID": "CH2605251779692955875",
            "TYPECODE": "RF_Q_Pm25RunStatusCheck",
            "FILENAME": "pm2.5膜片原始值.jpg",
            "FILEPATH": "/WebFiles/NewFiles/2026/5/25/Check/RF_Q_Pm25RunStatusCheck/original.jpg",
        },
        {
            "REFID": "CH2605251779692955875",
            "TYPECODE": "RF_Q_Pm25RunStatusCheck",
            "FILENAME": "pm2.5膜片检查.jpg",
            "FILEPATH": "/WebFiles/NewFiles/2026/5/25/Check/RF_Q_Pm25RunStatusCheck/check.jpg",
        },
        {
            "REFID": "CH2605251779692955875",
            "TYPECODE": "RF_HY_StationDeviceMaintain",
            "FILENAME": "pm2.5加热正常.jpg",
            "FILEPATH": "/WebFiles/NewFiles/2026/5/25/Check/RF_HY_StationDeviceMaintain/heater.jpg",
        },
    ]

    tasks = build_flow_visual_tasks(_order(), forms, [], attachments)

    filenames = {task["item"]["filename"] for task in tasks}
    assert "pm2.5膜片原始值.jpg" in filenames
    assert "pm2.5膜片检查.jpg" in filenames
    assert "pm2.5加热正常.jpg" not in filenames


def test_pm_membrane_ocr_compares_original_and_check_values(monkeypatch):
    def fake_extract(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_pm_membrane_photo": True,
                "original_value": 0.806,
                "check_value": 0.810,
                "confidence": 0.94,
                "reason": "膜片检查照片读取到检查值0.810",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract)
    issues: list[Issue] = []

    run_flow_visual_task(
        {
            "order": _order(),
            "forms": [
                (
                    "RF_Q_PM25RUNSTATUSCHECK",
                    {
                        "WORKINGORDERCODE": "CH2605251779692955875",
                        "PM25CHECKTEMP1VALUE": "0.806",
                        "PM25CHECKTEMP2VALUE": "0.804",
                        "PM25CHECKTEMP3VALUE": "0.2",
                    },
                )
            ],
            "item": {
                "filename": "pm2.5膜片检查.jpg",
                "source_path": "http://example.test/pm25-check.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert [issue.rule_id for issue in issues] == ["ATTACHMENT_PM_MEMBRANE_VALUE_MISMATCH"]
    evidence = json.loads(issues[0].evidence)
    fields = {comparison["field"] for comparison in evidence["comparisons"]}
    assert "PM25CHECKTEMP2VALUE" in fields


def test_pm_membrane_ocr_does_not_duplicate_formula_rules(monkeypatch):
    def fake_extract(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_pm_membrane_photo": True,
                "original_value": 0.806,
                "check_value": 0.830,
                "confidence": 0.94,
                "reason": "膜片读数照片",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract)
    issues: list[Issue] = []

    run_flow_visual_task(
        {
            "order": _order(),
            "forms": [
                (
                    "RF_Q_PM25RUNSTATUSCHECK",
                    {
                        "WORKINGORDERCODE": "CH2605251779692955875",
                        "PM25CHECKTEMP1VALUE": "0.806",
                        "PM25CHECKTEMP2VALUE": "0.830",
                        "PM25CHECKTEMP3VALUE": "0.2",
                    },
                )
            ],
            "item": {
                "filename": "pm2.5膜片检查.jpg",
                "source_path": "http://example.test/pm25-check.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert not issues
