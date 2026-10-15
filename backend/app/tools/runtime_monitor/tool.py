"""查询上一时段后台运行异常工具（只读，仅定时任务上下文可用）。

与定时任务"运行监控"任务配套：Agent 先调用本工具拿结构化异常数据，
分析后自行决定是否调用 broadcast_social_users 推送结论。无异常时 Agent
应直接结束、不打扰用户。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import structlog

from app.tools.base import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class QueryRuntimeAnomaliesTool(LLMTool):
    """Collect anomalies in the window since the monitor task's last success."""

    def __init__(self):
        function_schema = {
            "name": "query_runtime_anomalies",
            "description": (
                "查询后台自本监控任务上次成功执行以来的异常与告警情况，"
                "包括：定时任务失败/超时、Agent 会话错误、数据抓取（Fetcher）失败、"
                "LLM 限流与供应商失败计数、百度路况配额余量。"
                "返回结构化数据与 has_anomalies 总体标记；仅运行监控定时任务可调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "window_minutes": {
                        "type": "integer",
                        "description": (
                            "可选。显式指定回看窗口分钟数（从现在往回）；"
                            "不传则自动使用上次成功执行以来的完整窗口"
                        ),
                        "minimum": 1,
                        "maximum": 4320,
                    },
                },
            },
        }
        super().__init__(
            name="query_runtime_anomalies",
            description="查询上一时段后台运行异常与告警情况",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(
        self,
        context=None,
        window_minutes: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        scheduled_context = getattr(context, "scheduled_task_context", None)
        if not isinstance(scheduled_context, dict) or not scheduled_context.get("task_id"):
            return {
                "status": "failed",
                "success": False,
                "data": {"has_anomalies": False},
                "summary": "当前不是定时任务执行上下文，不能查询运行异常",
            }

        task_id = str(scheduled_context["task_id"])
        execution_id = scheduled_context.get("execution_id")
        try:
            from app.scheduled_tasks.service import get_scheduled_task_service

            service = get_scheduled_task_service()
            execution_storage = service.execution_storage

            from app.tools.runtime_monitor import collector

            window = await collector.resolve_window(
                execution_storage,
                task_id=task_id,
                current_execution_id=str(execution_id) if execution_id else None,
                window_minutes=window_minutes,
            )
            since, until = window["start"], window["end"]

            task_failures = await collector.collect_scheduled_task_failures(
                execution_storage,
                since=since,
                until=until,
                exclude_task_id=task_id,
            )
            session_errors = await collector.collect_agent_session_errors(
                since=since, until=until
            )
            fetcher_failures = collector.collect_fetcher_failures(
                since=since, until=until
            )
            llm_failures = await collector.collect_llm_failures(since=since)
            baidu_quota = await collector.collect_baidu_traffic_quota()

            quota_warning = bool(
                baidu_quota.get("available") and baidu_quota.get("warning")
            )
            has_anomalies = any(
                section.get("count", 0) > 0
                for section in (
                    task_failures,
                    session_errors,
                    fetcher_failures,
                    llm_failures,
                )
            ) or quota_warning

            data = {
                "window": {
                    "start": since.isoformat(timespec="seconds"),
                    "end": until.isoformat(timespec="seconds"),
                    "source": window["source"],
                },
                "scheduled_task_failures": task_failures,
                "agent_session_errors": session_errors,
                "fetcher_failures": fetcher_failures,
                "llm_failures": llm_failures,
                "baidu_traffic_quota": baidu_quota,
                "has_anomalies": has_anomalies,
            }
            logger.info(
                "runtime_anomalies_queried",
                task_id=task_id,
                execution_id=execution_id,
                window_source=window["source"],
                has_anomalies=has_anomalies,
            )
            summary = (
                f"窗口 {data['window']['start']} ~ {data['window']['end']}："
                f"任务失败 {task_failures.get('count', 0)}，会话错误 "
                f"{session_errors.get('count', 0)}，抓取失败 "
                f"{fetcher_failures.get('count', 0)}，LLM 失败 "
                f"{llm_failures.get('count', 0)}"
                + ("，百度路况配额紧张" if quota_warning else "")
                + ("；存在异常" if has_anomalies else "；未发现异常")
            )
            return {
                "status": "success",
                "success": True,
                "data": data,
                "metadata": {
                    "tool_name": self.name,
                    "task_id": task_id,
                    "execution_id": execution_id,
                },
                "summary": summary,
            }
        except Exception as exc:  # noqa: BLE001 - 工具错误以结构化结果返回
            logger.error(
                "runtime_anomalies_query_failed",
                task_id=task_id,
                error=str(exc),
                exc_info=True,
            )
            return {
                "status": "failed",
                "success": False,
                "data": {"has_anomalies": False},
                "metadata": {"tool_name": self.name, "task_id": task_id},
                "summary": f"运行异常查询失败：{str(exc)[:120]}",
            }


query_runtime_anomalies_tool = QueryRuntimeAnomaliesTool()
