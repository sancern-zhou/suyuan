"""任务级自愈工具（仅定时任务上下文可用，带硬缰绳）。

与 query_runtime_anomalies 配套：监控 Agent 确认异常后，对可安全重跑的
对象执行一次自动恢复动作——失败定时任务重跑（retry_scheduled_task）、
连续失败 fetcher 立即触发抓取（trigger_fetcher）。

缰绳全部是工具内运行时硬约束，不依赖 prompt 自觉：
- 门禁：仅运行监控定时任务上下文可调用（与 query_runtime_anomalies 同款）；
- 冷却：同一对象 15 分钟内最多一次自愈动作（Redis SETNX）；
- 日上限：同一对象每天最多 5 次，超限返回"需人工介入"；
- 对象排除：监控任务自身不重试（防自激励）；已禁用的任务/fetcher 不碰
  （运维主动停的不自动拉起）；最近一次执行已成功的任务不重试；
- Redis 不可用时拒绝执行自愈（无法约束上限，宁可不动手）；
- 动作后台化（asyncio.create_task），不阻塞监控任务自身的执行预算；
  重跑以 manual 触发，其失败不会再次发射异常事件（emitter 排除 manual）。

进程级重启（worker/web）刻意不在此层提供：自愈进程运行在被监控进程内，
重启自己是盲区，由宿主机 L0 探针 + 人工兜底。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict

import structlog

from app.tools.base import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)

MONITOR_TAG = "runtime-monitor"
SELF_HEAL_COOLDOWN_SECONDS = 900
SELF_HEAL_DAILY_LIMIT = 5


def _gate_scheduled_context(context) -> Dict[str, Any] | None:
    """非定时任务上下文返回失败结果；通过返回 None。"""
    scheduled_context = getattr(context, "scheduled_task_context", None)
    if not isinstance(scheduled_context, dict) or not scheduled_context.get("task_id"):
        return {
            "status": "failed",
            "success": False,
            "data": {},
            "summary": "当前不是定时任务执行上下文，不能执行自愈动作",
        }
    return None


async def _check_reins(kind: str, name: str) -> str | None:
    """冷却 + 日上限；返回 None 表示通过，否则返回拒绝原因。"""
    from app.monitoring.anomaly_emitter import get_redis_client

    try:
        client = get_redis_client()
        acquired = await client.set(
            f"monitor:selfheal:cd:{kind}:{name}", "1",
            nx=True, ex=SELF_HEAL_COOLDOWN_SECONDS,
        )
        if not acquired:
            return f"{name} 处于自愈冷却期（{SELF_HEAL_COOLDOWN_SECONDS // 60} 分钟内最多一次），本次不重复执行"
        day_key = f"monitor:selfheal:day:{kind}:{name}:{datetime.now().strftime('%Y%m%d')}"
        used = int(await client.incr(day_key))
        if used == 1:
            await client.expire(day_key, 86400)
        if used > SELF_HEAL_DAILY_LIMIT:
            return (
                f"{name} 今日自愈次数已达上限（{SELF_HEAL_DAILY_LIMIT} 次），"
                "连续自动恢复无效，需人工介入排查"
            )
        return None
    except Exception as exc:  # noqa: BLE001 - 无法约束上限时拒绝动手
        logger.warning("self_heal_reins_unavailable", kind=kind, name=name, error=str(exc))
        return "自愈缰绳（Redis）不可用，为避免失去次数约束本次不执行自动恢复"


def _refuse(
    summary: str,
    task_id: str | None = None,
    tool_name: str = "retry_scheduled_task",
) -> Dict[str, Any]:
    return {
        "status": "failed",
        "success": False,
        "data": {},
        "metadata": {"tool_name": tool_name, "task_id": task_id},
        "summary": summary,
    }


class RetryScheduledTaskTool(LLMTool):
    """Retry a recently failed scheduled task once, in the background."""

    def __init__(self):
        function_schema = {
            "name": "retry_scheduled_task",
            "description": (
                "对最近一次执行失败的定时任务发起一次后台重跑（自愈动作）。"
                "仅运行监控任务可调用；工具内置冷却与每日次数上限，"
                "重跑不阻塞当前监控任务，结果由下一轮巡检核实。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "要重跑的定时任务 ID（来自 query_runtime_anomalies 的失败明细）",
                    },
                },
                "required": ["task_id"],
            },
        }
        super().__init__(
            name="retry_scheduled_task",
            description="后台重跑最近失败的定时任务（自愈，带硬缰绳）",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(self, context=None, task_id: str = "", **kwargs) -> Dict[str, Any]:
        if gate := _gate_scheduled_context(context):
            return gate
        if not task_id:
            return _refuse("缺少 task_id 参数")

        try:
            from app.scheduled_tasks.service import get_scheduled_task_service

            service = get_scheduled_task_service()
        except Exception:
            service = None
        if service is None:
            return _refuse("定时任务服务不可用", task_id)

        task = service.task_storage.get(task_id)
        if task is None:
            return _refuse(f"任务不存在：{task_id}", task_id)
        if MONITOR_TAG in (task.tags or []):
            return _refuse(f"监控任务自身不自动重试：{task_id}", task_id)
        trigger = str(getattr(task.trigger_type, "value", task.trigger_type))
        if trigger != "schedule":
            return _refuse(f"事件驱动任务不自动重跑（由事件触发）：{task_id}", task_id)
        if not task.enabled:
            return _refuse(f"任务已被禁用（运维主动停用，不自动拉起）：{task_id}", task_id)

        recent = service.execution_storage.list_by_task(task_id, limit=1)
        if recent and str(getattr(recent[0], "status", "")) == "success":
            return _refuse(f"任务最近一次执行已成功，无需重试：{task_id}", task_id)

        reason = await _check_reins("task", task_id)
        if reason:
            return _refuse(reason, task_id)

        async def _run() -> None:
            try:
                execution = await service.execute_task_now(task_id)
                logger.info(
                    "self_heal_retry_finished",
                    task_id=task_id,
                    status=str(execution.status),
                )
            except Exception as exc:  # noqa: BLE001 - 后台任务失败留痕即可
                logger.warning("self_heal_retry_failed", task_id=task_id, error=str(exc))

        asyncio.create_task(_run())
        logger.info("self_heal_retry_started", task_id=task_id)
        return {
            "status": "success",
            "success": True,
            "data": {"task_id": task_id, "action": "background_retry_started"},
            "metadata": {"tool_name": self.name, "task_id": task_id},
            "summary": f"已在后台发起 {task.name} 的重跑；重跑结果由下一轮巡检核实并通报",
        }


class TriggerFetcherTool(LLMTool):
    """Trigger a failing fetcher immediately, in the background."""

    def __init__(self):
        function_schema = {
            "name": "trigger_fetcher",
            "description": (
                "对连续失败的抓取器立即触发一次后台抓取（自愈动作）。"
                "仅运行监控任务可调用；工具内置冷却与每日次数上限，"
                "抓取结果写入运行留痕，由下一轮巡检核实是否恢复。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fetcher_name": {
                        "type": "string",
                        "description": "要触发的抓取器名称（来自 query_runtime_anomalies 的失败明细）",
                    },
                },
                "required": ["fetcher_name"],
            },
        }
        super().__init__(
            name="trigger_fetcher",
            description="立即触发一次抓取器运行（自愈，带硬缰绳）",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(self, context=None, fetcher_name: str = "", **kwargs) -> Dict[str, Any]:
        if gate := _gate_scheduled_context(context):
            return gate
        if not fetcher_name:
            return _refuse("缺少 fetcher_name 参数", tool_name="trigger_fetcher")

        from app.services.lifecycle_manager import get_fetcher_scheduler

        scheduler = get_fetcher_scheduler()
        if scheduler is None:
            return _refuse("抓取调度器不可用（仅 worker 进程可自愈）", tool_name="trigger_fetcher")
        fetcher = scheduler.fetchers.get(fetcher_name)
        if fetcher is None:
            return _refuse(f"抓取器不存在：{fetcher_name}", tool_name="trigger_fetcher")
        status_value = str(getattr(fetcher.status, "value", fetcher.status))
        if status_value == "disabled":
            return _refuse(
                f"抓取器已被禁用（运维主动停用，不自动拉起）：{fetcher_name}",
                tool_name="trigger_fetcher",
            )

        reason = await _check_reins("fetcher", fetcher_name)
        if reason:
            return _refuse(reason, tool_name="trigger_fetcher")

        async def _run() -> None:
            try:
                await scheduler.run_now(fetcher_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("self_heal_fetch_failed", fetcher_name=fetcher_name, error=str(exc))

        asyncio.create_task(_run())
        logger.info("self_heal_fetch_started", fetcher_name=fetcher_name)
        return {
            "status": "success",
            "success": True,
            "data": {"fetcher_name": fetcher_name, "action": "background_trigger_started"},
            "metadata": {"tool_name": self.name, "fetcher_name": fetcher_name},
            "summary": f"已在后台触发 {fetcher_name} 抓取一次；结果由下一轮巡检核实并通报",
        }


retry_scheduled_task_tool = RetryScheduledTaskTool()
trigger_fetcher_tool = TriggerFetcherTool()
