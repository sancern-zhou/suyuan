"""运行异常事件发射器（Fast Path）。

失败落库点（定时任务失败、fetcher 连续失败）写完留痕后调用本模块，向
事件总线发射统一的 ``runtime.anomaly.detected`` 事件，由 event 型实时诊断
任务（task_runtime_monitor_realtime 种子）消费。与小时级巡检任务互补：

- 事件路径：分钟级响应；程序层 Redis 冷却去重（SET NX + TTL），冷却窗口
  内的重复失败不进总线、不消耗 LLM；
- 巡检路径：小时级全量回看（task_runtime_monitor），兜底事件发射自身故障
  （Redis 不可用、事件无订阅者）造成的漏报。

发射是旁路能力：Redis 不可用、定时任务服务未初始化、事件无订阅者时全部
静默降级，绝不放大被监控对象的故障。监控任务自身（tags 含 runtime-monitor）
的失败不发射，避免"诊断失败→触发诊断"的自激励循环。

Redis 访问模式与 app.services.llm_failure_counter 一致：模块级懒加载单例，
环境变量配置，失败只记日志。
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 统一事件类型：实时诊断任务按它订阅，attributes.source 区分异常来源。
EVENT_TYPE = "runtime.anomaly.detected"
# 监控任务自身标记：带此 tag 的任务失败不发射事件（防自激励循环）。
MONITOR_TAG = "runtime-monitor"
DEFAULT_COOLDOWN_SECONDS = 1800
DEFAULT_FETCHER_STREAK_THRESHOLD = 2

_redis: Any = None


def _get_redis():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis

        _redis = aioredis.Redis(
            host=os.getenv("REDIS_HOST", "127.0.0.1"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD") or None,
            decode_responses=True,
        )
    return _redis


def get_redis_client():
    """共享同一懒加载客户端（自愈工具的缰绳复用，避免第二份连接池）。"""
    return _get_redis()


def _cooldown_seconds() -> int:
    try:
        return max(60, int(os.getenv("RUNTIME_MONITOR_EVENT_COOLDOWN_SECONDS", DEFAULT_COOLDOWN_SECONDS)))
    except ValueError:
        return DEFAULT_COOLDOWN_SECONDS


async def _try_acquire(source_key: str) -> bool:
    """SET NX EX 抢冷却锁；抢到才允许发射。Redis 故障返回 False（宁漏勿扰）。"""
    try:
        client = _get_redis()
        acquired = await client.set(
            f"monitor:evtcd:{source_key}", "1", nx=True, ex=_cooldown_seconds()
        )
        return bool(acquired)
    except Exception as exc:  # noqa: BLE001 - 旁路能力不放大故障
        logger.warning("anomaly_emitter_cooldown_unavailable", error=str(exc))
        return False


async def _window_incr(source_key: str) -> int:
    """冷却窗口内失败计数（自首次失败起算），供事件携带"窗口内第 N 次"。"""
    try:
        client = _get_redis()
        key = f"monitor:evtwin:{source_key}"
        count = int(await client.incr(key))
        if count == 1:
            # 仅首次创建时设 TTL：计数窗口自首次失败起算一个冷却期。
            await client.expire(key, _cooldown_seconds())
        return count
    except Exception:  # noqa: BLE001 - 计数失败不影响发射判断
        return 0


async def _resolve_service() -> Any | None:
    try:
        from app.scheduled_tasks.service import get_scheduled_task_service

        return get_scheduled_task_service()
    except Exception:  # noqa: BLE001 - 服务未初始化（web 进程）时静默
        return None


async def _publish(attributes: dict[str, Any]) -> None:
    """构造事件并投递到总线；无订阅者是正常情况（publish_event 内部自然空转）。"""
    service = await _resolve_service()
    if service is None:
        return
    try:
        from app.scheduled_tasks.models.event import TaskEvent

        event = TaskEvent(
            event_id=uuid.uuid4().hex,
            event_type=EVENT_TYPE,
            attributes=attributes,
        )
        await service.publish_event(event)
        logger.info(
            "runtime_anomaly_event_published",
            source=attributes.get("source"),
            subject=attributes.get("task_id") or attributes.get("fetcher"),
        )
    except Exception as exc:  # noqa: BLE001 - 发射失败不反向影响业务路径
        logger.warning("runtime_anomaly_event_publish_failed", error=str(exc))


async def emit_task_failure(task: Any, execution: Any) -> None:
    """cron 触发的定时任务失败/超时后发射异常事件。

    排除规则（调用点无需重复判断）：
    - 监控任务自身（tags 含 runtime-monitor）不发射，防自激励；
    - 仅 trigger_type=scheduled 的执行发射——手动触发有人在场，event 触发
      的失败已在事件链路内部留痕，再发射会放大。
    """
    tags = list(getattr(task, "tags", None) or [])
    if MONITOR_TAG in tags:
        return
    if getattr(execution, "trigger_type", None) != "scheduled":
        return
    source_key = f"task:{getattr(task, 'task_id', 'unknown')}"
    window_failures = await _window_incr(source_key)
    if not await _try_acquire(source_key):
        return
    await _publish(
        {
            "source": "scheduled_task",
            "task_id": str(getattr(task, "task_id", "")),
            "task_name": str(getattr(task, "name", "")),
            "status": str(getattr(execution, "status", "failed")),
            "error": str(getattr(execution, "error_message", "") or "")[:200],
            "window_failures": window_failures,
        }
    )


async def emit_fetcher_failure(fetcher_name: str, error: str) -> None:
    """fetcher 失败后计数；连续失败达到阈值才发射（滤掉单次瞬时抖动）。"""
    try:
        client = _get_redis()
        streak = int(await client.incr(f"monitor:fetchstreak:{fetcher_name}"))
        await client.expire(
            f"monitor:fetchstreak:{fetcher_name}", _cooldown_seconds() * 4
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("anomaly_emitter_streak_unavailable", error=str(exc))
        return
    threshold = DEFAULT_FETCHER_STREAK_THRESHOLD
    if streak < threshold:
        return
    source_key = f"fetcher:{fetcher_name}"
    if not await _try_acquire(source_key):
        return
    await _publish(
        {
            "source": "fetcher",
            "fetcher": fetcher_name,
            "error": str(error)[:200],
            "consecutive_failures": streak,
        }
    )


async def reset_fetcher_streak(fetcher_name: str) -> None:
    """fetcher 成功后清零连续失败计数；失败静默。"""
    try:
        await _get_redis().delete(f"monitor:fetchstreak:{fetcher_name}")
    except Exception:  # noqa: BLE001
        pass
