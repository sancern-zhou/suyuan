import json
from pathlib import Path

import pytest

from app.services.ops_audit.final_issue_list import ensure_issue_ids
from app.services.ops_audit.review_artifacts import (
    apply_review_decisions,
    apply_human_feedback,
    build_human_feedback_request,
    build_report_input,
    build_review_input,
    issue_list_sha256,
    persist_report_input,
)


def _final_issue_list() -> dict:
    result = {
        "generated_at": "2026-08-17 10:00:00",
        "issue_count": 2,
        "items": [
            {
                "working_order_code": "CH2608031785714694090",
                "rf_table": "RF_W_GASEOUSCHECK_O3",
                "rf_record_key": "O3-record",
                "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                "field": "rf.RF_W_GASEOUSCHECK_O3.CYYLCHECKVALUE",
                "message": "臭氧周检异常值备注为占位符",
                "evidence": json.dumps({"value": 5.2, "remark_candidates": {"REMARK": "/"}}, ensure_ascii=False),
            },
            {
                "working_order_code": "CH2608031785714694090",
                "rf_table": "RF_W_PMCHECK",
                "rf_record_key": "PM-record",
                "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                "field": "rf.RF_W_PMCHECK.AIRTEMP",
                "message": "METONE无采样管温度项目",
                "evidence": json.dumps({"brand": "METONE", "field": "AIRTEMP"}, ensure_ascii=False),
            },
        ],
    }
    return ensure_issue_ids(result)


def test_issue_ids_distinguish_same_order_and_rule_across_forms() -> None:
    issue_list = _final_issue_list()

    assert issue_list["items"][0]["issue_id"] != issue_list["items"][1]["issue_id"]


