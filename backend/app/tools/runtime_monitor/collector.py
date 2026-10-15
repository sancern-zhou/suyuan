"""运行监控数据采集：窗口计算 + 异常数据汇总。

窗口口径：默认以监控任务自身上次成功执行完成时间为起点（首个周期回退
过去 60 分钟），保证不规则调度间隔与监控自身失败造成的空缺都在下一轮
被完整覆盖，窗口不重叠不遗漏。手动传 window_minutes 可强制指定窗口。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import structlog

from app.fetchers.base.run_log import read_recent_runs
from app.scheduled_tasks.models.execution import ExecutionStatus

logger = structlog.get_logger()

DEFAULT_WINDOW_MINUTES = 60
MAX_SAMPLE_ITEMS = 10
# 百度路况日配额剩余低于该值时视为告警（硬顶 1900，见 quota.py）。
BAIDU_QUOTA_WARNING_REMAINING = 100


async def resolve_window(
    execution_storage: Any,
    task_id: str,
    current_execution_id: Optional[str],
    window_minutes: Optional[int] = None,
) -> dict[str, Any]:
    """返回 {"start": datetime, "end": datetime, "source": str}。"""
    now = datetime.now()
    if window_minutes and int(window_minutes) > 0:
        return {
            "start": now - timedelta(minutes=int(window_minutes)),
            "end": now,
            "source": "manual",
        }

    last_success_at: Optional[datetime] = None
    try:
        records = execution_storage.list_by_task(
            task_id, limit=5, status=ExecutionStatus.SUCCESS
        )
    except Exception as exc:  # noqa: BLE001 - 窗口退化为默认值
        logger.warning("runtime_monitor_window_lookup_failed", error=str(exc))
        records = []
    for record in records:
        if current_execution_id and record.execution_id == current_execution_id:
            continue
        if record.completed_at:
            last_success_at = record.completed_at
            break

    if last_success_at is None:
        return {
            "start": now - timedelta(minutes=DEFAULT_WINDOW_MINUTES),
            "end": now,
            "source": "default_first_run",
        }
    return {"start": last_success_at, "end": now, "source": "last_success"}


async def collect_scheduled_task_failures(
    execution_storage: Any,
    since: datetime,
    until: datetime,
    exclude_task_id: Optional[str] = None,
) -> dict[str, Any]:
    """定时任务失败/超时/取消执行记录。"""
    try:
        if hasattr(execution_storage, "list_in_window"):
            records = execution_storage.list_in_window(
                since=since,
                until=until,
                statuses=[
                    ExecutionStatus.FAILED,
                    ExecutionStatus.TIMEOUT,
                    ExecutionStatus.CANCELLED,
                ],
                exclude_task_id=exclude_task_id,
                limit=100,
            )
        else:
            records = [
                record
                for record in (execution_storage.list_recent(limit=200) or [])
                if record.started_at
                and since <= record.started_at < until
                and record.status
                in (
                    ExecutionStatus.FAILED,
                    ExecutionStatus.TIMEOUT,
                    ExecutionStatus.CANCELLED,
                )
                and (not exclude_task_id or record.task_id != exclude_task_id)
            ]
        items = [
            {
                "task_id": record.task_id,
                "task_name": record.task_name,
                "status": record.status.value,
                "started_at": record.started_at.isoformat(timespec="seconds")
                if record.started_at
                else None,
                "error_message": (record.error_message or "")[:300] or None,
            }
            for record in records
        ]
        return {"available": True, "count": len(items), "items": items[:MAX_SAMPLE_ITEMS]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("runtime_monitor_task_failures_failed", error=str(exc))
        return {"available": False, "error": str(exc)[:200], "count": 0, "items": []}


async def collect_agent_session_errors(
    since: datetime,
    until: datetime,
) -> dict[str, Any]:
    """Agent 会话 error 语义消息。"""
    try:
        from app.db.session_repository import SessionRepository

        rows = await SessionRepository().list_error_messages_in_window(
            since=since, until=until, limit=100
        )
        return {
            "available": True,
            "count": len(rows),
            "items": rows[:MAX_SAMPLE_ITEMS],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("runtime_monitor_session_errors_failed", error=str(exc))
        return {"available": False, "error": str(exc)[:200], "count": 0, "items": []}


def collect_fetcher_failures(since: datetime, until: datetime) -> dict[str, Any]:
    """Fetcher 抓取失败（fetcher_runs.jsonl 留痕）。"""
    try:
        runs = read_recent_runs(limit=500)
        failures = [
            run
            for run in runs
            if run.get("status") == "failed"
            and _in_window(run.get("finished_at"), since, until)
        ]
        items = [
            {
                "fetcher": run.get("fetcher"),
                "finished_at": run.get("finished_at"),
                "error": (run.get("error") or "")[:300] or None,
            }
            for run in failures
        ]
        return {"available": True, "count": len(items), "items": items[:MAX_SAMPLE_ITEMS]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("runtime_monitor_fetcher_failures_failed", error=str(exc))
        return {"available": False, "error": str(exc)[:200], "count": 0, "items": []}


async def collect_llm_failures(since: datetime) -> dict[str, Any]:
    """LLM 限流/失败小时桶计数（覆盖窗口起点所在小时起）。"""
    try:
        from app.services.llm_failure_counter import read_llm_failure_buckets

        hours = max(
            1, int((datetime.now() - since).total_seconds() // 3600) + 1
        )
        buckets = await read_llm_failure_buckets(hours=hours)
        total = sum(int(bucket.get("total") or 0) for bucket in buckets.values())
        return {"available": True, "count": total, "buckets": buckets}
    except Exception as exc:  # noqa: BLE001
        logger.warning("runtime_monitor_llm_failures_failed", error=str(exc))
        return {"available": False, "error": str(exc)[:200], "count": 0}


async def collect_baidu_traffic_quota() -> dict[str, Any]:
    """百度路况当日配额余量；模块不存在（非许昌环境）时返回 not_applicable。"""
    try:
        from app.tools.xuchang.traffic_status.quota import (
            QUOTA_HARDCAP,
            quota_remaining,
        )
    except Exception:  # noqa: BLE001 - 非许昌部署没有该模块
        return {"available": False, "applicable": False}
    try:
        remaining = await quota_remaining()
        if remaining is None:
            return {"available": False, "applicable": True}
        used = QUOTA_HARDCAP - remaining
        return {
            "available": True,
            "applicable": True,
            "used": used,
            "hardcap": QUOTA_HARDCAP,
            "remaining": remaining,
            "warning": remaining <= BAIDU_QUOTA_WARNING_REMAINING,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("runtime_monitor_baidu_quota_failed", error=str(exc))
        return {"available": False, "applicable": True, "error": str(exc)[:200]}


def _in_window(iso_time: Optional[str], since: datetime, until: datetime) -> bool:
    if not iso_time:
        return False
    try:
        moment = datetime.fromisoformat(str(iso_time))
    except ValueError:
        return False
    return since <= moment < until
