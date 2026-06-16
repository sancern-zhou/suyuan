import json

from app.services.ops_audit.rules import attachment_ocr_rules


def test_pm_flow_photo_matches_pollutant_and_before_standard_value(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_flow_calibration_photo": True,
                "before_flow": None,
                "after_flow": 16.42,
                "unit": "LPM",
                "visible_flow_values": [{"label": "Volu Flow", "value": 16.42, "unit": "LPM"}],
                "confidence": 0.95,
                "reason": "读取流量计屏幕Volu Flow 16.420 LPM",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(
        {
            "order": {"WORKINGORDERCODE": "CH2606011780295505974"},
            "forms": [
                (
                    "RF_TW_PmFlowCalibrate",
                    {
                        "WORKINGORDERCODE": "CH2606011780295505974",
                        "PollutantType": "PM2.5",
                        "Prev_S": "15.936",
                        "Prev_A": "15.91",
                        "Prev_B": "16.66",
                        "Next_S": "16.661",
                        "Next_A": "16.63",
                        "Next_B": "16.66",
                    },
                ),
                (
                    "RF_TW_PmFlowCalibrate",
                    {
                        "WORKINGORDERCODE": "CH2606011780295505974",
                        "PollutantType": "PM10",
                        "Prev_S": "16.420",
                        "Prev_A": "16.39",
                        "Prev_B": "16.66",
                    },
                ),
            ],
            "item": {
                "filename": "PM10流量检查.jpg",
                "source_path": "/WebFiles/NewFiles/2026/6/1/Check/RF_TW_PmFlowCalibratePM10/1780315645488110935.jpg",
                "typecode": "RF_TW_PmFlowCalibratePM10",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_pm_flow_before_photo_matches_pm25_before_standard_value(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_flow_calibration_photo": True,
                "before_flow": None,
                "after_flow": 15.936,
                "unit": "L/min",
                "visible_flow_values": [{"label": "Valu Flow", "value": 15.936, "unit": "LFM Air"}],
                "confidence": 0.95,
                "reason": "读取流量计屏幕Valu Flow 15.936 LFM",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(
        {
            "order": {"WORKINGORDERCODE": "CH2606011780295505974"},
            "forms": [
                (
                    "RF_TW_PmFlowCalibrate",
                    {
                        "WORKINGORDERCODE": "CH2606011780295505974",
                        "PollutantType": "PM2.5",
                        "Prev_S": "15.936",
                        "Prev_A": "15.91",
                        "Prev_B": "16.66",
                        "Next_S": "16.661",
                        "Next_A": "16.63",
                        "Next_B": "16.66",
                    },
                ),
                (
                    "RF_TW_PmFlowCalibrate",
                    {
                        "WORKINGORDERCODE": "CH2606011780295505974",
                        "PollutantType": "PM10",
                        "Prev_S": "16.420",
                        "Prev_A": "16.39",
                        "Prev_B": "16.66",
                    },
                ),
            ],
            "item": {
                "filename": "PM2.5流量校准前.jpg",
                "source_path": "/WebFiles/NewFiles/2026/6/1/Check/RF_TW_PmFlowCalibratePM25/1780315509418127258.jpg",
                "typecode": "RF_TW_PmFlowCalibratePM25",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_monthly_gas_flow_measured_photo_converts_lpm_to_lh_without_display_issue(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        assert "SLPM" in prompt
        assert "SCCM" in prompt
        assert "L/h" in prompt
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": 0.713},
                "measured_values": {"CO": 0.713},
                "display_units": {"CO": "LPM"},
                "measured_units": {"CO": "LPM"},
                "confidence": 0.98,
                "reason": "外接流量计照片，读取0.713 LPM",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(
        {
            "order": {"WORKINGORDERCODE": "WO-GAS-FLOW"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "WORKINGORDERCODE": "WO-GAS-FLOW",
                        "FLOWRANGCO": "50±5l/h",
                        "DISPLAYVALUECO": "42.74",
                        "MEASUREDVALUECO": "42.78",
                    },
                )
            ],
            "item": {
                "filename": "CO流量检查(流量计测值).jpg",
                "source_path": "http://example.test/co-meter.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_monthly_gas_flow_display_photo_matches_lh_or_lmin_form_value(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"NO2": 44.87},
                "measured_values": {"NO2": None},
                "display_units": {"NO2": "NL/h"},
                "measured_units": {"NO2": ""},
                "confidence": 0.95,
                "reason": "NO2显示流量44.87 NL/h",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(
        {
            "order": {"WORKINGORDERCODE": "CH2606021780374083109"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "WORKINGORDERCODE": "CH2606021780374083109",
                        "FLOWRANGNO2": "0.3-0.8",
                        "DISPLAYVALUENO2": "0.747",
                    },
                )
            ],
            "item": {
                "filename": "NO2显示流量.jpg",
                "source_path": "/WebFiles/NewFiles/2026/6/2/Check/RF_M_GaseousFlowCheck/no2-display.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_monthly_gas_flow_display_ccm_matches_ml_min_form_range(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": 780},
                "measured_values": {"CO": None},
                "display_units": {"CO": "CC/M"},
                "measured_units": {"CO": ""},
                "unit": "CC/M",
                "confidence": 0.95,
                "reason": "CO SAMP FL=780 CC/M",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(
        {
            "order": {"WORKINGORDERCODE": "CH2606041780548288923"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "WORKINGORDERCODE": "CH2606041780548288923",
                        "FLOWRANGCO": "800±10%ml/min",
                        "DISPLAYVALUECO": "780",
                    },
                )
            ],
            "item": {
                "filename": "CO.jpg",
                "source_path": "/WebFiles/NewFiles/2026/6/4/Check/RF_M_GaseousFlowCheck/co.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_monthly_gas_flow_measured_photo_does_not_create_display_mismatch(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": 0.713},
                "measured_values": {"CO": 0.713},
                "display_units": {"CO": "LPM"},
                "measured_units": {"CO": "LPM"},
                "confidence": 0.98,
                "reason": "外接流量计照片，读取0.713 LPM",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(
        {
            "order": {"WORKINGORDERCODE": "WO-GAS-FLOW"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "WORKINGORDERCODE": "WO-GAS-FLOW",
                        "FLOWRANGCO": "50±5l/h",
                        "DISPLAYVALUECO": "42.74",
                        "MEASUREDVALUECO": "99.99",
                    },
                )
            ],
            "item": {
                "filename": "CO流量检查(流量计测值).jpg",
                "source_path": "http://example.test/co-meter.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert [issue.rule_id for issue in issues] == ["ATTACHMENT_GAS_FLOW_MEASURED_VALUE_MISMATCH"]
    evidence = json.loads(issues[0].evidence)
    comparison = evidence["comparisons"][0]
    assert comparison["field"] == "MEASUREDVALUECO"
    assert comparison["visual_value"] == 42.78


def test_monthly_gas_flow_short_measured_filename_skips_display_comparison(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": 0.788},
                "measured_values": {"CO": 0.788},
                "display_units": {"CO": "LPM"},
                "measured_units": {"CO": "LPM"},
                "unit": "LPM",
                "confidence": 0.95,
                "reason": "Volu Flow 0.788 LPM",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(
        {
            "order": {"WORKINGORDERCODE": "CH2606041780548288923"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "WORKINGORDERCODE": "CH2606041780548288923",
                        "FLOWRANGCO": "800±10%ml/min",
                        "DISPLAYVALUECO": "780",
                        "MEASUREDVALUECO": "788",
                    },
                )
            ],
            "item": {
                "filename": "CO测.jpg",
                "source_path": "/WebFiles/NewFiles/2026/6/4/Check/RF_M_GaseousFlowCheck/co-measured.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_monthly_gas_flow_ce_liang_filename_does_not_create_display_mismatch(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": 833.32},
                "measured_values": {"CO": None},
                "display_units": {"CO": "L/h"},
                "measured_units": {"CO": ""},
                "confidence": 0.98,
                "reason": "外接流量计测量照片，读数833.32 L/h",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(
        {
            "order": {"WORKINGORDERCODE": "CH2606051780659814832"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "WORKINGORDERCODE": "CH2606051780659814832",
                        "FLOWRANGCO": "L/h",
                        "DISPLAYVALUECO": "759.27",
                        "MEASUREDVALUECO": "833.32",
                    },
                )
            ],
            "item": {
                "filename": "新华CO测量流量.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_M_GaseousFlowCheck/新华CO测量流量.jpg",
                "typecode": "RF_M_GASEOUSFLOWCHECK",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_monthly_gas_flow_measured_role_does_not_use_display_value_when_measured_missing(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": 0.84},
                "measured_values": {"CO": None},
                "display_units": {"CO": "LPM"},
                "measured_units": {"CO": ""},
                "unit": "LPM",
                "confidence": 0.95,
                "reason": "面板显示0.84 LPM，但未识别到外接流量计测量值。",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(
        {
            "order": {"WORKINGORDERCODE": "CH2606041780561581081"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "WORKINGORDERCODE": "CH2606041780561581081",
                        "FLOWRANGCO": "400～1200 SCCM",
                        "DISPLAYVALUECO": "727",
                        "MEASUREDVALUECO": "727",
                    },
                )
            ],
            "item": {
                "filename": "CO测量流量.jpg",
                "source_path": "/WebFiles/NewFiles/2026/6/4/Check/RF_M_GaseousFlowCheck/co.jpg",
                "typecode": "RF_M_GASEOUSFLOWCHECK",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_monthly_gas_flow_measured_photo_can_match_alternate_lpm_value(monkeypatch):
    def fake_ocr(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"CO": 0.713},
                "measured_values": {"CO": 0.692},
                "display_units": {"CO": "LPM"},
                "measured_units": {"CO": "SLPM"},
                "confidence": 0.98,
                "reason": "同一流量计照片中包含Volu Flow 0.713 LPM和SLPM 0.692",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_ocr)
    issues = []

    attachment_ocr_rules.run_flow_visual_task(
        {
            "order": {"WORKINGORDERCODE": "WO-GAS-FLOW"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "WORKINGORDERCODE": "WO-GAS-FLOW",
                        "FLOWRANGCO": "50±5l/h",
                        "DISPLAYVALUECO": "42.74",
                        "MEASUREDVALUECO": "42.78",
                    },
                )
            ],
            "item": {
                "filename": "CO流量检查(流量计测值).jpg",
                "source_path": "http://example.test/co-meter.jpg",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


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


def test_monthly_thermo_o3_display_skips_when_components_are_incomplete(monkeypatch):
    seen_prompt = {}

    def fake_extract_attachment_json(source, *, provider, task, prompt):
        seen_prompt["text"] = prompt
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"O3": 0.698},
                "display_components": {},
                "measured_values": {},
                "display_units": {"O3": "L/min"},
                "measured_units": {},
                "unit": "L/min",
                "confidence": 0.82,
                "reason": "只识别到热电臭氧照片的单个流量分量",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-M-THERMO-INCOMPLETE"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {"DEVICEBRAND": "TE", "DISPLAYVALUEO3": "1.394"},
                )
            ],
            "item": {
                "filename": "O3示值.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_M_GASEOUSFLOWCHECK/o3.jpg",
                "typecode": "RF_M_GASEOUSFLOWCHECK",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []
    assert "不能同时识别流量A和流量B" in seen_prompt["text"]


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


def test_pm_membrane_numbered_photos_use_filename_slot_for_original_and_check(monkeypatch):
    responses = {
        "pm10-1.jpg": {
            "status": "success",
            "data": {
                "is_pm_membrane_photo": True,
                "original_value": None,
                "check_value": 0.875,
                "visible_values": [{"label": "ABS", "value": 0.875}],
                "confidence": 0.9,
                "reason": "模型把ABS识别为本次检查值",
            },
        },
        "pm10-2.jpg": {
            "status": "success",
            "data": {
                "is_pm_membrane_photo": True,
                "original_value": 0.885,
                "check_value": None,
                "visible_values": [{"label": "CAL MASS m", "value": 0.885}],
                "confidence": 0.95,
                "reason": "模型把CAL MASS识别为原始值",
            },
        },
    }

    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return responses[source]

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    forms = [
        (
            "RF_Q_PM10RUNSTATUSCHECK",
            {
                "PM10CHECKTEMP1VALUE": "0.875",
                "PM10CHECKTEMP2VALUE": "0.885",
            },
        )
    ]
    for filename, source_path in (("PM10膜片检查1.jpg", "pm10-1.jpg"), ("PM10膜片检查2.jpg", "pm10-2.jpg")):
        attachment_ocr_rules.run_flow_visual_task(
            {
                "task_type": "flow_visual",
                "order": {"WORKINGORDERCODE": "CH2606021780378435516"},
                "forms": forms,
                "item": {
                    "filename": filename,
                    "source_path": source_path,
                    "typecode": "RF_Q_Pm10RunStatusCheck",
                    "types": ["photo"],
                },
            },
            issues,
        )

    assert issues == []


def test_pm_membrane_prompt_targets_mass_factor_not_membrane_label_value(monkeypatch):
    seen_prompt = {}

    def fake_extract_attachment_json(source, *, provider, task, prompt):
        seen_prompt["text"] = prompt
        return {
            "status": "success",
            "data": {
                "is_pm_membrane_photo": True,
                "original_value": None,
                "check_value": None,
                "visible_values": [
                    {"label": "校准膜读数", "value": 1404},
                    {"label": "MASS系数", "value": 7281.3},
                ],
                "confidence": 0.95,
                "reason": "prompt inspection",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "CH2606041780581111441"},
            "forms": [
                (
                    "RF_Q_PM10RUNSTATUSCHECK",
                    {
                        "PM10CHECKTEMP1VALUE": "7281.3",
                        "PM10CHECKTEMP2VALUE": "7294.9",
                    },
                )
            ],
            "item": {
                "filename": "PM10原始值.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_Q_Pm10RunStatusCheck/pm10.jpg",
                "typecode": "RF_Q_Pm10RunStatusCheck",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []
    assert "MASS系数" in seen_prompt["text"]
    assert "PM10CHECKTEMP1VALUE" in seen_prompt["text"]
    assert "校准膜读数" in seen_prompt["text"]
    assert "1400/1404" in seen_prompt["text"]
    assert "只可作为 visible_values 记录" in seen_prompt["text"]


def test_pm_membrane_result_filename_forces_check_slot_when_model_returns_both(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_pm_membrane_photo": True,
                "original_value": 7294.9,
                "check_value": 7294.9,
                "visible_values": [
                    {"label": "MASS系数", "value": 7294.9},
                    {"label": "校准膜读数", "value": 1404},
                ],
                "confidence": 0.95,
                "reason": "模型同时填了两个槽位",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "CH2606041780581111441"},
            "forms": [
                (
                    "RF_Q_PM10RUNSTATUSCHECK",
                    {
                        "PM10CHECKTEMP1VALUE": "7281.3",
                        "PM10CHECKTEMP2VALUE": "7294.9",
                    },
                )
            ],
            "item": {
                "filename": "PM10膜片结果.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_Q_Pm10RunStatusCheck/pm10-result.jpg",
                "typecode": "RF_Q_Pm10RunStatusCheck",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_pm_temp_pressure_visual_rule_is_disabled(monkeypatch):
    def fail_if_extract_attachment_json_is_called(source, *, provider, task, prompt):
        raise AssertionError("PM temperature/pressure visual OCR should be disabled")

    monkeypatch.setattr(
        attachment_ocr_rules,
        "extract_attachment_json",
        fail_if_extract_attachment_json_is_called,
    )

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-PMPRESSURE"},
            "forms": [
                (
                    "RF_Q_PMPRESSURE",
                    {
                        "PM25CHECKTEMP1VALUE": "20.1",
                        "PM25CHECKTEMP2VALUE": "20.0",
                        "PM25CHECKPRES1VALUE": "99.8",
                        "PM25CHECKPRES2VALUE": "100.0",
                    },
                )
            ],
            "item": {
                "filename": "PM2.5温湿度气压仪器示值.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_Q_PMPRESSURE/pm25.jpg",
                "typecode": "RF_Q_PMPRESSURE",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []
