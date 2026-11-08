import pytest

from app.agent.workflow.coordinator import WorkflowCoordinator
from app.agent.workflow.deliverable_validation import validate_deliverable_entries


def test_deliverables_require_real_paths_only(tmp_path):
    assert validate_deliverable_entries(None) == []
    assert validate_deliverable_entries("data.json") == [
        {"path": "$.deliverables", "expected": "array of {path}", "got": "string"}
    ]
    missing = tmp_path / "absent.json"
    assert validate_deliverable_entries([{"path": str(missing), "format": "json"}]) == [
        {"path": "$.deliverables[0].path", "expected": "existing file", "got": "not found"}
    ]
    actual = tmp_path / "air.json"
    actual.write_text('{"pm25": 42}', encoding="utf-8")
    assert validate_deliverable_entries([{"path": str(actual)}]) == []


@pytest.mark.asyncio
async def test_legacy_resource_contracts_do_not_affect_execution_or_terminal_state(tmp_path):
    actual = tmp_path / "weather.json"
    actual.write_text('{"pm25": 42}', encoding="utf-8")
    definition = {"workflow_id": "legacy-contract", "nodes": [
        {"task_id": "fetch", "output_contract": {"format": "csv", "fields": ["date"]}},
        {"task_id": "analysis", "dependencies": ["fetch"], "input_contracts": [
            {"source_task_id": "fetch", "format": "csv", "fields": ["date"]}
        ]},
    ]}
    final = await WorkflowCoordinator(
        definition,
        executor=lambda *args: {"success": True, "data": {"file_paths": [str(actual)]}},
    ).run()
    assert final["status"] == "succeeded"
    assert final["delivery"]["gaps"] == []
    assert final["delivery"]["complete"] is True
    assert "node_contract_errors" not in final
    assert "output_contract" not in final["definition"]["nodes"][0]


@pytest.mark.asyncio
async def test_legacy_contract_only_snapshot_is_normalized_without_replaying_nodes(tmp_path):
    definition = {"workflow_id": "legacy-resume", "nodes": [
        {"task_id": "fetch", "output_contract": {"format": "csv"}}
    ]}
    original = WorkflowCoordinator(definition, executor=lambda *args: {"success": True})
    snapshot = original.snapshot()
    snapshot["status"] = "partial"
    snapshot["node_contract_errors"] = {"fetch": [{"code": "resource_incompatible"}]}
    snapshot["node_input_gaps"] = {"analysis": [{"status": "resource_gap"}]}
    snapshot["graph"]["fetch"]["status"] = "succeeded"
    snapshot["node_results"] = {"fetch": {"success": True}}
    snapshot["definition_hash"] = "legacy-contract-only-change"
    nodes = snapshot["definition"]["nodes"]
    import hashlib
    import json
    snapshot["definition_hash"] = hashlib.sha256(
        json.dumps(snapshot["definition"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    nodes[0]["output_contract"] = {"format": "csv"}
    calls = []

    async def execute(node, *args):
        calls.append(node.task_id)
        return {"success": True}

    final = await WorkflowCoordinator(definition, executor=execute, snapshot=snapshot).run()
    assert final["status"] == "succeeded"
    assert calls == []
    assert final["delivery"]["gaps"] == []
