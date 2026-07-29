import json

from app.services.ops_audit.final_issue_list import build_final_issue_list
from app.services.ops_audit.rules import attachment_ocr_rules
from app.services.ops_audit.semantic import reviewer


def test_manufacturer_filed_range_note_is_a_range_mismatch_explanation():
    assert reviewer._has_range_mismatch_explanation("厂家备案参数0-4.096V") is True


def test_generic_remark_review_is_per_issue_and_final_mapping_is_exact(monkeypatch):
    def issue(table, field, message, remark_candidates):
        return {
            "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
            "category": "异常说明问题",
            "severity": "高",
            "field": f"rf.{table}.remark",
            "message": message,
            "evidence": json.dumps(
                {
                    "working_order_code": "WO-MULTI",
                    "rf_table": table,
                    "reason_rule_id": "RF_RANGE_OUT_OF_SPEC",
                    "abnormal_field": f"rf.{table}.{field}",
                    "abnormal_message": message,
                    "remark_candidates": remark_candidates,
                    "needs_semantic_review": True,
                },
                ensure_ascii=False,
            ),
        }

    cleared_issue = issue(
        "RF_W_GASEOUSCHECK_NOX",
        "PMTCHECKVALUE",
        "NOx参考PMT信号值0.001超出通用范围",
        {"PMTCHECKROW": "厂家备案参数0-4.096V"},
    )
    confirmed_issue = issue(
        "RF_W_GASEOUSCHECK_SO2",
        "PMTCHECKVALUE",
        "SO2参考PMT信号值异常且未说明",
        {"REMARK": "正常"},
    )
    record = {
        "working_order_code": "WO-MULTI",
        "station_id": "ST-1",
        "station_name": "测试站",
        "order_type": "Check",
        "maintenance_type": "Week",
        "finish_time": "2026-07-10 12:00:00",
        "audit_level": "有问题",
        "workflow_steps": [],
        "rf_tables": ["RF_W_GASEOUSCHECK_NOX", "RF_W_GASEOUSCHECK_SO2"],
        "scoring_issues": [cleared_issue, confirmed_issue],
    }
    base_task = reviewer.build_semantic_review_tasks({"records": [record]})["tasks"][0]
    tasks = reviewer._expand_generic_remark_tasks([base_task])

    assert len(tasks) == 2
    assert len({task["review_item_id"] for task in tasks}) == 2
    assert all(len(task["evidence_summary"]["sample_issues"]) == 1 for task in tasks)

    pending_task = next(
        task for task in tasks
        if task["source_issue"]["field"] == "rf.RF_W_GASEOUSCHECK_SO2.remark"
    )

    def fake_call(prompt, text, *, context=None):
        payload = json.loads(text)
        assert [item["review_item_id"] for item in payload["items"]] == [pending_task["review_item_id"]]
        item = payload["items"][0]
        assert item["issue"]["rf_table"] == "RF_W_GASEOUSCHECK_SO2"
        assert item["issue"]["remark_candidates"] == {"REMARK": "正常"}
        return {
            "results": [
                {
                    "review_item_id": pending_task["review_item_id"],
                    "working_order_code": "WO-MULTI",
                    "is_complete": False,
                    "has_cause": False,
                    "has_action": False,
                    "has_result": False,
                    "problem_description": "SO2字段备注未解释该异常值。",
                    "confidence": 0.95,
                }
            ]
        }

    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", fake_call)
    results = reviewer._review_remark_tasks_batch(
        tasks,
        {"WO-MULTI": record},
        {"WO-MULTI": {"ORDERTITLE": "任务检查单"}},
        {},
        {"WO-MULTI": []},
    )

    assert len(results) == 2
    assert sorted(result["judgment"] for result in results.values()) == ["cleared", "confirmed_issue"]

    final = build_final_issue_list(
        {"records": [record]},
        {"results": list(results.values())},
    )
    assert final["issue_count"] == 1
    assert final["items"][0]["rf_table"] == "RF_W_GASEOUSCHECK_SO2"
    assert final["items"][0]["message"] == "SO2参考PMT信号值异常且未说明"


