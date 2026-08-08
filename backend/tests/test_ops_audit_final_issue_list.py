from app.services.ops_audit.final_issue_list import build_final_issue_list


def test_final_issue_list_keeps_deterministic_and_promoted_remark_only():
    audit = {
        "records": [
            {
                "working_order_code": "WO-1",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "scoring_issues": [
                    {
                        "rule_id": "RF_MISSING",
                        "severity": "高",
                        "category": "表单完整性",
                        "field": "rf_forms",
                        "message": "RF表单缺失",
                    },
                    {
                        "rule_id": "FLOW_REMARK_LOW_VALUE",
                        "severity": "中",
                        "category": "流程备注",
                        "field": "SUBMITREMARK",
                        "message": "流程备注低价值",
                    },
                    {
                        "rule_id": "ATTACHMENT_REPORT_MISSING",
                        "severity": "高",
                        "category": "附件内容",
                        "field": "attachments",
                        "message": "报告附件缺失",
                    },
                    {
                        "rule_id": "RF_AUDITOR_EMPTY",
                        "severity": "低",
                        "category": "表单完整性",
                        "field": "AUDITORUSERID",
                        "message": "审核人为空",
                    },
                ],
            }
        ]
    }
    semantic_results = {
        "results": [
            {
                "working_order_code": "WO-1",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "can_promote_to_final_issue": True,
                "supported_rule_ids": ["FLOW_REMARK_LOW_VALUE"],
                "conclusion": "备注语义不完整，缺少原因、措施或结果。",
                "evidence_text": "计划任务单",
                "confidence": 0.82,
                "remark_review": {"problem_description": "备注未说明异常原因、处置措施和处理结果。"},
            }
        ]
    }

    result = build_final_issue_list(audit, semantic_results)

    rule_ids = {item["rule_id"] for item in result["items"]}
    assert rule_ids == {"RF_MISSING", "FLOW_REMARK_LOW_VALUE"}
    assert result["stage_counts"] == {"deterministic": 1, "semantic_remark": 1}
    assert all("suggestion" not in item for item in result["items"])
    assert all("severity" not in item for item in result["items"])
    semantic_item = next(item for item in result["items"] if item["rule_id"] == "FLOW_REMARK_LOW_VALUE")
    assert semantic_item["message"] == "备注未说明异常原因、处置措施和处理结果。"


def test_final_issue_list_does_not_directly_emit_semantic_review_range_issue():
    audit = {
        "records": [
            {
                "working_order_code": "WO-RANGE-SEMANTIC",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "scoring_issues": [
                    {
                        "rule_id": "RF_RANGE_OUT_OF_SPEC",
                        "severity": "高",
                        "category": "数值逻辑问题",
                        "field": "rf.RF_W_GASEOUSCHECK_NOX.PMTCHECKVALUE",
                        "message": "NOx周检参考PMT信号检查值(0.002)超出FPI品牌正常范围(1.5-4.096 V)",
                        "evidence": (
                            '{"working_order_code":"WO-RANGE-SEMANTIC","rf_table":"RF_W_GASEOUSCHECK_NOX",'
                            '"needs_semantic_review":true,'
                            '"handling_record_candidates":{"EXCEPTIONHANDLINGRECORD":"已清洁光室并复测恢复正常。"},'
                            '"out_of_spec_values":[{"field":"PMTCHECKVALUE","label":"参考PMT信号","raw_value":"0.002"}]}'
                        ),
                    },
                    {
                        "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                        "severity": "高",
                        "category": "异常说明问题",
                        "field": "rf.RF_W_GASEOUSCHECK_NOX.remark",
                        "message": "RF表单存在异常/漏填/错配，需语义判断备注是否解释充分: NOx周检参考PMT信号检查值(0.002)超出FPI品牌正常范围(1.5-4.096 V)",
                        "evidence": (
                            '{"working_order_code":"WO-RANGE-SEMANTIC","rf_table":"RF_W_GASEOUSCHECK_NOX",'
                            '"reason_rule_id":"RF_RANGE_OUT_OF_SPEC",'
                            '"abnormal_field":"rf.RF_W_GASEOUSCHECK_NOX.PMTCHECKVALUE",'
                            '"abnormal_message":"NOx周检参考PMT信号检查值(0.002)超出FPI品牌正常范围(1.5-4.096 V)",'
                            '"remark_candidates":{"EXCEPTIONHANDLINGRECORD":"已清洁光室并复测恢复正常。"},'
                            '"needs_semantic_review":true}'
                        ),
                    },
                ],
            }
        ]
    }
    semantic_results = {
        "results": [
            {
                "working_order_code": "WO-RANGE-SEMANTIC",
                "can_promote_to_final_issue": True,
                "supported_rule_ids": ["RF_ABNORMAL_VALUE_NO_REMARK"],
                "confidence": 0.91,
                "remark_review": {
                    "problem_description": "异常时处理记录只写已处理，未说明复测值是否恢复到正常范围。"
                },
                "evidence_summary": {
                    "sample_issues": [
                        audit["records"][0]["scoring_issues"][1],
                    ]
                },
            }
        ]
    }

    result = build_final_issue_list(audit, semantic_results)

    rule_ids = [item["rule_id"] for item in result["items"]]
    assert rule_ids == ["RF_ABNORMAL_VALUE_NO_REMARK"]
    assert result["items"][0]["rf_table"] == "RF_W_GASEOUSCHECK_NOX"
    assert result["items"][0]["message"] == "RF表单存在异常/漏填/错配，需语义判断备注是否解释充分: NOx周检参考PMT信号检查值(0.002)超出FPI品牌正常范围(1.5-4.096 V)"


