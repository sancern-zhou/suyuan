import asyncio

import pytest

from app.agent.workflow.coordinator import WorkflowCoordinator, WorkflowDefinition


def condition(op="gt", value=0):
    return {"source_task_id": "fetch", "path": "data.count", "op": op, "value": value}


@pytest.mark.asyncio
@pytest.mark.parametrize("count,selected", [(0, "normal"), (2, "analysis")])
async def test_exclusive_branches_join_and_restore_without_reexecuting(count, selected):
    calls = []

    async def execute(node, inputs, *args):
        calls.append(node.task_id)
        if node.task_id == "join":
            assert set(inputs) == {selected}
        return {"data": {"count": count}}

    coordinator = WorkflowCoordinator({"workflow_id": "branch", "nodes": [
        {"task_id": "fetch"},
        {"task_id": "analysis", "dependencies": ["fetch"], "when": condition()},
        {"task_id": "normal", "dependencies": ["fetch"], "when": {"not": condition()}},
        {"task_id": "join", "dependencies": ["analysis", "normal"], "dependency_policy": "allow_partial"},
    ]}, executor=execute)
    final = await coordinator.run()
    assert final["status"] == "succeeded"
    assert calls == ["fetch", selected, "join"]
    assert len(final["delivery"]["skipped_nodes"]) == 1
    assert final["delivery"]["gaps"] == []
    restored = WorkflowCoordinator(final["definition"], executor=execute, snapshot=final)
    assert (await restored.run())["status"] == "succeeded"
    assert calls == ["fetch", selected, "join"]


@pytest.mark.asyncio
async def test_skipped_branch_propagates_and_missing_evidence_is_not_false():
    calls = []

    async def execute(node, *args):
        calls.append(node.task_id)
        return {"data": {"count": 0}}

    definition = {"workflow_id": "skip", "nodes": [
        {"task_id": "fetch"}, {"task_id": "analysis", "dependencies": ["fetch"], "when": condition()},
        {"task_id": "chart", "dependencies": ["analysis"]},
    ]}
    final = await WorkflowCoordinator(definition, executor=execute).run()
    assert final["status"] == "succeeded"
    assert final["graph"]["chart"]["status"] == "skipped"
    definition["nodes"][1]["when"]["path"] = "data.unknown"
    missing = await WorkflowCoordinator(definition, executor=execute).run()
    assert missing["status"] == "failed"
    assert missing["node_decisions"]["analysis"]["selected"] is None
    assert missing["delivery"]["retryable_nodes"] == []
    assert calls == ["fetch", "fetch"]


@pytest.mark.asyncio
@pytest.mark.parametrize("required,status", [(False, "partial"), (True, "failed")])
async def test_failed_upstream_is_only_consumed_under_explicit_policy(required, status):
    inputs_seen = []

    async def execute(node, inputs, *args):
        if node.task_id == "weather":
            raise ValueError("weather unavailable")
        if node.task_id == "join":
            inputs_seen.append(inputs)
        await asyncio.sleep(.001)
        return {"value": 42}

    final = await WorkflowCoordinator({"workflow_id": "partial", "nodes": [
        {"task_id": "air"}, {"task_id": "weather", "required": required},
        {"task_id": "join", "dependencies": ["air", "weather"], "dependency_policy": "allow_partial"},
    ]}, executor=execute).run()
    assert final["status"] == status
    assert inputs_seen == [{"air": {"value": 42}}]
    assert final["node_input_gaps"]["join"][0]["task_id"] == "weather"
    assert final["delivery"]["deliverable"] is (status == "partial")
    assert final["delivery"]["complete"] is False


@pytest.mark.asyncio
async def test_allow_partial_never_runs_without_successful_evidence():
    calls = []

    async def execute(node, *args):
        calls.append(node.task_id)
        raise ValueError("unavailable")

    final = await WorkflowCoordinator({"workflow_id": "empty", "nodes": [
        {"task_id": "source", "required": False},
        {"task_id": "analysis", "dependencies": ["source"], "dependency_policy": "allow_partial"},
    ]}, executor=execute).run()
    assert final["status"] == "failed"
    assert calls == ["source"]
    assert final["graph"]["analysis"]["status"] == "blocked"


def test_reject_invalid_routing_before_execution_and_preserve_legacy_fingerprint():
    for when in [condition("execute_python"), {**condition(), "source_task_id": "foreign"}, {"all": []},
                 {"any": [condition()], "not": condition()}]:
        with pytest.raises(ValueError):
            WorkflowDefinition.from_mapping({"workflow_id": "invalid", "nodes": [
                {"task_id": "fetch"}, {"task_id": "analysis", "dependencies": ["fetch"], "when": when},
            ]})
    legacy = WorkflowDefinition.from_mapping({"workflow_id": "legacy", "nodes": [{"task_id": "fetch"}]})
    serialized = legacy.to_dict()
    assert "required" not in serialized["nodes"][0]
    assert "dependency_policy" not in serialized["nodes"][0]
    assert WorkflowDefinition.from_mapping(serialized).fingerprint() == legacy.fingerprint()
