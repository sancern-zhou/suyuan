"""Parent-scoped checkpoint continuation through the actual orchestration tool."""

from types import SimpleNamespace

import pytest

from app.agent.workflow.registry import ActiveWorkflowRegistry
from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool


@pytest.fixture
def tool_setup(monkeypatch, tmp_path):
    calls, checkpoints = [], {}

    class Child:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            return {"success": True, "status": "success", "data": {"result_envelope": {
                "status": "completed", "summary": "done", "evidence": [], "data_gaps": [],
            }}}

    async def load_session(session_id, **kwargs):
        return SimpleNamespace(metadata={"workflow_coordinators": checkpoints.get(session_id, {})})

    def persist(context, snapshot):
        checkpoints.setdefault(context.session_id, {})[snapshot["workflow_id"]] = snapshot

    monkeypatch.setattr(RunAgentWorkflowTool, "_build_sub_agent_tool", staticmethod(Child))
    monkeypatch.setattr(RunAgentWorkflowTool, "_build_workflow_registry", staticmethod(lambda: ActiveWorkflowRegistry()))
    monkeypatch.setattr(RunAgentWorkflowTool, "_persist_parent_snapshot", staticmethod(persist))
    monkeypatch.setattr(RunAgentWorkflowTool, "_write_full_results", staticmethod(lambda *args: None))
    monkeypatch.setattr("app.agent.session.session_resolver.load_session_for_mode", load_session)
    monkeypatch.setattr("app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "cache")
    return RunAgentWorkflowTool(), SimpleNamespace(session_id="parent", runtime_mode="query"), calls, checkpoints


@pytest.mark.asyncio
async def test_parent_can_extend_and_repeated_revision_is_rejected(tool_setup):
    tool, context, calls, checkpoints = tool_setup
    first = await tool.execute(context=context, workflow={"workflow_id": "flow", "nodes": [{
        "task_id": "a", "target_mode": "query_monitoring_city", "goal": "fetch air",
    }]})
    assert first["success"]
    assert first["data"]["revision"] == 0
    extension = {"expected_revision": 0, "reason": "weather gap", "nodes": [{
        "task_id": "b", "target_mode": "query_forecast", "goal": "fetch weather", "dependencies": ["a"],
    }]}
    second = await tool.execute(context=context, workflow={"workflow_id": "flow"}, extension=extension)
    assert second["success"], second
    assert second["data"]["revision"] == 1
    assert set(second["data"]["node_results"]) == {"a", "b"}
    assert len(calls) == 2
    rejected = await tool.execute(context=context, workflow={"workflow_id": "flow"}, extension=extension)
    assert not rejected["success"]
    assert len(calls) == 2
    assert checkpoints["parent"]["flow"]["revision"] == 1


@pytest.mark.asyncio
async def test_extension_is_session_scoped_and_rechecks_mode_boundary(tool_setup):
    tool, context, calls, _ = tool_setup
    await tool.execute(context=context, workflow={"workflow_id": "flow", "nodes": [{
        "task_id": "a", "target_mode": "query_monitoring_city", "goal": "fetch air",
    }]})
    extension = {"expected_revision": 0, "reason": "gap", "nodes": [{
        "task_id": "b", "target_mode": "expert_analysis", "goal": "analysis",
        "task_contract": {"deliverables": ["conclusion"]},
    }]}
    foreign = await tool.execute(context=SimpleNamespace(session_id="foreign", runtime_mode="query"),
                                 workflow={"workflow_id": "flow"}, extension=extension)
    forbidden = await tool.execute(context=context, workflow={"workflow_id": "flow"}, extension=extension)
    assert not foreign["success"]
    assert not forbidden["success"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_worker_canonical_definition_is_accepted_without_changing_fingerprint(tool_setup):
    tool, context, calls, checkpoints = tool_setup
    first = await tool.execute(context=context, workflow={"workflow_id": "canonical", "nodes": [{
        "task_id": "a", "target_mode": "query_monitoring_city", "goal": "fetch air",
    }]})
    assert first["success"]
    snapshot = checkpoints["parent"]["canonical"]
    assert "target_mode" in snapshot["definition"]["nodes"][0]["payload"]
    resumed = await tool.execute(context=context, workflow=snapshot["definition"], snapshot=snapshot)
    assert resumed["success"], resumed
    assert len(calls) == 1
    # A queued canonical checkpoint must also dispatch through the real tool
    # entry point, rather than only accepting an already-completed graph.
    import copy
    queued = copy.deepcopy(snapshot)
    queued["status"] = "queued"
    queued["node_results"] = {}
    queued["node_lineage"] = {}
    queued["budget_state"] = {}
    queued["graph"]["a"]["status"] = "pending"
    for run in queued["runtime"]["runs"].values():
        run["status"] = "queued"
        run["attempt"] = 0
    dispatched = await tool.execute(context=context, workflow=queued["definition"], snapshot=queued)
    assert dispatched["success"], dispatched
    assert len(calls) == 2
