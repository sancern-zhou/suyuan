from app.services.ops_audit.rules.attachment_rules import check_attachment_requirements


def test_month_flow_check_report_missing_attachment_is_not_issue_when_sync_may_lag():
    issues = []

    check_attachment_requirements(
        {
            "WORKINGORDERCODE": "CH2606041780545777107",
            "DDWORKINGORDERTYPE": "Check",
            "MAINTENANCETYPE": "Month",
        },
        [("RF_M_GASEOUSFLOWCHECK", {"WORKINGORDERCODE": "CH2606041780545777107"})],
        [],
        [],
        issues,
    )

    assert issues == []


def test_two_week_pm_flow_check_report_missing_attachment_is_not_issue_when_sync_may_lag():
    issues = []

    check_attachment_requirements(
        {
            "WORKINGORDERCODE": "CH2606061780706161834",
            "DDWORKINGORDERTYPE": "Check",
            "MAINTENANCETYPE": "TwoWeek",
        },
        [("RF_TW_PmFlowCalibrate", {"WORKINGORDERCODE": "CH2606061780706161834"})],
        [],
        [],
        issues,
    )

    assert issues == []


def test_multipoint_calibration_missing_attachment_is_not_issue_when_sync_may_lag():
    issues = []

    check_attachment_requirements(
        {
            "WORKINGORDERCODE": "CH2606061780715418079",
            "DDWORKINGORDERTYPE": "Check",
            "MAINTENANCETYPE": "Quarter",
        },
        [("RF_Q_GASEOUSMULTIPOINT_O3", {"WORKINGORDERCODE": "CH2606061780715418079"})],
        [],
        [],
        issues,
    )

    assert issues == []


def test_multipoint_calibration_does_not_require_curve_attachment_when_report_exists():
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

    assert issues == []


def test_o3_value_pass_requires_dynamic_calibration_report():
    issues = []

    check_attachment_requirements(
        {
            "WORKINGORDERCODE": "WO-O3-MISSING-REPORT",
            "DDWORKINGORDERTYPE": "Check",
            "MAINTENANCETYPE": "Quarter",
        },
        [("RF_HY_O3VALUEPASS", {"WORKINGORDERCODE": "WO-O3-MISSING-REPORT"})],
        [],
        [],
        issues,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "ATTACHMENT_REQUIRED_MISSING"
    assert "O3动态校准仪量值传递报告" in issues[0].message


def test_o3_value_pass_report_accepts_xlsx_attachment():
    issues = []

    check_attachment_requirements(
        {
            "WORKINGORDERCODE": "WO-O3-XLS-REPORT",
            "DDWORKINGORDERTYPE": "Check",
            "MAINTENANCETYPE": "Quarter",
        },
        [("RF_HY_O3VALUEPASS", {"WORKINGORDERCODE": "WO-O3-XLS-REPORT"})],
        [],
        [
            {
                "REFID": "WO-O3-XLS-REPORT",
                "TYPECODE": "RF_HY_O3ValuePass",
                "FILENAME": "臭氧量值传递计算.xlsx",
                "FILEPATH": "/WebFiles/NewFiles/o3.xlsx",
            }
        ],
        issues,
    )

    assert issues == []


def test_visibility_calibration_attachment_requirement_allows_no_device_remark():
    issues = []

    check_attachment_requirements(
        {
            "WORKINGORDERCODE": "WO-NO-VISIBILITY",
            "DDWORKINGORDERTYPE": "Check",
            "MAINTENANCETYPE": "HalfYear",
        },
        [
            (
                "RF_HY_VISIBILITYCALI",
                {
                    "WORKINGORDERCODE": "WO-NO-VISIBILITY",
                    "TEMP": "/",
                    "DAMP": "/",
                    "REMARK": "站点无能见度分析仪。",
                },
            )
        ],
        [],
        [],
        issues,
    )

    assert issues == []
