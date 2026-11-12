"""Tool-layer integration tests for the self-iteration agent tools."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.services.ops_audit import feedback_ledger
from app.tools.analysis.ops_audit_retrospective import tool as retrospective_tool


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path_factory, monkeypatch):
    ledger_dir = tmp_path_factory.mktemp("tool_ledger")
    memory_dir = tmp_path_factory.mktemp("tool_memory")
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
    monkeypatch.setattr(retrospective_tool, "get_memory_dir", lambda: memory_dir)


def _issue_list(*issues: dict) -> dict:
    return {"generated_at": "2026-11-11 00:00:00", "issue_count": len(issues), "items": list(issues)}


def test_reconcile_tool_end_to_end(tmp_path: Path) -> None:
    issue_path = tmp_path / "final_issue_list.json"
    issue_path.write_text(
        json.dumps(
            _issue_list(
                {
                    "working_order_code": "WO-1",
                    "rule_id": "RF_RULE_A",
                    "category": "一致性问题",
                    "message": "表单与附件不一致",
                    "review_status": "rule_detected",
                }
            )
        ),
        encoding="utf-8",
    )
    source_path = tmp_path / "checklist.txt"
    source_path.write_text("WO-1 表单和附件对不上", encoding="utf-8")

    result = asyncio.run(
        retrospective_tool.OpsAuditReconcileChecklistTool().execute(
            final_issue_list_path=str(issue_path),
            checklist_items=[
                {
                    "order_code": "WO-1",
                    "verdict": "problem",
                    "problem_category": "一致性问题",
                    "note": "表单和附件对不上",
                }
            ],
            full_review_declared=True,
            checklist_source_path=str(source_path),
            reviewer_name="张工",
        )
    )
    assert result["status"] == "success", result
    data = result["data"]
    assert data["metrics"]["counts"]["confirmed"] == 1
    assert data["ledger"] == {"appended": 1, "deduplicated": False, "existing_count": 0}
    assert data["echo_lines"] and "WO-1" in data["echo_lines"][0]
    assert Path(data["archive_dir"]).is_dir()
    ledger_records = feedback_ledger.read_records()
    assert len(ledger_records) == 1
    assert ledger_records[0]["channel"] == "checklist"
    assert ledger_records[0]["reviewer"] == {"name": "张工"}
    history = feedback_ledger.read_metrics_history()
    assert history[0]["kind"] == "checklist_reconciliation"
    assert history[0]["full_review_declared"] is True

    # 重复提交同一对账 → 幂等去重，metrics history 不再追加
    repeat = asyncio.run(
        retrospective_tool.OpsAuditReconcileChecklistTool().execute(
            final_issue_list_path=str(issue_path),
            checklist_items=[
                {
                    "order_code": "WO-1",
                    "verdict": "problem",
                    "problem_category": "一致性问题",
                    "note": "表单和附件对不上",
                }
            ],
            full_review_declared=True,
        )
    )
    assert repeat["data"]["ledger"]["deduplicated"] is True
    assert len(feedback_ledger.read_records()) == 1
    assert len(feedback_ledger.read_metrics_history()) == 1


def test_reconcile_tool_unknown_category_fails_with_vocab() -> None:
    result = asyncio.run(
        retrospective_tool.OpsAuditReconcileChecklistTool().execute(
            final_issue_list_path="whatever.json",
            checklist_items=[{"order_code": "WO-1", "verdict": "problem", "problem_category": "玄学分型"}],
            full_review_declared=False,
        )
    )
    assert result["status"] == "failed"
    assert "valid categories" in result["data"]["error"]


def test_stats_tool_end_to_end_without_recheck() -> None:
    # normalize_record 只在入账时打时间戳；统计期内的历史记录直接落文件
    record = feedback_ledger.normalize_record(
        {
            "channel": "panel",
            "outcome": "confirmed",
            "order_code": "WO-1",
            "rule_id": "RF_RULE_A",
        },
        recorded_at="2026-10-15T10:00:00",
    )
    ledger_path = feedback_ledger.default_ledger_path()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    result = asyncio.run(
        retrospective_tool.OpsAuditRetrospectiveStatsTool().execute(month="2026-10")
    )
    assert result["status"] == "success", result
    data = result["data"]
    assert data["month"] == "2026-10"
    assert data["record_count"] == 1
    assert data["panel_metrics"]["panel_confirm_rate"]["text"] == "面板确认率：100%（1/1）"
    assert Path(data["archive_path"]).is_file()
    history = feedback_ledger.read_metrics_history()
    assert history[-1]["kind"] == "monthly_retrospective"
    # 未开启回库分诊时不应有 db_recheck 段
    assert "db_recheck" not in data
