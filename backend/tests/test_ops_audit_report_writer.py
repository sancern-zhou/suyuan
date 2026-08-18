import json
from pathlib import Path

from app.services.ops_audit.report_writer import write_report


def test_write_report_only_keeps_issue_details(tmp_path: Path) -> None:
    audit = {
        "audit_info": {
            "generated_at": "2026-05-26 23:09:39",
            "rule_stage": "deterministic_with_common_pattern_postprocess",
            "order_count": 2,
        },
        "summary": {
            "audit_level_counts": {"通过": 1, "需补正": 1},
        },
        "records": [
            {
                "working_order_code": "WO-1",
                "station_id": "1007",
                "order_type": "Check",
                "maintenance_type": "Month",
                "audit_level": "需补正",
                "score": 82,
                "create_time": "2026-05-15 08:00:00",
                "scoring_issues": [
                    {
                        "rule_id": "RF_MISSING",
                        "severity": "高",
                        "assessment": "deterministic_issue",
                        "message": "检查/巡检类完工工单未找到 RF 表单",
                    },
                    {
                        "rule_id": "RF_AUDITOR_EMPTY",
                        "severity": "中",
                        "assessment": "common_pattern_pending_calibration",
                        "message": "表单审批人为空",
                    },
                ],
            },
            {
                "working_order_code": "WO-2",
                "station_id": "12",
                "order_type": "SupCheck",
                "maintenance_type": "Week",
                "audit_level": "通过",
                "score": 97,
                "create_time": "2026-05-19 20:00:00",
                "scoring_issues": [
                    {
                        "rule_id": "MAIN_CONTENT_EMPTY",
                        "severity": "低",
                        "assessment": "candidate_issue",
                        "message": "工单内容为低价值内容: '计划任务单'",
                    },
                    {
                        "rule_id": "RF_REVIEW_EMPTY",
                        "severity": "中",
                        "assessment": "candidate_issue",
                        "message": "表单复核人为空",
                    },
                    {
                        "rule_id": "ATTACHMENT_FLOW_VISUAL_DIAGNOSTIC",
                        "severity": "低",
                        "assessment": "technical_diagnostic",
                        "message": "流量照片视觉识别未执行成功",
                    },
                ],
            },
        ],
    }
    dataset = {
        "orders": [
            {"STATIONID": "1007", "DDWORKINGORDERTYPE": "Check", "MAINTENANCETYPE": "Month", "CREATETIME": "2026-05-15 08:00:00"},
            {"STATIONID": "12", "DDWORKINGORDERTYPE": "SupCheck", "MAINTENANCETYPE": "Week", "CREATETIME": "2026-05-19 20:00:00"},
        ],
        "details": [1, 2, 3],
        "rf_forms": {"RF_A": [1, 2], "RF_B": [1]},
        "attachments": [1, 2, 3, 4],
        "devices": [1],
        "wo_commonfile": [1, 2],
    }

    out_path = tmp_path / "report.md"
    write_report(audit, out_path, dataset=dataset)
    text = out_path.read_text(encoding="utf-8")

    assert "运维工单审核报告（2026-05-15 至 2026-05-19 创建）" in text
    assert "RF_MISSING" in text
    assert "检查/巡检类完工工单未找到 RF 表单" in text
    assert "MAIN_CONTENT_EMPTY" in text
    assert "通过" not in text
    assert "需补正" not in text
    assert "严重程度" not in text
    assert "RF_MISSING（高）" not in text
    assert "表单审批人为空" not in text
    assert "表单复核人为空" not in text
    assert "流量照片视觉识别未执行成功" not in text
    assert "整改建议" not in text
    assert "后续优化建议" not in text


