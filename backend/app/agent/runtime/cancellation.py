"""Runtime cancellation registry for streaming agent runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from .ownership import run_ownership_registry
from .cancellation_state import (
    CancellationStateStore,
    InMemoryCancellationStateStore,
    RedisCancellationStateStore,
)

logger = structlog.get_logger()


class AgentRunCancelled(Exception):
    """Raised when a user cancels an in-flight agent run."""


class PauseCheckpointError(RuntimeError):
    """Raised when a paused run could not commit its durable transcript."""


async def await_unkillable(awaitable: Any) -> Any:
    """等待 awaitable 完成并忽略投向外层任务的重复取消。

    SSE 断开与暂停/停止请求会对同一个濒死任务多次调用 cancel()，每次都
    立即打断一个 await。屏障释放信号（store.finish）一旦被打断，取消状态
    将卡在非终态：REGISTER 会拒绝该会话一切新 run，带 previous_paused_run_id
    的消息会在屏障处等满超时后报"暂停记录保存失败"（2026-11-05 事故）。
    """
    task = asyncio.ensure_future(awaitable)
    current = asyncio.current_task()
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if current is not None and hasattr(current, "uncancel"):
                while current.cancelling():
                    current.uncancel()
    return task.result()


async def commit_with_retry(factory: Any, *, attempts: int = 3, delay: float = 0.2) -> Any:
    """屏障释放信号必须送达：单次失败（如 Redis 瞬断）按有限次数重试。"""
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            return await await_unkillable(factory())
        except asyncio.CancelledError:
            raise
        except Exception as error:
            last_error = error
            if attempt < attempts - 1:
                await await_unkillable(asyncio.sleep(delay))
    logger.error(
        "cancellation_commit_failed_after_retries",
        attempts=attempts,
        error=str(last_error),
    )
    raise last_error


@dataclass
class RunHandle:
    session_id: str
    cancel_event: asyncio.Event
    started_at: datetime
    streaming_executor: Optional[Any] = None
    run_task: Optional[asyncio.Task] = None
    run_id: Optional[str] = None
    pause_reason: Optional[str] = None
    task_armed: bool = False
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    monitor_task: Optional[asyncio.Task] = None
    shared_registration_rejected: bool = False


class CancellationRegistry:
    def __init__(
        self,
        store: Optional[CancellationStateStore] = None,
        *,
        poll_interval: float = 0.05,
        barrier_timeout: float = 30.0,
    ) -> None:
        self._handles: Dict[str, RunHandle] = {}
        self._pause_errors: Dict[tuple[str, str], str] = {}
        self._lock = asyncio.Lock()
        self._store = store or InMemoryCancellationStateStore()
        self._poll_interval = max(0.005, float(poll_interval))
        self._barrier_timeout = max(0.1, float(barrier_timeout))

    async def register(self, session_id: str) -> asyncio.Event:
        while True:
            async with self._lock:
                previous = self._handles.get(session_id)
                if not previous:
                    cancel_event = asyncio.Event()
                    self._handles[session_id] = RunHandle(
                        session_id=session_id,
                        cancel_event=cancel_event,
                        started_at=datetime.now(),
                    )
                    logger.info("agent_run_registered", session_id=session_id)
                    return cancel_event
                previous_run_id = previous.run_id
                previous_finished = previous.finished

            # A new run for the same session must not overtake persistence of
            # the previous run's interrupted transcript.
            await self.cancel(
                session_id,
                expected_run_id=previous_run_id,
                reason="superseded_by_new_run",
            )
            await previous_finished.wait()
            if previous_run_id:
                await self.ensure_pause_succeeded(session_id, previous_run_id)

    async def attach_run_id(
        self,
        session_id: str,
        cancel_event: asyncio.Event,
        run_id: str,
    ) -> bool:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle or handle.cancel_event is not cancel_event:
                return False
            if handle.run_id == run_id:
                return True
            # Commit local ownership only after the shared claim succeeds.
            # Keep the local lock across the claim so unregister cannot race it.
            registered = await self._store.register(session_id, run_id)
            if not registered:
                handle.shared_registration_rejected = True
                logger.warning(
                    "agent_run_shared_registration_rejected",
                    session_id=session_id,
                    run_id=run_id,
                )
                return False
            handle.run_id = run_id
            handle.shared_registration_rejected = False
            handle.monitor_task = asyncio.create_task(
                self._monitor_shared_cancellation(session_id, cancel_event, run_id)
            )
        return True

    async def _monitor_shared_cancellation(
        self,
        session_id: str,
        cancel_event: asyncio.Event,
        run_id: str,
    ) -> None:
        while True:
            try:
                state = await self._store.get(session_id)
                if (
                    state
                    and state.run_id == run_id
                    and state.status == "pause_requested"
                ):
                    await self._cancel_local(
                        session_id,
                        expected_run_id=run_id,
                        reason=state.reason or "client_cancelled",
                    )
                    return
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning(
                    "agent_run_cancel_monitor_failed",
                    session_id=session_id,
                    run_id=run_id,
                    error=str(error),
                )
            async with self._lock:
                handle = self._handles.get(session_id)
                if not handle or handle.cancel_event is not cancel_event:
                    return
            await asyncio.sleep(self._poll_interval)

    async def attach_streaming_executor(self, session_id: str, executor: Any) -> None:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle:
                return
            handle.streaming_executor = executor
            if handle.cancel_event.is_set():
                executor.discard()

    async def attach_run_task(self, session_id: str, task: asyncio.Task) -> None:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle:
                return
            handle.run_task = task

    async def arm_run_task(self, session_id: str, cancel_event: asyncio.Event) -> None:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle or handle.cancel_event is not cancel_event:
                return
            handle.task_armed = True
            if handle.cancel_event.is_set() and handle.run_task and not handle.run_task.done():
                handle.run_task.cancel()

    async def cancel(
        self,
        session_id: str,
        *,
        expected_run_id: Optional[str] = None,
        reason: str = "user_paused",
    ) -> bool:
        shared_cancelled = await self._store.request_cancel(
            session_id,
            expected_run_id,
            reason,
        )
        local_cancelled = await self._cancel_local(
            session_id,
            expected_run_id=expected_run_id,
            reason=reason,
        )
        return shared_cancelled or local_cancelled

    async def _cancel_local(
        self,
        session_id: str,
        *,
        expected_run_id: Optional[str],
        reason: str,
    ) -> bool:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle:
                return False
            if expected_run_id is not None and handle.run_id != expected_run_id:
                logger.info(
                    "agent_run_cancel_ignored",
                    session_id=session_id,
                    expected_run_id=expected_run_id,
                    active_run_id=handle.run_id,
                )
                return False
            if handle.pause_reason != "user_paused" or reason == "user_paused":
                handle.pause_reason = reason
            run_id = handle.run_id

        await run_ownership_registry.begin_pause(session_id, run_id)
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle or (expected_run_id is not None and handle.run_id != expected_run_id):
                return False
            handle.cancel_event.set()
            if handle.streaming_executor:
                handle.streaming_executor.discard()
            if handle.task_armed and handle.run_task and not handle.run_task.done():
                handle.run_task.cancel()
        logger.info(
            "agent_run_cancelled",
            session_id=session_id,
            run_id=run_id,
            reason=reason,
        )
        return True

    async def pause_reason(
        self,
        session_id: str,
        cancel_event: asyncio.Event,
    ) -> Optional[str]:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle or handle.cancel_event is not cancel_event:
                return None
            local_reason = handle.pause_reason
            run_id = handle.run_id
        if local_reason == "user_paused" or not run_id:
            return local_reason

        state = await self._store.get(session_id)
        if (
            not state
            or state.run_id != run_id
            or state.status != "pause_requested"
            or not state.reason
        ):
            return local_reason

        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle or handle.cancel_event is not cancel_event:
                return None
            if handle.pause_reason != "user_paused" or state.reason == "user_paused":
                handle.pause_reason = state.reason
            effective_reason = handle.pause_reason
        await run_ownership_registry.begin_pause(session_id, run_id)
        return effective_reason

    async def can_finalize(
        self,
        session_id: str,
        cancel_event: asyncio.Event,
    ) -> bool:
        async with self._lock:
            handle = self._handles.get(session_id)
            if not handle or handle.cancel_event is not cancel_event or handle.shared_registration_rejected:
                return False
            run_id = handle.run_id
        if not run_id:
            # Cancellation can arrive during setup, before the runtime binds
            # its run ID. Permit that checkpoint only if no shared run owns it.
            shared = await self._store.get(session_id)
            return shared is None or shared.status in {"paused", "finished", "failed"}
        shared = await self._store.get(session_id)
        return bool(shared and shared.run_id == run_id)

    async def record_finalization_error(
        self,
        session_id: str,
        cancel_event: asyncio.Event,
        error: Exception,
    ) -> None:
        run_id = None
        async with self._lock:
            handle = self._handles.get(session_id)
            if handle and handle.cancel_event is cancel_event and handle.run_id:
                run_id = handle.run_id
                self._pause_errors[(session_id, handle.run_id)] = str(error)
        if run_id:
            # 送达失败只影响跨进程屏障等待方（退化为超时）；异常不外抛，
            # 避免顶掉调用方正在传播的原始 finalization 错误。
            try:
                await commit_with_retry(
                    lambda: self._store.finish(session_id, run_id, error=str(error))
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

    async def ensure_pause_succeeded(self, session_id: str, run_id: str) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._barrier_timeout
        while True:
            async with self._lock:
                error = self._pause_errors.get((session_id, run_id))
            if error:
                raise PauseCheckpointError(error)
            state = await self._store.get(session_id)
            if state and state.run_id == run_id:
                if state.status == "failed":
                    raise PauseCheckpointError(state.error or "pause_checkpoint_failed")
                if state.status in {"paused", "finished"}:
                    return
            elif state and state.run_id != run_id:
                raise PauseCheckpointError("pause_checkpoint_state_replaced")
            if loop.time() >= deadline:
                raise PauseCheckpointError("pause_checkpoint_timeout")
            await asyncio.sleep(self._poll_interval)

    async def unregister(self, session_id: str, cancel_event: asyncio.Event) -> None:
        run_id = None
        monitor_task = None
        async with self._lock:
            handle = self._handles.get(session_id)
            if handle and handle.cancel_event is cancel_event:
                run_id = handle.run_id
                monitor_task = handle.monitor_task
                handle.finished.set()
                self._handles.pop(session_id, None)
                logger.info("agent_run_unregistered", session_id=session_id)
        if monitor_task and monitor_task is not asyncio.current_task():
            monitor_task.cancel()
            try:
                await await_unkillable(asyncio.gather(monitor_task, return_exceptions=True))
            except Exception:
                pass
        if run_id is not None:
            # 这是暂停屏障的释放信号，必须送达（见 await_unkillable）；
            # 最终失败也只记日志，不外抛以免顶掉濒死任务的原生异常。
            try:
                await commit_with_retry(lambda: self._store.finish(session_id, run_id))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error(
                    "agent_run_finish_commit_failed",
                    session_id=session_id,
                    run_id=run_id,
                    error=str(error),
                )
            try:
                await await_unkillable(run_ownership_registry.revoke(session_id, run_id))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning(
                    "agent_run_ownership_revoke_failed",
                    session_id=session_id,
                    run_id=run_id,
                    error=str(error),
                )

    async def recover_stale_states(self) -> int:
        """启动对账：回收硬杀/重启遗留的非终态取消状态。

        进程重启后本进程不可能存在存活 run，`state:<session>` 键上的非终态
        状态全部是清理链没能送达 finish 的孤儿；REGISTER 对非终态异 run_id
        的注册拒绝会把会话锁死到 TTL 到期。agent-workflow 键可能属于其他
        进程（worker 侧调度），不在回收范围。
        """
        try:
            stale = await self._store.list_non_terminal_sessions()
        except Exception as error:
            logger.warning("cancellation_state_scan_failed", error=str(error))
            return 0
        recovered = 0
        for session_id, state in stale:
            if session_id.startswith("agent-workflow:"):
                continue
            try:
                finished = await self._store.finish(session_id, state.run_id)
            except Exception as error:
                logger.warning(
                    "cancellation_state_recover_failed",
                    session_id=session_id,
                    run_id=state.run_id,
                    error=str(error),
                )
                continue
            if finished:
                recovered += 1
                logger.info(
                    "cancellation_state_recovered",
                    session_id=session_id,
                    run_id=state.run_id,
                    status=state.status,
                    reason=state.reason,
                )
        if stale:
            logger.info(
                "cancellation_state_recover_completed",
                stale=len(stale),
                recovered=recovered,
                skipped_workflow=sum(
                    1 for session_id, _ in stale if session_id.startswith("agent-workflow:")
                ),
            )
        return recovered

    async def is_cancelled(self, session_id: str) -> bool:
        async with self._lock:
            handle = self._handles.get(session_id)
            return bool(handle and handle.cancel_event.is_set())


def _create_production_registry() -> CancellationRegistry:
    import redis.asyncio as redis

    from config.settings import settings

    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    store = RedisCancellationStateStore(
        client,
        key_prefix=f"{settings.agent_steering_redis_prefix}:cancellation",
        ttl_seconds=settings.agent_steering_ttl_seconds,
    )
    return CancellationRegistry(store=store)


cancellation_registry = _create_production_registry()
