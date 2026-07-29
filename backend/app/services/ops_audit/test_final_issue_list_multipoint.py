import json

from app.services.ops_audit.final_issue_list import build_final_issue_list


def test_final_issue_list_exposes_multipoint_image_evidence_fields():
    evidence = {
        "rf_table": "RF_Q_GASEOUSMULTIPOINT_O3",
        "pollutant_type": "O3",
        "report_classification": "疑似问题待人工复核",
        "needs_manual_review": True,
        "attachment_filename": "O3多点曲线.jpg",
        "attachment_local_path": "/abs/evidence/CH1/O3/O3多点曲线.jpg",
        "attachment_original_path": "/WebFiles/NewFiles/2026/5/14/curve.jpg",
        "attachment_url": "http://example.test/curve.jpg",
        "reason_code": "GRADIENT_MISMATCH",
        "reason": "曲线梯度与表单浓度不一致。",
        "observed_summary": "仅有3个平台。",
        "form_concentrations": [90, 160, 240, 320, 410],
        "concentration_unit": "ppb",
    }
    issue = {
        "rule_id": "ATTACHMENT_MULTIPOINT_GRADIENT_REVIEW",
        "category": "附件质量问题",
        "severity": "中",
        "field": "attachment.multipoint_curve.o3",
        "message": "疑似问题待人工复核：曲线梯度与表单浓度不一致。",
        "evidence": json.dumps(evidence, ensure_ascii=False),
    }
    audit = {
        "records": [
            {
                "working_order_code": "CH1",
                "station_id": "1001",
                "station_name": "测试站",
                "operation_unit": "测试单位",
                "order_type": "Check",
                "maintenance_type": "Quarter",
                "scoring_issues": [issue],
            }
        ]
    }

    result = build_final_issue_list(audit, {})

    item = result["items"][0]
    assert item["report_classification"] == "疑似问题待人工复核"
    assert item["needs_manual_review"] is True
    assert item["attachment_filename"] == "O3多点曲线.jpg"
    assert item["attachment_local_path"] == "/abs/evidence/CH1/O3/O3多点曲线.jpg"
    assert item["attachment_original_path"] == "/WebFiles/NewFiles/2026/5/14/curve.jpg"
    assert item["attachment_url"] == "http://example.test/curve.jpg"
    assert item["reason_code"] == "GRADIENT_MISMATCH"
    assert item["form_concentrations"] == [90, 160, 240, 320, 410]


def test_final_issue_list_keeps_insufficient_evidence_classification():
    evidence = {
        "rf_table": "RF_Q_GASEOUSMULTIPOINT_SO2",
        "pollutant_type": "SO2",
        "report_classification": "资料不足待人工复核",
        "needs_manual_review": True,
        "reason_code": "NOT_MULTIPOINT_CURVE",
        "reason": "未找到可用于审核的多点曲线图片。",
        "form_concentrations": [50, 100, 200, 300, 400],
        "concentration_unit": "ppb",
    }
    issue = {
        "rule_id": "ATTACHMENT_MULTIPOINT_GRADIENT_REVIEW",
        "category": "附件质量问题",
        "severity": "中",
        "field": "attachment.multipoint_curve.so2",
        "message": "资料不足待人工复核：未找到曲线。",
        "evidence": json.dumps(evidence, ensure_ascii=False),
    }
    audit = {"records": [{"working_order_code": "CH2", "scoring_issues": [issue]}]}

    item = build_final_issue_list(audit, {})["items"][0]

    assert item["report_classification"] == "资料不足待人工复核"
    assert item["needs_manual_review"] is True
