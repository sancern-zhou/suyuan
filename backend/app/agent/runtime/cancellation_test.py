import asyncio

import pytest

from app.agent.runtime.cancellation import CancellationRegistry, PauseCheckpointError


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
    await registry.arm_run_task("session_a", cancel_event)

    cancelled = await registry.cancel("session_a")
    await asyncio.sleep(0)

    assert cancelled is True
    assert cancel_event.is_set()
    assert executor.discarded is True
    assert run_task.cancelled()


@pytest.mark.asyncio
async def test_cancel_ignores_a_stale_expected_run_id():
    registry = CancellationRegistry()
    cancel_event = await registry.register("session_a")
    await registry.attach_run_id("session_a", cancel_event, "run_new")

    cancelled = await registry.cancel(
        "session_a",
        expected_run_id="run_old",
        reason="user_paused",
    )

    assert cancelled is False
    assert cancel_event.is_set() is False


@pytest.mark.asyncio
async def test_early_cancel_is_delivered_only_after_route_arms_its_handler():
    registry = CancellationRegistry()
    cancel_event = await registry.register("session_a")

    async def wait_forever():
        await asyncio.Event().wait()

    run_task = asyncio.create_task(wait_forever())
    await registry.attach_run_task("session_a", run_task)
    await registry.cancel("session_a", reason="user_paused")

    assert run_task.cancelled() is False

    await registry.arm_run_task("session_a", cancel_event)
    await asyncio.sleep(0)
    assert run_task.cancelled() is True
    await registry.unregister("session_a", cancel_event)


@pytest.mark.asyncio
async def test_next_run_waits_until_previous_run_unregisters():
    registry = CancellationRegistry()
    first_event = await registry.register("session_a")
    await registry.attach_run_id("session_a", first_event, "run_old")

    async def old_run():
        try:
            await asyncio.Event().wait()
        finally:
            await registry.unregister("session_a", first_event)

    old_task = asyncio.create_task(old_run())
    await registry.attach_run_task("session_a", old_task)
    await registry.arm_run_task("session_a", first_event)

    next_registration = asyncio.create_task(registry.register("session_a"))
    next_event = await asyncio.wait_for(next_registration, timeout=1)

    assert old_task.cancelled()
    assert next_event is not first_event


@pytest.mark.asyncio
async def test_failed_pause_checkpoint_blocks_a_silent_next_run():
    registry = CancellationRegistry()
    cancel_event = await registry.register("session_a")
    await registry.attach_run_id("session_a", cancel_event, "run_old")
    await registry.record_finalization_error(
        "session_a",
        cancel_event,
        RuntimeError("pause_checkpoint_failed"),
    )
    await registry.unregister("session_a", cancel_event)

    with pytest.raises(PauseCheckpointError, match="pause_checkpoint_failed"):
        await registry.ensure_pause_succeeded("session_a", "run_old")
