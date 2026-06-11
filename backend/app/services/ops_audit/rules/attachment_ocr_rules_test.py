import json

from app.services.ops_audit.rules import attachment_ocr_rules


def test_reference_flowmeter_certificate_always_uses_ocr(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_flowmeter_certificate": True,
                "factory_code": "A741905036",
                "calibration_date": "2025-05-07",
                "valid_until": "2026-05-06",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)

    result = attachment_ocr_rules._extract_reference_flowmeter_certificate(
        {"filename": "流量计-THM-703-A741905036.pdf", "source_path": "http://example.test/cert.pdf"}
    )

    assert result["ocr_status"] == "success"
    assert result["factory_code"] == "A741905036"
    assert result["calibration_date"] == "2025-05-07"
    assert result["valid_until"] == "2026-05-06"


def test_reference_flowmeter_certificate_fills_factory_code_from_filename_after_ocr(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_flowmeter_certificate": True,
                "factory_code": "A741905036",
                "calibration_date": "2025-05-07",
                "valid_until": "2026-05-06",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)

    result = attachment_ocr_rules._extract_reference_flowmeter_certificate(
        {
            "filename": "流量计-THM-703-A741905036.pdf",
            "source_path": "http://example.test/cert.pdf",
        }
    )

    assert result["ocr_status"] == "success"
    assert result["factory_code"] == "A741905036"
    assert result["calibration_date"] == "2025-05-07"
    assert result["valid_until"] == "2026-05-06"


def test_reference_flowmeter_certificate_date_mismatch_adds_issue(monkeypatch):
    monkeypatch.setattr(
        attachment_ocr_rules,
        "_extract_reference_flowmeter_material",
        lambda item: {
            "is_reference_flowmeter_material": True,
            "factory_code": "A741905036",
            "last_calibration_date": "2025-05-06",
            "next_calibration_date": "2026-05-06",
            "source_filename": item["filename"],
        },
    )
    monkeypatch.setattr(
        attachment_ocr_rules,
        "_extract_reference_flowmeter_certificate",
        lambda item: {
            "is_flowmeter_certificate": True,
            "factory_code": "A741905036",
            "calibration_date": "2025-05-07",
            "valid_until": "2026-05-06",
            "source_filename": item["filename"],
        },
    )

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "reference_flowmeter_certificate",
            "order": {"WORKINGORDERCODE": "WO-001"},
            "forms": [("RF_M_GASEOUSFLOWCHECK", {"CHECKDATE": "2026-05-07"})],
            "material_items": [{"filename": "THM-703.jpg", "source_path": "http://example.test/material.jpg"}],
            "certificate_items": [
                {"filename": "流量计-THM-703-A741905036.pdf", "source_path": "http://example.test/cert.pdf"}
            ],
        },
        issues,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "RF_REFERENCE_FLOWMETER_CERT_DATE_MISMATCH"
    evidence = json.loads(issues[0].evidence)
    mismatch = next(item for item in evidence["comparisons"] if item["status"] == "mismatch")
    assert mismatch["field"] == "last_calibration_date"
    assert mismatch["material_date"] == "2025-05-06"
    assert mismatch["certificate_date"] == "2025-05-07"


def test_reference_flowmeter_certificate_missing_dates_adds_issue(monkeypatch):
    monkeypatch.setattr(
        attachment_ocr_rules,
        "_extract_reference_flowmeter_material",
        lambda item: {
            "is_reference_flowmeter_material": True,
            "factory_code": "A741905036",
            "last_calibration_date": "2025-05-07",
            "next_calibration_date": "2026-05-06",
            "source_filename": item["filename"],
        },
    )
    monkeypatch.setattr(
        attachment_ocr_rules,
        "_extract_reference_flowmeter_certificate",
        lambda item: {
            "is_flowmeter_certificate": True,
            "factory_code": "A741905036",
            "calibration_date": "",
            "valid_until": "",
            "next_calibration_date": "",
            "source_filename": item["filename"],
            "ocr_status": "success",
        },
    )

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "reference_flowmeter_certificate",
            "order": {"WORKINGORDERCODE": "WO-002"},
            "forms": [("RF_M_GASEOUSFLOWCHECK", {"CHECKDATE": "2026-05-07"})],
            "material_items": [{"filename": "THM-703.jpg", "source_path": "http://example.test/material.jpg"}],
            "certificate_items": [
                {"filename": "流量计-THM-703-A741905036.pdf", "source_path": "http://example.test/cert.pdf"}
            ],
        },
        issues,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "RF_REFERENCE_FLOWMETER_CERT_DATE_MISMATCH"
    evidence = json.loads(issues[0].evidence)
    missing = [item for item in evidence["comparisons"] if item["status"] == "missing_certificate_date"]
    assert {item["field"] for item in missing} == {"last_calibration_date", "next_calibration_date"}


