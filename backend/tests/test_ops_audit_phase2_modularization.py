from app.services.ops_audit.config import (
    load_attachment_requirements,
    load_rf_field_profiles,
    load_rule_catalog,
    review_stage_for_rule,
    rules_for_review_stage,
)
from app.services.ops_audit.evidence_builder import build_dataset_evidence
from app.services.ops_audit.rule_engine import run_rule_engine
from app.services.ops_audit.scoring import apply_rule_pattern_assessment, classify_rule_patterns
from app.services.ops_work_order_audit import list_ops_audit_rules
from app.services.ops_work_order_audit_engine import audit_dataset


def test_rule_catalog_is_loaded_from_modular_config():
    catalog = load_rule_catalog()
    listed = list_ops_audit_rules()

    assert catalog
    assert listed["rule_count"] == len(catalog)
    assert {rule["rule_id"] for rule in catalog} >= {
        "RF_CHECK_TIME_OUTSIDE_RANGE",
        "RF_ABNORMAL_VALUE_NO_REMARK",
    }
    assert "RF_PM_MEMBRANE_ERROR_MISMATCH" not in {rule["rule_id"] for rule in catalog}
    assert "RF_REVIEW_EMPTY" not in {rule["rule_id"] for rule in catalog}


def test_rf_field_profiles_are_config_driven():
    profiles = load_rf_field_profiles()

    assert "CHECKTIME" in profiles["check_time_fields"]
    assert "STARTTIME" in profiles["start_time_fields"]
    assert "ENDTIME" in profiles["end_time_fields"]
    assert "人员" in profiles["low_value_field_groups"]


def test_attachment_requirements_are_config_driven():
    requirements = load_attachment_requirements()

    assert requirements["requirements"]
    assert any(item["id"] == "MONTH_FLOW_CHECK_REPORT" for item in requirements["requirements"])
    assert "报告" in requirements["global_keywords"]["report"]


def test_rule_review_stages_separate_current_semantic_and_future_ocr():
    assert "RF_Q_PENDING_NO_REMARK" in rules_for_review_stage("semantic_remark")
    assert review_stage_for_rule("ATTACHMENT_REPORT_MISSING") == "future_ocr"
    assert review_stage_for_rule("ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH") == "flow_visual"
    assert review_stage_for_rule("ATTACHMENT_FLOW_VISUAL_DIAGNOSTIC") == "technical_diagnostic"
    assert review_stage_for_rule("RF_RANGE_UNIT_MISMATCH") == "technical_diagnostic"
    assert review_stage_for_rule("RF_MISSING") == "deterministic"


def test_scoring_keeps_technical_diagnostics_out_of_work_order_issues():
    records = [
        {
            "working_order_code": "WO-DIAGNOSTIC",
            "order_type": "Check",
            "issues": [
                {
                    "rule_id": "ATTACHMENT_FLOW_VISUAL_DIAGNOSTIC",
                    "category": "附件质量问题",
                    "severity": "低",
                    "message": "视觉识别未执行成功",
                },
                {
                    "rule_id": "RF_RANGE_UNIT_MISMATCH",
                    "category": "一致性问题",
                    "severity": "中",
                    "message": "检查值与配置范围单位不一致",
                },
            ],
        }
    ]

    patterns = classify_rule_patterns(records)
    apply_rule_pattern_assessment(records, patterns)

    assert records[0]["audit_level"] == ""
    assert records[0]["scoring_issues"] == []
    assert records[0]["technical_diagnostic_count"] == 2
    assert {
        issue["rule_id"] for issue in records[0]["technical_diagnostics"]
    } == {"ATTACHMENT_FLOW_VISUAL_DIAGNOSTIC", "RF_RANGE_UNIT_MISMATCH"}
    assert all(
        issue["assessment"] == "technical_diagnostic"
        for issue in records[0]["technical_diagnostics"]
    )


