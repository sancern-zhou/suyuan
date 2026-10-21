"""Incremental graph changes preserve evidence and cumulative operational limits."""

import asyncio

import pytest

from app.agent.workflow.coordinator import WorkflowCoordinator, WorkflowDefinition


@pytest.mark.asyncio
async def test_extend_checkpoint_preserves_results_and_runs_only_new_nodes():
    calls = []

    async def execute(node, dependencies, *args):
        calls.append(node.task_id)
        if node.task_id == "analysis":
            assert dependencies == {"fetch": {"value": 42}}
        return {"value": 42}

    original = WorkflowCoordinator({"workflow_id": "extend", "nodes": [{"task_id": "fetch"}]}, executor=execute)
    first = await original.run()
    coordinator = WorkflowCoordinator(first["definition"], executor=execute, snapshot=first)
    coordinator.extend([{"task_id": "analysis", "dependencies": ["fetch"]}], expected_revision=0, reason="missing analysis")
    queued = coordinator.snapshot()
    assert queued["workflow_run_id"] != first["workflow_run_id"]
    restored = WorkflowCoordinator(queued["definition"], executor=execute, snapshot=queued)
    final = await restored.run()
    assert final["status"] == "succeeded"
    assert final["revision"] == 1
    assert calls == ["fetch", "analysis"]
    assert final["budget_state"]["executions"] == {"fetch": 1, "analysis": 1}
    assert final["budget_state"]["elapsed_seconds"] >= first["budget_state"]["elapsed_seconds"]


@pytest.mark.asyncio
async def test_extension_validation_is_atomic_and_revision_is_checked():
    coordinator = WorkflowCoordinator({"workflow_id": "atomic", "budget": {"max_nodes": 3, "max_extensions": 1},
                                       "nodes": [{"task_id": "a"}]}, executor=lambda *args: {})
    await coordinator.run()
    before = coordinator.snapshot()
    for nodes, revision in [([{ "task_id": "a"}], 0), ([{"task_id": "b", "dependencies": ["missing"]}], 0),
                            ([{"task_id": "b", "dependencies": ["c"]}, {"task_id": "c", "dependencies": ["b"]}], 0),
                            ([{"task_id": "b"}, {"task_id": "c"}, {"task_id": "d"}], 0),
                            ([{"task_id": "b"}], 1)]:
        with pytest.raises(ValueError):
            coordinator.extend(nodes, expected_revision=revision, reason="gap")
        assert coordinator.snapshot() == before
    coordinator.extend([{"task_id": "b"}], expected_revision=0, reason="gap")
    with pytest.raises(ValueError, match="extension budget"):
        coordinator.extend([{"task_id": "c"}], expected_revision=1, reason="gap")


@pytest.mark.asyncio
async def test_total_time_budget_cancels_children_preserves_successes_and_survives_restore():
    cancelled = asyncio.Event()
    calls = []

    async def execute(node, *args):
        calls.append(node.task_id)
        if node.task_id == "slow":
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return {"ok": True}

    coordinator = WorkflowCoordinator({"workflow_id": "time", "budget": {"timeout_seconds": .05},
                                       "nodes": [{"task_id": "fast"}, {"task_id": "slow"}]}, executor=execute)
    final = await coordinator.run()
    assert cancelled.is_set()
    assert final["status"] == "failed"
    assert final["node_results"] == {"fast": {"ok": True}}
    assert final["budget_state"]["exhausted"] == "timeout_seconds"
    restored = WorkflowCoordinator(final["definition"], executor=execute, snapshot=final)
    assert (await restored.run())["status"] == "failed"
    assert calls == ["fast", "slow"]
    with pytest.raises(ValueError, match="budget-exhausted"):
        restored.extend([{"task_id": "new"}], expected_revision=0, reason="gap")


@pytest.mark.asyncio
async def test_retry_budget_covers_multiple_nodes_and_resume_does_not_reset_it():
    calls = []

    async def execute(node, *args):
        calls.append(node.task_id)
        raise RuntimeError("temporary")

    coordinator = WorkflowCoordinator({"workflow_id": "retry", "budget": {"max_retries": 1},
                                       "nodes": [{"task_id": "a", "max_attempts": 3}, {"task_id": "b", "max_attempts": 3}]}, executor=execute)
    first = await coordinator.run()
    assert len(calls) == 3
    restored = WorkflowCoordinator(first["definition"], executor=execute, snapshot=first)
    final = await restored.run()
    assert len(calls) == 3
    assert final["budget_state"]["retries_used"] == 1


def test_legacy_definition_fingerprint_and_invalid_budgets():
    definition = WorkflowDefinition.from_mapping({"workflow_id": "legacy", "nodes": [{"task_id": "a"}]})
    assert "budget" not in definition.to_dict()
    assert WorkflowDefinition.from_mapping(definition.to_dict()).fingerprint() == definition.fingerprint()
    for budget in [{"timeout_seconds": float("nan")}, {"timeout_seconds": 0}, {"max_nodes": 1.5}, {"max_retries": -1}]:
        with pytest.raises(ValueError):
            WorkflowDefinition.from_mapping({"workflow_id": "invalid", "nodes": [{"task_id": "a"}], "budget": budget})