def test_final_issue_list_excludes_main_order_rules():
    audit = {
        "records": [
            {
                "working_order_code": "WO-MAIN",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Month",
                "scoring_issues": [
                    {
                        "rule_id": "MAIN_CONTENT_EMPTY",
                        "severity": "中",
                        "category": "主表完整性",
                        "field": "ORDERCONTENT",
                        "message": "工单内容为空",
                    },
                    {
                        "rule_id": "MAIN_GENERIC_TITLE",
                        "severity": "低",
                        "category": "填报规范性",
                        "field": "ORDERTITLE",
                        "message": "工单标题过于泛化",
                    },
                ],
            }
        ]
    }
    semantic_results = {
        "results": [
            {
                "working_order_code": "WO-MAIN",
                "can_promote_to_final_issue": True,
                "supported_rule_ids": ["MAIN_CONTENT_EMPTY"],
                "conclusion": "工单主表描述不足。",
            }
        ]
    }

    result = build_final_issue_list(audit, semantic_results)

    assert result["issue_count"] == 0


def test_final_issue_list_hides_formula_mismatch_rules():
    audit = {
        "records": [
            {
                "working_order_code": "WO-FORMULA",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Month",
                "scoring_issues": [
                    {
                        "rule_id": "RF_VALUE_FORMULA_MISMATCH",
                        "severity": "高",
                        "category": "表单数值逻辑",
                        "field": "rf.RF_Q_GaseousFlowCheck.formula",
                        "message": "RF表单公式计算结果不一致",
                    }
                ],
            }
        ]
    }

    result = build_final_issue_list(audit)

    assert result["issue_count"] == 0


def test_final_issue_list_hides_semantic_abnormal_remark_from_formula_mismatch():
    audit = {
        "records": [
            {
                "working_order_code": "WO-FORMULA",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Month",
                "scoring_issues": [],
            }
        ]
    }
    semantic_results = {
        "results": [
            {
                "working_order_code": "WO-FORMULA",
                "can_promote_to_final_issue": True,
                "supported_rule_ids": ["RF_ABNORMAL_VALUE_NO_REMARK"],
                "evidence_summary": {
                    "sample_issues": [
                        {
                            "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                            "severity": "中",
                            "category": "结果合理性",
                            "field": "rf.RF_Q_GaseousFlowCheck.formula",
                            "message": "公式异常无有效说明",
                            "evidence": (
                                '{"reason_rule_id":"RF_VALUE_FORMULA_MISMATCH",'
                                '"abnormal_message":"RF表单公式计算结果不一致"}'
                            ),
                        }
                    ]
                },
            }
        ]
    }

    result = build_final_issue_list(audit, semantic_results)

    assert result["issue_count"] == 0


def test_final_issue_list_drops_remark_only_required_field_noise():
    audit = {
        "records": [
            {
                "working_order_code": "WO-2",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "scoring_issues": [
                    {
                        "rule_id": "RF_REQUIRED_FIELD_LOW_VALUE",
                        "severity": "中",
                        "category": "表单完整性",
                        "field": "REMARK",
                        "message": "必填字段低价值",
                        "evidence": '{"low_value_fields":["备注.REMARK=正常"]}',
                    }
                ],
            }
        ]
    }

    result = build_final_issue_list(audit)

    assert result["issue_count"] == 0