def test_report_input_projects_comparison_evidence_for_agent() -> None:
    issue_list = {
        "items": [
            {
                "working_order_code": "WO-O3",
                "rule_id": "ATTACHMENT_O3_VALUE_PASS_XLS_VALUE_MISMATCH",
                "message": "O3量值传递表单与XLS附件不一致",
                "evidence": json.dumps(
                    {
                        "comparisons": [
                            {
                                "field": "DEVICEDELIVERMODEL",
                                "label": "斜率",
                                "comparison_type": "number",
                                "cell": "F25",
                                "form_value": "1.001",
                                "xls_value": 0.975,
                                "status": "mismatch",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    }
    report = build_report_input(ensure_issue_ids(issue_list))
    display = report["items"][0]["display_evidence"]
    assert display[0]["label"] == "斜率"
    assert display[0]["location"] == "F25"
    assert display[0]["text"] == "斜率：表单值“1.001”，附件值“0.975”（位置：F25）。"


def test_report_input_projects_range_and_violation_evidence_without_machine_keys() -> None:
    issue_list = {
        "items": [
            {
                "working_order_code": "WO-RANGE",
                "rule_id": "RF_RANGE_OUT_OF_SPEC",
                "message": "高压电源超出正常范围",
                "decision_evidence": {
                    "field": "GYCHECKVALUE",
                    "field_label": "高压电源",
                    "raw_value": "701 mV",
                    "expected_range": "500-950 V",
                    "brand": "ESA",
                },
                "evidence": json.dumps({"out_of_spec_values": [{"field": "GYCHECKVALUE", "value": 0.701}]}, ensure_ascii=False),
            },
            {
                "working_order_code": "WO-FLOW",
                "rule_id": "RF_Q_GASEOUS_FLOW_TARGET_POINT_MISMATCH",
                "message": "流量点不匹配",
                "evidence": json.dumps({
                    "violations": [{"field": "DF_Valuve_60", "actual": 4981.7, "expected": 6000}]
                }, ensure_ascii=False),
            },
        ]
    }
    report = build_report_input(ensure_issue_ids(issue_list))
    texts = [entry["text"] for item in report["items"] for entry in item["display_evidence"]]
    assert any("高压电源：实测值“701 mV”" in text for text in texts)
    assert any("实际值“4981.7”，期望值“6000”" in text for text in texts)
    assert all("field=" not in text and "comparison_type" not in text for text in texts)


def test_human_feedback_rebuilds_report_input_without_second_llm_pass(tmp_path: Path) -> None:
    issue_list = _final_issue_list()
    issue_list["items"][0]["needs_manual_review"] = True
    issue_list["items"][1]["needs_manual_review"] = True
    source_path = tmp_path / "final_issue_list.json"
    report_path = tmp_path / "latest_finished_work_orders_report_input.json"
    source_path.write_text(json.dumps(issue_list, ensure_ascii=False), encoding="utf-8")
    report = persist_report_input(issue_list, report_path, source_path=source_path)
    request = build_human_feedback_request(report, report_input_path=report_path)
    assert request["learning_mode"] == "ops"

    result = apply_human_feedback(
        report_path,
        [
            {"item_id": request["items"][0]["item_id"], "decision": "include", "comment": "已核对原始记录"},
            {"item_id": request["items"][1]["item_id"], "decision": "exclude", "comment": "设备不适用"},
        ],
        expected_source_sha256=report["source"]["sha256"],
        feedback_id="feedback-test",
        reviewer={"user_id": "operator-1"},
    )

    updated = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["report_ready"] is True
    assert updated["summary"]["pending_review_count"] == 0
    assert [item["issue_id"] for item in updated["items"]] == [issue_list["items"][0]["issue_id"]]
    assert updated["source"]["sha256"] != report["source"]["sha256"]


def test_report_is_blocked_until_manual_and_semantic_pending_items_are_resolved() -> None:
    issue_list = _final_issue_list()
    issue_list["items"][0]["needs_manual_review"] = True
    issue_list["pending_semantic_reviews"] = [
        {
            "review_item_id": "semantic-1",
            "working_order_code": "WO-1",
            "conclusion": "备注适用性待确认",
        }
    ]

    report = build_report_input(issue_list)
    request = build_human_feedback_request(report)

    assert report["report_ready"] is False
    assert report["summary"]["pending_review_count"] == 1
    assert report["summary"]["pending_semantic_review_count"] == 1
    assert {item["item_id"] for item in request["items"]} == {
        issue_list["items"][0]["issue_id"],
        "semantic-1",
    }


def test_semantic_pending_review_is_resolved_by_human_feedback(tmp_path: Path) -> None:
    issue_list = _final_issue_list()
    issue_list["pending_semantic_reviews"] = [
        {
            "review_item_id": "WO-TAPE::PM10::TAPEUSAGEDISPOSAL",
            "working_order_code": "WO-1",
            "conclusion": "耗材使用/处置情况语义复核未完成，暂不进入最终问题清单。",
        }
    ]
    source_path = tmp_path / "final_issue_list.json"
    report_path = tmp_path / "latest_finished_work_orders_report_input.json"
    source_path.write_text(json.dumps(issue_list, ensure_ascii=False), encoding="utf-8")
    report = persist_report_input(issue_list, report_path, source_path=source_path)
    request = build_human_feedback_request(report, report_input_path=report_path)

    semantic_ids = {
        item["item_id"] for item in request["items"] if item["kind"] == "semantic_review"
    }
    assert semantic_ids == {"WO-TAPE::PM10::TAPEUSAGEDISPOSAL"}

    result = apply_human_feedback(
        report_path,
        [
            {
                "item_id": "WO-TAPE::PM10::TAPEUSAGEDISPOSAL",
                "decision": "exclude",
                "comment": "耗材说明充分",
            }
        ],
        expected_source_sha256=report["source"]["sha256"],
        feedback_id="feedback-semantic",
        reviewer={"user_id": "operator-1"},
    )

    assert result["report_ready"] is True
    assert result["summary"]["pending_semantic_review_count"] == 0


def test_review_requires_complete_coverage(tmp_path: Path) -> None:
    issue_list = _final_issue_list()
    review_input = build_review_input(issue_list)

    with pytest.raises(ValueError, match="do not cover all issues"):
        _apply(tmp_path, issue_list, review_input, [{"issue_id": issue_list["items"][0]["issue_id"], "decision": "retain", "reason": "证据充分"}])


def test_review_rejects_changed_source(tmp_path: Path) -> None:
    issue_list = _final_issue_list()
    review_input = build_review_input(issue_list)
    issue_list["items"][0]["message"] = "changed after review"

    with pytest.raises(ValueError, match="changed after review input"):
        _apply(tmp_path, issue_list, review_input, [])


def test_review_materializes_clean_report_input_without_excluded_item(tmp_path: Path) -> None:
    issue_list = _final_issue_list()
    source_path = tmp_path / "final_issue_list.json"
    source_path.write_text(json.dumps(issue_list, ensure_ascii=False), encoding="utf-8")
    source_hash = issue_list_sha256(issue_list)
    retained_id = issue_list["items"][0]["issue_id"]
    excluded_id = issue_list["items"][1]["issue_id"]

    result = apply_review_decisions(
        source_path,
        [
            {"issue_id": retained_id, "decision": "retain", "reason": "证据充分"},
            {"issue_id": excluded_id, "decision": "exclude", "reason": "该品牌无此检查项目"},
        ],
        expected_source_sha256=source_hash,
        reviewer={"name": "ops-child-agent"},
    )

    report_input = json.loads(Path(result["report_input_path"]).read_text(encoding="utf-8"))
    reviewed = json.loads(Path(result["reviewed_issue_list_path"]).read_text(encoding="utf-8"))
    assert result["report_ready"] is True
    assert report_input["summary"] == {
        "reviewed_count": 2,
        "retained_count": 1,
        "excluded_count": 1,
        "manual_review_count": 0,
        "affected_order_count": 1,
        "report_issue_count": 1,
    }
    assert [item["issue_id"] for item in report_input["items"]] == [retained_id]
    assert excluded_id not in json.dumps(report_input, ensure_ascii=False)
    assert reviewed["excluded_items"][0]["issue_id"] == excluded_id


def _linked_items() -> dict:
    base = {
        "working_order_code": "CH2608051785908567346",
        "rf_table": "RF_W_GASEOUSCHECK_NOX",
        "rf_record_key": "NOX-record",
        "issue_group_id": "order::NOX::CYLLCHECKVALUE",
    }
    return ensure_issue_ids({"items": [
        {**base, "rule_id": "RF_RANGE_OUT_OF_SPEC", "field": "rf.RF_W_GASEOUSCHECK_NOX.CYLLCHECKVALUE",
         "message": "采样流量76.176超出350-650 sccm", "evidence": json.dumps({
             "handling_record_candidates": {"CYLLCHECKROW": "", "REMARK": "", "PROCESSTYPE": 0},
         })},
        {**base, "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK", "field": "rf.RF_W_GASEOUSCHECK_NOX.remark",
         "message": "未填写与当前异常相关的说明。", "remark_status": "missing",
         "original_remarks": [], "original_remark_text": ""},
    ]})


def test_empty_associated_remarks_survive_review_projection() -> None:
    review = build_review_input(_linked_items())
    fact, explanation = review["items"]
    assert fact["remark_context"]["status"] == "missing"
    assert fact["evidence_facts"]["handling_record_candidates"]["CYLLCHECKROW"] == ""
    assert {entry["field"] for entry in fact["remark_context"]["entries"]} == {"CYLLCHECKROW", "REMARK"}
    assert explanation["remark_status"] == "missing"
    assert explanation["remark_context"]["status"] == "missing"


@pytest.mark.parametrize("extra", [None, "other_field", "other_record"])
def test_report_merges_linked_rules_without_merging_other_abnormalities(tmp_path: Path, extra: str | None) -> None:
    source = _linked_items()
    if extra:
        additional = dict(source["items"][0])
        additional.pop("issue_id")
        if extra == "other_field":
            additional.update(field="rf.RF_W_GASEOUSCHECK_NOX.CYYLCHECKVALUE", issue_group_id="order::NOX::CYYLCHECKVALUE")
        else:
            additional["rf_record_key"] = "second-record"
        source["items"].append(additional)
        ensure_issue_ids(source)
    review = build_review_input(source)
    result = _apply(tmp_path, source, review, [
        {"issue_id": item["issue_id"], "decision": "retain", "reason": "证据确认"} for item in source["items"]
    ])
    report = json.loads(Path(result["report_input_path"]).read_text())
    assert len(report["items"]) == (2 if extra else 1)
    row = report["items"][0]
    assert row["rule_ids"] == ["RF_RANGE_OUT_OF_SPEC", "RF_ABNORMAL_VALUE_NO_REMARK"]
    assert len(row["components"]) == 2
    assert "76.176" in row["message"] and "未填写" in row["message"]
    assert row["remark_context"]["status"] == "missing"
    assert report["summary"]["retained_count"] == len(source["items"])
    assert report["summary"]["report_issue_count"] == len(report["items"])
    assert sorted(value for item in report["items"] for value in item["source_issue_ids"]) == sorted(item["issue_id"] for item in source["items"])


@pytest.mark.parametrize("fields, expected", [
    ({}, "unavailable"),
    ({"remark_status": "not_applicable"}, "not_applicable"),
    ({"evidence": {"remark_candidates": {"CYLLCHECKROW": "厂家说明范围为70-80"}}}, "provided"),
    ({"evidence": {"remark_candidates": {"PROCESSTYPE": 0}}}, "unavailable"),
])
def test_remark_presence_is_not_inferred_from_absent_metadata(fields: dict, expected: str) -> None:
    source = _linked_items()
    source["items"][0].pop("evidence")
    source["items"][0].update(fields)
    assert build_review_input(source)["items"][0]["remark_context"]["status"] == expected


@pytest.mark.parametrize("ambiguous", [False, True])
def test_legacy_order_only_record_key_merges_only_with_unique_record(tmp_path: Path, ambiguous: bool) -> None:
    source = _linked_items()
    source["items"][1]["rf_record_key"] = source["items"][1]["working_order_code"]
    if ambiguous:
        other = dict(source["items"][0])
        other.pop("issue_id")
        other["rf_record_key"] = "another-record"
        source["items"].append(other)
    ensure_issue_ids(source)
    result = _apply(tmp_path, source, build_review_input(source), [
        {"issue_id": item["issue_id"], "decision": "retain", "reason": "证据确认"} for item in source["items"]
    ])
    report = json.loads(Path(result["report_input_path"]).read_text())
    assert len(report["items"]) == (3 if ambiguous else 1)


def _apply(tmp_path: Path, issue_list: dict, review_input: dict, decisions: list[dict]) -> dict:
    path = tmp_path / "final_issue_list.json"
    path.write_text(json.dumps(issue_list, ensure_ascii=False), encoding="utf-8")
    return apply_review_decisions(
        path,
        decisions,
        expected_source_sha256=review_input["source"]["sha256"],
    )
