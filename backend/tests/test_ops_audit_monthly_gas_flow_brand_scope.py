from app.services.ops_audit.rules import attachment_ocr_rules


def _task(brand):
    return {
        "task_type": "flow_visual",
        "order": {"WORKINGORDERCODE": "WO-GAS"},
        "forms": [("RF_M_GASEOUSFLOWCHECK", {
            "DEVICEBRAND": brand,
            "DISPLAYVALUECO": "0.63",
            "MEASUREDVALUECO": "0.63",
        })],
        "item": {
            "filename": "CO流量照片.jpg",
            "source_path": "/WebFiles/co.jpg",
            "typecode": "RF_M_GASEOUSFLOWCHECK",
            "types": ["photo"],
        },
    }


def test_monthly_gas_flow_api_brand_compares_raw_values(monkeypatch):
    calls = []

    def fake_ocr(*args, **kwargs):
        calls.append(True)
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": 0.63},
                "measured_values": {"CO": 0.63},
                "display_units": {"CO": "L/min"},
                "measured_units": {"CO": "L/min"},
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(_task("API"), issues)

    assert calls
    assert issues == []


def test_monthly_gas_flow_te_brand_does_not_convert_values(monkeypatch):
    monkeypatch.setattr(
        attachment_ocr_rules,
        "extract_attachment_json",
        lambda *args, **kwargs: {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": 0.63},
                "measured_values": {"CO": 0.63},
                "display_units": {"CO": "L/min"},
                "measured_units": {"CO": "L/min"},
            },
        },
    )
    issues = []
    task = _task("TE")
    task["forms"][0][1]["MEASUREDVALUECO"] = "630"

    attachment_ocr_rules.run_flow_visual_task(task, issues)

    assert {issue.rule_id for issue in issues} == {
        "ATTACHMENT_GAS_FLOW_MEASURED_VALUE_MISMATCH",
    }


def test_monthly_gas_flow_other_brand_skips_visual_identification(monkeypatch):
    calls = []
    monkeypatch.setattr(
        attachment_ocr_rules,
        "extract_attachment_json",
        lambda *args, **kwargs: calls.append(True),
    )
    issues = []

    attachment_ocr_rules.run_flow_visual_task(_task("FPI"), issues)

    assert calls == []
    assert issues == []


def test_monthly_gas_flow_task_builder_skips_other_brand():
    forms = [("RF_M_GASEOUSFLOWCHECK", {"DEVICEBRAND": "FPI"})]
    attachments = [{
        "TYPECODE": "RF_M_GASEOUSFLOWCHECK",
        "FILENAME": "CO流量照片.jpg",
        "FILEPATH": "/WebFiles/co.jpg",
    }]

    assert attachment_ocr_rules.build_flow_visual_tasks({}, forms, attachments, []) == []