def test_final_issue_list_keeps_rf_table_and_record_context():
    issue_base = {
        "rule_id": "RF_RANGE_VALUE_MISSING",
        "severity": "中",
        "category": "规范性问题",
        "field": "rf.RF_W_PMCHECK.TAPEUSAGEDISPOSAL",
        "message": "颗粒物周检纸带使用量需复核",
    }
    audit = {
        "records": [
            {
                "working_order_code": "WO-3",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "scoring_issues": [
                    {
                        **issue_base,
                        "evidence": (
                            '{"working_order_code":"WO-3","rf_table":"RF_W_PMCHECK",'
                            '"pollutant_type":"PM10","field":"TAPEUSAGEDISPOSAL","value":""}'
                        ),
                    },
                    {
                        **issue_base,
                        "evidence": (
                            '{"working_order_code":"WO-3","rf_table":"RF_W_PMCHECK",'
                            '"pollutant_type":"PM2.5","field":"TAPEUSAGEDISPOSAL","value":""}'
                        ),
                    },
                ],
            }
        ]
    }

    result = build_final_issue_list(audit)

    assert result["issue_count"] == 2
    pollutant_types = {item["pollutant_type"] for item in result["items"]}
    assert pollutant_types == {"PM10", "PM2.5"}
    assert {item["rf_table"] for item in result["items"]} == {"RF_W_PMCHECK"}
    assert {item["rf_form_name"] for item in result["items"]} == {
        "颗粒物PM10/PM2.5自动监测分析仪运行状况检查记录表（每周）"
    }
    assert all(item["rf_record_key"] for item in result["items"])


def test_final_issue_list_uses_device_identity_rf_table_from_evidence():
    audit = {
        "records": [
            {
                "working_order_code": "WO-DEVICE",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "scoring_issues": [
                    {
                        "rule_id": "RF_DEVICE_IDENTITY_INCONSISTENT",
                        "severity": "中",
                        "category": "一致性问题",
                        "field": "device_identity.model",
                        "message": "同设备跨工单型号不一致",
                        "evidence": (
                            '{"working_order_code":"WO-DEVICE","rf_table":"RF_W_PMCHECK",'
                            '"field":"model","current_value":"FH62C14",'
                            '"comparisons":[{"compare_order_code":"WO-HISTORY",'
                            '"compare_table":"RF_W_PMCHECK","current_raw":"FH62C14",'
                            '"compare_raw":"SHARP5030"}]}'
                        ),
                    }
                ],
            }
        ]
    }

    result = build_final_issue_list(audit)

    assert result["issue_count"] == 1
    item = result["items"][0]
    assert item["rf_table"] == "RF_W_PMCHECK"
    assert item["rf_form_name"] == "颗粒物PM10/PM2.5自动监测分析仪运行状况检查记录表（每周）"
    assert item["rf_record_key"] == "WO-DEVICE::RF_W_PMCHECK::model"


def test_final_issue_list_uses_device_identity_compare_table_for_legacy_evidence():
    audit = {
        "records": [
            {
                "working_order_code": "WO-DEVICE",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "scoring_issues": [
                    {
                        "rule_id": "RF_DEVICE_IDENTITY_INCONSISTENT",
                        "severity": "中",
                        "category": "一致性问题",
                        "field": "device_identity.device_code",
                        "message": "同设备跨工单设备编号不一致",
                        "evidence": (
                            '{"current_order_code":"WO-DEVICE","field":"device_code",'
                            '"comparisons":[{"compare_order_code":"WO-HISTORY",'
                            '"compare_table":"RF_W_PMCHECK","current_raw":"CM-0706",'
                            '"compare_raw":"CM-0695"}]}'
                        ),
                    }
                ],
            }
        ]
    }

    result = build_final_issue_list(audit)

    item = result["items"][0]
    assert item["rf_table"] == "RF_W_PMCHECK"
    assert item["rf_form_name"] == "颗粒物PM10/PM2.5自动监测分析仪运行状况检查记录表（每周）"
    assert item["rf_record_key"] == "WO-DEVICE::RF_W_PMCHECK::device_code"