def test_generic_remark_review_expands_every_issue_beyond_summary_sample_limit():
    issues = []
    for index in range(9):
        issues.append(
            {
                "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                "field": f"rf.RF_W_GASEOUSCHECK_NOX.FIELD{index}",
                "message": f"异常项{index}",
                "evidence": json.dumps(
                    {
                        "rf_table": "RF_W_GASEOUSCHECK_NOX",
                        "abnormal_field": f"rf.RF_W_GASEOUSCHECK_NOX.FIELD{index}",
                        "remark_candidates": {"REMARK": ""},
                    },
                    ensure_ascii=False,
                ),
            }
        )
    record = {
        "working_order_code": "WO-NINE",
        "station_id": "ST-1",
        "order_type": "Check",
        "maintenance_type": "Week",
        "finish_time": "2026-07-10 12:00:00",
        "scoring_issues": issues,
    }

    base_task = reviewer.build_semantic_review_tasks({"records": [record]})["tasks"][0]
    expanded = reviewer._expand_generic_remark_tasks([base_task])

    assert len(expanded) == 9


def test_generic_remark_batch_failure_keeps_each_review_item_separate():
    tasks = [
        {
            "review_item_id": f"WO-FAIL::ITEM::{index}",
            "working_order_code": "WO-FAIL",
            "semantic_focus": ["RF_ABNORMAL_VALUE_NO_REMARK"],
            "evidence_summary": {"sample_issues": []},
        }
        for index in range(2)
    ]

    results = reviewer._fallback_semantic_results(
        tasks,
        {"WO-FAIL": {}},
        {"WO-FAIL": {}},
        "failed",
        RuntimeError("boom"),
    )

    assert set(results) == {"WO-FAIL::ITEM::0", "WO-FAIL::ITEM::1"}
    assert all(result["judgment"] == "needs_followup" for result in results.values())


def test_field_level_range_note_clears_abnormal_value_remark_review(monkeypatch):
    def fail_llm_call(*args, **kwargs):
        raise AssertionError("field-level range note should be handled before LLM review")

    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", fail_llm_call)
    audit = {
        "records": [
            {
                "working_order_code": "CH2606231782222662769",
                "station_id": "huilai",
                "order_type": "运维工单",
                "maintenance_type": "周检",
                "finish_time": "2026-06-23 12:00:00",
                "scoring_issues": [
                    {
                        "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                        "category": "异常值无备注说明",
                        "field": "RF_W_GASEOUSCHECK_NOX.CYYLCHECKVALUE",
                        "message": (
                            "RF表单存在异常/漏填/错配，需语义判断备注是否解释充分: "
                            "NOx周检采样压力检查值(988hpa)超出ESA品牌正常范围(408-610 mV)"
                        ),
                        "evidence": json.dumps(
                            {
                                "needs_semantic_review": True,
                                "reason_rule_id": "RF_RANGE_OUT_OF_SPEC",
                                "remark_candidates": {
                                    "REMARK": "更换泵零跨校准，质控合格",
                                    "CYYLCHECKROW": "表格范围有误，厂家实际参数范围是hpa",
                                },
                            },
                            ensure_ascii=False,
                        ),
                    }
                ],
            }
        ]
    }
    dataset = {
        "wo_working_order": [{"WORKINGORDERCODE": "CH2606231782222662769"}],
        "wo_working_order_detail": [],
        "rf_forms": {
            "RF_W_GASEOUSCHECK_NOX": [
                {
                    "WORKINGORDERCODE": "CH2606231782222662769",
                    "CYYLCHECKVALUE": "988hpa",
                    "CYYLCHECKROW": "表格范围有误，厂家实际参数范围是hpa",
                    "REMARK": "更换泵零跨校准，质控合格",
                }
            ]
        },
        "attachments": [],
        "wo_commonfile": [],
    }

    semantic = reviewer.build_semantic_review_results(audit, dataset)
    result = semantic["results"][0]

    assert result["judgment"] == "cleared"
    assert result["can_promote_to_final_issue"] is False
    assert result["remark_review"]["is_complete"] is True
    assert "厂家实际参数范围" in result["remark_review"]["remark"]
    assert build_final_issue_list(audit, semantic)["issue_count"] == 0


