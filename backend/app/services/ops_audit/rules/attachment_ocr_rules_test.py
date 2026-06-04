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
