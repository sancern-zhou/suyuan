import json
from pathlib import Path

import pytest

from app.services.ops_audit import feedback_ledger
from app.services.ops_audit.final_issue_list import ensure_issue_ids
from app.services.ops_audit.review_artifacts import (
    apply_human_feedback,
    build_human_feedback_request,
    persist_report_input,
)


@pytest.fixture(autouse=True)
def _isolate_feedback_ledger(tmp_path_factory, monkeypatch):
    ledger_dir = tmp_path_factory.mktemp("feedback_ledger")
    monkeypatch.setattr(
        feedback_ledger,
        "default_ledger_path",
        lambda: ledger_dir / feedback_ledger.LEDGER_FILENAME,
    )


def test_append_query_roundtrip(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    written = feedback_ledger.append_records(
        [
            {
                "channel": "panel",
                "outcome": "confirmed",
                "order_code": "WO-1",
                "rule_id": "RF_RANGE_OUT_OF_SPEC",
                "reason": "已核对原始记录",
            },
            {
                "channel": "panel",
                "outcome": "rejected",
                "order_code": "WO-2",
                "rule_id": None,
                "reason": "",
            },
        ],
        path=ledger,
    )

    assert len(written) == 2
    assert written[0]["schema_version"] == feedback_ledger.LEDGER_SCHEMA_VERSION
    assert written[0]["recorded_at"]
    assert written[1]["reason"] is None
    assert feedback_ledger.query_records(path=ledger, rule_id="RF_RANGE_OUT_OF_SPEC")[0][
        "order_code"
    ] == "WO-1"
    assert feedback_ledger.query_records(path=ledger, outcome="rejected")[0][
        "order_code"
    ] == "WO-2"
    assert (
        feedback_ledger.query_records(path=ledger, channel="checklist") == []
    )


def test_append_rejects_unknown_channel_outcome_and_missing_order(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    with pytest.raises(ValueError, match="channel"):
        feedback_ledger.append_records(
            [{"channel": "web", "outcome": "confirmed", "order_code": "WO-1"}], path=ledger
        )
    with pytest.raises(ValueError, match="outcome"):
        feedback_ledger.append_records(
            [{"channel": "panel", "outcome": "maybe", "order_code": "WO-1"}], path=ledger
        )
    with pytest.raises(ValueError, match="order_code"):
        feedback_ledger.append_records(
            [{"channel": "panel", "outcome": "confirmed"}], path=ledger
        )
    assert not ledger.exists()


def test_read_records_skips_malformed_lines(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    good = feedback_ledger.normalize_record(
        {"channel": "panel", "outcome": "confirmed", "order_code": "WO-1"}
    )
    ledger.write_text(
        json.dumps(good, ensure_ascii=False) + "\n{not json\n\n", encoding="utf-8"
    )

    records = feedback_ledger.read_records(path=ledger)

    assert [record["order_code"] for record in records] == ["WO-1"]


def test_aggregate_by_rule_groups_outcomes() -> None:
    records = [
        {"rule_id": "RF_X", "channel": "panel", "outcome": "confirmed"},
        {"rule_id": "RF_X", "channel": "panel", "outcome": "rejected"},
        {"rule_id": None, "channel": "panel", "outcome": "missed"},
        {"rule_id": "RF_X", "channel": "db_recheck", "outcome": "confirmed"},
    ]

    aggregated = feedback_ledger.aggregate_by_rule(records, channel="panel")

    assert aggregated == {
        "RF_X": {"confirmed": 1, "rejected": 1},
        None: {"missed": 1},
    }


def test_derive_execution_ref_extracts_scheduled_task_scope() -> None:
    scheduled = Path(
        "D:/registry/scheduled_tasks/executions/gd_routine_work_order_audit/exec-42/ops_audit/x.json"
    )
    interactive = Path("D:/registry/memory/ops/audit/x.json")

    assert feedback_ledger.derive_execution_ref(scheduled) == (
        "gd_routine_work_order_audit/exec-42"
    )
    assert feedback_ledger.derive_execution_ref(interactive) is None


def _panel_issue_list() -> dict:
    result = {
        "generated_at": "2026-11-11 10:00:00",
        "issue_count": 2,
        "items": [
            {
                "working_order_code": "WO-1",
                "station_id": "ST-01",
                "rf_table": "RF_W_PMCHECK",
                "rule_id": "RF_RANGE_OUT_OF_SPEC",
                "review_status": "rule_detected",
                "needs_manual_review": True,
                "message": "高压电源超出正常范围",
                "evidence": json.dumps({"value": 701}, ensure_ascii=False),
            },
            {
                "working_order_code": "WO-2",
                "station_id": "ST-02",
                "rf_table": "RF_W_GASEOUSCHECK_O3",
                "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
                "remark_review_status": "pending_semantic_review",
                "needs_manual_review": True,
                "message": "臭氧周检异常值备注为占位符",
                "evidence": json.dumps({"value": 5.2}, ensure_ascii=False),
            },
        ],
        "pending_semantic_reviews": [
            {
                "review_item_id": "WO-3::PM10::TAPEUSAGEDISPOSAL",
                "working_order_code": "WO-3",
                "conclusion": "耗材使用/处置情况语义复核未完成。",
            }
        ],
    }
    return ensure_issue_ids(result)


def _apply_panel_feedback(report_path: Path, report: dict, decisions: list[dict]) -> dict:
    return apply_human_feedback(
        report_path,
        decisions,
        expected_source_sha256=report["source"]["sha256"],
        feedback_id="feedback-test",
        reviewer={"user_id": "operator-1"},
    )


def test_panel_feedback_appends_ledger_records(tmp_path: Path) -> None:
    issue_list = _panel_issue_list()
    source_path = tmp_path / "final_issue_list.json"
    report_path = tmp_path / "latest_finished_work_orders_report_input.json"
    source_path.write_text(json.dumps(issue_list, ensure_ascii=False), encoding="utf-8")
    report = persist_report_input(issue_list, report_path, source_path=source_path)
    request = build_human_feedback_request(report, report_input_path=report_path)

    result = _apply_panel_feedback(
        report_path,
        report,
        [
            {"item_id": request["items"][0]["item_id"], "decision": "include", "comment": "已核对"},
            {"item_id": request["items"][1]["item_id"], "decision": "exclude", "comment": "设备不适用"},
            {"item_id": "WO-3::PM10::TAPEUSAGEDISPOSAL", "decision": "pending"},
        ],
    )

    assert result["feedback_ledger_count"] == 2
    records = feedback_ledger.read_records()
    assert len(records) == 2
    by_order = {record["order_code"]: record for record in records}
    confirmed, rejected = by_order["WO-1"], by_order["WO-2"]
    assert confirmed["channel"] == "panel"
    assert confirmed["outcome"] == "confirmed"
    assert confirmed["rule_id"] == "RF_RANGE_OUT_OF_SPEC"
    assert confirmed["original_judgment"] == "rule_detected"
    assert confirmed["station_id"] == "ST-01"
    assert confirmed["explicit"] is True
    assert rejected["outcome"] == "rejected"
    # remark_review_status is the fallback judgment when review_status is absent.
    assert rejected["original_judgment"] == "pending_semantic_review"
    for record in records:
        assert record["feedback_id"] == "feedback-test"
        assert record["snapshot_ref"] == report["source"]["sha256"]
        assert record["source_ref"] == str(source_path)
        assert record["execution_ref"] is None


def test_semantic_review_decision_records_matched_item(tmp_path: Path) -> None:
    issue_list = _panel_issue_list()
    issue_list["items"] = [
        {
            "working_order_code": "WO-3",
            "station_id": "ST-03",
            "rule_id": "RF_TAPE_DISPOSAL_REMARK",
            "review_stage": "semantic_remark",
            "review_status": "pending_semantic_review",
            "message": "耗材处置备注待确认",
            "evidence": json.dumps({}, ensure_ascii=False),
        }
    ]
    source_path = tmp_path / "final_issue_list.json"
    report_path = tmp_path / "latest_finished_work_orders_report_input.json"
    source_path.write_text(json.dumps(issue_list, ensure_ascii=False), encoding="utf-8")
    report = persist_report_input(issue_list, report_path, source_path=source_path)

    result = _apply_panel_feedback(
        report_path,
        report,
        [
            {
                "item_id": "WO-3::PM10::TAPEUSAGEDISPOSAL",
                "decision": "exclude",
                "comment": "耗材说明充分",
            }
        ],
    )

    assert result["feedback_ledger_count"] == 1
    record = feedback_ledger.read_records()[0]
    assert record["order_code"] == "WO-3"
    assert record["rule_id"] == "RF_TAPE_DISPOSAL_REMARK"
    assert record["outcome"] == "rejected"
    assert record["original_judgment"] == "pending_semantic_review"
    assert record["item_id"] == "WO-3::PM10::TAPEUSAGEDISPOSAL"


def test_ledger_failure_does_not_break_applied_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(records, *, path=None):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(feedback_ledger, "append_records", _boom)
    issue_list = _panel_issue_list()
    source_path = tmp_path / "final_issue_list.json"
    report_path = tmp_path / "latest_finished_work_orders_report_input.json"
    source_path.write_text(json.dumps(issue_list, ensure_ascii=False), encoding="utf-8")
    report = persist_report_input(issue_list, report_path, source_path=source_path)
    request = build_human_feedback_request(report, report_input_path=report_path)

    result = _apply_panel_feedback(
        report_path,
        report,
        [
            {"item_id": request["items"][0]["item_id"], "decision": "include", "comment": ""},
            {"item_id": request["items"][1]["item_id"], "decision": "exclude", "comment": ""},
            {"item_id": "WO-3::PM10::TAPEUSAGEDISPOSAL", "decision": "pending"},
        ],
    )

    assert result["feedback_ledger_count"] == 0
    updated = json.loads(report_path.read_text(encoding="utf-8"))
    assert updated["summary"]["pending_review_count"] == 0
    assert feedback_ledger.read_records() == []
