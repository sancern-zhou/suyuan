"""Retrospective stats layer + channel-3 DB recheck triage tests (phase 1 step 3)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.services.ops_audit import feedback_ledger
from app.services.ops_audit.retrospective_stats import (
    build_retrospective_stats,
    eligible_recheck_records,
    month_bounds,
    resolve_month,
    run_db_recheck,
)


@pytest.fixture(autouse=True)
def _isolate_ledger(tmp_path_factory, monkeypatch):
    ledger_dir = tmp_path_factory.mktemp("retro_ledger")
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


def _record(
    *,
    channel: str = "panel",
    outcome: str = "confirmed",
    order: str = "WO-1",
    rule: str | None = "RF_RULE_A",
    recorded_at: str = "2026-10-15T10:00:00",
    **extra,
) -> dict:
    return {
        "channel": channel,
        "outcome": outcome,
        "order_code": order,
        "rule_id": rule,
        "recorded_at": recorded_at,
        **extra,
    }


# ---------------------------------------------------------------- period

def test_resolve_month_default_and_validation() -> None:
    assert resolve_month(None, today=date(2026, 11, 11)) == "2026-10"
    assert resolve_month("2026-01", today=date(2026, 11, 11)) == "2026-01"
    assert resolve_month(None, today=date(2026, 1, 1)) == "2025-12"
    with pytest.raises(ValueError, match="YYYY-MM"):
        resolve_month("2026/10")
    start, end = month_bounds("2026-10")
    assert (start, end) == ("2026-10-01T00:00:00", "2026-11-01T00:00:00")


# ---------------------------------------------------------------- stats

def test_stats_period_filter_and_channel_counts() -> None:
    records = [
        _record(outcome="confirmed"),
        _record(outcome="rejected", order="WO-2"),
        _record(channel="checklist", outcome="missed", rule=None, order="WO-3"),
        _record(channel="db_recheck", outcome="verified", order="WO-4"),
        _record(outcome="confirmed", recorded_at="2026-09-20T10:00:00"),  # 期外
    ]
    stats = build_retrospective_stats(month="2026-10", records=records, metrics_history=[])
    assert stats["record_count"] == 4
    assert stats["counts_by_channel_outcome"]["panel"] == {"confirmed": 1, "rejected": 1}
    assert stats["counts_by_channel_outcome"]["checklist"] == {"missed": 1}
    assert stats["counts_by_channel_outcome"]["db_recheck"] == {"verified": 1}


def test_checklist_metrics_from_history_with_gating() -> None:
    history = [
        {
            "kind": "checklist_reconciliation",
            "recorded_at": "2026-10-05T09:00:00",
            "full_review_declared": True,
            "metrics": {
                "identification_rate": {"numerator": 7, "denominator": 9},
                "error_rate": {"numerator": 2, "denominator": 10},
            },
        },
        {
            "kind": "checklist_reconciliation",
            "recorded_at": "2026-10-12T09:00:00",
            "full_review_declared": False,  # 部分清单：只进识别率
            "metrics": {
                "identification_rate": {"numerator": 7, "denominator": 9},
                "error_rate": {"numerator": 0, "denominator": 0},
            },
        },
        {
            "kind": "checklist_reconciliation",
            "recorded_at": "2026-09-01T09:00:00",  # 期外
            "full_review_declared": True,
            "metrics": {
                "identification_rate": {"numerator": 99, "denominator": 99},
                "error_rate": {"numerator": 99, "denominator": 99},
            },
        },
    ]
    stats = build_retrospective_stats(month="2026-10", records=[], metrics_history=history)
    checklist = stats["checklist_metrics"]
    assert checklist["source"] == "metrics_history"
    assert checklist["reconciliation_count"] == 2
    assert checklist["identification_rate"]["numerator"] == 14
    assert checklist["identification_rate"]["denominator"] == 18
    assert "78%（14/18）" in checklist["identification_rate"]["text"]
    # 错误率分母只累计全量声明的对账
    assert checklist["error_rate"]["numerator"] == 2
    assert checklist["error_rate"]["denominator"] == 10
    assert checklist["error_rate"]["applicable"] is True


def test_checklist_metrics_ledger_fallback_without_history() -> None:
    records = [
        _record(channel="checklist", outcome="confirmed"),
        _record(channel="checklist", outcome="confirmed"),
        _record(channel="checklist", outcome="missed", rule=None),
        _record(channel="checklist", outcome="tacit_confirmed"),
        _record(channel="checklist", outcome="rejected"),
    ]
    stats = build_retrospective_stats(month="2026-10", records=records, metrics_history=[])
    checklist = stats["checklist_metrics"]
    assert checklist["source"] == "ledger_fallback"
    assert (checklist["identification_rate"]["numerator"], checklist["identification_rate"]["denominator"]) == (2, 3)
    assert checklist["error_rate"]["applicable"] is True
    assert (checklist["error_rate"]["numerator"], checklist["error_rate"]["denominator"]) == (1, 4)


def test_error_rate_inapplicable_without_full_declaration() -> None:
    records = [
        _record(channel="checklist", outcome="confirmed"),
        _record(channel="checklist", outcome="rejected"),
    ]
    stats = build_retrospective_stats(month="2026-10", records=records, metrics_history=[])
    assert stats["checklist_metrics"]["error_rate"]["applicable"] is False
    assert "不适用" in stats["checklist_metrics"]["error_rate"]["text"]


def test_by_rule_overturn_and_null_rule_last() -> None:
    records = [
        _record(rule="RF_RULE_A", outcome="confirmed"),
        _record(rule="RF_RULE_A", outcome="rejected"),
        _record(rule="RF_RULE_A", outcome="rejected"),
        _record(rule="RF_RULE_B", outcome="confirmed"),
        _record(rule=None, channel="checklist", outcome="missed"),  # missed 不进推翻率
        _record(rule=None, outcome="rejected"),  # 语义项被排除 → null 桶进推翻率
    ]
    stats = build_retrospective_stats(month="2026-10", records=records, metrics_history=[])
    rows = stats["by_rule"]
    assert rows[0]["rule_id"] == "RF_RULE_A"
    assert rows[0]["overturn_rate"] == 0.6667
    assert "67%（2/3）" in rows[0]["overturn_text"]
    assert rows[-1]["rule_id"] is None
    assert rows[-1]["rejected"] == 1
    a_row = next(r for r in rows if r["rule_id"] == "RF_RULE_A")
    assert a_row["confirmed"] == 1 and a_row["rejected"] == 2
    assert all(row["rule_id"] != "RF_RULE_B" or row["overturn_rate"] == 0.0 for row in rows)


def test_candidate_new_rules_and_calibration() -> None:
    records = [
        _record(channel="checklist", outcome="missed", rule=None, order="WO-9", reason="现场有照片但没报"),
        _record(channel="checklist", outcome="missed", rule=None, order="WO-8"),
        _record(channel="panel", outcome="confirmed", original_judgment="pending_semantic_review"),
        _record(channel="panel", outcome="rejected", original_judgment="rule_detected"),
    ]
    stats = build_retrospective_stats(month="2026-10", records=records, metrics_history=[])
    candidates = stats["candidate_new_rules"]
    assert candidates["missed_without_rule_count"] == 2
    assert candidates["samples"][0]["order_code"] in {"WO-9", "WO-8"}
    calibration = {row["original_judgment"]: row for row in stats["calibration"]}
    assert calibration["rule_detected"]["outcomes"] == {"rejected": 1}
    assert calibration["pending_semantic_review"]["outcomes"] == {"confirmed": 1}


def test_rolling_window_excludes_old_records() -> None:
    records = [
        _record(channel="checklist", outcome="confirmed", recorded_at="2026-11-02T10:00:00"),
        _record(channel="checklist", outcome="missed", rule=None, recorded_at="2026-11-03T10:00:00"),
        _record(channel="panel", outcome="rejected", recorded_at="2026-11-04T10:00:00"),
        _record(channel="panel", outcome="confirmed", recorded_at="2026-05-04T10:00:00"),  # 窗口外
    ]
    stats = build_retrospective_stats(
        month="2026-10", records=records, metrics_history=[], today=date(2026, 11, 11)
    )
    rolling = stats["rolling"]
    assert rolling["checklist_identification_rate"]["numerator"] == 1
    assert rolling["checklist_identification_rate"]["denominator"] == 2
    assert rolling["panel_exclude_rate"]["denominator"] == 1  # 只含窗口内的 panel 记录


def test_panel_parallel_ratios() -> None:
    records = [
        _record(channel="panel", outcome="confirmed"),
        _record(channel="panel", outcome="confirmed"),
        _record(channel="panel", outcome="confirmed"),
        _record(channel="panel", outcome="rejected"),
    ]
    stats = build_retrospective_stats(month="2026-10", records=records, metrics_history=[])
    assert stats["panel_metrics"]["panel_confirm_rate"]["text"] == "面板确认率：75%（3/4）"
    assert stats["panel_metrics"]["panel_exclude_rate"]["text"] == "面板排除率：25%（1/4）"


# ---------------------------------------------------------------- recheck

def _rejected(**extra) -> dict:
    return _record(outcome="rejected", **extra)


def test_eligible_recheck_filters() -> None:
    records = [
        _rejected(order="WO-1", rule="RF_A"),
        _rejected(order="WO-2", rule=None),   # 语义项无法复跑
        _rejected(order="", rule="RF_A"),     # 无工单号
        _record(outcome="confirmed"),
    ]
    eligible = eligible_recheck_records(records)
    assert [r["order_code"] for r in eligible] == ["WO-1"]


def _fake_fetch(issues_by_order: dict[str, list[dict]], orders: set[str], dataset: dict):
    def fetch(codes: list[str]) -> dict:
        flat = []
        for code in codes:
            for issue in issues_by_order.get(code, []):
                flat.append({"working_order_code": code, **issue})
        return {"issues": flat, "dataset": dataset, "dataset_orders": orders}

    return fetch


def test_recheck_triage_verified_on_same_fingerprint(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"orders": [{"working_order_code": "WO-1", "status": "Finish"}]}), encoding="utf-8"
    )
    dataset = {"orders": [{"working_order_code": "WO-1", "status": "Finish"}]}
    result = run_db_recheck(
        [_rejected(order="WO-1", rule="RF_A")],
        month="2026-10",
        fetch_and_run=_fake_fetch({"WO-1": [{"rule_id": "RF_A", "message": "m"}]}, {"WO-1"}, dataset),
        baseline_dataset_for=lambda record: baseline,
        output_dir=tmp_path / "recheck",
    )
    assert result["counts"] == {"verified": 1}
    assert result["ledger_records"][0]["channel"] == "db_recheck"
    assert result["ledger_records"][0]["explicit"] is False
    assert result["archive_path"] and Path(result["archive_path"]).is_file()


def test_recheck_triage_data_drifted_on_fingerprint_change(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"orders": [{"working_order_code": "WO-1", "remark": "旧"}]}), encoding="utf-8"
    )
    dataset = {"orders": [{"working_order_code": "WO-1", "remark": "事后补录"}]}
    result = run_db_recheck(
        [_rejected(order="WO-1", rule="RF_A")],
        month="2026-10",
        fetch_and_run=_fake_fetch({"WO-1": [{"rule_id": "RF_A", "message": "新"}]}, {"WO-1"}, dataset),
        baseline_dataset_for=lambda record: baseline,
    )
    assert result["counts"] == {"data_drifted": 1}
    assert "数据管道" in result["triage"][0]["reason"]


def test_recheck_triage_evidence_mismatch_when_data_unchanged_but_rule_silent(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"orders": [{"working_order_code": "WO-1", "status": "Finish"}]}), encoding="utf-8"
    )
    dataset = {"orders": [{"working_order_code": "WO-1", "status": "Finish"}]}
    result = run_db_recheck(
        [_rejected(order="WO-1", rule="RF_A")],
        month="2026-10",
        fetch_and_run=_fake_fetch({}, {"WO-1"}, dataset),
        baseline_dataset_for=lambda record: baseline,
    )
    assert result["counts"] == {"evidence_mismatch": 1}


def test_recheck_triage_order_missing_is_data_drifted() -> None:
    result = run_db_recheck(
        [_rejected(order="WO-1", rule="RF_A")],
        month="2026-10",
        fetch_and_run=_fake_fetch({}, set(), {"orders": []}),
        baseline_dataset_for=lambda record: None,
    )
    assert result["counts"] == {"data_drifted": 1}


def test_recheck_fallback_without_baseline(tmp_path: Path) -> None:
    dataset = {"orders": [{"working_order_code": "WO-1"}]}
    fires = run_db_recheck(
        [_rejected(order="WO-1", rule="RF_A")],
        month="2026-10",
        fetch_and_run=_fake_fetch({"WO-1": [{"rule_id": "RF_A", "message": "m"}]}, {"WO-1"}, dataset),
        baseline_dataset_for=lambda record: None,
    )
    silent = run_db_recheck(
        [_rejected(order="WO-1", rule="RF_A")],
        month="2026-10",
        fetch_and_run=_fake_fetch({}, {"WO-1"}, dataset),
        baseline_dataset_for=lambda record: None,
    )
    assert fires["counts"] == {"verified": 1}
    assert "无基线" in fires["triage"][0]["reason"]
    assert silent["counts"] == {"evidence_mismatch": 1}


def test_recheck_no_eligible_records_short_circuits() -> None:
    result = run_db_recheck(
        [_record(outcome="confirmed"), _rejected(order="WO-2", rule=None)],
        month="2026-10",
        fetch_and_run=_fake_fetch({}, set(), {"orders": []}),
    )
    assert result["eligible_count"] == 0
    assert result["counts"] == {}
    assert result["skipped"] == [{"order_code": "WO-2", "reason": "missing rule_id"}]


def test_recheck_ledger_records_append_validly(tmp_path: Path) -> None:
    dataset = {"orders": [{"working_order_code": "WO-1"}]}
    result = run_db_recheck(
        [
            _rejected(order="WO-1", rule="RF_A"),
            _rejected(order="WO-1", rule="RF_A"),  # 同工单同规则去重后仍各记一条
        ],
        month="2026-10",
        fetch_and_run=_fake_fetch({"WO-1": [{"rule_id": "RF_A", "message": "m"}]}, {"WO-1"}, dataset),
        baseline_dataset_for=lambda record: None,
    )
    written = feedback_ledger.append_records(result["ledger_records"], path=tmp_path / "l.jsonl")
    assert len(written) == 2
    assert {r["outcome"] for r in written} == {"verified"}
    assert written[0]["feedback_id"] == "db_recheck:2026-10"
