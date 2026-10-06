import asyncio

import pytest

from app.agent.workflow.worker import _run_job
from app.agent.workflow.jobs import WorkflowJob


class _Store:
    def __init__(self):
        self.snapshots = []
        self.finished = []

    async def publish_snapshot(self, workflow_id, snapshot):
        self.snapshots.append((workflow_id, snapshot))

    async def finish(self, workflow_id, *, status, result=None):
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
        async def publish_snapshot(self, workflow_id, snapshot):
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
