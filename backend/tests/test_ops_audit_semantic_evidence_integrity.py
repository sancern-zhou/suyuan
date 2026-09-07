import json
import time

import pytest

from app.services.ops_audit.final_issue_list import build_final_issue_list, ensure_issue_ids
from app.services.ops_audit.review_artifacts import apply_review_decisions, issue_list_sha256
from app.services.ops_audit.semantic import reviewer
from app.services.ops_audit.rules.rf_required_rules import check_rf_required_fields


def _task(field="FLOW", remark="设备已复测", code="WO-1"):
    source = {
        "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
        "field": "rf.RF_TEST.remark",
        "evidence": json.dumps({
            "rf_table": "RF_TEST", "reason_rule_id": "RF_RANGE_OUT_OF_SPEC",
            "abnormal_field": f"rf.RF_TEST.{field}",
            "remark_candidates": {f"{field}CHECKROW": remark},
        }, ensure_ascii=False),
    }
    return {
        "review_item_id": f"{code}::{field}", "working_order_code": code,
        "semantic_focus": [source["rule_id"]], "source_issue": source,
        "evidence_summary": {"sample_issues": [source]},
    }


def test_batch_transport_preserves_every_item_and_long_item(monkeypatch):
    monkeypatch.setattr(reviewer.llm_service, "base_url", "test")
    monkeypatch.setattr(reviewer.llm_service, "model", "test")
    received = []

    def fake_llm(prompt):
        envelope = json.loads(prompt.split("\n\n", 1)[1])
        items = json.loads(envelope["text"])["items"]
        assert len(items) <= reviewer.SEMANTIC_BATCH_MAX_ITEMS
        received.extend(items)
        return {"results": [{"review_item_id": item["review_item_id"]} for item in items]}

    monkeypatch.setattr(reviewer, "_run_async_llm_json", fake_llm)
    items = [{"review_item_id": str(i), "evidence": "x" * (14000 if i == 5 else 2000)} for i in range(23)]
    result = reviewer._call_semantic_llm_json("test", json.dumps({"items": items}))
    assert sorted(received, key=lambda item: int(item["review_item_id"])) == items
    assert len(result["results"]) == len(items)


@pytest.mark.parametrize("raw", [None, {"results": []}, {"results": [
    {"working_order_code": "WO-1", "judgment_type": "unrelated"},
]}])
def test_missing_or_order_only_result_cannot_convict_multiple_fields(monkeypatch, raw):
    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", lambda *a, **kw: raw)
    tasks = [_task("FLOW"), _task("PMT")]
    results = reviewer._review_remark_tasks_batch(tasks, {}, {}, {}, {})
    assert len(results) == 2
    assert all(r["judgment"] == "needs_followup" for r in results.values())
    assert not any(r["can_promote_to_final_issue"] for r in results.values())


def test_duplicate_item_response_is_not_silently_overwritten():
    assert reviewer._batch_results_by_key({"results": [
        {"review_item_id": "1", "judgment_type": "valid"},
        {"review_item_id": "1", "judgment_type": "unrelated"},
    ]}, "review_item_id") == {}


def test_batch_timeout_keeps_completed_chunks(monkeypatch):
    monkeypatch.setattr(reviewer, "SEMANTIC_BATCH_MAX_ITEMS", 1)
    monkeypatch.setattr(reviewer, "SEMANTIC_BATCH_TOTAL_TIMEOUT_SECONDS", 0.05)
    tasks = [_task("FLOW", code="FAST"), _task("FLOW", code="SLOW")]
    for task in tasks:
        task["review_kind"] = "remark_semantics"

    def review(tasks, *args):
        task = tasks[0]
        if task["working_order_code"] == "SLOW":
            time.sleep(0.1)
        return {task["review_item_id"]: {"working_order_code": task["working_order_code"], "judgment": "cleared"}}

    monkeypatch.setattr(reviewer, "_review_remark_tasks_batch", review)
    results = reviewer._review_batch_semantic_tasks(tasks, {}, {}, {}, {})
    by_code = {result["working_order_code"]: result for result in results.values()}
    assert by_code["FAST"]["judgment"] == "cleared"
    assert by_code["SLOW"]["judgment"] == "needs_followup"


