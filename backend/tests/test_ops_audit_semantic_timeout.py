import time

from app.services.ops_audit.semantic import reviewer


def test_semantic_batch_timeout_returns_partial_results(monkeypatch):
    monkeypatch.setattr(reviewer, "SEMANTIC_BATCH_TOTAL_TIMEOUT_SECONDS", 0.05)

    def slow_no_device_batch(*args, **kwargs):
        time.sleep(2)
        return {}

    def fast_pm_tape_batch(tasks, audit_records, dataset_orders, details_by_code, rf_forms_by_code):
        task = tasks[0]
        code = str(task["working_order_code"])
        return {
            code: reviewer._build_semantic_task_result(
                task,
                audit_records.get(code, {}),
                dataset_orders.get(code, {}),
                "cleared",
                "fast batch completed",
                0.8,
                {
                    "is_complete": True,
                    "has_cause": True,
                    "has_action": True,
                    "has_result": True,
                    "problem_description": "",
                    "confidence": 0.8,
                    "remark": "ok",
                },
                [],
                "ok",
            )
        }

    monkeypatch.setattr(reviewer, "_review_no_device_tasks_batch", slow_no_device_batch)
    monkeypatch.setattr(reviewer, "_review_pm_tape_usage_tasks_batch", fast_pm_tape_batch)

    audit = {
        "records": [
            _record_with_issue("WO-SLOW", "RF_NO_DEVICE_WITHOUT_REMARK"),
            _record_with_issue("WO-FAST", "RF_PM_TAPE_USAGE_INVALID"),
        ]
    }
    start = time.monotonic()

    results = reviewer.build_semantic_review_results(audit, {"orders": [], "details": [], "rf_forms": {}})

    elapsed = time.monotonic() - start
    by_code = {result["working_order_code"]: result for result in results["results"]}
    assert elapsed < 1
    assert by_code["WO-FAST"]["review_status"] == "completed"
    assert by_code["WO-SLOW"]["review_status"] == "timeout"
    assert by_code["WO-SLOW"]["judgment"] == "needs_followup"


def _record_with_issue(code: str, rule_id: str) -> dict:
    issue = {
        "rule_id": rule_id,
        "severity": "中",
        "category": "规范性问题",
        "assessment": "candidate_issue",
        "field": f"rf.{rule_id}",
        "message": rule_id,
        "evidence": "{}",
    }
    return {
        "working_order_code": code,
        "station_id": "1",
        "order_type": "Check",
        "maintenance_type": "Week",
        "finish_time": "2026-05-27 10:00:00",
        "audit_level": "待确认问题",
        "attachment_count": 0,
        "workflow_steps": [],
        "rf_tables": [],
        "issues": [issue],
        "scoring_issues": [issue],
    }
