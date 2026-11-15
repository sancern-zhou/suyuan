"""运行故障严重度分级器（确定性规则，P0/P1）。

分级自治的"谁能决定重启"这一安全关键判断绝不交给模型：规则由代码写死，
restart_service 在放行动作前用本模块对**当时**的实时数据重新判级——即使
prompt 被注入或模型幻觉声称 P0，规则不命中就不放行。

P0（重大影响服务运行，允许 AI 决断修复并重启）：
- 抓取器大面积瘫痪：失败 fetcher 数 ≥ 5 且占注册总数 ≥ 80%；
- 定时任务失败风暴：窗口内 ≥ 5 个不同任务出现失败/超时；
- 会话错误风暴：窗口内 Agent 会话错误 ≥ 20 条。

其余一律 P1（一般问题：允许修复与测试，重启生效交人决定）。

测试旁路：环境变量 RUNTIME_MONITOR_FORCE_SEVERITY=p0|p1 仅用于本地联调
（生产环境文件不得设置；命中旁路时结果会带 forced=true 标记）。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

P0 = "p0"
P1 = "p1"

# 抓取器瘫痪：失败的独立 fetcher 数量与占比双阈值
FETCHER_P0_MIN_FAILED = 5
FETCHER_P0_RATIO = 0.8
# 任务失败风暴：窗口内不同任务的失败数
TASK_P0_MIN_DISTINCT = 5
# 会话错误风暴：窗口内错误消息数
SESSION_P0_MIN_ERRORS = 20
# 判级回看窗口
SEVERITY_WINDOW_MINUTES = 30


def classify_severity(
    task_failures: dict[str, Any] | None = None,
    session_errors: dict[str, Any] | None = None,
    fetcher_failures: dict[str, Any] | None = None,
    *,
    total_registered_fetchers: int = 0,
) -> dict[str, Any]:
    """对已采集的窗口数据做确定性判级。

    返回 {"severity": "p0"|"p1", "reasons": [触发规则的人类可读说明]}。
    输入为 collector 各 collect_* 的返回结构（缺省视为无数据，不触发）。
    """
    reasons: list[str] = []

    if fetcher_failures:
        failed_items = fetcher_failures.get("items") or []
        failed_names = {
            item.get("fetcher") for item in failed_items if item.get("fetcher")
        }
        # 注册总数未知时退化为数量阈值
        ratio_hit = (
            total_registered_fetchers > 0
            and len(failed_names) >= FETCHER_P0_MIN_FAILED
            and len(failed_names) / max(total_registered_fetchers, 1) >= FETCHER_P0_RATIO
        )
        count_hit = (
            total_registered_fetchers <= 0 and len(failed_names) >= FETCHER_P0_MIN_FAILED
        )
        if ratio_hit or count_hit:
            reasons.append(
                f"抓取器大面积瘫痪：{len(failed_names)} 个抓取器在窗口内失败"
                + (
                    f"（注册 {total_registered_fetchers} 个，占比 "
                    f"{len(failed_names) / total_registered_fetchers:.0%}）"
                    if total_registered_fetchers > 0
                    else ""
                )
            )

    if task_failures:
        failed_tasks = {
            item.get("task_id") for item in (task_failures.get("items") or [])
            if item.get("task_id")
        }
        if len(failed_tasks) >= TASK_P0_MIN_DISTINCT:
            reasons.append(
                f"定时任务失败风暴：窗口内 {len(failed_tasks)} 个不同任务失败/超时"
            )

    if session_errors:
        count = int(session_errors.get("count") or 0)
        if count >= SESSION_P0_MIN_ERRORS:
            reasons.append(f"会话错误风暴：窗口内 {count} 条 Agent 会话错误")

    severity = P0 if reasons else P1

    forced = (os.getenv("RUNTIME_MONITOR_FORCE_SEVERITY") or "").strip().lower()
    if forced in {P0, P1}:
        if forced == P0 and severity != P0:
            reasons.append("测试旁路强制 P0（RUNTIME_MONITOR_FORCE_SEVERITY）")
        severity = forced
        logger.warning("severity_forced_by_env", severity=severity)

    return {"severity": severity, "reasons": reasons}


async def classify_current_severity(service: Any | None = None) -> dict[str, Any]:
    """对当前实时数据判级（restart_service 放行前调用）。

    独立采集最近 SEVERITY_WINDOW_MINUTES 窗口，不依赖调用方转述的数据——
    门禁必须基于实时事实而非任何一方的声称。
    """
    from app.scheduled_tasks.service import get_scheduled_task_service
    from app.tools.runtime_monitor import collector

    since = datetime.now() - timedelta(minutes=SEVERITY_WINDOW_MINUTES)
    task_failures: dict[str, Any] = {"count": 0, "items": []}
    session_errors: dict[str, Any] = {"count": 0}
    total_fetchers = 0
    try:
        svc = service or get_scheduled_task_service()
        if svc is not None:
            task_failures = await collector.collect_scheduled_task_failures(
                svc.execution_storage, since=since, until=datetime.now()
            )
        session_errors = await collector.collect_agent_session_errors(
            since=since, until=datetime.now()
        )
    except Exception as exc:  # noqa: BLE001 - 判级失败按 P1 处理（宁可不重启）
        logger.warning("severity_collect_failed", error=str(exc))
        return {"severity": P1, "reasons": [f"判级数据采集失败，保守按 P1：{exc}"]}

    fetcher_failures = collector.collect_fetcher_failures(since=since, until=datetime.now())
    try:
        from app.services.lifecycle_manager import get_fetcher_scheduler

        scheduler = get_fetcher_scheduler()
        if scheduler is not None:
            total_fetchers = len(getattr(scheduler, "fetchers", {}) or {})
    except Exception:  # noqa: BLE001
        total_fetchers = 0

    return classify_severity(
        task_failures=task_failures,
        session_errors=session_errors,
        fetcher_failures=fetcher_failures,
        total_registered_fetchers=total_fetchers,
    )
