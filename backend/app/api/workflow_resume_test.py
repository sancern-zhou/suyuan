from app.agent.workflow.coordinator import WorkflowCoordinator


def test_failed_snapshot_can_resume_with_remaining_node_attempts():
    async def run():
        definition = {
            "workflow_id": "resume-api-test",
            "nodes": [{"task_id": "node", "max_attempts": 2}],
        }
        first = WorkflowCoordinator(definition, executor=lambda *args: {"success": True})
        failed = first.snapshot()
        failed["status"] = "failed"
        failed["graph"]["node"]["status"] = "failed"
        failed["runtime"]["runs"][failed["workflow_run_id"]]["status"] = "failed"
        failed["runtime"]["runs"]["resume-api-test:node"]["status"] = "failed"
        failed["runtime"]["runs"]["resume-api-test:node"]["attempt"] = 1
        resumed = WorkflowCoordinator(
            definition,
            executor=lambda *args: {"success": True},
            snapshot=failed,
        )
        assert (await resumed.run())["status"] == "succeeded"

    import asyncio

    asyncio.run(run())