def _audit(task):
    evidence = json.loads(task["source_issue"]["evidence"])
    return {"records": [{
        "working_order_code": task["working_order_code"],
        "scoring_issues": [{
            "rule_id": "RF_RANGE_OUT_OF_SPEC", "field": evidence["abnormal_field"],
            "message": "outside configured range", "evidence": json.dumps({"rf_table": "RF_TEST"}),
        }],
    }]}


def test_manufacturer_explanation_reaches_final_fact_as_pending():
    task = _task(remark="厂家报备参数0.7-1.3")
    result = reviewer._deterministic_remark_semantic_result(task, {}, {}, "")
    assert result["judgment"] == "cleared"
    final = build_final_issue_list(_audit(task), {"results": [result]})
    assert final["items"][0]["needs_manual_review"] is True
    assert final["items"][0]["semantic_conclusion"] == result["conclusion"]


def test_explained_repair_does_not_erase_real_abnormal_fact():
    task = _task(remark="已维修，复测正常")
    final = build_final_issue_list(_audit(task), {"results": [{
        **task, "judgment": "cleared", "can_promote_to_final_issue": False,
        "remark_review": {"judgment_type": "valid"}, "conclusion": "有效处置说明",
    }]})
    assert len(final["items"]) == 1
    assert not final["items"][0].get("needs_manual_review")


@pytest.mark.parametrize("fact_decision,expected", [("exclude", "exclude"), ("manual_review", "manual_review")])
def test_explanation_cannot_survive_excluded_or_pending_fact(tmp_path, fact_decision, expected):
    source = ensure_issue_ids({"items": [
        {"working_order_code": "WO", "rule_id": "RF_RANGE_OUT_OF_SPEC", "field": "flow", "issue_group_id": "group"},
        {"working_order_code": "WO", "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK", "field": "remark", "issue_group_id": "group"},
    ]})
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    result = apply_review_decisions(path, [
        {"issue_id": source["items"][0]["issue_id"], "decision": fact_decision, "reason": "source checked"},
        {"issue_id": source["items"][1]["issue_id"], "decision": "retain", "reason": "missing remark"},
    ], expected_source_sha256=issue_list_sha256(source))
    assert result["retained_count"] == 0
    decisions = json.loads((tmp_path / "latest_finished_work_orders_review_decisions.json").read_text())
    assert decisions["decisions"][1]["decision"] == expected


def test_retain_requires_reason_and_pending_requires_evidence(tmp_path):
    source = ensure_issue_ids({"items": [{"rule_id": "RF_RANGE_OUT_OF_SPEC", "needs_manual_review": True}]})
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    decision = {"issue_id": source["items"][0]["issue_id"], "decision": "retain"}
    with pytest.raises(ValueError, match="reason is required"):
        apply_review_decisions(path, [decision], expected_source_sha256=issue_list_sha256(source))
    result = apply_review_decisions(path, [{**decision, "reason": "outside range"}], expected_source_sha256=issue_list_sha256(source))
    assert result["manual_review_count"] == 1
    assert not result["report_ready"]


def test_unfinished_semantic_review_prevents_report_even_without_confirmed_issues(tmp_path):
    source = {"items": [], "pending_semantic_reviews": [{"review_item_id": "WO::FLOW"}]}
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    result = apply_review_decisions(path, [], expected_source_sha256=issue_list_sha256(source))
    assert not result["report_ready"]
    assert result["pending_semantic_review_count"] == 1


@pytest.mark.parametrize("value", ["颗粒物设备为振荡天平法仪器，无纸带", "此款设备未使用纸带"])
def test_teom_accepts_explicit_non_applicability_sentence(value):
    issues = []
    check_rf_required_fields({"WORKINGORDERCODE": "WO"}, [("RF_W_PMCHECK", {
        "DEVICEMODEL": "1405", "TAPEUSAGEDISPOSAL": value, "TEOMMEMBRANEDISPOSAL": "30%",
    })], issues)
    assert not any(i.rule_id == "RF_PM_PAPER_TAPE_NOT_APPLICABLE_FILLED" for i in issues)