def test_write_report_groups_final_issue_list_by_operation_unit(tmp_path: Path) -> None:
    audit = {
        "audit_info": {
            "generated_at": "2026-05-26 23:09:39",
            "rule_stage": "deterministic_with_semantic_review",
            "order_count": 2,
        },
        "summary": {"audit_level_counts": {"需补正": 2}},
        "records": [
            {"working_order_code": "WO-1", "create_time": "2026-05-15 08:00:00"},
            {"working_order_code": "WO-2", "create_time": "2026-05-16 08:00:00"},
        ],
    }
    final_issue_list = {
        "items": [
            {
                "operation_unit": "一厂运维",
                "station_name": "东城站",
                "station_id": "1551",
                "rf_form_name": "其他设备运行状况检查记录表（每周）",
                "working_order_code": "WO-1",
                "message": "城市摄影是否正常=0",
                "rule_id": "RF_ENUM_VALUE_INVALID",
            },
            {
                "operation_unit": "二厂运维",
                "station_name": "",
                "station_id": "1007",
                "rf_form_name": "",
                "working_order_code": "WO-2",
                "message": "RF表单缺失",
                "rule_id": "RF_MISSING",
            },
        ]
    }

    out_path = tmp_path / "report.md"
    write_report(audit, out_path, final_issue_list=final_issue_list)
    text = out_path.read_text(encoding="utf-8")

    assert "### 一厂运维" in text
    assert "1. 东城站、其他设备运行状况检查记录表（每周）、WO-1、城市摄影是否正常=0、RF_ENUM_VALUE_INVALID" in text
    assert "### 二厂运维" in text
    assert "1. 站点1007、未关联中文表单、WO-2、RF表单缺失、RF_MISSING" in text
    assert "WO-1 | 站点" not in text


