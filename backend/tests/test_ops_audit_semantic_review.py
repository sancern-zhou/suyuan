from app.services.ops_audit.semantic import (
    build_semantic_review_tasks,
    check_attachment_value_consistency,
    check_photo_watermark,
    review_attachment_quality,
    review_remark_semantic,
)
from app.services.ops_audit.semantic import reviewer


def test_review_remark_semantic_uses_llm_json(monkeypatch):
    reviewer._SEMANTIC_CACHE.clear()
    monkeypatch.setattr(reviewer.llm_service, "base_url", "https://fake.example.com/v1")
    monkeypatch.setattr(reviewer.llm_service, "model", "configured-model")
    monkeypatch.setattr(
        reviewer,
        "_run_async_llm_json",
        lambda prompt: {
            "is_complete": True,
            "has_cause": True,
            "has_action": True,
            "has_result": True,
            "problem_description": "备注已说明设备异常原因、更换传感器措施和恢复正常结果。",
            "confidence": 0.91,
        },
    )

    result = review_remark_semantic("设备异常，已更换传感器，恢复正常")

    assert result["is_complete"] is True
    assert result["has_cause"] is True
    assert result["has_action"] is True
    assert result["has_result"] is True
    assert result["problem_description"] == "备注已说明设备异常原因、更换传感器措施和恢复正常结果。"
    assert "suggestion" not in result
    assert result["confidence"] == 0.91


def test_review_attachment_quality_heuristic_for_cert(monkeypatch):
    monkeypatch.setattr(reviewer, "extract_attachment_text", lambda *args, **kwargs: {
        "status": "success",
        "text": "封面",
        "confidence": 0.8,
    })
    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", lambda *args, **kwargs: None)

    result = review_attachment_quality("/tmp/cert.pdf", "cert")

    assert result["is_complete"] is False
    assert any("证书只附封面" in issue for issue in result["issues"])


def test_check_photo_watermark_detects_date(monkeypatch):
    monkeypatch.setattr(reviewer, "extract_attachment_text", lambda *args, **kwargs: {
        "status": "success",
        "text": "现场照片 2026-05-26 10:30",
        "confidence": 0.85,
    })

    result = check_photo_watermark("/tmp/photo.jpg")

    assert result["has_watermark"] is True
    assert result["has_date"] is True
    assert result["date_text"] == "2026-05-26"


def test_check_attachment_value_consistency_matches_numeric(monkeypatch):
    monkeypatch.setattr(reviewer, "extract_attachment_text", lambda *args, **kwargs: {
        "status": "success",
        "text": "读数 123.45",
        "confidence": 0.85,
    })

    result = check_attachment_value_consistency("/tmp/photo.jpg", "123.45")

    assert result["is_consistent"] is True
    assert result["difference"] == 0.0


def test_build_semantic_review_tasks_includes_stage5_rules():
    audit = {
        "records": [
            {
                "working_order_code": "WO-1",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "finish_time": "2026-05-26 10:00:00",
                "audit_level": "需补正",
                "score": 72,
                "attachment_count": 1,
                "attachment_review_rules": ["ATTACHMENT_CERT_INCOMPLETE"],
                "workflow_steps": ["CreateOrder", "CheckOrder"],
                "rf_tables": ["RF_W_PMCHECK"],
                "scoring_issues": [
                    {
                        "rule_id": "REMARK_SEMANTIC_INCOMPLETE",
                        "severity": "高",
                        "assessment": "candidate_issue",
                    }
                ],
                "issues": [
                    {
                        "rule_id": "REMARK_SEMANTIC_INCOMPLETE",
                        "severity": "高",
                        "assessment": "candidate_issue",
                        "message": "remark incomplete",
                    }
                ],
            }
        ]
    }

    result = build_semantic_review_tasks(audit)

    assert result["task_count"] == 1
    assert result["tasks"][0]["review_kind"] == "remark_semantics"
    assert "REMARK_SEMANTIC_INCOMPLETE" in result["tasks"][0]["semantic_focus"]


def test_main_content_empty_is_no_longer_semantic_reviewed(monkeypatch):
    monkeypatch.setattr(
        reviewer,
        "_call_semantic_llm_json",
        lambda *args, **kwargs: {
            "results": [
                {
                    "working_order_code": "CH2605211779354539935",
                    "is_sufficient": True,
                    "has_task_object": True,
                    "has_task_type": True,
                    "reason": "工单类型、周期和RF表已表明这是周检计划任务。",
                    "problem_description": "主表描述较泛化，但工单类型、周期和RF表已表明这是周检计划任务。",
                    "confidence": 0.88,
                }
            ]
        },
    )

    audit = {
        "records": [
            {
                "working_order_code": "CH2605211779354539935",
                "station_id": "12",
                "order_type": "SupCheck",
                "maintenance_type": "Week",
                "finish_time": "2026-05-21 10:00:00",
                "audit_level": "需语义复核",
                "score": 85,
                "attachment_count": 0,
                "workflow_steps": ["CreateOrder"],
                "rf_tables": ["RF_W_OTHERDEVICECHECK"],
                "scoring_issues": [
                    {
                        "rule_id": "MAIN_CONTENT_EMPTY",
                        "severity": "低",
                        "assessment": "candidate_issue",
                        "message": "工单内容为低价值内容: '计划任务单'",
                    }
                ],
            }
        ]
    }
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "CH2605211779354539935",
                "ORDERTITLE": "计划任务单",
                "ORDERCONTENT": "计划任务单",
                "DDWORKINGORDERTYPE": "SupCheck",
                "MAINTENANCETYPE": "Week",
            }
        ],
        "details": [{"WORKINGORDERCODE": "CH2605211779354539935", "STEPNAME": "创建工单"}],
        "rf_forms": {
            "RF_W_OTHERDEVICECHECK": [{"WORKINGORDERCODE": "CH2605211779354539935"}],
        },
    }

    results = reviewer.build_semantic_review_results(audit, dataset)

    assert results["result_count"] == 0


def test_build_semantic_review_tasks_excludes_deterministic_high_severity_rules():
    audit = {
        "records": [
            {
                "working_order_code": "WO-HARD",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Month",
                "finish_time": "2026-05-26 10:00:00",
                "audit_level": "确定性规则问题",
                "score": 60,
                "attachment_count": 0,
                "attachment_review_rules": [],
                "workflow_steps": ["CreateOrder", "CheckOrder"],
                "rf_tables": [],
                "scoring_issues": [
                    {
                        "rule_id": "RF_MISSING",
                        "severity": "高",
                        "assessment": "deterministic_issue",
                    },
                    {
                        "rule_id": "RF_VALUE_FORMULA_MISMATCH",
                        "severity": "高",
                        "assessment": "deterministic_issue",
                    },
                    {
                        "rule_id": "RF_REQUIRED_FIELD_LOW_VALUE",
                        "severity": "中",
                        "assessment": "candidate_issue",
                    },
                ],
            }
        ]
    }

    result = build_semantic_review_tasks(audit)

    assert result["task_count"] == 0