def test_scoring_marks_hard_rules_as_deterministic():
    records = [
        {
            "working_order_code": "WO-1",
            "order_type": "Check",
            "issues": [
                {
                    "rule_id": "RF_MISSING",
                    "category": "表单完整性",
                    "severity": "高",
                    "message": "missing",
                }
            ],
        }
    ]

    patterns = classify_rule_patterns(records)
    apply_rule_pattern_assessment(records, patterns)

    assert patterns["RF_MISSING"]["pattern_type"] == "deterministic_issue"
    assert records[0]["audit_level"] == "有问题"
    assert records[0]["scoring_issues"][0]["assessment"] == "deterministic_issue"


def test_review_user_empty_is_not_flagged():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-REVIEW",
                "STATIONID": "ST-1",
                "DEVICEID": "DEV-1",
                "CREATETIME": "2026-05-20 10:00:00",
                "FINISHTIME": "2026-05-20 11:00:00",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "MAINTENANCETYPE": "Week",
                "ORDERCONTENT": "weekly check",
            }
        ],
        "details": [
            {
                "WORKINGORDERCODE": "WO-REVIEW",
                "PROCESSSTEP": "CreateOrder",
                "PROCESSSTATUS": 1,
            },
            {
                "WORKINGORDERCODE": "WO-REVIEW",
                "PROCESSSTEP": "CheckOrder",
                "PROCESSSTATUS": 1,
            },
            {
                "WORKINGORDERCODE": "WO-REVIEW",
                "PROCESSSTEP": "Review",
                "PROCESSSTATUS": 1,
            },
        ],
        "devices": [],
        "attachments": [],
        "wo_commonfile": [],
        "rf_forms": {
            "RF_W_PMCHECK": [
                {
                    "WORKINGORDERCODE": "WO-REVIEW",
                    "REVIEWUSERID": "",
                    "AUDITORUSERID": "A-1",
                    "REMARK": "正常",
                }
            ]
        },
        "device_history": {"orders": [], "rf_forms": {}},
    }

    audit = audit_dataset(dataset)
    ids = {issue["rule_id"] for issue in audit["records"][0]["issues"]}

    assert "RF_REVIEW_EMPTY" not in ids


def test_device_identity_consistency_uses_history_evidence():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-CURRENT",
                "STATIONID": "ST-1",
                "DEVICEID": "DEV-1",
                "CREATETIME": "2026-05-20 10:00:00",
                "FINISHTIME": "2026-05-20 11:00:00",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "MAINTENANCETYPE": "Week",
                "ORDERCONTENT": "weekly check",
            }
        ],
        "details": [
            {
                "WORKINGORDERCODE": "WO-CURRENT",
                "PROCESSSTEP": "CreateOrder",
                "PROCESSSTATUS": 1,
            },
            {
                "WORKINGORDERCODE": "WO-CURRENT",
                "PROCESSSTEP": "CheckOrder",
                "PROCESSSTATUS": 1,
                "SUBMITREMARK": "完成设备检查",
            },
            {
                "WORKINGORDERCODE": "WO-CURRENT",
                "PROCESSSTEP": "Review",
                "PROCESSSTATUS": 1,
                "SUBMITREMARK": "复核通过",
            },
        ],
        "devices": [],
        "rf_forms": {
            "RF_W_GASEOUSCHECK_CO": [
                {
                    "WORKINGORDERCODE": "WO-CURRENT",
                    "DEVICEBRAND": "API",
                    "DEVICEMODEL": "T100",
                    "DEVICECODE": "CO-001",
                    "POLLUTANTTYPE": "CO",
                    "CYLLCHECKVALUE": "1.0",
                    "CYYLCHECKVALUE": "300",
                    "FYCHECKVALUE": "20",
                    "GSWDCHECKVALUE": "45",
                    "YLCHECKVALUE": "1.0",
                    "JGCHECKVALUE": "0",
                    "REMARK": "正常",
                }
            ]
        },
        "device_history": {
            "orders": [
                {
                    "WORKINGORDERCODE": "WO-HISTORY",
                    "STATIONID": "ST-1",
                    "DEVICEID": "DEV-1",
                    "CREATETIME": "2026-04-22 10:00:00",
                    "FINISHTIME": "2026-04-22 11:00:00",
                    "DDWORKINGORDERTYPE": "Check",
                    "DDWORKINGORDERSTATUS": "Finish",
                    "CURRENTWORKFLOWSTATUS": "Finish",
                    "MAINTENANCETYPE": "Month",
                    "ORDERCONTENT": "monthly check",
                }
            ],
            "rf_forms": {
                "RF_W_GASEOUSCHECK_CO": [
                    {
                        "WORKINGORDERCODE": "WO-HISTORY",
                        "DEVICEBRAND": "API",
                        "DEVICEMODEL": "T200",
                        "DEVICECODE": "CO-001",
                        "POLLUTANTTYPE": "CO",
                    }
                ]
            },
        },
    }

    audit = audit_dataset(dataset)
    current = audit["records"][0]
    device_issues = [
        issue
        for issue in current["issues"]
        if issue["rule_id"] == "RF_DEVICE_IDENTITY_INCONSISTENT"
    ]

    assert audit["summary"]["device_consistency_issue_count"] == 1
    assert device_issues
    assert device_issues[0]["field"] == "device_identity.model"
    assert "WO-HISTORY" in device_issues[0]["evidence"]
    assert "RF_DEVICE_IDENTITY_INCONSISTENT" in {
        issue["rule_id"] for issue in current["candidate_issues"]
    }
    assert "RF_DEVICE_IDENTITY_INCONSISTENT" not in {
        issue["rule_id"] for issue in current["deterministic_issues"]
    }


