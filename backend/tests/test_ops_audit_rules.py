"""Test cases for ops audit rules modules.

This module provides test examples for the new rule modules:
- workflow_rules.py
- rf_required_rules.py
- rf_time_rules.py
- rf_range_rules.py
- lifecycle_rules.py

The tests demonstrate how to use the rule checkers with sample data.
"""

from datetime import datetime

from app.services.ops_audit.rules import (
    check_workflow_completeness,
    check_lifecycle_closure,
    check_rf_calibration_dates,
    check_rf_required_fields,
    check_rf_enum_values,
    check_rf_time_ranges,
    check_rf_range_values,
)
from app.services.ops_work_order_audit_engine import audit_dataset
from app.services.ops_work_order_audit_engine import effective_audit_order_types
from app.services.ops_work_order_audit_engine import select_final_rf_form_versions


def test_audit_dataset_does_not_emit_main_order_rules():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-MAIN-SKIP",
                "STATIONID": "ST-1",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Doing",
                "ORDERTITLE": "任务检查单",
                "ORDERCONTENT": "",
                "CREATETIME": "2026-05-20 10:00:00",
                "FINISHTIME": "2026-05-19 10:00:00",
                "MAINTENANCETYPE": "Month",
                "DEVICEID": "",
            }
        ],
        "details": [],
        "attachments": [],
        "wo_commonfile": [],
        "rf_forms": {},
        "device_history": {"orders": [], "rf_forms": {}},
    }

    result = audit_dataset(dataset)

    rule_ids = {
        issue["rule_id"]
        for record in result["records"]
        for issue in record.get("scoring_issues", [])
    }
    assert not {rule_id for rule_id in rule_ids if rule_id.startswith("MAIN_")}


def test_audit_dataset_does_not_emit_rf_missing_when_rf_attachment_typecode_exists():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "CH2605201779246584195",
                "STATIONID": "1005",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "CREATETIME": "2026-05-20 11:09:44",
                "FINISHTIME": "2026-05-22 14:56:10",
                "MAINTENANCETYPE": "Quarter",
            }
        ],
        "details": [],
        "attachments": [],
        "wo_commonfile": [
            {
                "REFID": "CH2605201779246584195",
                "TYPECODE": "RF_Q_StationDeviceClean",
                "FILENAME": "清洁采样总管.jpg",
            }
        ],
        "rf_forms": {},
        "device_history": {"orders": [], "rf_forms": {}},
    }

    result = audit_dataset(dataset)

    record = result["records"][0]
    rule_ids = {issue["rule_id"] for issue in record.get("scoring_issues", [])}
    assert "RF_MISSING" not in rule_ids
    assert record["rf_attachment_typecodes"] == ["RF_Q_StationDeviceClean"]


def test_audit_dataset_clears_tw_cleaning_remark_when_cleaning_photo_exists():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-TW-CLEAN-PHOTO",
                "STATIONID": "ST-1",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "CREATETIME": "2026-05-20 09:20:05",
                "FINISHTIME": "2026-05-22 13:50:08",
                "MAINTENANCETYPE": "TwoWeek",
            }
        ],
        "details": [],
        "attachments": [
            {
                "refid": "WO-TW-CLEAN-PHOTO",
                "typecode": "RF_TW_CleanCuttingHeadPM10",
                "filename": "切割器清洁前.jpg",
            },
            {
                "refid": "WO-TW-CLEAN-PHOTO",
                "typecode": "RF_TW_CleanCuttingHeadPM10",
                "filename": "切割器清洁后.jpg",
            },
        ],
        "wo_commonfile": [],
        "rf_forms": {
            "RF_TW_CleanCuttingHead": [
                {
                    "WORKINGORDERCODE": "WO-TW-CLEAN-PHOTO",
                    "STATIONID": "ST-1",
                    "PollutantType": "PM10",
                    "PM_DeviceType": "PM10",
                    "CleaningRemark": "/",
                }
            ]
        },
        "device_history": {"orders": [], "rf_forms": {}},
    }

    result = audit_dataset(dataset)

    record = result["records"][0]
    rule_ids = {issue["rule_id"] for issue in record.get("scoring_issues", [])}
    assert "RF_TW_REMARK_LOW_VALUE" not in rule_ids
    assert "RF_REQUIRED_FIELD_LOW_VALUE" not in rule_ids