def test_reference_flowmeter_material_missing_dates_adds_issue(monkeypatch):
    monkeypatch.setattr(
        attachment_ocr_rules,
        "_extract_reference_flowmeter_material",
        lambda item: {
            "is_reference_flowmeter_material": True,
            "factory_code": "A741905036",
            "last_calibration_date": "",
            "next_calibration_date": "",
            "source_filename": item["filename"],
            "ocr_status": "success",
        },
    )
    monkeypatch.setattr(
        attachment_ocr_rules,
        "_extract_reference_flowmeter_certificate",
        lambda item: {
            "is_flowmeter_certificate": True,
            "factory_code": "A741905036",
            "calibration_date": "2025-05-07",
            "valid_until": "2026-05-06",
            "source_filename": item["filename"],
            "ocr_status": "success",
        },
    )

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "reference_flowmeter_certificate",
            "order": {"WORKINGORDERCODE": "WO-004"},
            "forms": [("RF_M_GASEOUSFLOWCHECK", {"CHECKDATE": "2026-05-07"})],
            "material_items": [{"filename": "THM-703.jpg", "source_path": "http://example.test/material.jpg"}],
            "certificate_items": [
                {"filename": "流量计-THM-703-A741905036.pdf", "source_path": "http://example.test/cert.pdf"}
            ],
        },
        issues,
    )

    assert len(issues) == 1
    evidence = json.loads(issues[0].evidence)
    missing = [item for item in evidence["comparisons"] if item["status"] == "missing_material_date"]
    assert {item["field"] for item in missing} == {"last_calibration_date", "next_calibration_date"}


def test_reference_flowmeter_certificate_task_uses_monthly_attachments_only():
    forms = [("RF_M_GASEOUSFLOWCHECK", {"WORKINGORDERCODE": "WO-003"})]
    attachments = [
        {
            "filename": "THM-703.jpg",
            "file_url": "http://example.test/Check/RF_Q_GaseousFlowCheck/q-material.jpg",
        },
        {
            "filename": "流量计-THM-703-A741905036.pdf",
            "file_url": "http://example.test/Check/RF_Q_GaseousFlowCheck/q-cert.pdf",
        },
        {
            "filename": "气压计-青萍CGP23W-582D3486080A.pdf",
            "file_url": "http://example.test/Check/RF_M_GaseousFlowCheck/pressure.pdf",
        },
        {
            "filename": "THM-703.jpg",
            "file_url": "http://example.test/Check/RF_M_GaseousFlowCheck/m-material.jpg",
        },
        {
            "filename": "流量计-THM-703-A741905036.pdf",
            "file_url": "http://example.test/Check/RF_M_GaseousFlowCheck/m-cert.pdf",
        },
    ]

    tasks = attachment_ocr_rules.build_flow_visual_tasks(
        {"WORKINGORDERCODE": "WO-003"},
        forms,
        attachments,
        [],
    )

    task = next(task for task in tasks if task.get("task_type") == "reference_flowmeter_certificate")
    assert [item["source_path"] for item in task["material_items"]] == [
        "http://example.test/Check/RF_M_GaseousFlowCheck/m-material.jpg"
    ]
    assert [item["source_path"] for item in task["certificate_items"]] == [
        "http://example.test/Check/RF_M_GaseousFlowCheck/m-cert.pdf"
    ]


