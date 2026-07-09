import pytest

from app.social.subagent_singleton import set_subagent_manager
from app.tools.social.wait_task.tool import WaitTaskTool


class DummyTaskStore:
    async def get_task(self, task_id):
        return {
            "task_id": task_id,
            "social_user_id": "default",
            "status": "completed",
            "result": "done",
        }


class DummySubagentManager:
    def __init__(self):
        self.task_store = DummyTaskStore()


@pytest.mark.asyncio
async def test_wait_task_reads_spawn_status_from_subagent_task_store():
    set_subagent_manager(DummySubagentManager())
    try:
        result = await WaitTaskTool().execute(
            task_id="spawn_task_20260708_180037_2a5b48dc",
            wait_timeout=0,
        )
    finally:
        set_subagent_manager(None)

    assert result["success"] is True
    assert result["metadata"]["task_type"] == "spawn"
    assert result["data"]["status"] == "completed"