def test_audit_dataset_accepts_preventive_maintenance_report_without_photo():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "CH2606261782415508679",
                "STATIONID": "1477",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "CREATETIME": "2026-06-26 03:25:08",
                "FINISHTIME": "2026-07-02 14:14:28",
                "MAINTENANCETYPE": "Year",
            }
        ],
        "details": [],
        "attachments": [],
        "wo_commonfile": [
            {
                "REFID": "CH2606261782415508679",
                "TYPECODE": "RF_TW_PmFlowCheck",
                "FILENAME": "3-高栏南水站2026年预防性维护报告.docx",
                "FILEPATH": "/WebFiles/NewFiles/2026/6/26/Check/RF_TW_PmFlowCheck/1782488522498125400.docx",
            }
        ],
        "rf_forms": {
            "RF_Y_PreventiveMaintenance": [
                {
                    "WORKINGORDERCODE": "CH2606261782415508679",
                    "STATIONID": "1477",
                }
            ]
        },
        "device_history": {"orders": [], "rf_forms": {}},
    }

    result = audit_dataset(dataset)

    record = result["records"][0]
    preventive_attachment_issues = [
        issue
        for issue in record.get("scoring_issues", [])
        if issue["rule_id"] == "ATTACHMENT_REQUIRED_MISSING"
        and issue["field"] == "attachment.PREVENTIVE_MAINTENANCE_REPORT.missing"
    ]
    assert preventive_attachment_issues == []


def test_audit_dataset_reports_preventive_maintenance_attachment_when_report_and_photo_missing():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-PM-NO-ATTACHMENT",
                "STATIONID": "1477",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "CREATETIME": "2026-06-26 03:25:08",
                "FINISHTIME": "2026-07-02 14:14:28",
                "MAINTENANCETYPE": "Year",
            }
        ],
        "details": [],
        "attachments": [],
        "wo_commonfile": [],
        "rf_forms": {
            "RF_Y_PreventiveMaintenance": [
                {
                    "WORKINGORDERCODE": "WO-PM-NO-ATTACHMENT",
                    "STATIONID": "1477",
                }
            ]
        },
        "device_history": {"orders": [], "rf_forms": {}},
    }

    result = audit_dataset(dataset)

    record = result["records"][0]
    preventive_attachment_issues = [
        issue
        for issue in record.get("scoring_issues", [])
        if issue["rule_id"] == "ATTACHMENT_REQUIRED_MISSING"
        and issue["field"] == "attachment.PREVENTIVE_MAINTENANCE_REPORT.missing"
    ]
    assert len(preventive_attachment_issues) == 1


def test_audit_dataset_routes_tw_cleaning_without_photo_to_semantic_review():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-TW-CLEAN-NO-PHOTO",
                "STATIONID": "ST-1",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "CREATETIME": "2026-05-20 09:20:05",
                "FINISHTIME": "2026-05-22 13:50:08",
                "MAINTENANCETYPE": "TwoWeek",
            }
        ],
        "details": [],
        "attachments": [],
        "wo_commonfile": [],
        "rf_forms": {
            "RF_TW_CleanCuttingHead": [
                {
                    "WORKINGORDERCODE": "WO-TW-CLEAN-NO-PHOTO",
                    "STATIONID": "ST-1",
                    "PollutantType": "PM10",
                    "PM_DeviceType": "PM10",
                    "CleaningRemark": "因现场网络问题无法上传照片，已完成PM10切割头清洗。",
                }
            ]
        },
        "device_history": {"orders": [], "rf_forms": {}},
    }

    result = audit_dataset(dataset)

    record = result["records"][0]
    issues = [
        issue
        for issue in record.get("scoring_issues", [])
        if issue["rule_id"] == "RF_TW_REMARK_LOW_VALUE"
    ]
    assert len(issues) == 1
    assert issues[0]["assessment"] == "candidate_issue"
    assert "需语义复核" in issues[0]["message"]


def test_effective_audit_order_types_excludes_supcheck():
    assert effective_audit_order_types(None) is None
    assert effective_audit_order_types(["Check", "SupCheck"]) == ["Check"]
    assert effective_audit_order_types(["SupCheck"]) == []


def test_select_final_rf_form_versions_prefers_audited_records_and_deduplicates():
    forms = [
        {
            "RFWGASEOUSCHECKID": 78138,
            "WORKINGORDERCODE": "CH2605191779204167341",
            "CALIBRATIONDATE": "2026-05-20 00:00:00",
            "CDDATE": "2026-05-20 00:00:00",
            "YXQDATE": "2026-05-20 00:00:00",
            "REVIEWUSERID": "",
            "AUDITORUSERID": "",
        },
        {
            "RFWGASEOUSCHECKID": 78138,
            "WORKINGORDERCODE": "CH2605191779204167341",
            "CALIBRATIONDATE": "2026-05-20 00:00:00",
            "CDDATE": "2026-04-08 00:00:00",
            "YXQDATE": "2026-07-07 00:00:00",
            "REVIEWUSERID": "reviewer-1",
            "AUDITORUSERID": "auditor-1",
        },
        {
            "RFWGASEOUSCHECKID": 78138,
            "WORKINGORDERCODE": "CH2605191779204167341",
            "CALIBRATIONDATE": "2026-05-20 00:00:00",
            "CDDATE": "2026-04-08 00:00:00",
            "YXQDATE": "2026-07-07 00:00:00",
            "REVIEWUSERID": "reviewer-1",
            "AUDITORUSERID": "auditor-1",
        },
    ]

    selected = select_final_rf_form_versions("RF_W_GASEOUSCHECK_O3", forms)

    assert len(selected) == 1
    assert selected[0]["CDDATE"] == "2026-04-08 00:00:00"
    assert selected[0]["YXQDATE"] == "2026-07-07 00:00:00"
    assert selected[0]["AUDITORUSERID"] == "auditor-1"


def test_select_final_rf_form_versions_only_filters_duplicate_business_ids():
    forms = [
        {
            "RFWGASEOUSCHECKID": 1,
            "WORKINGORDERCODE": "WO-1",
            "YXQDATE": "2026-05-20 00:00:00",
            "AUDITORUSERID": "",
        },
        {
            "RFWGASEOUSCHECKID": 2,
            "WORKINGORDERCODE": "WO-2",
            "YXQDATE": "2026-05-21 00:00:00",
            "AUDITORUSERID": "auditor-2",
        },
        {
            "WORKINGORDERCODE": "WO-NO-ID",
            "YXQDATE": "2026-05-22 00:00:00",
            "AUDITORUSERID": "",
        },
    ]

    selected = select_final_rf_form_versions("RF_W_GASEOUSCHECK_O3", forms)

    assert selected == forms


def test_audit_dataset_flags_multipoint_range_change_against_device_history():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "CH_CURRENT",
                "STATIONID": "1001",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "CREATETIME": "2026-05-20 10:00:00",
                "FINISHTIME": "2026-05-20 12:00:00",
                "MAINTENANCETYPE": "Quarter",
            }
        ],
        "details": [],
        "attachments": [],
        "wo_commonfile": [],
        "rf_forms": {
            "RF_Q_GASEOUSMULTIPOINT_CO": [
                {
                    "WORKINGORDERCODE": "CH_CURRENT",
                    "STATIONID": "1001",
                    "CALIBRATIONDATE": "2026-05-20 10:00:00",
                    "POLLUTANTTYPE": "CO",
                    "PPB": 500,
                }
            ]
        },
        "device_history": {
            "orders": [
                {
                    "WORKINGORDERCODE": "CH_PREVIOUS",
                    "STATIONID": "1001",
                    "DDWORKINGORDERTYPE": "Check",
                    "CREATETIME": "2026-02-20 10:00:00",
                    "MAINTENANCETYPE": "Quarter",
                }
            ],
            "rf_forms": {
                "RF_Q_GASEOUSMULTIPOINT_CO": [
                    {
                        "WORKINGORDERCODE": "CH_PREVIOUS",
                        "STATIONID": "1001",
                        "CALIBRATIONDATE": "2026-02-20 10:00:00",
                        "POLLUTANTTYPE": "CO",
                        "PPB": 20000,
                    }
                ]
            },
        },
    }

    result = audit_dataset(dataset)

    rule_ids = {
        issue["rule_id"]
        for record in result["records"]
        for issue in record.get("scoring_issues", [])
    }
    assert "RF_MULTIPOINT_RANGE_INVALID" in rule_ids


