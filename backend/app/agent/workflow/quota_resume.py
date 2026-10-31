"""配额重置自动续跑（对齐 ZCode dynamic-workflow-quota-resume）。

设计原则（与 ZCode 一致）：
- **唯一数据源是快照本身**：父会话 metadata 里 coordinator 快照的
  ``quota_pause.reset_at`` 才是事实，Redis ZSET 只当"到点唤醒器"，不建
  独立状态表；定时器到点必须重读快照、复核 reset_at 仍然匹配才续跑。
- 续跑走与手动 resume 完全同一条路：读快照 → 校验 → ``store.enqueue``
  入 worker 队列（resume 一个 stopped 工作流，不是重新提交）。
- 防循环：同一 reset_at 重复失败（网关给出假/停滞的重置时间）按 10 分钟起
  ×2 逐次、封顶 60 分钟拉开间隔，最多 3 次后放弃（留手动 resume）；reset_at
  变化（真正的新额度窗口）则重新计数。
- 全程 fail-soft：Redis 不可用/会话读取失败只记日志，行为退化为今天的
  "失败后手动 resume"，绝不因续跑设施放大故障。

覆盖两条路径：inline（web 进程内跑的工作流，主流）与 durable（worker 队列），
都在工作流结算后调用 :func:`schedule_quota_resume` 挂起唤醒器；worker 循环
的 :func:`scan_and_resume_due` 每秒 tick 扫描到点任务。
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Mapping, Optional

import structlog

from .jobs import get_workflow_job_store

logger = structlog.get_logger()

# 续跑余量：reset_at + 60s，避免卡着整点边界请求
RESUME_MARGIN_SECONDS = 60.0
# 同一 reset_at 重复失败的拉开间隔：10 分钟起 ×2 逐次、封顶 60 分钟、最多 3 次
MIN_SPACING_SECONDS = 600.0
MAX_SPACING_SECONDS = 3600.0
MAX_RESUME_ATTEMPTS = 3
# 每轮 tick 最多处理的到点任务数
SCAN_BATCH = 10


def _zset_key(store: Any) -> str:
    return f"{store.prefix}:quota_resume"


def _meta_key(store: Any) -> str:
    return f"{store.prefix}:quota_resume_meta"


def _member(session_id: str, workflow_id: str) -> str:
    return f"{session_id}:{workflow_id}"


async def schedule_quota_resume(
    session_id: str,
    workflow_id: str,
    reset_at: float,
    *,
    source: str = "",
) -> bool:
    """挂起一个到点唤醒器；fail-soft，Redis 不可用返回 False。"""
    if not session_id or not workflow_id or not reset_at or reset_at <= 0:
        return False
    try:
        store = get_workflow_job_store()
        redis = store.redis
        member = _member(session_id, workflow_id)
        # 同一 reset_at 的重试计数（防假重置时间循环）；reset_at 变化则重新计数
        attempts = 0
        raw_meta = await redis.hget(_meta_key(store), member)
        if raw_meta:
            try:
                meta = json.loads(raw_meta)
                if float(meta.get("reset_at") or 0) == float(reset_at):
                    attempts = int(meta.get("attempts") or 0)
            except (TypeError, ValueError):
                attempts = 0
        if attempts >= MAX_RESUME_ATTEMPTS:
            logger.warning(
                "workflow_quota_resume_attempts_exhausted",
                workflow_id=workflow_id,
                reset_at=reset_at,
                source=source,
            )
            return False
        payload = json.dumps(
            {"session_id": session_id, "workflow_id": workflow_id, "reset_at": float(reset_at), "attempts": attempts},
            ensure_ascii=False,
        )
        await redis.zadd(_zset_key(store), {member: float(reset_at) + RESUME_MARGIN_SECONDS})
        await redis.hset(_meta_key(store), member, payload)
        logger.info(
            "workflow_quota_resume_scheduled",
            workflow_id=workflow_id,
            session_id=session_id,
            reset_at=reset_at,
            attempts=attempts,
            source=source,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - 续跑设施不放大故障
        logger.warning("workflow_quota_resume_schedule_failed", workflow_id=workflow_id, error=str(exc))
        return False


async def _reschedule(
    store: Any,
    member: str,
    payload: Mapping[str, Any],
    *,
    reset_at: Optional[float] = None,
    bump_attempts: bool = False,
    delay_seconds: Optional[float] = None,
) -> None:
    """重排唤醒器：delay_seconds（失败退避）或新 reset_at；超限则丢弃。"""
    attempts = int(payload.get("attempts") or 0) + (1 if bump_attempts else 0)
    effective_reset = float(reset_at if reset_at is not None else payload.get("reset_at") or 0)
    if bump_attempts and attempts >= MAX_RESUME_ATTEMPTS:
        await store.redis.zrem(_zset_key(store), member)
        await store.redis.hdel(_meta_key(store), member)
        logger.warning("workflow_quota_resume_dropped_after_backoff", member=member)
        return
    if delay_seconds is not None:
        score = time.time() + delay_seconds
    else:
        score = effective_reset + RESUME_MARGIN_SECONDS
    updated = {
        **dict(payload),
        "reset_at": effective_reset,
        "attempts": attempts,
    }
    await store.redis.zadd(_zset_key(store), {member: score})
    await store.redis.hset(_meta_key(store), member, json.dumps(updated, ensure_ascii=False))


async def _load_workflow_snapshot(session_id: str, workflow_id: str) -> Optional[Mapping[str, Any]]:
    """从父会话 metadata 读工作流快照（与 resume 端点同源）。"""
    try:
        from app.agent.session import get_session_manager

        session = get_session_manager().load_session(session_id)
        import inspect

        if inspect.isawaitable(session):
            session = await session
        if session is None:
            return None
        metadata = dict(getattr(session, "metadata", None) or {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("workflow_quota_resume_snapshot_load_failed", session_id=session_id, error=str(exc))
        return None
    values = metadata.get("workflow_coordinators")
    snapshots: Mapping[str, Any] = {}
    if isinstance(values, dict):
        snapshots = {
            str(key): dict(value)
            for key, value in values.items()
            if isinstance(value, dict) and value.get("workflow_id")
        }
    else:
        legacy = metadata.get("workflow_coordinator")
        if isinstance(legacy, dict) and legacy.get("workflow_id"):
            snapshots = {str(legacy["workflow_id"]): dict(legacy)}
    return snapshots.get(workflow_id)


async def scan_and_resume_due(store: Optional[Any] = None, *, now: Optional[float] = None) -> int:
    """扫描到点的配额暂停工作流并投递续跑；返回投递数量。worker 循环每秒调用。"""
    if store is None:
        try:
            store = get_workflow_job_store()
        except Exception as exc:  # noqa: BLE001 - Redis 不可用时静默（fail-soft）
            logger.debug("workflow_quota_resume_store_unavailable", error=str(exc))
            return 0
    current = time.time() if now is None else now
    dispatched = 0
    try:
        members = await store.redis.zrangebyscore(_zset_key(store), "-inf", current, start=0, num=SCAN_BATCH)
    except Exception as exc:  # noqa: BLE001 - Redis 不可用时静默（fail-soft）
        logger.debug("workflow_quota_resume_scan_unavailable", error=str(exc))
        return 0
    for member in members:
        member = str(member)
        try:
            raw_meta = await store.redis.hget(_meta_key(store), member)
            if not raw_meta:
                # 唤醒器在但元数据丢失：丢弃，靠下一次失败重新挂起
                await store.redis.zrem(_zset_key(store), member)
                continue
            payload = json.loads(raw_meta)
            session_id = str(payload.get("session_id") or "")
            workflow_id = str(payload.get("workflow_id") or "")
            scheduled_reset = float(payload.get("reset_at") or 0)
            snapshot = await _load_workflow_snapshot(session_id, workflow_id)
            if snapshot is None:
                # 快照没了（会话清理）：唤醒器作废
                await store.redis.zrem(_zset_key(store), member)
                await store.redis.hdel(_meta_key(store), member)
                continue
            quota_pause = snapshot.get("quota_pause") if isinstance(snapshot, Mapping) else None
            if not isinstance(quota_pause, Mapping) or not quota_pause.get("reset_at"):
                # 快照已无配额暂停（被手动续跑过/已被别的路径处理）：作废
                await store.redis.zrem(_zset_key(store), member)
                await store.redis.hdel(_meta_key(store), member)
                continue
            current_reset = float(quota_pause.get("reset_at") or 0)
            if current_reset != scheduled_reset:
                # 网关给出了新的重置时刻：按新时刻重排，计数清零
                await _reschedule(store, member, payload, reset_at=current_reset)
                continue
            if snapshot.get("status") == "cancelled" or (snapshot.get("budget_state") or {}).get("exhausted"):
                await store.redis.zrem(_zset_key(store), member)
                await store.redis.hdel(_meta_key(store), member)
                continue
            from .registry import active_workflow_registry

            if await active_workflow_registry.get(workflow_id) is not None:
                # 仍在运行（被手动续跑）：唤醒器作废
                await store.redis.zrem(_zset_key(store), member)
                await store.redis.hdel(_meta_key(store), member)
                continue
            attempts = int(payload.get("attempts") or 0)
            if attempts >= MAX_RESUME_ATTEMPTS:
                # 同一 reset_at 的续跑次数已用尽：丢弃，留手动 resume
                await store.redis.zrem(_zset_key(store), member)
                await store.redis.hdel(_meta_key(store), member)
                logger.warning(
                    "workflow_quota_resume_attempts_exhausted",
                    workflow_id=workflow_id,
                    reset_at=scheduled_reset,
                )
                continue
            await store.enqueue(
                session_id=session_id,
                workflow_id=workflow_id,
                definition=snapshot.get("definition") or {},
                snapshot=dict(snapshot),
            )
            await store.redis.zrem(_zset_key(store), member)
            # 保留计数（不删 meta）：若工作流以同一 reset_at 再次失败，
            # schedule 会继承 attempts，达到上限后停止自动续跑。
            await store.redis.hset(
                _meta_key(store),
                member,
                json.dumps({**payload, "attempts": attempts + 1}, ensure_ascii=False),
            )
            dispatched += 1
            logger.info(
                "workflow_quota_resume_dispatched",
                workflow_id=workflow_id,
                session_id=session_id,
                reset_at=scheduled_reset,
            )
        except Exception as exc:  # noqa: BLE001 - 单条失败退避重排，不影响其余
            logger.warning("workflow_quota_resume_member_failed", member=member, error=str(exc))
            try:
                raw_meta = await store.redis.hget(_meta_key(store), member)
                payload = json.loads(raw_meta) if raw_meta else {}
                if payload:
                    attempts = int(payload.get("attempts") or 0)
                    delay = min(MAX_SPACING_SECONDS, MIN_SPACING_SECONDS * (2 ** attempts))
                    await _reschedule(store, member, payload, bump_attempts=True, delay_seconds=delay)
            except Exception:  # noqa: BLE001
                pass
    return dispatched


async def pending_quota_resumes() -> int:
    """当前挂起的配额续跑任务数（运行监控用）。"""
    try:
        store = get_workflow_job_store()
        return int(await store.redis.zcard(_zset_key(store)))
    except Exception:  # noqa: BLE001
        return 0