def _attachment_rule_dataset(attachments=None, wo_commonfile=None):
    return {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-ATTACH",
                "STATIONID": "ST-1",
                "DEVICEID": "DEV-1",
                "CREATETIME": "2026-05-20 10:00:00",
                "FINISHTIME": "2026-05-20 11:00:00",
                "PLANFINISHTIME": "2026-05-21 10:00:00",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "MAINTENANCETYPE": "Month",
                "ORDERCONTENT": "monthly flow check",
            }
        ],
        "details": [
            {
                "WORKINGORDERCODE": "WO-ATTACH",
                "PROCESSSTEP": "CreateOrder",
                "PROCESSSTATUS": 1,
            },
            {
                "WORKINGORDERCODE": "WO-ATTACH",
                "PROCESSSTEP": "CheckOrder",
                "PROCESSSTATUS": 1,
                "SUBMITREMARK": "完成月流量检查",
            },
            {
                "WORKINGORDERCODE": "WO-ATTACH",
                "PROCESSSTEP": "Review",
                "PROCESSSTATUS": 1,
                "SUBMITREMARK": "复核通过",
            },
        ],
        "devices": [],
        "attachments": attachments or [],
        "wo_commonfile": wo_commonfile or [],
        "rf_forms": {
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
        "device_history": {"orders": [], "rf_forms": {}},
    }


def test_attachment_required_missing_rule_uses_rf_and_maintenance_scope():
    audit = audit_dataset(_attachment_rule_dataset())
    record = audit["records"][0]

    attachment_issues = [
        issue
        for issue in record["issues"]
        if issue["rule_id"] == "ATTACHMENT_REQUIRED_MISSING"
    ]

    assert audit["summary"]["attachment_issue_count"] == 1
    assert audit["summary"]["attachment_review_candidate_count"] == 1
    assert record["attachment_review_required"] is True
    assert attachment_issues
    assert "MONTH_FLOW_CHECK_REPORT" in attachment_issues[0]["evidence"]


def test_attachment_required_missing_skips_not_applicable_device_records():
    dataset = _attachment_rule_dataset()
    dataset["orders"][0]["MAINTENANCETYPE"] = "HalfYear"
    dataset["rf_forms"] = {
        "RF_HY_VISIBILITYCALI": [
            {
                "WORKINGORDERCODE": "WO-ATTACH",
                "TEMP": "/",
                "REMARK": "站点无该设备",
            }
        ]
    }

    audit = audit_dataset(dataset)
    record = audit["records"][0]

    assert not any(issue["rule_id"] == "ATTACHMENT_REQUIRED_MISSING" for issue in record["issues"])


