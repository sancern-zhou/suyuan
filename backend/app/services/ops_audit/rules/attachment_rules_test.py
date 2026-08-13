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

