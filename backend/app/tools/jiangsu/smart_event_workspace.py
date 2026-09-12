"""Agent command tool for the Jiangsu smart-event workspace.

The tool emits a structured UI command for the browser and, for list commands,
also resolves the matching events so the Agent can quote real ``event_id`` /
``task_id`` values in follow-up commands.  Users describe natural conditions
(time, station, AI event type, level, status); the tool translates them into
concrete identifiers.  It never changes event data.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.services.jiangsu_smart_event import JiangsuSmartEventService
from app.tools.base import LLMTool, ToolCategory


COMMANDS = {
    "show_event_list",
    "filter_event_list",
    "open_event_detail",
    "focus_evidence",
    "compare_events",
    "open_task",
    "show_operation_history",
}

FILTER_FIELDS = ("start_time", "end_time", "station", "status", "event_type", "level", "keyword")

EVENT_SUMMARY_FIELDS = (
    "event_id",
    "event_name",
    "initial_event_name",
    "site_name",
    "site_id",
    "event_status",
    "ai_event_type",
    "ai_suggested_level",
    "latest_occurrence_time",
    "event_start_time",
)


def _first_value(filters: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = filters.get(key)
        text = str(value).strip() if value is not None else ""
        if text:
            return text
    return None


def _normalize_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Merge user-habit filter slots into the list query contract."""
    keyword_parts = [
        _first_value(filters, "keyword", "query"),
        _first_value(filters, "station", "station_name", "site_name", "station_code"),
    ]
    normalized = {
        "start_time": _first_value(filters, "start_time", "startTime", "from"),
        "end_time": _first_value(filters, "end_time", "endTime", "to"),
        "status": _first_value(filters, "status", "event_status"),
        "event_type": _first_value(filters, "event_type", "ai_event_type", "type"),
        "level": _first_value(filters, "level", "ai_suggested_level", "severity"),
        "keyword": " ".join(part for part in keyword_parts if part) or None,
    }
    return {key: value for key, value in normalized.items() if value}


class JiangsuSmartEventWorkspaceTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_smart_event_workspace",
            description="在江苏智能事件中心打开事件列表、固定详情、证据焦点或关联任务。仅调度右侧展示，不修改业务数据。",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "jiangsu_smart_event_workspace",
                "description": (
                    "调度江苏智能事件右侧工作区。用户用自然条件描述事件（时间范围、站点、AI事件类型、等级、状态、关键词），"
                    "请把这些条件提取到 filters，不要向用户索要 event_id/task_id。"
                    "需要定位单个事件或任务时，先用 show_event_list / filter_event_list 查询，"
                    "工具会在 events 中返回带 event_id 的事件摘要，再据此调用 open_event_detail / focus_evidence / "
                    "compare_events / show_operation_history；open_task 可传 event_id 自动定位其关联任务。"
                    "不要用该工具修改事件或确认处置。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "enum": sorted(COMMANDS),
                            "description": "要执行的展示命令",
                        },
                        "event_id": {"type": "string", "description": "事件 ID（来自本工具 events 返回，不让用户提供）"},
                        "event_ids": {"type": "array", "items": {"type": "string"}, "description": "对比事件 ID 列表（来自本工具 events 返回）"},
                        "task_id": {"type": "string", "description": "任务卡片 ID 或调度任务 ID（来自本工具返回，不让用户提供）"},
                        "focus": {"type": "string", "description": "证据焦点，例如 alarm、timeline、impact"},
                        "filters": {
                            "type": "object",
                            "description": "事件列表筛选条件，字段：start_time、end_time（ISO 时间）、"
                            "station（站点名称）、status（事件状态）、event_type（AI事件类型）、"
                            "level（等级）、keyword（关键词）",
                            "properties": {field: {"type": "string"} for field in FILTER_FIELDS},
                        },
                    },
                    "required": ["command"],
                },
            },
        )

    async def _query_events(self, normalized: dict[str, Any]) -> dict[str, Any]:
        end_at = datetime.now().astimezone()
        start_at = end_at - timedelta(days=7)
        service = JiangsuSmartEventService()
        payload = await service.list_events(
            start_time=normalized.get("start_time") or start_at.isoformat(),
            end_time=normalized.get("end_time") or end_at.isoformat(),
            status=normalized.get("status"),
            keyword=normalized.get("keyword"),
            event_type=normalized.get("event_type"),
            level=normalized.get("level"),
            limit=20,
            page=1,
            summary=True,
            refresh=False,
        )
        events = [
            {key: value for key, value in value_dict.items() if key in EVENT_SUMMARY_FIELDS}
            for value_dict in payload.get("events", [])
            if isinstance(value_dict, dict)
        ]
        return {
            "events": events,
            "total": payload.get("total", len(events)),
            "filters": normalized,
        }

    async def execute(
        self,
        command: str,
        event_id: str | None = None,
        event_ids: list[str] | None = None,
        task_id: str | None = None,
        focus: str | None = None,
        filters: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        command = str(command or "").strip()
        if command not in COMMANDS:
            return {"status": "failed", "success": False, "summary": f"不支持的事件工作区命令：{command}"}
        if command == "open_event_detail" and not str(event_id or "").strip():
            return {"status": "failed", "success": False, "summary": "打开事件详情需要 event_id。"}
        if command in {"focus_evidence", "show_operation_history"} and not str(event_id or "").strip():
            return {"status": "failed", "success": False, "summary": f"{command} 需要 event_id。"}
        if command == "compare_events" and len([item for item in (event_ids or []) if str(item).strip()]) < 2:
            return {"status": "failed", "success": False, "summary": "事件对比至少需要两个 event_ids。"}
        if command == "open_task" and not str(task_id or "").strip() and not str(event_id or "").strip():
            return {"status": "failed", "success": False, "summary": "打开任务工作区需要 task_id 或 event_id。"}

        normalized = _normalize_filters(filters or {})
        summary_text = "已调度江苏智能事件工作区展示。"
        data: dict[str, Any] = {}

        if command in {"show_event_list", "filter_event_list"}:
            query = await self._query_events(normalized)
            data["events"] = query["events"]
            data["total"] = query["total"]
            data["filters"] = query["filters"]
            summary_text = (
                f"已在智能事件中心打开事件列表（共 {query['total']} 条）。"
                "events 返回了事件摘要及 event_id，后续 open_event_detail / focus_evidence / "
                "compare_events / show_operation_history / open_task 请使用这些 event_id。"
            )
        elif command == "open_task" and not str(task_id or "").strip():
            tasks = JiangsuSmartEventService().list_tasks(event_id=str(event_id).strip(), limit=5)
            if not tasks:
                return {"status": "failed", "success": False, "summary": "该事件暂无关联任务卡片。"}
            task_id = str(tasks[0].get("task_id") or "").strip()
            data["tasks"] = [
                {key: task.get(key) for key in ("task_id", "scheduled_task_id", "title", "status", "event_id") if task.get(key) is not None}
                for task in tasks
            ]
            summary_text = "已打开事件关联的任务卡片，tasks 返回了 task_id。"

        payload = {
            "type": command,
            "event_id": str(event_id).strip() if event_id else None,
            "event_ids": [str(item).strip() for item in (event_ids or []) if str(item).strip()],
            "task_id": str(task_id).strip() if task_id else None,
            "focus": str(focus).strip() if focus else None,
            "filters": normalized,
        }
        data["ui_command"] = {key: value for key, value in payload.items() if value not in (None, [], {})}
        return {
            "status": "success",
            "success": True,
            "data": data,
            "summary": summary_text,
        }