def test_flow_visual_task_reports_vision_error_instead_of_silent_success(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "provider": "qwen-vl-max",
            "status": "error",
            "source": source,
            "error": "文件不存在且未配置附件根路径/基础URL：/WebFiles/NewFiles/flow.jpg",
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-005"},
            "forms": [("RF_TW_PmFlowCalibrate", {"Prev_A": "16.7", "Next_A": "16.8"})],
            "item": {
                "filename": "流量校准前.jpg",
                "source_path": "/WebFiles/NewFiles/flow.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "ATTACHMENT_FLOW_VISUAL_DIAGNOSTIC"
    assert issues[0].severity == "低"
    evidence = json.loads(issues[0].evidence)
    assert evidence["working_order_code"] == "WO-005"
    assert evidence["vision_status"] == "error"
    assert "附件根路径/基础URL" in evidence["vision_error"]


def test_monthly_thermo_o3_display_uses_flow_a_plus_b(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        assert "流量A" in prompt
        assert "流量B" in prompt
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"O3": 0.572},
                "display_components": {
                    "O3": [
                        {"label": "流量A", "value": 0.572, "unit": "L/min"},
                        {"label": "流量B", "value": 0.566, "unit": "L/min"},
                    ]
                },
                "measured_values": {},
                "display_units": {"O3": "L/min"},
                "measured_units": {},
                "unit": "L/min",
                "confidence": 0.95,
                "reason": "热电臭氧照片包含流量A和流量B",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-M-THERMO"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {"DEVICEBRAND": "热电", "DISPLAYVALUEO3": "1.138"},
                )
            ],
            "item": {
                "filename": "O3流量检查照片.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_M_GASEOUSFLOWCHECK/o3.jpg",
                "typecode": "RF_M_GASEOUSFLOWCHECK",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_monthly_non_thermo_o3_display_does_not_sum_flow_a_plus_b(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"O3": 0.572},
                "display_components": {
                    "O3": [
                        {"label": "流量A", "value": 0.572, "unit": "L/min"},
                        {"label": "流量B", "value": 0.566, "unit": "L/min"},
                    ]
                },
                "measured_values": {},
                "display_units": {"O3": "L/min"},
                "measured_units": {},
                "unit": "L/min",
                "confidence": 0.95,
                "reason": "非热电品牌不应把A和B相加",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-M-FPI"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {"DEVICEBRAND": "FPI", "DISPLAYVALUEO3": "1.138"},
                )
            ],
            "item": {
                "filename": "O3流量检查照片.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_M_GASEOUSFLOWCHECK/o3.jpg",
                "typecode": "RF_M_GASEOUSFLOWCHECK",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "ATTACHMENT_GAS_FLOW_DISPLAY_VALUE_MISMATCH"
    assert "O3 图片值 0.572" in issues[0].message


def test_quarter_gas_flow_attachment_does_not_compare_monthly_form(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {},
                "measured_values": {"SO2": 6.105},
                "display_units": {},
                "measured_units": {"SO2": "LPM"},
                "unit": "L/min",
                "confidence": 0.95,
                "reason": "季度6L实测流量照片",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-Q"},
            "forms": [
                ("RF_M_GASEOUSFLOWCHECK", {"MEASUREDVALUESO2": "0.442"}),
                ("RF_Q_GaseousFlowCheck", {"RF_Valuve_60": "6105"}),
            ],
            "item": {
                "filename": "6L实测流量.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_Q_GaseousFlowCheck/6l.jpg",
                "typecode": "RF_Q_GaseousFlowCheck",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_quarter_gas_flow_measured_photo_compares_rf_value(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {},
                "measured_values": {"60": 6200},
                "display_units": {},
                "measured_units": {"60": "ml/min"},
                "unit": "ml/min",
                "confidence": 0.95,
                "reason": "季度6L实测流量照片",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-Q"},
            "forms": [("RF_Q_GaseousFlowCheck", {"RF_Valuve_60": "6105"})],
            "item": {
                "filename": "6L实测流量.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_Q_GaseousFlowCheck/6l.jpg",
                "typecode": "RF_Q_GaseousFlowCheck",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "ATTACHMENT_GAS_FLOW_MEASURED_VALUE_MISMATCH"
    assert "RF_Valuve_60=6105.0" in issues[0].message


def test_pm_membrane_attachment_matches_pm10_form_by_typecode(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_pm_membrane_photo": True,
                "original_value": None,
                "check_value": 0.812,
                "visible_values": [{"label": "CAL MASS m", "value": 0.812}],
                "confidence": 0.95,
                "reason": "pm10膜片实测",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-PM"},
            "forms": [
                ("RF_Q_PM25RUNSTATUSCHECK", {"PM25CHECKTEMP2VALUE": "0.807"}),
                ("RF_Q_PM10RUNSTATUSCHECK", {"PM10CHECKTEMP2VALUE": "0.812"}),
            ],
            "item": {
                "filename": "pm10膜片实测.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_Q_Pm10RunStatusCheck/pm10.jpg",
                "typecode": "RF_Q_Pm10RunStatusCheck",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_pm_membrane_attachment_matches_pm25_form_by_typecode(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_pm_membrane_photo": True,
                "original_value": None,
                "check_value": 0.807,
                "visible_values": [{"label": "CAL MASS m", "value": 0.807}],
                "confidence": 0.95,
                "reason": "pm2.5膜片实测",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-PM"},
            "forms": [
                ("RF_Q_PM25RUNSTATUSCHECK", {"PM25CHECKTEMP2VALUE": "0.807"}),
                ("RF_Q_PM10RUNSTATUSCHECK", {"PM10CHECKTEMP2VALUE": "0.812"}),
            ],
            "item": {
                "filename": "pm2.5膜片实测.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_Q_Pm25RunStatusCheck/pm25.jpg",
                "typecode": "RF_Q_Pm25RunStatusCheck",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []
