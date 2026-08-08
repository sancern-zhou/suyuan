from app.services.ops_work_order_audit_engine import audit_dataset
from app.services.ops_audit.semantic_candidates import build_semantic_candidates


def _base_order(code: str = "WO-1") -> dict:
    return {
        "WORKINGORDERCODE": code,
        "STATIONID": "ST-1",
        "DEVICEID": "DEV-1",
        "CREATETIME": "2026-05-20 10:00:00",
        "FINISHTIME": "2026-05-20 11:00:00",
        "PLANFINISHTIME": "2026-05-20 12:00:00",
        "DDWORKINGORDERTYPE": "Check",
        "DDWORKINGORDERSTATUS": "Finish",
        "CURRENTWORKFLOWSTATUS": "Finish",
        "MAINTENANCETYPE": "Week",
        "ORDERTITLE": "周检查",
        "ORDERCONTENT": "weekly check",
    }


def _base_dataset(order: dict, *, details=None, rf_forms=None, attachments=None, wo_commonfile=None, device_history=None):
    return {
        "orders": [order],
        "details": details or [],
        "rf_forms": rf_forms or {},
        "attachments": attachments or [],
        "wo_commonfile": wo_commonfile or [],
        "devices": [],
        "device_history": device_history or {"orders": [], "rf_forms": {}},
    }


def _issue_ids(audit: dict) -> set[str]:
    return {issue["rule_id"] for issue in audit["records"][0]["issues"]}


def test_main_order_and_workflow_rules_are_detected():
    order = {
        "WORKINGORDERCODE": "WO-MAIN",
        "STATIONID": "",
        "CREATETIME": "",
        "FINISHTIME": "",
        "DDWORKINGORDERTYPE": "Check",
        "DDWORKINGORDERSTATUS": "Pending",
        "ORDERTITLE": "",
        "ORDERCONTENT": "",
    }
    audit = audit_dataset(_base_dataset(order))
    ids = _issue_ids(audit)
    assert "MAIN_REQUIRED" in ids
    assert "MAIN_STATUS" in ids
    assert "MAIN_CONTENT_EMPTY" in ids
    assert "FLOW_MISSING" in ids


def test_workflow_step_rules_are_detected():
    order = _base_order("WO-FLOW")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-FLOW", "PROCESSSTEP": "CheckOrder"},
            ],
        )
    )
    ids = _issue_ids(audit)
    assert "FLOW_NO_CREATE" in ids
    assert "FLOW_NO_CHECK" not in ids


def test_rf_required_and_time_rules_are_detected():
    order = _base_order("WO-RF-TIME")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-RF-TIME", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-RF-TIME", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_PMCHECK": [
                    {
                        "WORKINGORDERCODE": "WO-RF-TIME",
                        "CHECKTIME": "2026-05-20 15:00:00",
                        "STARTTIME": "2026-05-20 12:00:00",
                        "ENDTIME": "2026-05-20 13:00:00",
                        "PERSON": "",
                        "CAR": "/",
                        "REMARK": "正常",
                        "INDOORTEMPERATURE": "",
                        "INDOORHUMIDITY": "",
                    }
                ]
            },
        )
    )
    ids = _issue_ids(audit)
    assert "RF_REQUIRED_FIELD_LOW_VALUE" in ids
    assert "RF_ENV_TEMP_HUMIDITY_EMPTY" in ids
    assert "RF_CHECK_TIME_OUTSIDE_RANGE" in ids


def test_rf_range_rules_are_detected():
    order = _base_order("WO-RF-RANGE")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-RF-RANGE", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-RF-RANGE", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_GASEOUSCHECK_CO": [
                    {
                        "WORKINGORDERCODE": "WO-RF-RANGE",
                        "DEVICEBRAND": "THERMO",
                        "DEVICEMODEL": "48i",
                        "DEVICECODE": "CO-001",
                        "POLLUTANTTYPE": "NOX",
                        "DISPLAYVALUE": "",
                        "MEASUREVALUE": "/",
                        "SENSORVALUE": None,
                    }
                ]
            },
        )
    )
    ids = _issue_ids(audit)
    assert "RF_RANGE_VALUE_MISSING" in ids
    assert "RF_RANGE_BY_GAS_TYPE_MISMATCH" in ids


def test_o3_weekly_brand_range_rules_use_structured_fields():
    order = _base_order("WO-O3-RANGE")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-O3-RANGE", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-O3-RANGE", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_GASEOUSCHECK_O3": [
                    {
                        "WORKINGORDERCODE": "WO-O3-RANGE",
                        "DEVICEBRAND": "FPI",
                        "DEVICEMODEL": "AQMS-300",
                        "DEVICECODE": "O3-001",
                        "POLLUTANTTYPE": "O3",
                        "GYCHECKVALUE": "1.2",
                        "GYBCHECKVALUE": "/",
                        "ZWDCHECKVALUE": "1.62",
                        "ZWDBCHECKVALUE": "/",
                        "CYYLCHECKVALUE": "12.5",
                        "CYLLCHECKVALUE": "850",
                        "CYLLBCHECKVALUE": "/",
                        "FYCHECKVALUE": "40",
                        "YLCHECKVALUE": "0.9062",
                        "JGCHECKVALUE": "0",
                    }
                ]
            },
        )
    )
    issues = audit["records"][0]["issues"]
    range_issues = [issue for issue in issues if issue["rule_id"] == "RF_RANGE_OUT_OF_SPEC"]
    assert len(range_issues) == 1
    assert range_issues[0]["field"] == "rf.RF_W_GASEOUSCHECK_O3.GYCHECKVALUE"
    assert "测量信号A" in range_issues[0]["message"]


def test_o3_weekly_brand_range_rules_accept_valid_values_and_blank_b_channel():
    order = _base_order("WO-O3-RANGE-OK")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-O3-RANGE-OK", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-O3-RANGE-OK", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_GASEOUSCHECK_O3": [
                    {
                        "WORKINGORDERCODE": "WO-O3-RANGE-OK",
                        "DEVICEBRAND": "API",
                        "DEVICEMODEL": "T400",
                        "DEVICECODE": "O3-002",
                        "POLLUTANTTYPE": "O3",
                        "GYCHECKVALUE": "3256.083mV",
                        "GYBCHECKVALUE": "/",
                        "ZWDCHECKVALUE": "3256.550",
                        "ZWDBCHECKVALUE": "/",
                        "CYYLCHECKVALUE": "25",
                        "CYLLCHECKVALUE": "850",
                        "CYLLBCHECKVALUE": "/",
                        "FYCHECKVALUE": "40",
                        "YLCHECKVALUE": "0.9062",
                        "JGCHECKVALUE": "0",
                    }
                ]
            },
        )
    )
    messages = [
        issue["message"]
        for issue in audit["records"][0]["issues"]
        if issue["rule_id"] == "RF_RANGE_OUT_OF_SPEC"
    ]
    assert not any("RF_W_GASEOUSCHECK_O3" in message for message in messages)


def test_o3_weekly_brand_range_rules_check_api_pressure():
    order = _base_order("WO-O3-API-PRESSURE")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-O3-API-PRESSURE", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-O3-API-PRESSURE", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_GASEOUSCHECK_O3": [
                    {
                        "WORKINGORDERCODE": "WO-O3-API-PRESSURE",
                        "DEVICEBRAND": "API",
                        "DEVICEMODEL": "T400",
                        "DEVICECODE": "O3-003",
                        "POLLUTANTTYPE": "O3",
                        "GYCHECKVALUE": "3256",
                        "ZWDCHECKVALUE": "3257",
                        "CYYLCHECKVALUE": "29",
                        "CYLLCHECKVALUE": "850",
                        "FYCHECKVALUE": "40",
                        "YLCHECKVALUE": "1.0",
                        "JGCHECKVALUE": "0",
                    }
                ]
            },
        )
    )
    pressure_issues = [
        issue
        for issue in audit["records"][0]["issues"]
        if issue["rule_id"] == "RF_RANGE_OUT_OF_SPEC"
        and issue["field"] == "rf.RF_W_GASEOUSCHECK_O3.CYYLCHECKVALUE"
    ]
    assert len(pressure_issues) == 1
    assert "压力" in pressure_issues[0]["message"]


def test_nox_weekly_brand_range_rules_use_structured_fields():
    order = _base_order("WO-NOX-RANGE")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-NOX-RANGE", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-NOX-RANGE", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_GASEOUSCHECK_NOX": [
                    {
                        "WORKINGORDERCODE": "WO-NOX-RANGE",
                        "DEVICEBRAND": "XH",
                        "DEVICEMODEL": "XHN2000",
                        "DEVICECODE": "NOX-001",
                        "POLLUTANTTYPE": "NOX",
                        "CYLLCHECKVALUE": "500",
                        "CYLLIANGCHECKVALUE": "85",
                        "PMTCHECKVALUE": "5100",
                        "GYCHECKVALUE": "630",
                        "FYCHECKVALUE": "50",
                        "ZHLCHECKVALUE": "316",
                        "FYSHICHECKVALUE": "20",
                        "CYYLCHECKVALUE": "90",
                        "NOXYLCHECKVALUE": "1",
                        "NOXJGCHECKVALUE": "1.36",
                        "NOYLCHECKVALUE": "0.963",
                        "NOJGCHECKVALUE": "-159",
                    }
                ]
            },
        )
    )
    range_issues = [
        issue
        for issue in audit["records"][0]["issues"]
        if issue["rule_id"] == "RF_RANGE_OUT_OF_SPEC"
    ]
    assert len(range_issues) == 1
    assert range_issues[0]["field"] == "rf.RF_W_GASEOUSCHECK_NOX.PMTCHECKVALUE"
    assert "参考PMT信号" in range_issues[0]["message"]


def test_nox_weekly_brand_range_rules_accept_valid_fpi_values():
    order = _base_order("WO-NOX-RANGE-OK")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-NOX-RANGE-OK", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-NOX-RANGE-OK", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_GASEOUSCHECK_NOX": [
                    {
                        "WORKINGORDERCODE": "WO-NOX-RANGE-OK",
                        "DEVICEBRAND": "FPI",
                        "DEVICEMODEL": "AQMS-600",
                        "DEVICECODE": "NOX-002",
                        "POLLUTANTTYPE": "NO2",
                        "CYLLCHECKVALUE": "604",
                        "CYLLIANGCHECKVALUE": "85",
                        "PMTCHECKVALUE": "1.62",
                        "GYCHECKVALUE": "630",
                        "FYCHECKVALUE": "50",
                        "ZHLCHECKVALUE": "316",
                        "FYSHICHECKVALUE": "3.7",
                        "CYYLCHECKVALUE": "14.8",
                        "NOXYLCHECKVALUE": "1",
                        "NOXJGCHECKVALUE": "1.36",
                        "NOYLCHECKVALUE": "0.963",
                        "NOJGCHECKVALUE": "0",
                    }
                ]
            },
        )
    )
    messages = [
        issue["message"]
        for issue in audit["records"][0]["issues"]
        if issue["rule_id"] == "RF_RANGE_OUT_OF_SPEC"
    ]
    assert not any("RF_W_GASEOUSCHECK_NOX" in message for message in messages)


def test_so2_weekly_brand_range_rules_use_structured_fields():
    order = _base_order("WO-SO2-RANGE")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-SO2-RANGE", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-SO2-RANGE", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_GASEOUSCHECK_SO2": [
                    {
                        "WORKINGORDERCODE": "WO-SO2-RANGE",
                        "DEVICEBRAND": "XH",
                        "DEVICEMODEL": "XHS2000",
                        "DEVICECODE": "SO2-001",
                        "POLLUTANTTYPE": "SO2",
                        "CYYLCHECKVALUE": "90",
                        "CYLLCHECKVALUE": "650",
                        "PMTCHECKVALUE": "5100",
                        "ZWDCHECKVALUE": "3.5",
                        "YLCHECKVALUE": "0.2",
                        "JGCHECKVALUE": "0.62",
                        "GYCHECKVALUE": "520",
                        "FYCHECKVALUE": "50",
                    }
                ]
            },
        )
    )
    range_issues = [
        issue
        for issue in audit["records"][0]["issues"]
        if issue["rule_id"] == "RF_RANGE_OUT_OF_SPEC"
    ]
    assert len(range_issues) == 1
    assert range_issues[0]["field"] == "rf.RF_W_GASEOUSCHECK_SO2.PMTCHECKVALUE"
    assert "参考PMT信号" in range_issues[0]["message"]


def test_so2_weekly_brand_range_rules_accept_valid_fpi_values():
    order = _base_order("WO-SO2-RANGE-OK")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-SO2-RANGE-OK", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-SO2-RANGE-OK", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_GASEOUSCHECK_SO2": [
                    {
                        "WORKINGORDERCODE": "WO-SO2-RANGE-OK",
                        "DEVICEBRAND": "FPI",
                        "DEVICEMODEL": "AQMS-500",
                        "DEVICECODE": "SO2-002",
                        "POLLUTANTTYPE": "SO2",
                        "CYYLCHECKVALUE": "13.4",
                        "CYLLCHECKVALUE": "680",
                        "PMTCHECKVALUE": "2.05",
                        "ZWDCHECKVALUE": "2.05",
                        "YLCHECKVALUE": "1.0554",
                        "JGCHECKVALUE": "0.6239",
                        "GYCHECKVALUE": "520",
                        "FYCHECKVALUE": "49.99789",
                    }
                ]
            },
        )
    )
    messages = [
        issue["message"]
        for issue in audit["records"][0]["issues"]
        if issue["rule_id"] == "RF_RANGE_OUT_OF_SPEC"
    ]
    assert not any("RF_W_GASEOUSCHECK_SO2" in message for message in messages)


def test_pm10_weekly_range_rules_use_structured_fields():
    order = _base_order("WO-PM10-RANGE")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-PM10-RANGE", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-PM10-RANGE", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_PMCHECK": [
                    {
                        "WORKINGORDERCODE": "WO-PM10-RANGE",
                        "DEVICEBRAND": "Thermo",
                        "DEVICEMODEL": "5014i",
                        "DEVICECODEN": "PM10-001",
                        "POLLUTANTTYPE": "PM10",
                        "MAINFLOWVALUE": "15.0",
                        "AIRTEMPVALUE": "45",
                        "REMARK": "",
                    }
                ]
            },
        )
    )
    range_issues = [
        issue
        for issue in audit["records"][0]["issues"]
        if issue["rule_id"] == "RF_RANGE_OUT_OF_SPEC"
    ]
    assert len(range_issues) == 1
    assert range_issues[0]["field"] == "rf.RF_W_PMCHECK.MAINFLOWVALUE"
    assert "流量(Main Flow)" in range_issues[0]["message"]


def test_pm10_blank_flow_with_remark_goes_to_semantic_review_candidate():
    order = _base_order("WO-PM10-RANGE-OK")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-PM10-RANGE-OK", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-PM10-RANGE-OK", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_PMCHECK": [
                    {
                        "WORKINGORDERCODE": "WO-PM10-RANGE-OK",
                        "DEVICEBRAND": "Thermo",
                        "DEVICEMODEL": "5014i",
                        "DEVICECODEN": "PM10-002",
                        "POLLUTANTTYPE": "PM10",
                        "MAINFLOWVALUE": "/",
                        "AIRTEMPVALUE": "50",
                        "REMARK": "本周无流量检查任务",
                    }
                ]
            },
        )
    )
    issues = audit["records"][0]["issues"]
    assert not any(
        issue["rule_id"] == "RF_RANGE_OUT_OF_SPEC" and issue["field"] == "rf.RF_W_PMCHECK.MAINFLOWVALUE"
        for issue in issues
    )
    semantic_issues = [
        issue
        for issue in audit["records"][0]["scoring_issues"]
        if issue["rule_id"] == "RF_ABNORMAL_VALUE_NO_REMARK"
        and issue["field"] == "rf.RF_W_PMCHECK.remark"
    ]
    assert len(semantic_issues) == 1
    assert semantic_issues[0]["assessment"] == "candidate_issue"
    assert "MAINFLOWVALUE" in semantic_issues[0]["evidence"]
    candidates = build_semantic_candidates(audit)
    assert candidates["candidate_count"] == 1
    assert candidates["candidates"][0]["semantic_focus"] == ["RF_ABNORMAL_VALUE_NO_REMARK"]


def test_range_out_of_spec_with_nonempty_remark_still_needs_semantic_review():
    order = _base_order("WO-O3-RANGE-REMARK")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-O3-RANGE-REMARK", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-O3-RANGE-REMARK", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_GASEOUSCHECK_O3": [
                    {
                        "WORKINGORDERCODE": "WO-O3-RANGE-REMARK",
                        "DEVICEBRAND": "FPI",
                        "DEVICEMODEL": "AQMS-300",
                        "POLLUTANTTYPE": "O3",
                        "GYCHECKVALUE": "1.2",
                        "ZWDCHECKVALUE": "1.62",
                        "CYYLCHECKVALUE": "12.5",
                        "CYLLCHECKVALUE": "850",
                        "FYCHECKVALUE": "40",
                        "YLCHECKVALUE": "0.9062",
                        "JGCHECKVALUE": "0",
                        "REMARK": "已处理",
                    }
                ]
            },
        )
    )
    semantic_issues = [
        issue
        for issue in audit["records"][0]["scoring_issues"]
        if issue["rule_id"] == "RF_ABNORMAL_VALUE_NO_REMARK"
        and issue["field"] == "rf.RF_W_GASEOUSCHECK_O3.remark"
    ]
    assert len(semantic_issues) == 1
    assert semantic_issues[0]["assessment"] == "candidate_issue"


def test_range_out_of_spec_with_handling_record_is_candidate_not_direct_deterministic():
    order = _base_order("WO-NOX-RANGE-HANDLING")
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-NOX-RANGE-HANDLING", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-NOX-RANGE-HANDLING", "PROCESSSTEP": "CheckOrder"},
            ],
            rf_forms={
                "RF_W_GASEOUSCHECK_NOX": [
                    {
                        "WORKINGORDERCODE": "WO-NOX-RANGE-HANDLING",
                        "DEVICEBRAND": "FPI",
                        "DEVICEMODEL": "AQMS-600",
                        "POLLUTANTTYPE": "NOX",
                        "PMTCHECKVALUE": "0.002",
                        "EXCEPTIONHANDLINGRECORD": "检查发现参考PMT偏低，已清洁光室并复测恢复正常。",
                    }
                ]
            },
        )
    )

    range_issues = [
        issue
        for issue in audit["records"][0]["scoring_issues"]
        if issue["rule_id"] == "RF_RANGE_OUT_OF_SPEC"
    ]
    assert len(range_issues) == 1
    assert range_issues[0]["assessment"] == "candidate_issue"
    assert "RF_RANGE_OUT_OF_SPEC" in audit["records"][0]["candidate_rules"]
    assert "RF_RANGE_OUT_OF_SPEC" not in audit["records"][0]["deterministic_rules"]


def test_lifecycle_attachment_and_device_rules_are_detected():
    order = _base_order("WO-ALL")
    order["FINISHTIME"] = "2026-05-20 10:20:00"
    order["MAINTENANCETYPE"] = "Month"
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-ALL", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-ALL", "PROCESSSTEP": "CheckOrder", "SUBMITREMARK": "完成"},
            ],
            rf_forms={
                "RF_M_GASEOUSFLOWCHECK": [
                    {
                        "WORKINGORDERCODE": "WO-ALL",
                        "DEVICEBRAND": "API",
                        "DEVICEMODEL": "T100",
                        "DEVICECODE": "FLOW-001",
                        "REMARK": "正常",
                    }
                ]
            },
            attachments=[],
            wo_commonfile=[],
            device_history={
                "orders": [
                    {
                        "WORKINGORDERCODE": "WO-HIS",
                        "STATIONID": "ST-1",
                        "DEVICEID": "DEV-1",
                        "CREATETIME": "2026-04-20 10:00:00",
                        "FINISHTIME": "2026-04-20 11:00:00",
                        "DDWORKINGORDERTYPE": "Check",
                        "DDWORKINGORDERSTATUS": "Finish",
                        "CURRENTWORKFLOWSTATUS": "Finish",
                        "MAINTENANCETYPE": "Week",
                        "ORDERTITLE": "周检查",
                        "ORDERCONTENT": "weekly check",
                    }
                ],
                "rf_forms": {
                    "RF_M_GASEOUSFLOWCHECK": [
                        {
                            "WORKINGORDERCODE": "WO-HIS",
                            "DEVICEBRAND": "API",
                            "DEVICEMODEL": "T200",
                            "DEVICECODE": "FLOW-001",
                            "REMARK": "正常",
                        }
                    ]
                },
            },
        )
    )
    ids = _issue_ids(audit)
    assert "LIFECYCLE_FINISH_WITHOUT_EFFECTIVE_CLOSURE" in ids
    assert "ATTACHMENT_REQUIRED_MISSING" in ids
    assert "RF_DEVICE_IDENTITY_INCONSISTENT" in ids


def test_attachment_report_only_photo_is_detected():
    order = _base_order("WO-ATTACH")
    order["MAINTENANCETYPE"] = "Month"
    audit = audit_dataset(
        _base_dataset(
            order,
            details=[
                {"WORKINGORDERCODE": "WO-ATTACH", "PROCESSSTEP": "CreateOrder"},
                {"WORKINGORDERCODE": "WO-ATTACH", "PROCESSSTEP": "CheckOrder"},
                {"WORKINGORDERCODE": "WO-ATTACH", "PROCESSSTEP": "Review"},
            ],
            rf_forms={
                "RF_M_GASEOUSFLOWCHECK": [
                    {
                        "WORKINGORDERCODE": "WO-ATTACH",
                        "DEVICEBRAND": "API",
                        "DEVICEMODEL": "T100",
                        "DEVICECODE": "FLOW-001",
                        "REMARK": "正常",
                    }
                ]
            },
            attachments=[
                {"refid": "WO-ATTACH", "filename": "现场照片.jpg", "createdate": "2026-05-20 11:00:00"}
            ],
        )
    )
    ids = _issue_ids(audit)
    assert "ATTACHMENT_REPORT_MISSING" in ids