def test_final_issue_list_adds_semantic_rf_form_display_name():
    audit = {"records": []}
    semantic_results = {
        "results": [
            {
                "working_order_code": "WO-4",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "can_promote_to_final_issue": True,
                "supported_rule_ids": ["RF_PM_TAPE_USAGE_INVALID"],
                "rf_table": "RF_W_PMCHECK",
                "rf_field": "TAPEUSAGEDISPOSAL",
                "field": "rf.RF_W_PMCHECK.TAPEUSAGEDISPOSAL",
                "pollutant_type": "PM10",
                "field_label": "纸带使用量及处置情况",
                "conclusion": "纸带使用量字段填写不规范。",
                "evidence_text": "字段填写为“正常”。",
                "remark_review": {"problem_description": "字段只填写为空，无法判断纸带使用量或处置情况。"},
            }
        ]
    }

    result = build_final_issue_list(audit, semantic_results)

    assert result["issue_count"] == 1
    item = result["items"][0]
    assert item["rf_table"] == "RF_W_PMCHECK"
    assert item["rf_form_name"] == "颗粒物PM10/PM2.5自动监测分析仪运行状况检查记录表（每周）"
    assert "suggestion" not in item


def test_final_issue_list_preserves_rf_abnormal_no_remark_source_issue():
    source_evidence = (
        '{"working_order_code":"WO-ABNORMAL","rf_table":"RF_W_PMCHECK",'
        '"reason_rule_id":"RF_RANGE_OUT_OF_SPEC",'
        '"abnormal_field":"rf.RF_W_PMCHECK.TAPEUSAGEDISPOSAL",'
        '"abnormal_message":"纸带使用量超出正常范围",'
        '"remark_candidates":{"REMARK":""}}'
    )
    audit = {"records": []}
    semantic_results = {
        "results": [
            {
                "working_order_code": "WO-ABNORMAL",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Month",
                "can_promote_to_final_issue": True,
                "supported_rule_ids": ["RF_ABNORMAL_VALUE_NO_REMARK"],
                "conclusion": "备注语义不完整，缺少原因、措施或结果。",
                "evidence_text": "备注为空",
                "confidence": 0.86,
                "remark_review": {"problem_description": "工单备注无实质性内容，未说明原因、措施及结果。"},
                "evidence_summary": {
                    "sample_issues": [
                        {
                            "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                            "severity": "中",
                            "category": "结果合理性",
                            "field": "rf.RF_W_PMCHECK.remark",
                            "message": "RF表单存在异常/漏填/错配但无有效说明: 纸带使用量超出正常范围",
                            "evidence": source_evidence,
                        }
                    ]
                },
            }
        ]
    }

    result = build_final_issue_list(audit, semantic_results)

    assert result["issue_count"] == 1
    item = result["items"][0]
    assert item["rule_id"] == "RF_ABNORMAL_VALUE_NO_REMARK"
    assert item["message"].startswith("RF表单存在异常/漏填/错配但无有效说明")
    assert item["message"] != "备注语义不完整，缺少原因、措施或结果。"
    assert item["field"] == "rf.RF_W_PMCHECK.remark"
    assert item["rf_table"] == "RF_W_PMCHECK"
    assert item["evidence"] == source_evidence
    assert "suggestion" not in item


def test_final_issue_list_does_not_promote_rf_abnormal_without_source_issue():
    audit = {"records": []}
    semantic_results = {
        "results": [
            {
                "working_order_code": "WO-REMARK-ONLY",
                "can_promote_to_final_issue": True,
                "supported_rule_ids": ["RF_ABNORMAL_VALUE_NO_REMARK"],
                "conclusion": "备注语义不完整，缺少原因、措施或结果。",
                "evidence_summary": {"sample_issues": []},
            }
        ]
    }

    result = build_final_issue_list(audit, semantic_results)

    assert result["issue_count"] == 0


def test_final_issue_list_adds_operation_unit_from_audit_record_to_rule_and_semantic_items():
    audit = {
        "records": [
            {
                "working_order_code": "WO-UNIT",
                "station_id": "1551",
                "station_name": "东城站",
                "operation_unit": "东城运维组",
                "order_type": "Check",
                "maintenance_type": "Week",
                "scoring_issues": [
                    {
                        "rule_id": "RF_MISSING",
                        "severity": "高",
                        "category": "表单完整性",
                        "field": "rf_forms",
                        "message": "RF表单缺失",
                    }
                ],
            }
        ]
    }
    semantic_results = {
        "results": [
            {
                "working_order_code": "WO-UNIT",
                "can_promote_to_final_issue": True,
                "supported_rule_ids": ["FLOW_REMARK_LOW_VALUE"],
                "conclusion": "备注语义不完整。",
            }
        ]
    }

    result = build_final_issue_list(audit, semantic_results)

    assert result["issue_count"] == 2
    assert {item["operation_unit"] for item in result["items"]} == {"东城运维组"}
    assert {item["station_name"] for item in result["items"]} == {"东城站"}
