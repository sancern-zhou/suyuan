import asyncio

from app.agent.workflow.background_tasks import BackgroundTaskRegistry
from app.agent.workflow.profiles import get_agent_profile, merge_denied_tools


def test_explore_profile_is_read_only_and_cannot_delegate():
    profile = get_agent_profile("query", profile="explore")
    assert profile.name == "explore"
    assert profile.read_only is True
    assert "write_file" in profile.denied_tools
    assert "call_sub_agent" not in merge_denied_tools(profile, [])


def test_background_registry_projects_completion():
    async def run():
        return {"status": "success", "summary": "done", "metadata": {"workflow_run_id": "run-1"}}

    async def scenario():
        registry = BackgroundTaskRegistry()
        task = asyncio.create_task(run())
        record = registry.launch("task-1", task, metadata={"target_mode": "query"})
        assert record["status"] == "running"
        await task
        await asyncio.sleep(0)
        completed = registry.get("task-1")
        assert completed["status"] == "success"
        assert completed["workflow_run_id"] == "run-1"

    asyncio.run(scenario())
