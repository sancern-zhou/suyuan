import asyncio
import threading

from app.tools.analysis.ops_work_order_audit import tool as audit_tool


async def test_run_rules_keeps_event_loop_schedulable(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text("{}", encoding="utf-8")
    event_loop_progressed = threading.Event()

    def blocking_run_rules(*args, **kwargs):
        progressed_while_running = event_loop_progressed.wait(timeout=0.5)
        return {"probe_ran_while_rules_running": progressed_while_running}

    async def event_loop_probe():
        await asyncio.sleep(0)
        event_loop_progressed.set()

    monkeypatch.setattr(audit_tool, "run_ops_audit_rules", blocking_run_rules)

    result, _ = await asyncio.gather(
        audit_tool.OpsAuditRunRulesTool().execute(dataset_path=str(dataset_path)),
        event_loop_probe(),
    )

    assert result["success"] is True
    assert result["data"]["probe_ran_while_rules_running"] is True
