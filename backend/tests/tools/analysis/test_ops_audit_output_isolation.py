from types import SimpleNamespace

from app.services.ops_work_order_audit_engine import OUTPUT_DIR
from app.tools.analysis.ops_work_order_audit import tool as audit_tool
from app.utils.path_config import get_memory_dir


def _scheduled_context(*, task_id: str, execution_id: str):
    return SimpleNamespace(
        scheduled_task_context={
            "task_id": task_id,
            "execution_id": execution_id,
        }
    )


def test_default_output_dir_uses_configured_data_registry():
    assert OUTPUT_DIR == get_memory_dir() / "ops" / "audit"


def test_scheduled_output_dir_is_isolated_by_execution(monkeypatch, tmp_path):
    monkeypatch.setattr(audit_tool, "get_data_registry", lambda: tmp_path)

    first = audit_tool._effective_audit_output_dir(
        _scheduled_context(task_id="weekly/audit", execution_id="exec/one"),
        "/tmp/model-selected-shared-dir",
    )
    second = audit_tool._effective_audit_output_dir(
        _scheduled_context(task_id="weekly/audit", execution_id="exec/two"),
        "/tmp/model-selected-shared-dir",
    )

    assert first == (
        tmp_path
        / "scheduled_tasks"
        / "executions"
        / "weekly_audit"
        / "exec_one"
        / "ops_audit"
    ).resolve()
    assert second == (
        tmp_path
        / "scheduled_tasks"
        / "executions"
        / "weekly_audit"
        / "exec_two"
        / "ops_audit"
    ).resolve()
    assert first != second


async def test_scheduled_fetch_forces_execution_output_dir(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(audit_tool, "get_data_registry", lambda: tmp_path)

    def fake_fetch(config):
        captured["output_dir"] = config.output_dir
        return {"summary": {}, "query_info": {}, "audit_window": None}

    monkeypatch.setattr(audit_tool, "fetch_ops_audit_dataset", fake_fetch)
    context = _scheduled_context(task_id="task-1", execution_id="exec-1")

    result = await audit_tool.OpsAuditFetchDatasetTool().execute(
        context=context,
        output_dir=str(tmp_path / "shared"),
    )

    expected = (
        tmp_path / "scheduled_tasks" / "executions" / "task-1" / "exec-1" / "ops_audit"
    ).resolve()
    assert result["success"] is True
    assert captured["output_dir"] == expected


async def test_scheduled_rules_force_same_execution_output_dir(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text("{}", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(audit_tool, "get_data_registry", lambda: tmp_path)

    def fake_run_rules(path, **kwargs):
        captured["dataset_path"] = path
        captured.update(kwargs)
        return {"summary": {"audit_level_counts": {}}, "business_review": {}}

    monkeypatch.setattr(audit_tool, "run_ops_audit_rules", fake_run_rules)
    context = _scheduled_context(task_id="task-1", execution_id="exec-1")

    result = await audit_tool.OpsAuditRunRulesTool().execute(
        context=context,
        dataset_path=str(dataset_path),
        output_dir=str(tmp_path / "shared"),
        enable_visual=False,
    )

    expected = (
        tmp_path / "scheduled_tasks" / "executions" / "task-1" / "exec-1" / "ops_audit"
    ).resolve()
    assert result["success"] is True
    assert captured["dataset_path"] == dataset_path.resolve()
    assert captured["output_dir"] == expected
