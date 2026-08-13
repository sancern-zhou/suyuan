import json

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules import attachment_ocr_rules


def _order(code="CH2605081778206675949"):
    return {"WORKINGORDERCODE": code}


def test_gas_flow_single_character_measured_filename_is_selected():
    forms = [
        (
            "RF_M_GASEOUSFLOWCHECK",
            {
                "WORKINGORDERCODE": "CH2605081778206675949",
                "MEASUREDVALUECO": "630",
            },
        )
    ]
    attachments = [
        {
            "filename": "CO测.jpg",
            "file_url": "http://example.test/CO-measured.jpg",
        }
    ]

    tasks = attachment_ocr_rules.build_flow_visual_tasks(_order(), forms, attachments, [])

    assert len(tasks) == 1
    assert tasks[0]["item"]["filename"] == "CO测.jpg"


def test_gas_flow_tasks_skip_meter_id_photo_and_deduplicate_sources():
    forms = [
        (
            "RF_M_GASEOUSFLOWCHECK",
            {
                "WORKINGORDERCODE": "CH2605081778206675949",
                "DISPLAYVALUECO": "683",
                "MEASUREDVALUECO": "630",
            },
        )
    ]
    attachments = [
        {"filename": "大流量计编号.jpg", "file_url": "http://example.test/meter-id.jpg"},
        {"filename": "CO.jpg", "file_url": "http://example.test/co-display.jpg"},
        {"filename": "CO测.jpg", "file_url": "http://example.test/co-measured.jpg"},
    ]
    wo_commonfile = [
        {"FILENAME": "CO测.jpg", "FILEPATH": "http://example.test/co-measured.jpg"},
    ]

    tasks = attachment_ocr_rules.build_flow_visual_tasks(_order(), forms, attachments, wo_commonfile)
    filenames = [task["item"]["filename"] for task in tasks]

    assert "大流量计编号.jpg" not in filenames
    assert filenames.count("CO测.jpg") == 1
    assert {"CO.jpg", "CO测.jpg"} <= set(filenames)


def test_gas_flow_measured_photo_compares_measured_value_with_unit_conversion(monkeypatch):
    def fake_extract_attachment_json(source, provider, task, prompt):
        assert "measured_values" in prompt
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": None},
                "measured_values": {"CO": 0.63},
                "display_units": {"CO": None},
                "measured_units": {"CO": "LPM"},
                "confidence": 0.95,
                "reason": "外接流量计测量值照片",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)
    issues: list[Issue] = []
    forms = [
        (
            "RF_M_GASEOUSFLOWCHECK",
            {
                "WORKINGORDERCODE": "CH2605081778206675949",
                "MEASUREDVALUECO": "630",
            },
        )
    ]
    task = {
        "order": _order(),
        "forms": forms,
        "item": {"filename": "CO测.jpg", "source_path": "http://example.test/CO-measured.jpg", "types": ["photo"]},
    }

    attachment_ocr_rules.run_flow_visual_task(task, issues)

    assert not issues


def test_gas_flow_measured_photo_flags_measured_value_mismatch(monkeypatch):
    def fake_extract_attachment_json(source, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": None},
                "measured_values": {"CO": 0.63},
                "measured_units": {"CO": "LPM"},
                "confidence": 0.95,
                "reason": "外接流量计测量值照片",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)
    issues: list[Issue] = []
    forms = [
        (
            "RF_M_GASEOUSFLOWCHECK",
            {
                "WORKINGORDERCODE": "CH2605081778206675949",
                "MEASUREDVALUECO": "683",
            },
        )
    ]
    task = {
        "order": _order(),
        "forms": forms,
        "item": {"filename": "CO测.jpg", "source_path": "http://example.test/CO-measured.jpg", "types": ["photo"]},
    }

    attachment_ocr_rules.run_flow_visual_task(task, issues)

    assert [issue.rule_id for issue in issues] == ["ATTACHMENT_GAS_FLOW_MEASURED_VALUE_MISMATCH"]
    evidence = json.loads(issues[0].evidence)
    assert evidence["comparisons"][0]["field"] == "MEASUREDVALUECO"
    assert evidence["comparisons"][0]["visual_value"] == 630


def test_pm_temp_pressure_photo_task_is_selected():
    forms = [
        (
            "RF_Q_PMPRESSURE",
            {
                "WORKINGORDERCODE": "CH2605131778663451989",
                "PM10CHECKTEMP1VALUE": "32.11",
                "PM10CHECKTEMP2VALUE": "33.2",
            },
        )
    ]
    attachments = [{"filename": "PM10温度压力读数.jpg", "file_url": "http://example.test/pm10-temp-pressure.jpg"}]

    tasks = attachment_ocr_rules.build_flow_visual_tasks(_order("CH2605131778663451989"), forms, attachments, [])

    assert len(tasks) == 1
    assert tasks[0]["item"]["filename"] == "PM10温度压力读数.jpg"


