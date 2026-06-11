import asyncio

import pytest

from app.agent.runtime.cancellation import CancellationRegistry


class _Executor:
    def __init__(self):
        self.discarded = False

    def discard(self):
        self.discarded = True


@pytest.mark.asyncio
async def test_cancel_cancels_attached_run_task_and_discards_executor():
    registry = CancellationRegistry()
    cancel_event = await registry.register("session_a")
    executor = _Executor()
    await registry.attach_streaming_executor("session_a", executor)

    async def wait_forever():
        await asyncio.Event().wait()

    run_task = asyncio.create_task(wait_forever())
    await registry.attach_run_task("session_a", run_task)

    cancelled = await registry.cancel("session_a")
    await asyncio.sleep(0)

    assert cancelled is True
    assert cancel_event.is_set()
    assert executor.discarded is True
    assert run_task.cancelled()
