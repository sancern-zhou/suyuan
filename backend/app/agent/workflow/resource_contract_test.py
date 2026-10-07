import pytest

from app.agent.workflow.coordinator import WorkflowCoordinator
from app.agent.workflow.resource_contract import assert_resource_contracts, ResourceContractError


def handle(path, **metadata):
    return {"source_task_id": "fetch", "file_path": str(path), "kind": "data", "format": "csv",
            "metadata": {"data_contract": metadata}}


def test_fields_checked_against_actual_file_not_claimed_schema(tmp_path):
    path = tmp_path / "air.csv"
    path.write_text("time,pm25\n2026-10-01,42\n", encoding="utf-8")
    ref = handle(path, fields=["time", "pm25", "wind"])
    assert_resource_contracts([{"source_task_id": "fetch", "fields": ["time", "pm25"]}], [ref])
    with pytest.raises(ResourceContractError, match="missing fields"):
        assert_resource_contracts([{"source_task_id": "fetch", "fields": ["wind"]}], [ref])
    path.unlink()
    with pytest.raises(ResourceContractError, match="missing"):
        assert_resource_contracts([{"source_task_id": "fetch"}], [ref])


def test_units_grain_scope_and_covering_time_range(tmp_path):
    path = tmp_path / "air.csv"
    path.write_text("pm25\n42\n", encoding="utf-8")
    ref = handle(path, units={"pm25": "ug/m3"}, granularity="hour", scope={"city": "xuchang"},
                 time_range={"start": "2026-10-01", "end": "2026-10-03"})
    contract = {"source_task_id": "fetch", "kind": "data", "format": "csv", "fields": ["pm25"],
                "units": {"pm25": "ug/m3"}, "granularity": "hour", "scope": {"city": "xuchang"},
                "time_range": {"start": "2026-10-01T12:00:00Z", "end": "2026-10-02"}}
    assert_resource_contracts([contract], [ref])
    for patch in [{"units": {"pm25": "mg/m3"}}, {"granularity": "day"}, {"scope": {"city": "other"}},
                  {"time_range": {"start": "2026-09-30", "end": "2026-10-02"}}]:
        with pytest.raises(ResourceContractError):
            assert_resource_contracts([{**contract, **patch}], [ref])
    with pytest.raises(ResourceContractError, match="missing"):
        assert_resource_contracts([contract], [{**ref, "metadata": {}}])


def test_existing_data_shape_is_accepted_for_large_json_fields(tmp_path):
    path = tmp_path / "large.json"
    path.write_text('{"data": []}' + ' ' * (2 * 1024 * 1024), encoding="utf-8")
    ref = {"source_task_id": "fetch", "file_path": str(path), "kind": "data", "format": "json",
           "metadata": {"data_shape": {"columns": [{"name": "pm25", "type": "float"}], "row_count": 0}}}
    assert_resource_contracts([{"source_task_id": "fetch", "fields": ["pm25"]}], [ref])
    with pytest.raises(ResourceContractError, match="unit"):
        assert_resource_contracts([{"source_task_id": "fetch", "units": {"pm25": "ug/m3"}}], [ref])


@pytest.mark.asyncio
async def test_missing_resource_stops_downstream_before_executor_and_persists_violations():
    calls = []

    async def execute(node, *args):
        calls.append(node.task_id)
        return {"success": True}

    coordinator = WorkflowCoordinator({"workflow_id": "contract", "nodes": [
        {"task_id": "fetch"}, {"task_id": "analysis", "dependencies": ["fetch"],
                               "input_contracts": [{"source_task_id": "fetch", "fields": ["pm25"]}]},
    ]}, executor=execute)
    final = await coordinator.run()
    assert final["status"] == "failed"
    assert calls == ["fetch"]
    assert final["node_contract_errors"]["analysis"][0]["code"] == "resource_missing"
    assert final["delivery"]["retryable_nodes"] == []
    restored = WorkflowCoordinator(final["definition"], executor=execute, snapshot=final)
    await restored.run()
    assert calls == ["fetch"]


@pytest.mark.asyncio
async def test_optional_contract_gap_is_visible_and_partial():
    final = await WorkflowCoordinator({"workflow_id": "optional-resource", "nodes": [
        {"task_id": "fetch"}, {"task_id": "analysis", "dependencies": ["fetch"],
                               "input_contracts": [{"source_task_id": "fetch", "required": False}]},
    ]}, executor=lambda *args: {"ok": True}).run()
    assert final["status"] == "partial"
    assert final["delivery"]["deliverable"]
    assert final["delivery"]["gaps"][0]["status"] == "resource_gap"


@pytest.mark.asyncio
async def test_optional_output_gap_reaches_downstream_context():
    coordinator = WorkflowCoordinator({"workflow_id": "optional-output", "nodes": [
        {"task_id": "fetch", "output_contract": {"required": False, "fields": ["pm25"]}},
        {"task_id": "analysis", "dependencies": ["fetch"]},
    ]}, executor=lambda *args: {"ok": True})
    final = await coordinator.run()
    assert final["status"] == "partial"
    assert final["node_input_gaps"]["analysis"][0]["task_id"] == "fetch"
    assert final["node_input_gaps"]["analysis"][0]["status"] == "resource_gap"


@pytest.mark.asyncio
async def test_bad_output_is_not_available_to_dependents_or_cache(tmp_path):
    path = tmp_path / "air.csv"
    path.write_text("pm25\n42\n", encoding="utf-8")
    calls = []

    async def execute(node, *args):
        calls.append(node.task_id)
        return {"data": {"file_paths": [str(path)]}}

    definition = {"workflow_id": "output", "nodes": [
        {"task_id": "fetch", "output_contract": {"fields": ["wind"]}},
        {"task_id": "analysis", "dependencies": ["fetch"]},
    ]}
    final = await WorkflowCoordinator(definition, executor=execute, completed_results={
        "fetch": {"data": {"file_paths": [str(path)]}}, "analysis": {"cached": True},
    }).run()
    assert final["status"] == "failed"
    assert final["node_results"] == {}
    assert calls == ["fetch"]
