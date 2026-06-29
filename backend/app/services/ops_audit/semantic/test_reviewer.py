import json

from app.services.ops_audit.final_issue_list import build_final_issue_list
from app.services.ops_audit.semantic import reviewer


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


def test_final_issue_message_uses_semantic_problem_description_for_source_issue():
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
    assert final_issues["items"][0]["message"] == "字段备注未解释采样压力异常原因。"


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
    assert final_issues["items"][0]["message"] == (
        "双周切割头清洗未识别到清洗照片，备注仅说明已清洗，"
        "未提供照片缺失或清洗证据不足的合理说明。"
    )