def test_write_report_expands_device_identity_evidence_details(tmp_path: Path) -> None:
    audit = {
        "audit_info": {
            "generated_at": "2026-05-26 23:09:39",
            "rule_stage": "deterministic_with_semantic_review",
            "order_count": 1,
        },
        "summary": {"audit_level_counts": {"需补正": 1}},
        "records": [
            {"working_order_code": "WO-CURRENT", "create_time": "2026-05-20 08:00:00"},
        ],
    }
    final_issue_list = {
        "items": [
            {
                "operation_unit": "一厂运维",
                "station_name": "连山金山",
                "station_id": "1545",
                "rf_form_name": "颗粒物PM10/PM2.5自动监测分析仪运行状况检查记录表（每周）",
                "working_order_code": "WO-CURRENT",
                "message": "同设备跨工单型号不一致",
                "rule_id": "RF_DEVICE_IDENTITY_INCONSISTENT",
                "evidence": json.dumps(
                    {
                        "field": "model",
                        "current_value": "FH62C14",
                        "comparisons": [
                            {
                                "compare_order_code": "WO-HISTORY",
                                "compare_create_time": "2026-05-13 21:21:18",
                                "compare_table": "RF_W_PMCHECK",
                                "current_raw": "FH62C14",
                                "compare_raw": "SHARP5030",
                                "current_source": "rf_form.DEVICEMODEL",
                                "compare_source": "rf_form.DEVICEMODEL",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    }

    out_path = tmp_path / "report.md"
    write_report(audit, out_path, final_issue_list=final_issue_list)
    text = out_path.read_text(encoding="utf-8")

    assert "连山金山、颗粒物PM10/PM2.5自动监测分析仪运行状况检查记录表（每周）、WO-CURRENT" in text
    assert "对比工单WO-HISTORY（2026-05-13 21:21:18）" in text
    assert "当前值FH62C14" in text
    assert "历史值SHARP5030" in text
    assert "字段rf_form.DEVICEMODEL/rf_form.DEVICEMODEL" in text


def test_write_report_separates_value_abnormal_from_missing_explanation(tmp_path: Path) -> None:
    audit = {
        "audit_info": {
            "generated_at": "2026-08-15 10:00:00",
            "order_count": 1,
            "rule_stage": "deterministic_with_semantic_review",
        },
        "summary": {"audit_level_counts": {"有问题": 1}},
        "records": [{"working_order_code": "WO-SPLIT", "create_time": "2026-08-15 09:00:00"}],
    }
    final_issue_list = {
        "items": [
            {
                "operation_unit": "测试运维",
                "station_name": "测试站",
                "rf_form_name": "NOx周检表",
                "working_order_code": "WO-SPLIT",
                "rule_id": "RF_RANGE_OUT_OF_SPEC",
                "message": "参考PMT信号值0.002超出正常范围",
                "issue_component": "value_abnormal",
                "issue_group_id": "WO-SPLIT::RF_W_GASEOUSCHECK_NOX::PMTCHECKVALUE",
            },
            {
                "operation_unit": "测试运维",
                "station_name": "测试站",
                "rf_form_name": "NOx周检表",
                "working_order_code": "WO-SPLIT",
                "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                "message": "原备注仅写已处理，未说明与当前异常的具体关联",
                "issue_component": "abnormal_explanation_issue",
                "issue_group_id": "WO-SPLIT::RF_W_GASEOUSCHECK_NOX::PMTCHECKVALUE",
                "remark_status": "provided",
                "remark_judgment": "unrelated",
                "remark_judgment_label": "与当前异常无关",
                "original_remarks": [
                    {
                        "field": "EXCEPTIONHANDLINGRECORD",
                        "field_label": "异常时处理记录",
                        "value": "已处理，但未记录复测结果",
                    }
                ],
            },
        ]
    }

    out_path = tmp_path / "report.md"
    write_report(audit, out_path, final_issue_list=final_issue_list)
    text = out_path.read_text(encoding="utf-8")

    assert "#### 异常事实与说明对照" in text
    assert "异常事实（值异常）：参考PMT信号值0.002超出正常范围" in text
    assert "原备注（异常时处理记录/EXCEPTIONHANDLINGRECORD）：已处理，但未记录复测结果" in text
    assert "说明判断：与当前异常无关" in text
    assert "语义结论：原备注仅写已处理，未说明与当前异常的具体关联" in text


def test_write_report_marks_missing_original_remark(tmp_path: Path) -> None:
    audit = {
        "audit_info": {"generated_at": "2026-08-15 10:00:00", "order_count": 1, "rule_stage": "test"},
        "summary": {"audit_level_counts": {"有问题": 1}},
        "records": [{"working_order_code": "WO-NO-REMARK"}],
    }
    final_issue_list = {
        "items": [
            {
                "operation_unit": "测试运维",
                "station_name": "测试站",
                "rf_form_name": "SO2周检表",
                "working_order_code": "WO-NO-REMARK",
                "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                "message": "未提供与当前异常相关的说明",
                "issue_component": "abnormal_explanation_issue",
                "remark_status": "missing",
                "original_remarks": [],
            }
        ]
    }

    out_path = tmp_path / "report.md"
    write_report(audit, out_path, final_issue_list=final_issue_list)
    text = out_path.read_text(encoding="utf-8")

    assert "原备注：未填写" in text


def test_write_report_shows_range_decision_and_remark_status_without_semantic_result(
    tmp_path: Path,
) -> None:
    audit = {
        "audit_info": {"generated_at": "2026-08-17 10:00:00", "order_count": 1, "rule_stage": "test"},
        "summary": {"audit_level_counts": {"有问题": 1}},
        "records": [{"working_order_code": "CH2608031785736302900"}],
    }
    final_issue_list = {
        "items": [
            {
                "operation_unit": "罗定兴华",
                "station_name": "测试站",
                "rf_form_name": "氮氧化物（NOx）分析仪运行状况检查记录表（每周）",
                "working_order_code": "CH2608031785736302900",
                "rule_id": "RF_RANGE_OUT_OF_SPEC",
                "message": "NOx周检高压电源检查值(670mv，换算为0.67 V)超出ESA品牌正常范围(500-950 V)",
                "issue_component": "value_abnormal",
                "issue_group_id": "CH2608031785736302900::RF_W_GASEOUSCHECK_NOX::GYCHECKVALUE",
                "decision_evidence": {
                    "brand": "ESA",
                    "raw_value": "670mv",
                    "normalized_value": 0.67,
                    "normalized_unit": "V",
                    "unit_conversion_applied": True,
                    "expected_range": "500-950 V",
                    "comparison_result": "out_of_spec",
                },
                "remark_status": "provided",
                "remark_status_label": "已填写",
                "remark_review_status": "pending_semantic_review",
                "remark_review_status_label": "内容有效性待语义复核",
                "original_remarks": [
                    {
                        "field": "EXCEPTIONHANDLINGRECORD",
                        "field_label": "异常时处理记录",
                        "value": "已检查高压电源接线，待复测。",
                    }
                ],
            }
        ]
    }

    out_path = tmp_path / "report.md"
    write_report(audit, out_path, final_issue_list=final_issue_list)
    text = out_path.read_text(encoding="utf-8")

    assert "判定依据：原始值 670mv；换算值 0.67 V；ESA 品牌正常范围 500-950 V" in text
    assert "原备注（异常时处理记录/EXCEPTIONHANDLINGRECORD）：已检查高压电源接线，待复测。" in text
    assert "备注状态：已填写；内容有效性待语义复核" in text

    item = final_issue_list["items"][0]
    item.update(
        {
            "remark_status": "missing",
            "remark_status_label": "未填写",
            "remark_review_status": "missing",
            "remark_review_status_label": "未填写备注",
            "original_remarks": [],
            "original_remark_text": "",
        }
    )
    missing_path = tmp_path / "report-missing.md"
    write_report(audit, missing_path, final_issue_list=final_issue_list)
    missing_text = missing_path.read_text(encoding="utf-8")
    assert "原备注：未填写" in missing_text
    assert "备注状态：未填写" in missing_text
