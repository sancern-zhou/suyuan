"""Pause barrier commit survival and startup reconciliation regressions.

2026-11-05 事故：取消风暴（SSE 断开 + 暂停请求对同一濒死任务多次 cancel()）
打断了 unregister 的 store.finish，取消状态卡在非终态——REGISTER 拒绝该会话
一切新 run、屏障等满超时报"暂停记录保存失败"，会话锁死到 TTL。
"""

import asyncio

import pytest

from app.agent.runtime.cancellation import CancellationRegistry
from app.agent.runtime.cancellation_state import InMemoryCancellationStateStore


class _SlowFinishStore:
    """finish 延迟一拍，让重复取消能落在屏障释放信号执行途中。"""

    def __init__(self, inner):
        self._inner = inner

    async def register(self, *args, **kwargs):
        return await self._inner.register(*args, **kwargs)

    async def request_cancel(self, *args, **kwargs):
        return await self._inner.request_cancel(*args, **kwargs)

    async def get(self, *args, **kwargs):
        return await self._inner.get(*args, **kwargs)

    async def finish(self, *args, **kwargs):
        await asyncio.sleep(0.05)
        return await self._inner.finish(*args, **kwargs)

    async def list_non_terminal_sessions(self):
        return await self._inner.list_non_terminal_sessions()

    async def aclose(self):
        return await self._inner.aclose()


class _FlakyFinishStore(_SlowFinishStore):
    """finish 首次抛瞬断异常，验证 commit_with_retry 的有限重试。"""

    def __init__(self, inner):
        super().__init__(inner)
        self.failures_left = 1

    async def finish(self, *args, **kwargs):
        if self.failures_left > 0:
            self.failures_left -= 1
            raise ConnectionError("redis transient")
        return await self._inner.finish(*args, **kwargs)


@pytest.mark.asyncio
async def test_unregister_finish_survives_repeated_cancellation():
    shared = InMemoryCancellationStateStore()
    registry = CancellationRegistry(store=_SlowFinishStore(shared), poll_interval=0.01)
    cancel_event = await registry.register("session_a")
    await registry.attach_run_id("session_a", cancel_event, "run_old")
    assert await registry.cancel(
        "session_a", expected_run_id="run_old", reason="user_paused"
    )

    unregister_task = asyncio.create_task(registry.unregister("session_a", cancel_event))
    for _ in range(3):
        await asyncio.sleep(0.01)
        unregister_task.cancel()
    await asyncio.wait_for(unregister_task, timeout=2)

    state = await shared.get("session_a")
    assert state is not None
    assert state.status == "paused"
    assert state.reason == "user_paused"


@pytest.mark.asyncio
async def test_unregister_retries_a_transient_finish_failure():
    shared = InMemoryCancellationStateStore()
    registry = CancellationRegistry(store=_FlakyFinishStore(shared), poll_interval=0.01)
    cancel_event = await registry.register("session_a")
    await registry.attach_run_id("session_a", cancel_event, "run_old")
    await registry.cancel("session_a", reason="user_paused")

    await asyncio.wait_for(
        registry.unregister("session_a", cancel_event), timeout=2
    )

    state = await shared.get("session_a")
    assert state is not None
    assert state.status == "paused"


@pytest.mark.asyncio
async def test_recover_stale_states_finishes_orphans_and_respects_boundaries():
    shared = InMemoryCancellationStateStore()
    registry = CancellationRegistry(store=shared, poll_interval=0.01)

    await shared.register("session_running", "run_a")
    await shared.register("session_paused", "run_b")
    await shared.request_cancel("session_paused", "run_b", "user_paused")
    await shared.register("session_finished", "run_c")
    await shared.finish("session_finished", "run_c")
    await shared.register("agent-workflow:delegation_x", "delegation_x")
    await shared.request_cancel(
        "agent-workflow:delegation_x", "delegation_x", "assistant_user_cancelled"
    )

    recovered = await registry.recover_stale_states()

    assert recovered == 2
    assert (await shared.get("session_running")).status == "finished"
    assert (await shared.get("session_paused")).status == "paused"
    assert (await shared.get("session_finished")).status == "finished"
    # workflow 键可能属于其他进程，不在回收范围
    workflow_state = await shared.get("agent-workflow:delegation_x")
    assert workflow_state.status == "pause_requested"


@pytest.mark.asyncio
async def test_recovered_state_releases_the_pause_barrier_and_registration():
    shared = InMemoryCancellationStateStore()
    registry = CancellationRegistry(store=shared, poll_interval=0.01, barrier_timeout=1.0)
    await shared.register("session_a", "run_old")
    await shared.request_cancel("session_a", "run_old", "user_paused")

    barrier = asyncio.create_task(registry.ensure_pause_succeeded("session_a", "run_old"))
    await asyncio.sleep(0.05)
    assert barrier.done() is False

    await registry.recover_stale_states()
    await asyncio.wait_for(barrier, timeout=1)

    # 终态放行新 run 注册（事故现场的第二重锁死）
    assert await shared.register("session_a", "run_new") is True
