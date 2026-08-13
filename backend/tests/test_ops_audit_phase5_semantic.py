from app.services.ops_audit.semantic.attachment_classifier import classify_attachment_metadata
from app.services.ops_audit.semantic.reviewer import build_semantic_review_tasks


def test_attachment_classifier_detects_photo_and_report_types():
    result = classify_attachment_metadata(
        "现场照片.jpg",
        filename="现场照片.jpg",
        global_keywords={
            "report": ["报告"],
            "photo": ["照片"],
        },
        photo_extensions=[".jpg"],
    )

    assert "photo" in result["types"]
    assert result["confidence_hint"] >= 0.7


def test_attachment_classifier_keeps_spaced_document_as_report():
    result = classify_attachment_metadata(
        "预防性维护报告 2026.7.14-15日.docx 无 /WebFiles/2026/7/report.docx",
        filename="预防性维护报告 2026.7.14-15日.docx",
        global_keywords={"report": ["报告"], "photo": ["现场", "照片"]},
        photo_extensions=[".jpg"],
    )

    assert result["types"] == ["report"]


def test_attachment_classifier_does_not_call_document_with现场_a_photo():
    result = classify_attachment_metadata(
        "现场维护记录 2026.docx",
        filename="现场维护记录 2026.docx",
        global_keywords={"report": ["记录"], "photo": ["现场"]},
        photo_extensions=[".jpg"],
    )

    assert result["types"] == ["report"]


def test_semantic_review_tasks_skip_inventory_only_attachment_rules():
    audit = {
        "records": [
            {
                "working_order_code": "WO-1",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Month",
                "finish_time": "2026-05-20 11:00:00",
                "audit_level": "需补正",
                "score": 82,
                "attachment_count": 1,
                "attachment_review_required": True,
                "attachment_review_rules": ["ATTACHMENT_REQUIRED_MISSING"],
                "workflow_steps": ["CreateOrder", "CheckOrder"],
                "rf_tables": ["RF_M_GASEOUSFLOWCHECK"],
                "scoring_issues": [
                    {
                        "rule_id": "ATTACHMENT_REQUIRED_MISSING",
                        "severity": "高",
                        "assessment": "deterministic_issue",
                        "message": "必需附件缺失",
                    }
                ],
            }
        ]
    }

    tasks = build_semantic_review_tasks(audit)

    assert tasks["task_count"] == 0


def test_semantic_review_tasks_skip_future_ocr_attachment_content_rules():
    audit = {
        "records": [
            {
                "working_order_code": "WO-1",
                "station_id": "ST-1",
                "order_type": "Check",
                "maintenance_type": "Month",
                "finish_time": "2026-05-20 11:00:00",
                "audit_level": "需补正",
                "score": 82,
                "attachment_count": 1,
                "attachment_review_required": True,
                "attachment_review_rules": ["ATTACHMENT_REPORT_MISSING"],
                "workflow_steps": ["CreateOrder", "CheckOrder"],
                "rf_tables": ["RF_M_GASEOUSFLOWCHECK"],
                "scoring_issues": [
                    {
                        "rule_id": "ATTACHMENT_REPORT_MISSING",
                        "severity": "高",
                        "assessment": "candidate_issue",
                        "message": "应上传报告但仅上传照片",
                    }
                ],
            }
        ]
    }

    tasks = build_semantic_review_tasks(audit)

    assert tasks["task_count"] == 0
