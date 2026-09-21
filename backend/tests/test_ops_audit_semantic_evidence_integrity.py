import json

import pytest

from app.services.ops_audit.final_issue_list import build_final_issue_list, ensure_issue_ids
from app.services.ops_audit.review_artifacts import apply_review_decisions, build_report_input, issue_list_sha256
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
    tasks = [_task("FLOW", code="FAST"), _task("FLOW", code="SLOW")]
    for task in tasks:
        task["review_kind"] = "remark_semantics"

    def review(tasks, *args):
        task = tasks[0]
        if task["working_order_code"] == "SLOW":
            raise TimeoutError("single model batch timed out")
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


def test_manufacturer_range_covering_value_excludes_configured_range_candidate():
    task = _task(remark="厂家报备参数0.7-1.3")
    source_evidence = json.loads(task["source_issue"]["evidence"])
    source_evidence["abnormal_evidence"] = {
        "observed_value": {"normalized_value": 1.172, "normalized_unit": ""},
    }
    task["source_issue"]["evidence"] = json.dumps(source_evidence, ensure_ascii=False)
    task["evidence_summary"]["sample_issues"] = [task["source_issue"]]
    result = reviewer._deterministic_remark_semantic_result(task, {}, {}, "")
    assert result["judgment"] == "cleared"
    assert result["abnormal_fact_assessment"] == "not_applicable"
    final = build_final_issue_list(_audit(task), {"results": [result]})
    assert final["items"] == []
    assert final["semantic_excluded_count"] == 1


def test_manufacturer_range_not_covering_value_stays_pending():
    task = _task(remark="厂家报备参数0.7-1.0")
    source_evidence = json.loads(task["source_issue"]["evidence"])
    source_evidence["abnormal_evidence"] = {
        "observed_value": {"normalized_value": 1.172, "normalized_unit": ""},
    }
    task["source_issue"]["evidence"] = json.dumps(source_evidence, ensure_ascii=False)
    task["evidence_summary"]["sample_issues"] = [task["source_issue"]]
    result = reviewer._deterministic_remark_semantic_result(task, {}, {}, "")
    assert result["abnormal_fact_assessment"] == "needs_verification"
    final = build_final_issue_list(_audit(task), {"results": [result]})
    assert final["items"][0]["needs_manual_review"] is True


def test_manufacturer_station_range_variant_covering_value_is_accepted():
    task = _task(field="CYLLCHECKVALUE", remark="聚光厂家备案总站最新流量参数为400-1200SCCM")
    source_evidence = json.loads(task["source_issue"]["evidence"])
    source_evidence["abnormal_evidence"] = {
        "observed_value": {"normalized_value": 622, "normalized_unit": "SCCM"},
    }
    task["source_issue"]["evidence"] = json.dumps(source_evidence, ensure_ascii=False)
    task["evidence_summary"]["sample_issues"] = [task["source_issue"]]
    result = reviewer._deterministic_remark_semantic_result(task, {}, {}, "")
    assert result["abnormal_fact_assessment"] == "not_applicable"


def test_th_o3_normal_display_note_excludes_inapplicable_generic_signal_range():
    task = _task(field="GYCHECKVALUE", remark="参考范围有误，仪器显示正常测量。")
    source_evidence = json.loads(task["source_issue"]["evidence"])
    source_evidence["abnormal_evidence"] = {
        "brand": "TH",
        "pollutant_type": "O3",
        "observed_value": {"normalized_value": 568, "normalized_unit": "mV"},
    }
    task["source_issue"]["evidence"] = json.dumps(source_evidence, ensure_ascii=False)
    task["evidence_summary"]["sample_issues"] = [task["source_issue"]]
    result = reviewer._deterministic_remark_semantic_result(task, {}, {}, "")
    assert result["abnormal_fact_assessment"] == "not_applicable"
    assert build_final_issue_list(_audit(task), {"results": [result]})["items"] == []


def test_identified_device_without_checked_item_is_not_applicable():
    task = _task(field="AIRTEMPVALUE/AIRTEMPISNORMAL", remark="METONE设备无采样管温度")
    source_evidence = json.loads(task["source_issue"]["evidence"])
    source_evidence["reason_rule_id"] = "RF_PM_SAMPLE_TUBE_TEMP_ABNORMAL"
    source_evidence["abnormal_evidence"] = {"device_model": "METONE 1020"}
    task["source_issue"]["evidence"] = json.dumps(source_evidence, ensure_ascii=False)
    task["evidence_summary"]["sample_issues"] = [task["source_issue"]]
    result = reviewer._deterministic_remark_semantic_result(task, {}, {}, "")
    assert result["abnormal_fact_assessment"] == "not_applicable"


def test_explained_repair_does_not_erase_real_abnormal_fact():
    task = _task(remark="已维修，复测正常")
    final = build_final_issue_list(_audit(task), {"results": [{
        **task, "judgment": "cleared", "can_promote_to_final_issue": False,
        "remark_review": {"judgment_type": "valid"}, "conclusion": "有效处置说明",
    }]})
    assert len(final["items"]) == 1
    assert not final["items"][0].get("needs_manual_review")


def test_explicit_non_applicability_removes_linked_fact_and_explanation():
    task = _task(remark="BAM1020设备无纸带，不适用该字段")
    task["source_issue"]["evidence"] = json.dumps({
        "rf_table": "RF_TEST", "reason_rule_id": "RF_RANGE_OUT_OF_SPEC",
        "abnormal_field": "rf.RF_TEST.TAPE", "device_model": "BAM1020",
        "remark_candidates": {"TAPEUSAGEDISPOSAL": "BAM1020设备无纸带，不适用该字段"},
    }, ensure_ascii=False)
    final = build_final_issue_list(_audit(task), {"results": [{
        **task, "judgment": "cleared", "can_promote_to_final_issue": False,
        "source_issue": task["source_issue"], "abnormal_fact_assessment": "not_applicable",
        "abnormal_fact_reason": "设备型号BAM1020无纸带，该字段不适用。", "conclusion": "字段不适用",
    }]})
    assert final["items"] == []
    assert len(final["semantic_excluded_items"]) == 1
    report = build_report_input(final)
    assert report["report_ready"] is True
    assert report["summary"]["semantic_excluded_count"] == 1


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
