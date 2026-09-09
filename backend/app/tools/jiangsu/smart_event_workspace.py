"""Agent command tool for the Jiangsu smart-event workspace.

The tool only emits a structured UI command.  It never changes event data;
the browser resolves the command into the fixed event list/detail workspace.
"""

from __future__ import annotations

from typing import Any

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


class JiangsuSmartEventWorkspaceTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_smart_event_workspace",
            description="在江苏智能事件中心打开事件列表、固定详情、证据焦点或关联任务。仅调度右侧展示，不修改业务数据。",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "jiangsu_smart_event_workspace",
                "description": (
                    "调度江苏智能事件右侧工作区。需要展示事件列表时使用 show_event_list；"
                    "需要展示固定详情时使用 open_event_detail；不要用该工具修改事件或确认处置。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "enum": sorted(COMMANDS),
                            "description": "要执行的展示命令",
                        },
                        "event_id": {"type": "string", "description": "事件 ID"},
                        "event_ids": {"type": "array", "items": {"type": "string"}, "description": "对比事件 ID 列表"},
                        "task_id": {"type": "string", "description": "任务卡片 ID 或调度任务 ID"},
                        "focus": {"type": "string", "description": "证据焦点，例如 alarm、timeline、impact"},
                        "filters": {"type": "object", "description": "事件列表筛选条件"},
                    },
                    "required": ["command"],
                },
            },
        )

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
        if command == "open_task" and not str(task_id or "").strip():
            return {"status": "failed", "success": False, "summary": "打开任务工作区需要 task_id。"}

        payload = {
            "type": command,
            "event_id": str(event_id).strip() if event_id else None,
            "event_ids": [str(item).strip() for item in (event_ids or []) if str(item).strip()],
            "task_id": str(task_id).strip() if task_id else None,
            "focus": str(focus).strip() if focus else None,
            "filters": filters or {},
        }
        return {
            "status": "success",
            "success": True,
            "data": {"ui_command": {key: value for key, value in payload.items() if value not in (None, [], {})}},
            "summary": "已调度江苏智能事件工作区展示。",
        }
