import json

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules import attachment_ocr_rules
from app.services.ops_audit.rules.attachment_ocr_rules import build_flow_visual_tasks, run_flow_visual_task


def _order():
    return {"WORKINGORDERCODE": "CH2605081778206675949"}


def _forms():
    return [
        (
            "RF_M_GASEOUSFLOWCHECK",
            {
                "WORKINGORDERCODE": "CH2605081778206675949",
                "DISPLAYVALUECO": "683",
                "MEASUREDVALUECO": "650",
            },
        )
    ]


def test_gas_flow_visual_tasks_include_single_character_measured_and_flow_check_names():
    attachments = [
        {
            "refid": "CH2605081778206675949",
            "filename": "CO测.jpg",
            "file_url": "http://example.test/CO-measured.jpg",
        },
        {
            "refid": "CH2605081778206675949",
            "filename": "SO2流量检查.jpg",
            "file_url": "http://example.test/SO2-check.jpg",
        },
        {
            "refid": "CH2605081778206675949",
            "filename": "大流量计编号.jpg",
            "file_url": "http://example.test/meter-label.jpg",
        },
    ]

    tasks = build_flow_visual_tasks(_order(), _forms(), attachments, [])

    filenames = {task["item"]["filename"] for task in tasks}
    assert "CO测.jpg" in filenames
    assert "SO2流量检查.jpg" in filenames
    assert "大流量计编号.jpg" not in filenames


def test_gas_flow_measured_photo_compares_measured_value_with_unit_conversion(monkeypatch):
    captured = {}

    def fake_extract(source, *, provider, task, prompt):
        captured["prompt"] = prompt
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": None},
                "measured_values": {"CO": 0.630},
                "measured_units": {"CO": "LPM"},
                "confidence": 0.95,
                "reason": "外接流量计照片，读取0.630 LPM",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract)
    issues: list[Issue] = []

    run_flow_visual_task(
        {
            "order": _order(),
            "forms": _forms(),
            "item": {
                "filename": "CO测.jpg",
                "source_path": "http://example.test/CO-measured.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert "CO测.jpg" in captured["prompt"]
    assert [issue.rule_id for issue in issues] == ["ATTACHMENT_GAS_FLOW_MEASURED_VALUE_MISMATCH"]
    evidence = json.loads(issues[0].evidence)
    comparison = evidence["comparisons"][0]
    assert comparison["field"] == "MEASUREDVALUECO"
    assert comparison["raw_visual_value"] == 0.63
    assert comparison["visual_value"] == 630
    assert comparison["form_value"] == 650


def test_gas_flow_display_photo_still_compares_display_value(monkeypatch):
    def fake_extract(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": 683},
                "display_units": {"CO": "cc/min"},
                "measured_values": {"CO": None},
                "confidence": 0.95,
                "reason": "仪器显示流量照片",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract)
    issues: list[Issue] = []

    run_flow_visual_task(
        {
            "order": _order(),
            "forms": _forms(),
            "item": {
                "filename": "CO.jpg",
                "source_path": "http://example.test/CO-display.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert not issues
