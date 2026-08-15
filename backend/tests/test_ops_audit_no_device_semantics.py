import json

from app.services.ops_audit.rules import rf_abnormal_remark_rules
from app.services.ops_audit.semantic import reviewer


def test_other_device_no_device_rule_emits_semantic_candidate():
    issues = []
    rf_abnormal_remark_rules.check_rf_abnormal_remarks(
        {"WORKINGORDERCODE": "CH2605191779151736054"},
        [
            (
                "RF_W_OTHERDEVICECHECK",
                {
                    "VISIBILITYDEVICEMODEL": "/",
                    "VISIBILITYSITUATION": "现场无能见度仪器",
                },
            )
        ],
        issues,
    )

    matched = [issue for issue in issues if issue.rule_id == "RF_NO_DEVICE_WITHOUT_REMARK"]
    assert len(matched) == 1
    assert "VISIBILITYDEVICEMODEL" in matched[0].field


def test_other_device_rule_skips_absent_device_fields():
    issues = []
    rf_abnormal_remark_rules.check_rf_abnormal_remarks(
        {"WORKINGORDERCODE": "WO-1"},
        [
            (
                "RF_W_OTHERDEVICECHECK",
                {
                    "VISIBILITYDEVICEMODEL": "/",
                    "VISIBILITYSITUATION": "无此设备",
                },
            )
        ],
        issues,
    )

    assert not any("WEATHERDEVICEMODEL" in issue.field for issue in issues)


def test_other_device_abnormal_situation_keeps_fact_and_routes_context_to_semantic_review():
    issues = []
    rf_abnormal_remark_rules.check_rf_abnormal_remarks(
        {"WORKINGORDERCODE": "WO-WEATHER-HANDOVER"},
        [
            (
                "RF_W_OTHERDEVICECHECK",
                {
                    "WEATHERSITUATION": "风速风向通讯失败，交接遗留问题",
                },
            )
        ],
        issues,
    )

    assert any(issue.rule_id == "RF_ABNORMAL_RESULT_FIELD" for issue in issues)
    companion = next(issue for issue in issues if issue.rule_id == "RF_ABNORMAL_VALUE_NO_REMARK")
    evidence = json.loads(companion.evidence)
    assert evidence["reason_rule_id"] == "RF_ABNORMAL_RESULT_FIELD"
    assert evidence["remark_candidates"]["WEATHERSITUATION"] == "风速风向通讯失败，交接遗留问题"


def test_no_device_semantic_batch_clears_equivalent_explanation(monkeypatch):
    monkeypatch.setattr(
        reviewer,
        "_call_semantic_llm_json",
        lambda *args, **kwargs: {
            "results": [
                {
                    "item_id": "WO-2::0",
                    "is_explained": True,
                    "reason": "运行情况已说明现场无能见度仪器，等价于无对应设备。",
                    "confidence": 0.92,
                }
            ]
        },
    )

    audit = _audit_with_no_device_issue("WO-2", "现场无能见度仪器")
    results = reviewer.build_semantic_review_results(audit, {"orders": [], "details": [], "rf_forms": {}})

    assert results["results"][0]["judgment"] == "cleared"
    assert results["results"][0]["can_promote_to_final_issue"] is False


def test_no_device_semantic_batch_confirms_low_information_text(monkeypatch):
    monkeypatch.setattr(
        reviewer,
        "_call_semantic_llm_json",
        lambda *args, **kwargs: {
            "results": [
                {
                    "item_id": "WO-3::0",
                    "is_explained": False,
                    "reason": "运行情况只有低信息占位内容。",
                    "confidence": 0.9,
                }
            ]
        },
    )

    audit = _audit_with_no_device_issue("WO-3", "/")
    results = reviewer.build_semantic_review_results(audit, {"orders": [], "details": [], "rf_forms": {}})

    assert results["results"][0]["judgment"] == "confirmed_issue"
    assert results["results"][0]["can_promote_to_final_issue"] is True
    assert results["results"][0]["supported_rule_ids"] == ["RF_NO_DEVICE_WITHOUT_REMARK"]


def _audit_with_no_device_issue(code: str, situation: str) -> dict:
    evidence = {
        "working_order_code": code,
        "rf_table": "RF_W_OTHERDEVICECHECK",
        "violations": [
            {
                "label": "能见度设备",
                "model_field": "VISIBILITYDEVICEMODEL",
                "model_value": "/",
                "situation_field": "VISIBILITYSITUATION",
                "situation_value": situation,
            }
        ],
    }
    issue = {
        "rule_id": "RF_NO_DEVICE_WITHOUT_REMARK",
        "severity": "中",
        "assessment": "candidate_issue",
        "field": "rf.RF_W_OTHERDEVICECHECK.VISIBILITYDEVICEMODEL",
        "message": "其他设备周检存在无对应设备但说明不清",
        "evidence": __import__("json").dumps(evidence, ensure_ascii=False),
    }
    return {
        "records": [
            {
                "working_order_code": code,
                "station_id": "1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "finish_time": "2026-05-27 10:00:00",
                "audit_level": "需语义复核",
                "score": 80,
                "attachment_count": 0,
                "workflow_steps": [],
                "rf_tables": ["RF_W_OTHERDEVICECHECK"],
                "scoring_issues": [issue],
            }
        ]
    }