def test_attachment_report_missing_when_only_photo_is_uploaded():
    audit = audit_dataset(
        _attachment_rule_dataset(
            attachments=[
                {
                    "refid": "WO-ATTACH",
                    "filename": "现场照片.jpg",
                    "createdate": "2026-05-20 11:00:00",
                }
            ]
        )
    )
    record = audit["records"][0]

    assert record["attachment_count"] == 1
    assert any(issue["rule_id"] == "ATTACHMENT_REPORT_MISSING" for issue in record["issues"])
    assert not any(issue["rule_id"] == "ATTACHMENT_REQUIRED_MISSING" for issue in record["issues"])


def test_workflow_and_gas_type_rules_run_in_batch_audit():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-RULES",
                "STATIONID": "ST-1",
                "DEVICEID": "DEV-1",
                "CREATETIME": "2026-05-20 10:00:00",
                "FINISHTIME": "2026-05-20 11:00:00",
                "PLANFINISHTIME": "2026-05-20 12:00:00",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "MAINTENANCETYPE": "Week",
                "ORDERCONTENT": "weekly check",
            }
        ],
        "details": [
            {
                "WORKINGORDERCODE": "WO-RULES",
                "PROCESSSTEP": "CreateOrder",
                "PROCESSSTATUS": 1,
            },
            {
                "WORKINGORDERCODE": "WO-RULES",
                "PROCESSSTEP": "CheckOrder",
                "PROCESSSTATUS": 1,
                "SUBMITREMARK": "完成检查",
            },
        ],
        "devices": [],
        "rf_forms": {
            "RF_W_GASEOUSCHECK_CO": [
                {
                    "WORKINGORDERCODE": "WO-RULES",
                    "DEVICEBRAND": "THERMO",
                    "DEVICEMODEL": "T100",
                    "POLLUTANTTYPE": "NOX",
                    "DISPLAYVALUE": "",
                    "MEASUREVALUE": "",
                    "SENSORVALUE": "",
                    "CHECKTIME": "2026-05-20 13:00:00",
                    "STARTTIME": "2026-05-20 12:00:00",
                    "ENDTIME": "2026-05-20 14:00:00",
                }
            ]
        },
        "attachments": [],
        "wo_commonfile": [],
        "device_history": {"orders": [], "rf_forms": {}},
    }

    audit = audit_dataset(dataset)
    record = audit["records"][0]
    rule_ids = {issue["rule_id"] for issue in record["issues"]}

    assert "FLOW_NO_CREATE" not in rule_ids
    assert "FLOW_NO_CHECK" not in rule_ids
    assert "RF_RANGE_BY_GAS_TYPE_MISMATCH" in rule_ids
    assert "RF_RANGE_VALUE_MISSING" in rule_ids


def test_evidence_builder_creates_layered_bundle():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-EVIDENCE",
                "STATIONID": "ST-1",
                "DEVICEID": "DEV-1",
                "CREATETIME": "2026-05-20 10:00:00",
                "FINISHTIME": "2026-05-20 11:00:00",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "MAINTENANCETYPE": "Week",
                "ORDERCONTENT": "weekly check",
            }
        ],
        "details": [
            {"WORKINGORDERCODE": "WO-EVIDENCE", "PROCESSSTEP": "CreateOrder"},
            {"WORKINGORDERCODE": "WO-EVIDENCE", "PROCESSSTEP": "CheckOrder"},
        ],
        "rf_forms": {
            "RF_W_PMCHECK": [
                {
                    "WORKINGORDERCODE": "WO-EVIDENCE",
                    "DEVICEBRAND": "API",
                    "DEVICEMODEL": "T100",
                    "DISPLAYVALUE": "1.0",
                }
            ]
        },
        "attachments": [
            {"refid": "WO-EVIDENCE", "filename": "report.pdf", "createdate": "2026-05-20 12:00:00"}
        ],
        "wo_commonfile": [],
        "device_history": {"orders": [], "rf_forms": {}},
    }

    summary_bundle = build_dataset_evidence(dataset, evidence_level="summary")
    detail_bundle = build_dataset_evidence(dataset, evidence_level="detail")
    raw_bundle = build_dataset_evidence(dataset, evidence_level="raw")

    assert summary_bundle["summary"]["order_count"] == 1
    assert "structured_detail" not in summary_bundle
    assert detail_bundle["structured_detail"]["count"] == 1
    assert "raw_evidence" not in detail_bundle
    assert raw_bundle["raw_evidence"]["count"] == 1


