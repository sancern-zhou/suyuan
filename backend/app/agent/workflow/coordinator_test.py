import asyncio

from app.agent.workflow.coordinator import WorkflowCoordinator


def test_coordinator_runs_independent_nodes_in_parallel_and_respects_dependencies():
    async def run():
        started = []
        finished = []

        async def execute(node, dependencies, attempt):
            started.append(node.task_id)
            await asyncio.sleep(0.01)
            finished.append(node.task_id)
            if node.task_id == "merge":
                assert set(dependencies) == {"air", "weather"}
            return {"task_id": node.task_id, "attempt": attempt}

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "report-1",
                "nodes": [
                    {"task_id": "air"},
                    {"task_id": "weather"},
                    {"task_id": "merge", "dependencies": ["air", "weather"]},
                ],
            },
            executor=execute,
            max_concurrency=2,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        assert set(started[:2]) == {"air", "weather"}
        assert started[-1] == "merge"
        assert result["node_results"]["merge"]["task_id"] == "merge"

    asyncio.run(run())


def test_coordinator_retries_node_and_persists_a_resumable_snapshot():
    async def run():
        attempts = []
        snapshots = []

        async def execute(node, dependencies, attempt):
            attempts.append(attempt)
            if len(attempts) == 1:
                raise RuntimeError("temporary")
            return {"ok": True}

        coordinator = WorkflowCoordinator(
            {"workflow_id": "retry-1", "nodes": [{"task_id": "fetch", "max_attempts": 2}]},
            executor=execute,
            persist=snapshots.append,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        assert attempts == [1, 2]
        restored = WorkflowCoordinator(
            result["definition"],
            executor=execute,
            snapshot=result,
        )
        assert restored.snapshot()["node_results"]["fetch"] == {"ok": True}
        assert snapshots
        assert all(
            snapshot.get("workflow_id") == "retry-1" and "definition" in snapshot
            for snapshot in snapshots
        )

    asyncio.run(run())


def test_coordinator_cancels_pending_nodes():
    async def run():
        release = asyncio.Event()

        async def execute(node, dependencies, attempt):
            await release.wait()
            return {"ok": True}

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "cancel-1",
                "nodes": [
                    {"task_id": "source"},
                    {"task_id": "downstream", "dependencies": ["source"]},
                ],
            },
            executor=execute,
        )
        task = asyncio.create_task(coordinator.run())
        await asyncio.sleep(0)
        await coordinator.cancel(reason="user stopped")
        release.set()
        result = await task
        assert result["status"] == "cancelled"
        assert result["graph"]["downstream"]["status"] == "cancelled"

    asyncio.run(run())


def test_coordinator_records_strict_node_lineage():
    async def run():
        async def execute(node, dependencies, attempt):
            return {
                "status": "success",
                "success": True,
                "data": {
                    "result_envelope": {
                        "status": "completed",
                        "summary": node.task_id,
                        "outputs": {"attempt": attempt},
                        "evidence": [{"source": node.task_id}],
                        "artifacts": [],
                    }
                },
            }

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "lineage-1",
                "nodes": [{"task_id": "source", "require_lineage": True}],
            },
            executor=execute,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        assert result["node_lineage"]["source"]["evidence"][0]["source_task_id"] == "source"

    asyncio.run(run())


def test_coordinator_resume_retries_failed_node_from_snapshot():
    async def run():
        definition = {
            "workflow_id": "resume-1",
            "nodes": [{"task_id": "source", "max_attempts": 2}],
        }
        first = WorkflowCoordinator(definition, executor=lambda *args: {"success": True})
        failed = first.snapshot()
        failed["status"] = "failed"
        failed["graph"]["source"]["status"] = "failed"
        failed["node_errors"] = {"source": "process interrupted"}
        failed["runtime"]["runs"][failed["workflow_run_id"]]["status"] = "failed"
        failed["runtime"]["runs"]["resume-1:source"]["status"] = "failed"
        failed["runtime"]["runs"]["resume-1:source"]["attempt"] = 1
        calls = []

        async def execute(node, dependencies, attempt):
            calls.append(attempt)
            return {"success": True}

        resumed = WorkflowCoordinator(definition, executor=execute, snapshot=failed)
        result = await resumed.run()
        assert result["status"] == "succeeded"
        assert calls == [2]

    asyncio.run(run())