def test_pm_temp_pressure_photo_compares_display_and_standard_values(monkeypatch):
    def fake_extract_attachment_json(source, provider, task, prompt):
        assert "temperature_display" in prompt
        assert "pressure_standard" in prompt
        return {
            "status": "success",
            "data": {
                "is_pm_temp_pressure_photo": True,
                "values": {
                    "PM10": {
                        "temperature_display": 32.11,
                        "temperature_standard": 33.2,
                        "pressure_display": 993,
                        "pressure_standard": 996,
                    }
                },
                "confidence": 0.95,
                "reason": "温度压力校准照片",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)
    issues: list[Issue] = []
    forms = [
        (
            "RF_Q_PMPRESSURE",
            {
                "WORKINGORDERCODE": "CH2605131778663451989",
                "PM10CHECKTEMP1VALUE": "32.11",
                "PM10CHECKTEMP2VALUE": "33.2",
                "PM10CHECKPRES1VALUE": "993",
                "PM10CHECKPRES2VALUE": "996",
            },
        )
    ]
    task = {
        "order": _order("CH2605131778663451989"),
        "forms": forms,
        "item": {"filename": "PM10温度压力读数.jpg", "source_path": "http://example.test/pm10.jpg", "types": ["photo"]},
    }

    attachment_ocr_rules.run_flow_visual_task(task, issues)

    assert not issues


def test_pm_temp_pressure_photo_flags_display_value_mismatch(monkeypatch):
    def fake_extract_attachment_json(source, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_pm_temp_pressure_photo": True,
                "values": {
                    "PM10": {
                        "temperature_display": 34.2,
                        "temperature_standard": 34.2,
                        "pressure_display": 993,
                        "pressure_standard": 996,
                    }
                },
                "confidence": 0.95,
                "reason": "温度压力校准照片",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)
    issues: list[Issue] = []
    forms = [
        (
            "RF_Q_PMPRESSURE",
            {
                "WORKINGORDERCODE": "CH2605131778663451989",
                "PM10CHECKTEMP1VALUE": "32.11",
                "PM10CHECKTEMP2VALUE": "33.2",
                "PM10CHECKPRES1VALUE": "993",
                "PM10CHECKPRES2VALUE": "996",
            },
        )
    ]
    task = {
        "order": _order("CH2605131778663451989"),
        "forms": forms,
        "item": {"filename": "PM10温度压力读数.jpg", "source_path": "http://example.test/pm10.jpg", "types": ["photo"]},
    }

    attachment_ocr_rules.run_flow_visual_task(task, issues)

    assert [issue.rule_id for issue in issues] == ["ATTACHMENT_PM_TEMP_PRESSURE_VALUE_MISMATCH"]
    evidence = json.loads(issues[0].evidence)
    mismatch = [item for item in evidence["comparisons"] if item["status"] == "mismatch"][0]
    assert mismatch["field"] == "PM10CHECKTEMP1VALUE"


def test_pm25_temp_pressure_filename_only_compares_pm25_display_fields(monkeypatch):
    def fake_extract_attachment_json(source, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_pm_temp_pressure_photo": True,
                "values": {
                    "PM10": {
                        "temperature_display": 25.9,
                        "temperature_standard": None,
                        "pressure_display": 100.2,
                        "pressure_standard": None,
                    },
                    "PM25": {
                        "temperature_display": 25.9,
                        "temperature_standard": None,
                        "pressure_display": 100.2,
                        "pressure_standard": None,
                    },
                },
                "confidence": 0.95,
                "reason": "PM2.5温度大气压照片",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)
    issues: list[Issue] = []
    forms = [
        (
            "RF_Q_PMPRESSURE",
            {
                "WORKINGORDERCODE": "CH2605151778840800461",
                "PM10CHECKTEMP1VALUE": "27.89",
                "PM10CHECKPRES1VALUE": "99.984",
                "PM25CHECKTEMP1VALUE": "25.9",
                "PM25CHECKPRES1VALUE": "100.2",
            },
        )
    ]
    task = {
        "order": _order("CH2605151778840800461"),
        "forms": forms,
        "item": {"filename": "PM2.5温度大气压.jpg", "source_path": "http://example.test/pm25.jpg", "types": ["photo"]},
    }

    attachment_ocr_rules.run_flow_visual_task(task, issues)

    assert not issues


def test_pm_temp_pressure_filename_without_pm_compares_standard_fields(monkeypatch):
    def fake_extract_attachment_json(source, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_pm_temp_pressure_photo": True,
                "values": {
                    "PM10": {
                        "temperature_display": None,
                        "temperature_standard": None,
                        "pressure_display": 100.3,
                        "pressure_standard": None,
                    },
                    "PM25": {
                        "temperature_display": None,
                        "temperature_standard": None,
                        "pressure_display": 100.3,
                        "pressure_standard": None,
                    },
                },
                "confidence": 0.95,
                "reason": "通用大气压照片",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)
    issues: list[Issue] = []
    forms = [
        (
            "RF_Q_PMPRESSURE",
            {
                "WORKINGORDERCODE": "CH2605151778840800461",
                "PM10CHECKPRES1VALUE": "99.984",
                "PM10CHECKPRES2VALUE": "100.3",
                "PM25CHECKPRES1VALUE": "100.2",
                "PM25CHECKPRES2VALUE": "100.3",
            },
        )
    ]
    tasks = attachment_ocr_rules.build_flow_visual_tasks(
        _order("CH2605151778840800461"),
        forms,
        [{"filename": "大气压.jpg", "file_url": "http://example.test/pressure.jpg"}],
        [],
    )

    assert [task["item"]["filename"] for task in tasks] == ["大气压.jpg"]
    attachment_ocr_rules.run_flow_visual_task(tasks[0], issues)

    assert not issues
