"""Structured scheduled task result query tool for agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from app.scheduled_tasks.service import get_scheduled_task_service
from app.tools.base import LLMTool, ToolCategory

logger = structlog.get_logger()


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None


class QueryScheduledTaskResultsTool(LLMTool):
    """Query structured execution results (conclusions) of scheduled tasks."""

    def __init__(self):
        function_schema = {
            "name": "query_scheduled_task_results",
            "description": (
                "查询定时任务的结构化执行结论（存储于数据库）。每次执行一条记录，"
                "包含：结论时间、城市、站点、污染物、LLM 最终结论、关键事实发现、"
                "图片路径、报告文档路径、证据包路径和报告引用。用于跨任务检索历史执行结论，"
                "例如：某站点某污染物最近的分析结论、某城市某天的日报结论、"
                "历史告警分析产出等。支持按任务、城市、站点、污染物、状态与时间范围过滤。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "可选：限定单个任务ID",
                    },
                    "city": {
                        "type": "string",
                        "description": "可选：按城市名称筛选",
                    },
                    "station_id": {
                        "type": "string",
                        "description": "可选：按站点ID筛选",
                    },
                    "pollutant": {
                        "type": "string",
                        "description": "可选：按污染物名称筛选（如 PM2.5、O3）",
                    },
                    "status": {
                        "type": "string",
                        "description": "可选：按执行状态筛选（success/failed/timeout）",
                    },
                    "start": {
                        "type": "string",
                        "description": "可选：结论时间起始，格式 YYYY-MM-DD 或 ISO 时间（含）",
                    },
                    "end": {
                        "type": "string",
                        "description": "可选：结论时间截止，格式 YYYY-MM-DD 或 ISO 时间（含）",
                    },
                    "page": {
                        "type": "integer",
                        "description": "页码，默认 1",
                        "default": 1,
                        "minimum": 1,
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "每页数量，默认 20，最大 100",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": [],
            },
        }
        super().__init__(
            name="query_scheduled_task_results",
            description="查询定时任务的结构化执行结论（结论时间/城市/站点/污染物/结论/图片/文档）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(
        self,
        context=None,
        task_id: Optional[str] = None,
        city: Optional[str] = None,
        station_id: Optional[str] = None,
        pollutant: Optional[str] = None,
        status: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            service = get_scheduled_task_service()
        except RuntimeError:
            return {
                "status": "failed",
                "success": False,
                "data": {"results": [], "count": 0},
                "summary": "定时任务服务未初始化",
            }

        page = max(int(page or 1), 1)
        try:
            page_size = min(max(int(page_size or 20), 1), 100)
        except (TypeError, ValueError):
            page_size = 20

        try:
            records, total = service.list_task_results(
                task_id=(task_id or None),
                city=(city or None),
                station_id=(station_id or None),
                pollutant=(pollutant or None),
                status=(status or None),
                started_after=_parse_date(start),
                started_before=_parse_date(end),
                page=page,
                page_size=page_size,
            )
        except Exception as exc:  # noqa: BLE001 - 工具错误要以结构化结果返回
            logger.error(
                "scheduled_task_results_query_failed",
                error=str(exc),
                exc_info=True,
            )
            return {
                "status": "failed",
                "success": False,
                "data": {"results": [], "count": 0},
                "summary": f"执行结论查询失败：{str(exc)[:120]}",
            }

        results = []
        for record in records:
            item = record.model_dump(mode="json")
            item.pop("extra", None)
            results.append(item)

        return {
            "status": "success",
            "success": True,
            "data": {
                "results": results,
                "count": len(results),
                "total": total,
                "page": page,
                "page_size": page_size,
            },
            "metadata": {
                "schema_version": "v1.0",
                "tool_name": self.name,
            },
            "summary": (
                f"查询到 {len(results)} 条执行结论（共 {total} 条，第 {page} 页）。"
                "字段包含结论时间、城市、站点、污染物、结论文本、图片、文档与证据包路径。"
            ),
        }


query_scheduled_task_results_tool = QueryScheduledTaskResultsTool()
