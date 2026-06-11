import json

from app.services.ops_audit.rules.attachment_rules import check_attachment_requirements


def test_multipoint_calibration_accepts_xlsx_as_report_without_report_keywords():
    issues = []

    check_attachment_requirements(
        {
            "WORKINGORDERCODE": "WO-XLSX-REPORT",
            "DDWORKINGORDERTYPE": "Check",
            "MAINTENANCETYPE": "Quarter",
        },
        [("RF_Q_GASEOUSMULTIPOINT_O3", {"WORKINGORDERCODE": "WO-XLSX-REPORT"})],
        [],
        [
            {
                "REFID": "WO-XLSX-REPORT",
                "TYPECODE": "RF_Q_GaseousMultipoint_O3",
                "FILENAME": "20260523.xlsx",
                "FILEPATH": "/WebFiles/NewFiles/20260523.xlsx",
            }
        ],
        issues,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "ATTACHMENT_REQUIRED_MISSING"
    assert issues[0].message == "多点校准曲线图缺失：curve"
    evidence = json.loads(issues[0].evidence)
    assert evidence["missing_types"] == ["curve"]
    assert evidence["type_counts"]["report"] == 1
