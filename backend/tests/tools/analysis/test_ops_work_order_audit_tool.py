import asyncio
import threading

from app.tools.analysis.ops_work_order_audit import tool as audit_tool


async def test_run_rules_keeps_event_loop_schedulable(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text("{}", encoding="utf-8")
    rules_started = threading.Event()
    event_loop_progressed = threading.Event()

    def blocking_run_rules(*args, **kwargs):
        rules_started.set()
        progressed_while_running = event_loop_progressed.wait(timeout=2)
        return {"probe_ran_while_rules_running": progressed_while_running}

    async def event_loop_probe():
        while not rules_started.is_set():
            await asyncio.sleep(0)
        event_loop_progressed.set()

    monkeypatch.setattr(audit_tool, "run_ops_audit_rules", blocking_run_rules)

    result, _ = await asyncio.gather(
        audit_tool.OpsAuditRunRulesTool().execute(dataset_path=str(dataset_path)),
        event_loop_probe(),
    )

    assert result["success"] is True
    assert result["data"]["probe_ran_while_rules_running"] is True


async def test_run_rules_preserves_arguments_and_context_data(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.json"
    output_dir = tmp_path / "output"
    dataset_path.write_text("{}", encoding="utf-8")
    captured = {}

    def fake_run_rules(path, **kwargs):
        captured["path"] = path
        captured.update(kwargs)
        return {"summary": {"audit_level_counts": {}}, "business_review": {}}

    class Context:
        def save_data(self, **kwargs):
            captured["saved"] = kwargs
            return "ops-audit-data-id"

    monkeypatch.setattr(audit_tool, "run_ops_audit_rules", fake_run_rules)

    result = await audit_tool.OpsAuditRunRulesTool().execute(
        context=Context(),
        dataset_path=str(dataset_path),
        output_dir=str(output_dir),
        evidence_level="detail",
        enable_visual=False,
    )

    assert captured["path"] == dataset_path.resolve()
    assert captured["output_dir"] == output_dir
    assert captured["evidence_level"] == "detail"
    assert captured["enable_visual"] is False
    assert captured["saved"]["schema"] == "ops_audit_rule_summary"
    assert captured["saved"]["metadata"]["dataset_path"] == str(dataset_path.resolve())
    assert result["data_id"] == "ops-audit-data-id"
    assert result["metadata"]["data_id"] == "ops-audit-data-id"


async def test_run_rules_preserves_failure_contract(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text("{}", encoding="utf-8")

    def fail_run_rules(*args, **kwargs):
        raise RuntimeError("rules exploded")

    monkeypatch.setattr(audit_tool, "run_ops_audit_rules", fail_run_rules)

    result = await audit_tool.OpsAuditRunRulesTool().execute(
        dataset_path=str(dataset_path)
    )

    assert result["status"] == "failed"
    assert result["success"] is False
    assert "rules exploded" in result["summary"]
    assert result["metadata"]["error"] == "rules exploded"


async def test_concurrent_rule_runs_are_serialized(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text("{}", encoding="utf-8")
    second_run_started = threading.Event()
    state_lock = threading.Lock()
    active_runs = 0
    maximum_active_runs = 0
    call_count = 0

    def blocking_run_rules(*args, **kwargs):
        nonlocal active_runs, maximum_active_runs, call_count
        with state_lock:
            call_count += 1
            call_index = call_count
            active_runs += 1
            maximum_active_runs = max(maximum_active_runs, active_runs)
        if call_index == 1:
            second_run_started.wait(timeout=0.5)
        else:
            second_run_started.set()
        with state_lock:
            active_runs -= 1
        return {}

    monkeypatch.setattr(audit_tool, "run_ops_audit_rules", blocking_run_rules)

    await asyncio.gather(
        audit_tool.OpsAuditRunRulesTool().execute(dataset_path=str(dataset_path)),
        audit_tool.OpsAuditRunRulesTool().execute(dataset_path=str(dataset_path)),
    )

    assert maximum_active_runs == 1
