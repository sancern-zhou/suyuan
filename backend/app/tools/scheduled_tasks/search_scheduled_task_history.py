"""Scheduled task history case retrieval tool."""

from __future__ import annotations

from typing import Any, Dict

import structlog

from app.scheduled_tasks.history_retrieval import search_history_cases
from app.scheduled_tasks.storage.task_case_storage import TaskCaseStorage
from app.tools.base import LLMTool, ToolCategory

logger = structlog.get_logger()


class SearchScheduledTaskHistoryTool(LLMTool):
    """Search the current scheduled task's case library."""

    def __init__(self):
        function_schema = {
            "name": "search_scheduled_task_history",
            "description": (
                "检索当前定时任务专属历史案例库。用于查找相似旧案例、复发问题、"
                "历史结论对比和上次报告引用；只能在定时任务执行上下文中使用。"
                "当任务需要判断问题是否复发、对比历史结论、参考相似异常、引用上次报告，"
                "或对旧经验不确定时，应主动调用。检索结果仅作历史背景参考，不能替代本次事实核查。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索词，包含站点、城市、污染物、事件类型、异常现象或历史结论关键词",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回案例数量，仍会受任务配置上限约束",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "status": {
                        "type": "string",
                        "description": "按执行状态筛选：succeeded、failed、timeout 或 any",
                        "enum": ["succeeded", "failed", "timeout", "any"],
                        "default": "any",
                    },
                    "trigger_type": {
                        "type": "string",
                        "description": "按触发类型筛选：schedule、event 或 any",
                        "enum": ["schedule", "event", "any"],
                        "default": "any",
                    },
                    "from_date": {
                        "type": "string",
                        "description": "可选起始日期或时间，格式 YYYY-MM-DD 或 ISO 时间",
                    },
                    "to_date": {
                        "type": "string",
                        "description": "可选结束日期或时间，格式 YYYY-MM-DD 或 ISO 时间",
                    },
                    "include_failed": {
                        "type": "boolean",
                        "description": "是否包含失败/超时案例；复盘工具错误时建议保留 true",
                        "default": True,
                    },
                },
                "required": ["query"],
            },
        }
        super().__init__(
            name="search_scheduled_task_history",
            description="检索当前定时任务专属历史案例库",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(
        self,
        context=None,
        query: str | None = None,
        limit: int = 5,
        status: str = "any",
        trigger_type: str = "any",
        from_date: str | None = None,
        to_date: str | None = None,
        include_failed: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        if not query or not str(query).strip():
            return {
                "status": "failed",
                "success": False,
                "data": {"matches": [], "count": 0},
                "summary": "缺少历史案例检索词",
            }

        scheduled_context = getattr(context, "scheduled_task_context", None)
        if not isinstance(scheduled_context, dict) or not scheduled_context.get("task_id"):
            return {
                "status": "failed",
                "success": False,
                "data": {"matches": [], "count": 0},
                "metadata": {"tool_name": self.name},
                "summary": "当前不是定时任务执行上下文，不能检索任务历史案例",
            }

        history_config = scheduled_context.get("history_learning")
        limit = _coerce_limit(limit)
        if isinstance(history_config, dict):
            if history_config.get("enabled") is False:
                return self._disabled_result(scheduled_context, "任务历史执行记忆未启用")
            if history_config.get("active_retrieval_enabled") is False:
                return self._disabled_result(scheduled_context, "任务历史主动检索未启用")
            configured_limit = _coerce_limit(history_config.get("active_retrieval_max_results") or 5)
            limit = min(limit, configured_limit)

        task_id = str(scheduled_context["task_id"])
        try:
            storage = TaskCaseStorage(task_id)
            result = search_history_cases(
                storage,
                query=str(query),
                limit=limit,
                status=status,
                trigger_type=trigger_type,
                from_date=from_date,
                to_date=to_date,
                include_failed=include_failed,
            )
            matches = result["matches"]
            logger.info(
                "scheduled_task_history_searched",
                task_id=task_id,
                execution_id=scheduled_context.get("execution_id"),
                query=str(query)[:120],
                count=len(matches),
                total_cases=result["total_cases"],
            )
            return {
                "status": "success",
                "success": True,
                "data": {
                    "task_id": task_id,
                    "task_name": scheduled_context.get("task_name"),
                    "matches": matches,
                    "count": len(matches),
                    "total_cases": result["total_cases"],
                    "query_terms": result["query_terms"],
                },
                "metadata": {
                    "schema_version": "v1.0",
                    "tool_name": self.name,
                    "task_id": task_id,
                    "execution_id": scheduled_context.get("execution_id"),
                },
                "summary": f"找到 {len(matches)} 条相关任务历史案例（案例库共 {result['total_cases']} 条）",
            }
        except Exception as exc:  # noqa: BLE001 - 工具错误要以结构化结果返回
            logger.error(
                "scheduled_task_history_search_failed",
                task_id=task_id,
                error=str(exc),
                exc_info=True,
            )
            return {
                "status": "failed",
                "success": False,
                "data": {"matches": [], "count": 0},
                "metadata": {"tool_name": self.name, "task_id": task_id},
                "summary": f"任务历史案例检索失败：{str(exc)[:120]}",
            }

    def _disabled_result(self, scheduled_context: dict[str, Any], summary: str) -> Dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "data": {"matches": [], "count": 0},
            "metadata": {
                "tool_name": self.name,
                "task_id": scheduled_context.get("task_id"),
                "execution_id": scheduled_context.get("execution_id"),
            },
            "summary": summary,
        }


search_scheduled_task_history_tool = SearchScheduledTaskHistoryTool()


def _coerce_limit(value: Any) -> int:
    try:
        return min(max(int(value or 5), 1), 20)
    except (TypeError, ValueError):
        return 5
