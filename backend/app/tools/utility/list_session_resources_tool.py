"""Discover durable resource refs from the current authorized session."""
from __future__ import annotations

from typing import Any

from app.agent.resources.models import ResourceKind, ResourceStatus
from app.agent.resources.resource_service import SessionResourceService
from app.tools.base.tool_interface import LLMTool, ToolCategory


class ListSessionResourcesTool(LLMTool):
    def __init__(self, *, service=None) -> None:
        super().__init__(
            name="list_session_resources",
            description="列出当前已授权会话中跨请求保存的数据、文件、产物、URL和可视化引用",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "list_session_resources",
                "description": "列出当前会话保存的资源引用，不读取资源正文",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": [kind.value for kind in ResourceKind]},
                        "status": {"type": "string", "enum": [status.value for status in ResourceStatus]},
                        "label": {"type": "string"},
                        "tool_name": {"type": "string"},
                        "run_id": {"type": "string"},
                        "logical_key": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            version="1.0.0",
            requires_context=True,
        )
        self.service = service or SessionResourceService.database()

    async def execute(
        self,
        context=None,
        kind: str | None = None,
        status: str | None = None,
        label: str | None = None,
        tool_name: str | None = None,
        run_id: str | None = None,
        logical_key: str | None = None,
        limit: int = 50,
        **_: Any,
    ) -> dict[str, Any]:
        session_id = getattr(context, "session_id", None)
        if not session_id:
            return {"success": False, "error": "current_session_context_required", "data": []}
        try:
            kind_filter = ResourceKind(kind) if kind else None
            status_filter = ResourceStatus(status) if status else None
        except ValueError as exc:
            return {"success": False, "error": str(exc), "data": []}
        try:
            page = await self.service.list_resources(session_id, kind=kind_filter.value if kind_filter else None, status=status_filter.value if status_filter else None, limit=min(max(int(limit), 1), 100))
        except Exception:
            return {"success": False, "error": "resource_store_unavailable", "data": []}
        matches = [r for r in page.resources if (not label or label.lower() in r.label.lower()) and (not tool_name or r.tool_name == tool_name) and (not run_id or r.run_id == run_id) and (not logical_key or r.resource_key == logical_key)]
        bounded_limit = min(max(int(limit), 1), 100)
        return {
            "success": True,
            "data": [r.__dict__ for r in matches[:bounded_limit]],
            "total_matches": len(matches),
            "truncated": len(matches) > bounded_limit,
            "resource_version": 0,
        }