def test_final_issue_message_preserves_source_issue_and_adds_semantic_supplement():
    audit = {
        "records": [
            {
                "working_order_code": "WO1",
                "station_id": "station-1",
                "scoring_issues": [
                    {
                        "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                        "category": "异常值无备注说明",
                        "field": "RF_W_GASEOUSCHECK_NOX.CYYLCHECKVALUE",
                        "message": "需语义判断备注是否解释充分: 原始规则信息",
                        "evidence": json.dumps(
                            {
                                "needs_semantic_review": True,
                                "field": "CYYLCHECKVALUE",
                                "rf_table": "RF_W_GASEOUSCHECK_NOX",
                            },
                            ensure_ascii=False,
                        ),
                    }
                ],
            }
        ]
    }
    semantic = {
        "results": [
            {
                "working_order_code": "WO1",
                "judgment": "confirmed_issue",
                "can_promote_to_final_issue": True,
                "supported_rule_ids": ["RF_ABNORMAL_VALUE_NO_REMARK"],
                "confidence": 0.88,
                "remark_review": {
                    "problem_description": "字段备注未解释采样压力异常原因。",
                    "remark": "仅填写质控合格",
                },
                "evidence_summary": {"sample_issues": audit["records"][0]["scoring_issues"]},
            }
        ]
    }

    final_issues = build_final_issue_list(audit, semantic)

    assert final_issues["issue_count"] == 1
    item = final_issues["items"][0]
    assert item["message"] == "需语义判断备注是否解释充分: 原始规则信息"
    assert item["semantic_message"] == "字段备注未解释采样压力异常原因。"
    assert item["semantic_conclusion"] is None
    assert item["source"] == "semantic_review"


def test_final_issue_message_preserves_cutting_head_photo_reason():
    source_issue = {
        "rule_id": "RF_TW_REMARK_LOW_VALUE",
        "category": "备注信息不充分",
        "field": "rf.RF_TW_CleanCuttingHead.CleaningRemark",
        "message": "双周切割头清洗未识别到清洗照片，需语义复核备注说明是否合理",
        "evidence": json.dumps(
            {
                "working_order_code": "CH2606231782220143337",
                "rf_table": "RF_TW_CleanCuttingHead",
                "field": "CleaningRemark",
                "remark_candidates": {
                    "PM2.5": ["CleaningRemark=已清洗", "REMARK="],
                    "PM10": ["CleaningRemark=已清洗", "REMARK="],
                },
                "attachment_summary": [],
                "needs_semantic_review": True,
                "review_basis": "未识别到切割头清洗照片，需语义复核备注是否说明无照片或清洗证据不足的合理原因。",
            },
            ensure_ascii=False,
        ),
    }
    audit = {
        "records": [
            {
                "working_order_code": "CH2606231782220143337",
                "station_id": "1005",
                "station_name": "增城派潭",
                "scoring_issues": [source_issue],
            }
        ]
    }
    semantic = {
        "results": [
            {
                "working_order_code": "CH2606231782220143337",
                "judgment": "confirmed_issue",
                "can_promote_to_final_issue": True,
                "supported_rule_ids": ["RF_TW_REMARK_LOW_VALUE"],
                "confidence": 0.7,
                "remark_review": {
                    "problem_description": "备注未说明原因、处置措施、处理结果。",
                    "remark": "CleaningRemark=已清洗",
                },
                "evidence_summary": {"sample_issues": [source_issue]},
            }
        ]
    }

    final_issues = build_final_issue_list(audit, semantic)

    assert final_issues["issue_count"] == 1
    item = final_issues["items"][0]
    assert item["message"] == "双周切割头清洗未识别到清洗照片，需语义复核备注说明是否合理"
    assert item["semantic_message"] == (
        "双周切割头清洗未识别到清洗照片，备注仅说明已清洗，"
        "未提供照片缺失或清洗证据不足的合理说明。"
    )


def test_default_flow_visual_allowlist_skips_pm_temp_pressure_without_calling_model(monkeypatch):
    def fail_extract_attachment_json(*args, **kwargs):
        raise AssertionError("disabled PM temp/pressure visual rule should not call the vision model")

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fail_extract_attachment_json)

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
                        "PM25CHECKPRES1VALUE": "99.8",
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


