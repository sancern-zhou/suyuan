"""Read a durable session resource by opaque id without guessing a path."""
from __future__ import annotations

from typing import Any

from app.agent.resources.resource_service import SessionResourceService
from app.tools.base.tool_interface import LLMTool, ToolCategory


class ReadSessionResourceTool(LLMTool):
    def __init__(self, *, service=None) -> None:
        super().__init__(
            name="read_session_resource",
            description="按 resource_id 读取当前会话资源；无需猜测物理路径",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "read_session_resource",
                "description": "读取当前会话资源。大文件应使用 offset/limit 分段读取。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_id": {"type": "string"},
                        "offset": {"type": "integer", "minimum": 0, "default": 0},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "required": ["resource_id"],
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
        resource_id: str = "",
        offset: int = 0,
        limit: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        session_id = getattr(context, "session_id", None)
        if not session_id:
            return {"success": False, "error": "current_session_context_required"}
        resource = await self.service.get_resource(session_id, resource_id)
        if resource is None:
            return {"success": False, "error": "resource_not_found"}
        locator = resource.locator or {}
        path = locator.get("path")
        if path:
            from app.tools.utility.read_file_tool import ReadFileTool

            result = await ReadFileTool().execute(path=path, offset=offset, limit=limit)
            if isinstance(result, dict):
                result.setdefault("resource_id", resource.resource_id)
                result.setdefault("resource_label", resource.label)
            return result
        # Non-file resource types retain their native resolver. Returning the
        # bounded locator here is intentional: it is fetched only on demand,
        # never injected into the standing prompt.
        return {
            "success": True,
            "resource_id": resource.resource_id,
            "kind": resource.kind,
            "label": resource.label,
            "locator": locator,
            "summary": (resource.metadata or {}).get("summary") or f"已解析资源 {resource.label}",
        }