def test_rf_enum_value_invalid_accepts_numeric_zero_for_allowed_boolean_fields():
    issues = []

    check_rf_enum_values(
        {"WORKINGORDERCODE": "WO-ENUM-ZERO"},
        [
            (
                "RF_W_OTHERDEVICECHECK",
                {
                    "WORKINGORDERCODE": "WO-ENUM-ZERO",
                    "IsOk1": 0,
                    "IsOk2": 0.0,
                    "IsOk3": "0",
                    "IsOk4": "0.0",
                },
            ),
            (
                "RF_TW_PmFlowCalibrate",
                {
                    "WORKINGORDERCODE": "WO-ENUM-ZERO",
                    "IsCalibrate": 0,
                },
            ),
        ],
        issues,
    )

    assert not any(issue.rule_id == "RF_ENUM_VALUE_INVALID" for issue in issues)


def test_rf_calibration_dates_records_next_field_in_violation():
    order = {
        "WORKINGORDERCODE": "CH202605260002",
        "CREATETIME": "2026-05-20 10:00:00",
    }
    forms = [
        (
            "RF_Q_GASEOUSMULTIPOINT_CO",
            {
                "CALIBRATIONDATE": "2026-05-20 10:00:00",
                "PPMCODEDATE": "2026-05-19 10:00:00",
            },
        )
    ]
    issues = []

    check_rf_calibration_dates(order, forms, issues)

    assert len(issues) == 1
    assert issues[0].rule_id == "RF_CALIBRATION_DATE_EXPIRED"
    assert issues[0].field == "rf.RF_Q_GASEOUSMULTIPOINT_CO.PPMCODEDATE"


def test_quarter_gaseous_flow_dynamic_calibrator_next_date_must_be_after_reference_time():
    order = {
        "WORKINGORDERCODE": "CH202605260003",
        "CREATETIME": "2026-05-20 10:00:00",
    }
    forms = [
        (
            "RF_Q_GaseousFlowCheck",
            {
                "WORKINGORDERCODE": "CH202605260003",
                "SdtTime": "2026-05-20 10:00:00",
                "D_CalibrateDatePrev": "2025-05-20 10:00:00",
                "D_CalibrateDateNext": "2026-05-20 10:00:00",
            },
        )
    ]
    issues = []

    check_rf_calibration_dates(order, forms, issues)

    assert len(issues) == 1
    assert issues[0].rule_id == "RF_CALIBRATION_DATE_EXPIRED"


def test_workflow_completeness():
    """Test workflow completeness rules."""
    print("\nTesting workflow completeness rules...")

    order = {
        "WORKINGORDERCODE": "CH202605260001",
        "STATIONID": "1001A",
        "DDWORKINGORDERTYPE": "Check",
    }

    # Test case 1: Missing workflow
    issues = []
    check_workflow_completeness(order, [], issues)
    print(f"  Missing workflow: {len(issues)} issues")
    for issue in issues:
        print(f"    - {issue.rule_id}: {issue.message}")

    # Test case 2: Workflow without create step
    workflow_no_create = [{
        "WORKFLOWID": "WF001",
        "steps": [
            {"NAME": "CheckOrder", "CREATETIME": "2026-05-26 10:00:00"},
        ]
    }]
    issues = []
    check_workflow_completeness(order, workflow_no_create, issues)
    print(f"  No create step: {len(issues)} issues")

    # Test case 3: Workflow without check step
    workflow_no_check = [{
        "WORKFLOWID": "WF002",
        "steps": [
            {"NAME": "CreateOrder", "CREATETIME": "2026-05-26 09:00:00"},
        ]
    }]
    issues = []
    check_workflow_completeness(order, workflow_no_check, issues)
    print(f"  No check step: {len(issues)} issues")


