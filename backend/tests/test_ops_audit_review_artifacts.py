import json
from pathlib import Path

import pytest

from app.services.ops_audit.final_issue_list import ensure_issue_ids
from app.services.ops_audit.review_artifacts import (
    apply_review_decisions,
    build_review_input,
    issue_list_sha256,
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


def test_review_requires_complete_coverage(tmp_path: Path) -> None:
    issue_list = _final_issue_list()
    review_input = build_review_input(issue_list)

    with pytest.raises(ValueError, match="do not cover all issues"):
        _apply(tmp_path, issue_list, review_input, [{"issue_id": issue_list["items"][0]["issue_id"], "decision": "retain"}])


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
    }
    assert [item["issue_id"] for item in report_input["items"]] == [retained_id]
    assert excluded_id not in json.dumps(report_input, ensure_ascii=False)
    assert reviewed["excluded_items"][0]["issue_id"] == excluded_id


def _apply(tmp_path: Path, issue_list: dict, review_input: dict, decisions: list[dict]) -> dict:
    path = tmp_path / "final_issue_list.json"
    path.write_text(json.dumps(issue_list, ensure_ascii=False), encoding="utf-8")
    return apply_review_decisions(
        path,
        decisions,
        expected_source_sha256=review_input["source"]["sha256"],
    )