def test_evidence_builder_splits_value_and_remark_evidence():
    dataset = {"orders": [], "details": [], "rf_forms": {}, "attachments": [], "wo_commonfile": []}
    value_issue = {
        "rule_id": "RF_RANGE_OUT_OF_SPEC",
        "field": "rf.RF_W_GASEOUSCHECK_NOX.PMTCHECKVALUE",
        "message": "参考PMT信号值0.002超出正常范围",
        "evidence": (
            '{"working_order_code":"WO-SPLIT","rf_table":"RF_W_GASEOUSCHECK_NOX",'
            '"out_of_spec_values":[{"field":"PMTCHECKVALUE","raw_value":"0.002"}]}'
        ),
    }
    remark_issue = {
        "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
        "field": "rf.RF_W_GASEOUSCHECK_NOX.remark",
        "message": "异常值未填写有效备注",
        "evidence": (
            '{"working_order_code":"WO-SPLIT","rf_table":"RF_W_GASEOUSCHECK_NOX",'
            '"reason_rule_id":"RF_RANGE_OUT_OF_SPEC",'
            '"abnormal_field":"rf.RF_W_GASEOUSCHECK_NOX.PMTCHECKVALUE",'
            '"remark_candidates":{"REMARK":""},"needs_semantic_review":true}'
        ),
    }
    audit = {
        "records": [
            {"working_order_code": "WO-SPLIT", "scoring_issues": [value_issue, remark_issue]}
        ]
    }

    bundle = build_dataset_evidence(dataset, audit=audit)

    issue_evidence = bundle["issue_evidence"]
    assert issue_evidence["component_counts"] == {
        "value_abnormal": 1,
        "abnormal_explanation_issue": 1,
    }
    value_item, remark_item = issue_evidence["items"]
    assert value_item["issue_group_id"] == remark_item["issue_group_id"]
    assert "value_evidence" in value_item and "remark_evidence" not in value_item
    assert "remark_evidence" in remark_item and "value_evidence" not in remark_item


def test_rule_engine_persists_audit_outputs(tmp_path):
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-RULE-ENGINE",
                "STATIONID": "ST-1",
                "DEVICEID": "DEV-1",
                "CREATETIME": "2026-05-20 10:00:00",
                "FINISHTIME": "2026-05-20 11:00:00",
                "PLANFINISHTIME": "2026-05-20 12:00:00",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "MAINTENANCETYPE": "Week",
                "ORDERCONTENT": "weekly check",
            }
        ],
        "details": [
            {"WORKINGORDERCODE": "WO-RULE-ENGINE", "PROCESSSTEP": "CreateOrder", "PROCESSSTATUS": 1},
            {"WORKINGORDERCODE": "WO-RULE-ENGINE", "PROCESSSTEP": "CheckOrder", "PROCESSSTATUS": 1},
        ],
        "rf_forms": {},
        "attachments": [],
        "wo_commonfile": [],
        "devices": [],
        "device_history": {"orders": [], "rf_forms": {}},
    }

    result = run_rule_engine(dataset, output_dir=tmp_path, persist_outputs=True, evidence_level="detail")

    assert result["success"] is True
    assert (tmp_path / "latest_finished_work_orders_deterministic_audit.json").exists()
    assert (tmp_path / "latest_finished_work_orders_semantic_candidates.json").exists()
    assert (tmp_path / "latest_finished_work_orders_final_issue_list.json").exists()
    assert "final_issue_list_path" in result
    assert result["summary"]["audit_level_counts"]
