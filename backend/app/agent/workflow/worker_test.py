import asyncio

import pytest

from app.agent.workflow.worker import _run_job
from app.agent.workflow.jobs import WorkflowJob, WorkflowLeaseLost


class _Store:
    def __init__(self):
        self.snapshots = []
        self.finished = []

    async def heartbeat(self, workflow_id, *, lease_token):
        pass

    async def publish_snapshot(self, workflow_id, snapshot, *, lease_token):
        self.snapshots.append((workflow_id, snapshot))

    async def finish(self, workflow_id, *, status, result=None, lease_token):
        self.finished.append((workflow_id, status))


@pytest.mark.asyncio
async def test_worker_executes_job_and_publishes_terminal_result(monkeypatch):
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool

    async def execute(self, **kwargs):
        kwargs["context"].workflow_event_sink({"workflow_id": "wf-1", "status": "succeeded"})
        return {"success": True, "data": {"snapshot": {"workflow_id": "wf-1", "status": "succeeded"}}}

    monkeypatch.setattr(RunAgentWorkflowTool, "execute", execute)
    store = _Store()
    await _run_job(WorkflowJob("wf-1", "session-1", {}, {}), store)
    assert store.finished == [("wf-1", "succeeded")]
    assert store.snapshots[0][0] == "wf-1"


@pytest.mark.asyncio
async def test_event_publication_failure_does_not_hang_worker(monkeypatch):
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool
    class FailingStore(_Store):
        async def publish_snapshot(self, workflow_id, snapshot, *, lease_token):
            raise ConnectionError("redis unavailable")
    async def execute(self, **kwargs):
        assert kwargs["context"].runtime_mode == "expert"
        assert kwargs["max_concurrency"] == 2
        kwargs["context"].workflow_event_sink({"status": "running"})
        kwargs["context"].workflow_event_sink({"status": "succeeded"})
        return {"success": True}
    monkeypatch.setattr(RunAgentWorkflowTool, "execute", execute)
    store = FailingStore()
    await asyncio.wait_for(_run_job(WorkflowJob(
        "wf", "s", {}, {"parent_mode": "expert", "max_concurrency": 2},
    ), store), timeout=1)
    assert store.finished == [("wf", "succeeded")]


@pytest.mark.asyncio
async def test_lost_lease_cancels_active_execution_without_finishing(monkeypatch):
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool
    cancelled = asyncio.Event()

    async def execute(self, **kwargs):
        try:
            kwargs["context"].workflow_event_sink({"status": "running"})
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    class ReclaimedStore(_Store):
        async def publish_snapshot(self, workflow_id, snapshot, *, lease_token):
            raise WorkflowLeaseLost(workflow_id)

    monkeypatch.setattr(RunAgentWorkflowTool, "execute", execute)
    store = ReclaimedStore()
    await asyncio.wait_for(_run_job(WorkflowJob("wf", "s", {}, {}, lease_token="old"), store), 1)
    assert cancelled.is_set()
    assert store.finished == []


@pytest.mark.asyncio
async def test_invalid_lease_never_starts_execution(monkeypatch):
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool
    async def execute(self, **kwargs):
        pytest.fail("child work must not start after lease loss")
    class ReclaimedStore(_Store):
        async def heartbeat(self, workflow_id, *, lease_token):
            raise WorkflowLeaseLost(workflow_id)
    monkeypatch.setattr(RunAgentWorkflowTool, "execute", execute)
    store = ReclaimedStore()
    await _run_job(WorkflowJob("wf", "s", {}, {}, lease_token="old"), store)
    assert store.finished == []


@pytest.mark.asyncio
async def test_explicit_workflow_cancellation_remains_terminal_cancelled(monkeypatch):
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool
    async def execute(self, **kwargs):
        kwargs["context"].workflow_event_sink({"status": "cancelled"})
        return {"status": "cancelled", "success": False}
    monkeypatch.setattr(RunAgentWorkflowTool, "execute", execute)
    store = _Store()
    await _run_job(WorkflowJob("wf", "s", {}, {}, lease_token="current"), store)
    assert store.finished == [("wf", "cancelled")]


@pytest.mark.asyncio
async def test_partial_delivery_is_a_terminal_worker_result(monkeypatch):
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool

    async def execute(self, **kwargs):
        kwargs["context"].workflow_event_sink({"status": "partial"})
        return {"status": "partial", "success": True, "data": {"delivery": {"deliverable": True, "complete": False}}}

    monkeypatch.setattr(RunAgentWorkflowTool, "execute", execute)
    store = _Store()
    await _run_job(WorkflowJob("wf", "s", {}, {}, lease_token="current"), store)
    assert store.finished == [("wf", "partial")]
