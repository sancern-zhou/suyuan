import json

from app.services.ops_audit.final_issue_list import build_final_issue_list
from app.services.ops_audit.rules.rf_required_rules import check_rf_required_fields
from app.services.ops_audit.semantic import reviewer


def test_pm_tape_usage_emits_semantic_candidate_for_natural_language():
    issues = []
    check_rf_required_fields(
        {"WORKINGORDERCODE": "WO-TAPE-1"},
        [
            (
                "RF_W_PMCHECK",
                {
                    "WORKINGORDERCODE": "WO-TAPE-1",
                    "POLLUTANTTYPE": "PM10",
                    "DEVICEMODEL": "SHARP5030I",
                    "TAPEUSAGEDISPOSAL": "已更换新的纸带",
                    "TEOMMEMBRANEDISPOSAL": "/",
                },
            )
        ],
        issues,
    )

    matched = [issue for issue in issues if issue.rule_id == "RF_PM_TAPE_USAGE_INVALID"]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert evidence["needs_semantic_review"] is True
    assert evidence["field"] == "TAPEUSAGEDISPOSAL"
    assert evidence["instrument_type"] == "paper_tape"


def test_pm_1405_uses_teom_membrane_field():
    issues = []
    check_rf_required_fields(
        {"WORKINGORDERCODE": "WO-TEOM-1"},
        [
            (
                "RF_W_PMCHECK",
                {
                    "WORKINGORDERCODE": "WO-TEOM-1",
                    "POLLUTANTTYPE": "PM2.5",
                    "DEVICEMODEL": "1405RPF",
                    "TAPEUSAGEDISPOSAL": "此款设备未使用纸带",
                    "TEOMMEMBRANEDISPOSAL": "85%",
                },
            )
        ],
        issues,
    )

    matched = [issue for issue in issues if issue.rule_id == "RF_PM_TAPE_USAGE_INVALID"]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert evidence["field"] == "TEOMMEMBRANEDISPOSAL"
    assert evidence["instrument_type"] == "teom_filter"
    assert evidence["needs_semantic_review"] is True


def test_pm_tape_usage_semantic_clears_new_tape_description(monkeypatch):
    monkeypatch.setattr(
        reviewer,
        "_call_semantic_llm_json",
        lambda *args, **kwargs: {
            "results": [
                {
                    "item_id": "WO-TAPE-2::PM10::TAPEUSAGEDISPOSAL",
                    "is_valid": True,
                    "reason": "描述说明已更换新的纸带，可支持本周使用。",
                    "suggestion": "",
                }
            ]
        },
    )

    results = reviewer.build_semantic_review_results(
        _audit_with_pm_tape_issue("WO-TAPE-2", "已更换新的纸带"),
        {"orders": [], "details": [], "rf_forms": {}},
    )

    assert results["results"][0]["judgment"] == "cleared"
    assert results["results"][0]["can_promote_to_final_issue"] is False
    assert results["results"][0]["remark_review"]["remark"] == "描述说明已更换新的纸带，可支持本周使用。"


def test_pm_tape_usage_blank_promotes_to_final_issue_without_llm(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("blank tape usage should not call LLM")

    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", fail_if_called)

    audit = _audit_with_pm_tape_issue("WO-TAPE-3", "")
    semantic_results = reviewer.build_semantic_review_results(audit, {"orders": [], "details": [], "rf_forms": {}})
    final_issue_list = build_final_issue_list(audit, semantic_results)

    assert semantic_results["results"][0]["judgment"] == "confirmed_issue"
    assert semantic_results["results"][0]["supported_rule_ids"] == ["RF_PM_TAPE_USAGE_INVALID"]
    assert final_issue_list["issue_count"] == 1
    assert final_issue_list["items"][0]["rule_id"] == "RF_PM_TAPE_USAGE_INVALID"


def test_pm_tape_usage_confirmation_does_not_promote_unrelated_semantic_rules(monkeypatch):
    monkeypatch.setattr(
        reviewer,
        "_call_semantic_llm_json",
        lambda *args, **kwargs: {
            "results": [
                {
                    "item_id": "WO-TAPE-4::PM10::TAPEUSAGEDISPOSAL",
                    "is_valid": False,
                    "reason": "无法判断纸带剩余量。",
                    "suggestion": "补充纸带剩余量。",
                }
            ]
        },
    )

    audit = _audit_with_pm_tape_issue("WO-TAPE-4", "正常")
    audit["records"][0]["scoring_issues"].extend(
        [
            {"rule_id": "RF_ABNORMAL_VALUE_NO_REMARK", "assessment": "candidate_issue"},
            {"rule_id": "RF_NO_DEVICE_WITHOUT_REMARK", "assessment": "candidate_issue"},
        ]
    )

    semantic_results = reviewer.build_semantic_review_results(audit, {"orders": [], "details": [], "rf_forms": {}})
    final_issue_list = build_final_issue_list(audit, semantic_results)

    pm_results = [
        result
        for result in semantic_results["results"]
        if result.get("conclusion") == "纸带使用量及处置情况填写不规范，无法判断对应耗材状态。"
    ]
    assert pm_results
    assert all(result["supported_rule_ids"] == ["RF_PM_TAPE_USAGE_INVALID"] for result in pm_results)
    assert {item["rule_id"] for item in final_issue_list["items"]} == {"RF_PM_TAPE_USAGE_INVALID"}


def _audit_with_pm_tape_issue(code: str, value: str) -> dict:
    evidence = {
        "working_order_code": code,
        "rf_table": "RF_W_PMCHECK",
        "pollutant_type": "PM10",
        "device_model": "SHARP5030I",
        "instrument_type": "paper_tape",
        "field": "TAPEUSAGEDISPOSAL",
        "field_label": "纸带使用量及处置情况",
        "value": value,
        "needs_semantic_review": bool(value),
    }
    issue = {
        "rule_id": "RF_PM_TAPE_USAGE_INVALID",
        "severity": "中",
        "category": "规范性问题",
        "assessment": "candidate_issue",
        "field": "rf.RF_W_PMCHECK.TAPEUSAGEDISPOSAL",
        "message": f"颗粒物周检纸带使用量需复核: {value or '<空>'}",
        "evidence": json.dumps(evidence, ensure_ascii=False),
    }
    return {
        "records": [
            {
                "working_order_code": code,
                "station_id": "1",
                "order_type": "Check",
                "maintenance_type": "Week",
                "finish_time": "2026-05-27 10:00:00",
                "audit_level": "待确认问题",
                "attachment_count": 0,
                "workflow_steps": [],
                "rf_tables": ["RF_W_PMCHECK"],
                "issues": [issue],
                "scoring_issues": [issue],
            }
        ]
    }
