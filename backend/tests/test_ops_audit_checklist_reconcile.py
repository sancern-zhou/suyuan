"""Channel-2 checklist reconciliation tests (design doc §3 通道2 矩阵 + §4 指标 gating)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.ops_audit import feedback_ledger
from app.services.ops_audit.checklist_reconcile import (
    append_reconciliation_to_ledger,
    archive_reconciliation,
    compute_reconciliation_metrics,
    normalize_checklist_items,
    reconcile_checklist,
)


@pytest.fixture(autouse=True)
def _isolate_ledger(tmp_path_factory, monkeypatch):
    ledger_dir = tmp_path_factory.mktemp("checklist_ledger")
    monkeypatch.setattr(
        feedback_ledger,
        "default_ledger_path",
        lambda: ledger_dir / feedback_ledger.LEDGER_FILENAME,
    )
    monkeypatch.setattr(
        feedback_ledger,
        "default_metrics_history_path",
        lambda: ledger_dir / feedback_ledger.METRICS_HISTORY_FILENAME,
    )


def _issue_list(*issues: dict) -> dict:
    return {
        "generated_at": "2026-11-11 00:00:00",
        "issue_count": len(issues),
        "items": list(issues),
    }


def _issue(order: str, rule_id: str, category: str, message: str = "问题") -> dict:
    return {
        "working_order_code": order,
        "rule_id": rule_id,
        "category": category,
        "message": message,
        "station_id": "ST-1",
        "review_status": "rule_detected",
    }


def test_classification_matrix_table_driven(tmp_path: Path) -> None:
    """Design doc §3 通道2 六行矩阵逐行对账。"""

    issue_list = _issue_list(
        _issue("WO-1", "RF_RULE_A", "一致性问题", "表单与附件不一致"),
        _issue("WO-2", "RF_RULE_B", "时间合理性问题", "检定日期超期"),
        _issue("WO-3", "RF_RULE_C", "一致性问题", "读数不一致"),
    )
    result = reconcile_checklist(
        issue_list,
        [
            {"order_code": "WO-1", "verdict": "problem", "problem_category": "一致性问题"},
            {"order_code": "WO-4", "verdict": "problem", "problem_category": "时间合理性问题"},
            {"order_code": "WO-2", "verdict": "ok", "problem_category": "时间合理性问题"},
            {"order_code": "WO-9", "verdict": "problem", "problem_category": "一致性问题"},
        ],
        full_review_declared=False,
        dataset_orders={"WO-1", "WO-2", "WO-3", "WO-4"},
    )
    outcomes = {(row["order_code"], row["verdict"]): row["outcome"] for row in result["classifications"]}
    assert outcomes[("WO-1", "problem")] == "confirmed"
    assert outcomes[("WO-4", "problem")] == "missed"
    assert outcomes[("WO-2", "ok")] == "rejected"
    assert outcomes[("WO-9", "problem")] == "unmatched"

    # 部分清单：未提及的 WO-3 不入账
    unmentioned = [row for row in result["classifications"] if row["order_code"] == "WO-3"]
    assert unmentioned[0]["outcome"] == "unmentioned_partial"
    assert unmentioned[0]["ledger"] is False

    ledger_outcomes = sorted(record["outcome"] for record in result["ledger_records"])
    assert ledger_outcomes == ["confirmed", "missed", "rejected"]
    missed_record = next(r for r in result["ledger_records"] if r["outcome"] == "missed")
    assert missed_record["rule_id"] is None  # 候选新规则语义
    assert missed_record["explicit"] is True


def test_full_review_declaration_produces_tacit_confirmed() -> None:
    issue_list = _issue_list(_issue("WO-1", "RF_RULE_A", "一致性问题"), _issue("WO-3", "RF_RULE_C", "一致性问题"))
    result = reconcile_checklist(
        issue_list,
        [{"order_code": "WO-1", "verdict": "problem", "problem_category": "一致性问题"}],
        full_review_declared=True,
        dataset_orders={"WO-1", "WO-3"},
    )
    tacit = [r for r in result["ledger_records"] if r["outcome"] == "tacit_confirmed"]
    assert len(tacit) == 1
    assert tacit[0]["order_code"] == "WO-3"
    assert tacit[0]["explicit"] is False
    assert tacit[0]["rule_id"] == "RF_RULE_C"


def test_category_mismatch_reports_other_type_is_still_missed() -> None:
    issue_list = _issue_list(_issue("WO-1", "RF_RULE_A", "一致性问题"))
    result = reconcile_checklist(
        issue_list,
        [{"order_code": "WO-1", "verdict": "problem", "problem_category": "时间合理性问题"}],
        full_review_declared=False,
        dataset_orders={"WO-1"},
    )
    row = result["classifications"][0]
    assert row["outcome"] == "missed"
    assert "报了其他类型问题" in row["note"]


def test_ok_verdict_without_category_rejects_every_issue_on_order() -> None:
    issue_list = _issue_list(
        _issue("WO-1", "RF_RULE_A", "一致性问题"),
        _issue("WO-1", "RF_RULE_B", "时间合理性问题"),
    )
    result = reconcile_checklist(
        issue_list,
        [{"order_code": "WO-1", "verdict": "ok"}],
        full_review_declared=False,
        dataset_orders={"WO-1"},
    )
    rejected = [r for r in result["ledger_records"] if r["outcome"] == "rejected"]
    assert {r["rule_id"] for r in rejected} == {"RF_RULE_A", "RF_RULE_B"}


def test_ok_verdict_with_no_reported_issue_records_nothing() -> None:
    result = reconcile_checklist(
        _issue_list(),
        [{"order_code": "WO-1", "verdict": "ok"}],
        full_review_declared=False,
        dataset_orders={"WO-1"},
    )
    assert result["ledger_records"] == []
    assert result["classifications"][0]["outcome"] == "agreement"


def test_metrics_gating_partial_vs_full() -> None:
    classifications = [
        {"outcome": "confirmed"},
        {"outcome": "confirmed"},
        {"outcome": "confirmed"},
        {"outcome": "missed"},
        {"outcome": "rejected"},
    ]
    partial = compute_reconciliation_metrics(classifications, full_review_declared=False)
    assert partial["identification_rate"]["applicable"] is True
    assert partial["identification_rate"]["numerator"] == 3
    assert partial["identification_rate"]["denominator"] == 4
    assert "75%（3/4）" in partial["identification_rate"]["text"]
    assert partial["error_rate"]["applicable"] is False
    assert partial["error_rate"]["gating_reason"] == "partial_checklist"
    assert "不适用" in partial["error_rate"]["text"]

    classifications.append({"outcome": "tacit_confirmed"})
    full = compute_reconciliation_metrics(classifications, full_review_declared=True)
    assert full["error_rate"]["applicable"] is True
    assert full["error_rate"]["denominator"] == 5  # confirmed+rejected+tacit，missed 不进分母
    assert full["error_rate"]["numerator"] == 1


def test_normalize_rejects_bad_items_with_vocab_recall() -> None:
    with pytest.raises(ValueError, match="order_code"):
        normalize_checklist_items([{"verdict": "problem"}])
    with pytest.raises(ValueError, match="verdict"):
        normalize_checklist_items([{"order_code": "WO-1", "verdict": "maybe"}])
    with pytest.raises(ValueError, match="valid categories"):
        normalize_checklist_items(
            [{"order_code": "WO-1", "verdict": "problem", "problem_category": "不存在的分类"}]
        )
    with pytest.raises(ValueError, match="duplicate"):
        normalize_checklist_items(
            [
                {"order_code": "WO-1", "verdict": "problem"},
                {"order_code": "WO-1", "verdict": "problem"},
            ]
        )
    normalized = normalize_checklist_items(
        [{"order_code": " WO-1 ", "verdict": "有问题", "note": "读数对不上"}]
    )
    assert normalized[0]["order_code"] == "WO-1"
    assert normalized[0]["verdict"] == "problem"
    assert normalized[0]["item_id"] == "chk-001"


def test_ledger_append_roundtrip_and_idempotent_dedup() -> None:
    issue_list = _issue_list(_issue("WO-1", "RF_RULE_A", "一致性问题"))
    result = reconcile_checklist(
        issue_list,
        [{"order_code": "WO-1", "verdict": "problem", "problem_category": "一致性问题"}],
        full_review_declared=False,
        dataset_orders={"WO-1"},
    )
    first = append_reconciliation_to_ledger(result)
    assert first == {"appended": 1, "deduplicated": False, "existing_count": 0}
    second = append_reconciliation_to_ledger(result)
    assert second["appended"] == 0
    assert second["deduplicated"] is True
    # 修正后的清单（新增条目）哈希不同 → 形成新记录
    corrected = reconcile_checklist(
        issue_list,
        [{"order_code": "WO-1", "verdict": "ok", "problem_category": "一致性问题"}],
        full_review_declared=False,
        dataset_orders={"WO-1"},
    )
    third = append_reconciliation_to_ledger(corrected)
    assert third["appended"] == 1
    records = feedback_ledger.read_records()
    assert len(records) == 2
    assert all(r["channel"] == "checklist" for r in records)
    assert records[0]["outcome"] == "confirmed"


def test_execution_ref_derived_from_scheduled_path(tmp_path: Path) -> None:
    issue_path = (
        tmp_path
        / "scheduled_tasks"
        / "executions"
        / "gd_routine_work_order_audit"
        / "exec-123"
        / "ops_audit"
        / "final_issue_list.json"
    )
    issue_path.parent.mkdir(parents=True)
    issue_path.write_text(json.dumps(_issue_list(_issue("WO-1", "RF_RULE_A", "一致性问题"))), encoding="utf-8")
    result = reconcile_checklist(
        json.loads(issue_path.read_text(encoding="utf-8")),
        [{"order_code": "WO-1", "verdict": "problem", "problem_category": "一致性问题"}],
        full_review_declared=False,
        dataset_orders={"WO-1"},
        final_issue_list_path=issue_path,
    )
    record = result["ledger_records"][0]
    assert record["execution_ref"] == "gd_routine_work_order_audit/exec-123"
    assert record["snapshot_ref"] == result["source_sha256"]
    assert record["source_ref"] == str(issue_path)


def test_archive_reconciliation_writes_result_and_copies_source(tmp_path: Path) -> None:
    issue_path = tmp_path / "final_issue_list.json"
    issue_path.write_text(
        json.dumps(_issue_list(_issue("WO-1", "RF_RULE_A", "一致性问题"))), encoding="utf-8"
    )
    source_path = tmp_path / "user_checklist.xlsx"
    source_path.write_bytes(b"fake-xlsx-bytes")
    items = [{"order_code": "WO-1", "verdict": "problem", "problem_category": "一致性问题"}]
    result = reconcile_checklist(
        json.loads(issue_path.read_text(encoding="utf-8")),
        items,
        full_review_declared=True,
        dataset_orders={"WO-1"},
    )
    archive_dir = archive_reconciliation(
        result,
        final_issue_list_path=issue_path,
        checklist_source_path=source_path,
        checklist_items=items,
    )
    assert archive_dir.parent == issue_path.parent / "checklist_reconcile"
    archived = json.loads((archive_dir / "reconciliation.json").read_text(encoding="utf-8"))
    assert archived["reconciliation_id"] == result["reconciliation_id"]
    assert (archive_dir / "checklist_source.xlsx").read_bytes() == b"fake-xlsx-bytes"
    saved_items = json.loads((archive_dir / "checklist_items.json").read_text(encoding="utf-8"))
    assert saved_items[0]["order_code"] == "WO-1"


def test_echo_lines_are_human_readable(tmp_path: Path) -> None:
    issue_list = _issue_list(_issue("WO-1", "RF_RULE_A", "一致性问题"))
    result = reconcile_checklist(
        issue_list,
        [{"order_code": "WO-1", "verdict": "problem", "problem_category": "一致性问题"}],
        full_review_declared=False,
        dataset_orders={"WO-1"},
    )
    line = result["echo_lines"][0]
    assert "WO-1" in line and "说有问题" in line and "confirmed" in line and "RF_RULE_A" in line
