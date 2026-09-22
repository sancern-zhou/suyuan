import asyncio

from app.api.workflow_routes import _resume_tasks, _track_resume_task


def test_resume_task_tracking_keeps_task_until_completion():
    async def run():
        task = asyncio.create_task(asyncio.sleep(0))
        _track_resume_task(task)
        assert task in _resume_tasks
        await task
        await asyncio.sleep(0)
        assert task not in _resume_tasks

    asyncio.run(run())