def test_default_flow_visual_allowlist_suppresses_gas_display_mismatch(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"SO2": 0.9, "NO2": None, "CO": None, "O3": None},
                "measured_values": {"SO2": None, "NO2": None, "CO": None, "O3": None},
                "display_units": {"SO2": "L/min"},
                "measured_units": {},
                "unit": "L/min",
                "confidence": 0.95,
                "reason": "读取到SO2仪器显示流量",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-GAS"},
            "forms": [("RF_M_GASEOUSFLOWCHECK", {"DISPLAYVALUESO2": "0.6"})],
            "item": {
                "filename": "SO2显示值.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_M_GASEOUSFLOWCHECK/so2.jpg",
                "typecode": "RF_M_GASEOUSFLOWCHECK",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_monthly_measured_flow_lpm_decimal_matches_decimal_form_value(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"SO2": None, "NO2": None, "CO": None, "O3": None},
                "measured_values": {"SO2": 0.61, "NO2": None, "CO": None, "O3": None},
                "display_units": {"SO2": "", "NO2": "", "CO": "", "O3": ""},
                "measured_units": {"SO2": "LPM", "NO2": "", "CO": "", "O3": ""},
                "unit": "LPM",
                "confidence": 0.95,
                "reason": "SO2实测流量0.61 LPM",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "CH2606231782210180137"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "FLOWRANGSO2": "650±10%ml/min",
                        "MEASUREDVALUESO2": "0.61",
                    },
                )
            ],
            "item": {
                "filename": "SO2实测流量0.61.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_M_GASEOUSFLOWCHECK/so2.jpg",
                "typecode": "RF_M_GASEOUSFLOWCHECK",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_monthly_measured_flow_filename_pollutant_filters_misclassified_ocr_key(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"SO2": None, "NO2": None, "CO": None, "O3": None},
                "measured_values": {"SO2": None, "NO2": None, "CO": None, "O3": 0.52},
                "display_units": {"SO2": "", "NO2": "", "CO": "", "O3": ""},
                "measured_units": {"SO2": "", "NO2": "", "CO": "", "O3": "LPM"},
                "unit": "LPM",
                "confidence": 0.95,
                "reason": "模型误把NO实测照片归入O3",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "CH2606231782210180137"},
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "FLOWRANGNO2": "500±10%ml/min",
                        "MEASUREDVALUENO2": "0.52",
                        "FLOWRANGO3": "800±10%ml/min",
                        "MEASUREDVALUEO3": "0.85",
                    },
                )
            ],
            "item": {
                "filename": "NO实测流量0.52.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_M_GASEOUSFLOWCHECK/no.jpg",
                "typecode": "RF_M_GASEOUSFLOWCHECK",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert issues == []


def test_flow_visual_watermark_single_point_date_does_not_add_issue(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        assert "watermark_date" in prompt
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"SO2": None, "NO2": None, "CO": None, "O3": None},
                "measured_values": {"SO2": 0.61, "NO2": None, "CO": None, "O3": None},
                "display_units": {"SO2": "", "NO2": "", "CO": "", "O3": ""},
                "measured_units": {"SO2": "LPM", "NO2": "", "CO": "", "O3": ""},
                "unit": "LPM",
                "watermark_datetime": "2026-06-22 09:10:00",
                "watermark_date": "2026-06-22",
                "watermark_time": "09:10:00",
                "watermark_text": "2026-06-22 09:10 丰顺八乡山",
                "watermark_confidence": 0.96,
                "confidence": 0.95,
                "reason": "SO2实测流量0.61 LPM，水印日期清晰",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {
                "WORKINGORDERCODE": "WO-WATERMARK",
                "CREATETIME": "2026-06-23 08:00:00",
                "FINISHTIME": "2026-06-23 11:00:00",
            },
            "forms": [
                (
                    "RF_M_GASEOUSFLOWCHECK",
                    {
                        "CHECKDATE": "2026-06-23 09:00:00",
                        "MEASUREDVALUESO2": "0.61",
                    },
                )
            ],
            "item": {
                "filename": "SO2实测流量0.61.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_M_GASEOUSFLOWCHECK/so2.jpg",
                "typecode": "RF_M_GASEOUSFLOWCHECK",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert not any(issue.rule_id == "ATTACHMENT_FLOW_PHOTO_WATERMARK_TIME_MISMATCH" for issue in issues)


def test_flow_visual_watermark_ignores_order_time_when_rf_operation_time_missing(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_gas_flow_panel_photo": True,
                "display_values": {"SO2": None, "NO2": None, "CO": None, "O3": None},
                "measured_values": {"SO2": 0.61, "NO2": None, "CO": None, "O3": None},
                "measured_units": {"SO2": "LPM"},
                "unit": "LPM",
                "watermark_datetime": "2026-06-22 09:10:00",
                "watermark_date": "2026-06-22",
                "watermark_time": "09:10:00",
                "watermark_confidence": 0.96,
                "confidence": 0.95,
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {
                "WORKINGORDERCODE": "WO-WATERMARK-NO-RF-TIME",
                "CREATETIME": "2026-06-23 08:00:00",
                "FINISHTIME": "2026-06-23 11:00:00",
            },
            "forms": [("RF_M_GASEOUSFLOWCHECK", {"MEASUREDVALUESO2": "0.61"})],
            "item": {
                "filename": "SO2实测流量0.61.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_M_GASEOUSFLOWCHECK/so2.jpg",
                "typecode": "RF_M_GASEOUSFLOWCHECK",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert not any(issue.rule_id == "ATTACHMENT_FLOW_PHOTO_WATERMARK_TIME_MISMATCH" for issue in issues)


def test_flow_visual_watermark_single_point_time_does_not_add_issue(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_flow_calibration_photo": True,
                "before_flow": 16.7,
                "after_flow": None,
                "unit": "L/min",
                "watermark_datetime": "2026-06-23 14:30:00",
                "watermark_date": "2026-06-23",
                "watermark_time": "14:30:00",
                "watermark_confidence": 0.96,
                "confidence": 0.95,
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-WATERMARK-TIME"},
            "forms": [
                (
                    "RF_TW_PmFlowCalibrate",
                    {
                        "CHECKDATE": "2026-06-23 09:00:00",
                        "Prev_A": "16.7",
                    },
                )
            ],
            "item": {
                "filename": "PM10流量校准前.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_TW_PmFlowCalibrate/pm10.jpg",
                "typecode": "RF_TW_PmFlowCalibrate",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert not any(issue.rule_id == "ATTACHMENT_FLOW_PHOTO_WATERMARK_TIME_MISMATCH" for issue in issues)


def test_flow_visual_watermark_rf_createdate_does_not_add_issue(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_flow_calibration_photo": True,
                "before_flow": 16.7,
                "unit": "L/min",
                "watermark_datetime": "2026-06-23 14:30:00",
                "watermark_date": "2026-06-23",
                "watermark_time": "14:30:00",
                "watermark_confidence": 0.96,
                "confidence": 0.95,
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-WATERMARK-CREATEDATE"},
            "forms": [
                (
                    "RF_TW_PmFlowCalibrate",
                    {
                        "CHECKDATE": "2026-06-23 09:00:00",
                        "CREATEDATE": "2026-06-23 14:40:00",
                        "Prev_A": "16.7",
                    },
                )
            ],
            "item": {
                "filename": "PM10流量校准前.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_TW_PmFlowCalibrate/pm10.jpg",
                "typecode": "RF_TW_PmFlowCalibrate",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert not any(issue.rule_id == "ATTACHMENT_FLOW_PHOTO_WATERMARK_TIME_MISMATCH" for issue in issues)


def test_flow_visual_watermark_matches_checkdate_date_and_window_clock(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_flow_calibration_photo": True,
                "before_flow": 16.67,
                "unit": "L/min",
                "watermark_datetime": "2026-06-23 11:14:00",
                "watermark_date": "2026-06-23",
                "watermark_time": "11:14:00",
                "watermark_confidence": 0.96,
                "confidence": 0.95,
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "CH2606231782157230018"},
            "forms": [
                (
                    "RF_TW_PmFlowCalibrate",
                    {
                        "CHECKDATE": "2026-06-23 11:13:00",
                        "CheckSdt": "06 26 2026 11:13AM",
                        "CheckEdt": "06 26 2026 11:27AM",
                        "Prev_A": "16.68",
                    },
                )
            ],
            "item": {
                "filename": "PM10流量检查(仪器示值).jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_TW_PmFlowCalibratePM10/pm10.jpg",
                "typecode": "RF_TW_PmFlowCalibratePM10",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert not any(issue.rule_id == "ATTACHMENT_FLOW_PHOTO_WATERMARK_TIME_MISMATCH" for issue in issues)


def test_flow_visual_watermark_date_mismatch_adds_issue_even_when_clock_inside_window(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_flow_calibration_photo": True,
                "before_flow": 16.7,
                "unit": "L/min",
                "watermark_datetime": "2026-06-22 11:14:00",
                "watermark_date": "2026-06-22",
                "watermark_time": "11:14:00",
                "watermark_confidence": 0.96,
                "confidence": 0.95,
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-WATERMARK-DATE"},
            "forms": [
                (
                    "RF_TW_PmFlowCalibrate",
                    {
                        "CHECKDATE": "2026-06-23 11:13:00",
                        "CheckSdt": "06 26 2026 11:13AM",
                        "CheckEdt": "06 26 2026 11:27AM",
                        "Prev_A": "16.7",
                    },
                )
            ],
            "item": {
                "filename": "PM10流量校准前.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_TW_PmFlowCalibratePM10/pm10.jpg",
                "typecode": "RF_TW_PmFlowCalibratePM10",
                "types": ["photo"],
            },
        },
        issues,
    )

    watermark_issues = [
        issue for issue in issues if issue.rule_id == "ATTACHMENT_FLOW_PHOTO_WATERMARK_TIME_MISMATCH"
    ]
    assert len(watermark_issues) == 1
    evidence = json.loads(watermark_issues[0].evidence)
    assert evidence["mismatch_level"] == "date"
    assert evidence["check_date"] == "2026-06-23"


def test_flow_visual_watermark_window_requires_time_inside_range(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_flow_calibration_photo": True,
                "before_flow": 16.7,
                "unit": "L/min",
                "watermark_datetime": "2026-06-23 11:00:00",
                "watermark_date": "2026-06-23",
                "watermark_time": "11:00:00",
                "watermark_confidence": 0.96,
                "confidence": 0.95,
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {"WORKINGORDERCODE": "WO-WATERMARK-WINDOW"},
            "forms": [
                (
                    "RF_TW_PmFlowCalibrate",
                    {
                        "CHECKDATE": "2026-06-23 10:14:00",
                        "CheckSdt": "06 23 2026 10:00AM",
                        "CheckEdt": "06 23 2026 10:30AM",
                        "Prev_A": "16.7",
                    },
                )
            ],
            "item": {
                "filename": "PM10流量校准前.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_TW_PmFlowCalibrate/pm10.jpg",
                "typecode": "RF_TW_PmFlowCalibrate",
                "types": ["photo"],
            },
        },
        issues,
    )

    watermark_issues = [
        issue for issue in issues if issue.rule_id == "ATTACHMENT_FLOW_PHOTO_WATERMARK_TIME_MISMATCH"
    ]
    assert len(watermark_issues) == 1
    evidence = json.loads(watermark_issues[0].evidence)
    assert evidence["mismatch_level"] == "time_window"
    assert evidence["nearest_delta_minutes"] == 30


def test_flow_visual_watermark_low_confidence_does_not_add_issue(monkeypatch):
    def fake_extract_attachment_json(source, *, provider, task, prompt):
        return {
            "status": "success",
            "data": {
                "is_flow_calibration_photo": True,
                "before_flow": 16.7,
                "after_flow": None,
                "unit": "L/min",
                "watermark_date": "2026-06-22",
                "watermark_confidence": 0.5,
                "confidence": 0.95,
                "reason": "水印模糊",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.run_flow_visual_task(
        {
            "task_type": "flow_visual",
            "order": {
                "WORKINGORDERCODE": "WO-WATERMARK-LOW",
                "FINISHTIME": "2026-06-23 11:00:00",
            },
            "forms": [
                (
                    "RF_TW_PmFlowCalibrate",
                    {
                        "CHECKDATE": "2026-06-23 09:00:00",
                        "Prev_A": "16.7",
                    },
                )
            ],
            "item": {
                "filename": "PM10流量校准前.jpg",
                "source_path": "/WebFiles/NewFiles/Check/RF_TW_PmFlowCalibrate/pm10.jpg",
                "typecode": "RF_TW_PmFlowCalibrate",
                "types": ["photo"],
            },
        },
        issues,
    )

    assert not any(issue.rule_id == "ATTACHMENT_FLOW_PHOTO_WATERMARK_TIME_MISMATCH" for issue in issues)