def test_rf_required_fields():
    """Test RF form required field rules."""
    print("\nTesting RF form required field rules...")

    order = {
        "WORKINGORDERCODE": "CH202605260001",
        "STATIONID": "1001A",
    }

    # Test case 1: Missing personnel and vehicle fields
    form_missing = {
        "WORKINGORDERCODE": "CH202605260001",
        "PERSON": "",  # Empty
        "CAR": "/",   # Low value
        "REMARK": "正常",  # Low value
        "INDOORTEMPERATURE": "",  # Missing temperature
        "INDOORHUMIDITY": "",  # Missing humidity
    }
    forms = [("RF_W_PMCHECK", form_missing)]
    issues = []
    check_rf_required_fields(order, forms, issues)
    print(f"  Missing/Low-value fields: {len(issues)} issues")
    for issue in issues:
        print(f"    - {issue.rule_id}: {issue.message}")


def test_rf_time_ranges():
    """Test RF form time range rules."""
    print("\nTesting RF form time range rules...")

    order = {
        "WORKINGORDERCODE": "CH202605260001",
        "STATIONID": "1001A",
        "CREATETIME": "2026-05-20 10:00:00",
        "PLANFINISHTIME": "2026-05-27 10:00:00",
        "FINISHTIME": "2026-05-27 09:45:00",  # Near deadline
    }

    # Test case 1: Check time outside range
    form_time_outside = {
        "WORKINGORDERCODE": "CH202605260001",
        "CHECKTIME": "2026-05-26 19:00:00",  # Outside range
        "STARTTIME": "2026-05-26 13:30:00",
        "ENDTIME": "2026-05-26 14:30:00",
    }
    forms = [("RF_W_PMCHECK", form_time_outside)]
    issues = []
    check_rf_time_ranges(order, forms, issues)
    print(f"  Time outside range: {len(issues)} issues")
    for issue in issues:
        print(f"    - {issue.rule_id}: {issue.message}")


def test_rf_range_values():
    """Test RF form range value rules."""
    print("\nTesting RF form range value rules...")

    order = {
        "WORKINGORDERCODE": "CH202605260001",
        "STATIONID": "1001A",
    }

    # Test case 1: Missing check values
    form_missing_values = {
        "WORKINGORDERCODE": "CH202605260001",
        "DEVICEBRAND": "THERMO",
        "DISPLAYVALUE": "",  # Missing
        "MEASUREVALUE": "/",  # Low value
        "SENSORVALUE": None,  # Missing
    }
    forms = [("RF_W_GASEOUSCHECK_CO", form_missing_values)]
    issues = []
    check_rf_range_values(order, forms, issues)
    print(f"  Missing range values: {len(issues)} issues")
    for issue in issues:
        print(f"    - {issue.rule_id}: {issue.message}")


def test_lifecycle_closure():
    """Test lifecycle closure rules."""
    print("\nTesting lifecycle closure rules...")

    # Test case 1: Order without effective closure
    order_no_closure = {
        "WORKINGORDERCODE": "CH202605260001",
        "STATIONID": "1001A",
        "DDWORKINGORDERTYPE": "Check",
        "MAINTENANCETYPE": "Week",
        "CREATETIME": "2026-05-27 09:00:00",
        "FINISHTIME": "2026-05-27 09:30:00",  # Only 30 min processing
        "PLANFINISHTIME": "2026-05-27 10:00:00",
    }

    workflows = [{
        "WORKFLOWID": "WF001",
        "steps": [
            {
                "NAME": "CreateOrder",
                "CREATETIME": "2026-05-27 09:00:00",
                "REMARK": "",
            },
            {
                "NAME": "CheckOrder",
                "CREATETIME": "2026-05-27 09:30:00",
                "REMARK": "完成",  # Low value remark
            },
        ]
    }]

    forms = [
        ("RF_W_PMCHECK", {
            "WORKINGORDERCODE": "CH202605260001",
            "DISPLAYVALUE": "0",  # Zero value
            "REMARK": "正常",  # Low value
        })
    ]

    issues = []
    check_lifecycle_closure(order_no_closure, workflows, forms, issues)
    print(f"  No effective closure: {len(issues)} issues")
    for issue in issues:
        print(f"    - {issue.rule_id}: {issue.message}")


def run_all_tests():
    """Run all test cases."""
    print("=" * 60)
    print("OPS AUDIT RULES MODULE TESTS")
    print("=" * 60)

    test_main_order_required()
    test_workflow_completeness()
    test_rf_required_fields()
    test_rf_time_ranges()
    test_rf_range_values()
    test_lifecycle_closure()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
