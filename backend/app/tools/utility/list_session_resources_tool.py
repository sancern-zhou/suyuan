"""Discover durable resource refs from the current authorized session."""
from __future__ import annotations

from typing import Any

from app.agent.resources.manifest import filter_session_resources
from app.agent.resources.models import ResourceKind, ResourceStatus
from app.agent.resources.service import (
    ManifestPersistenceError,
    get_session_resource_manifest_service,
)
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
        self.service = service or get_session_resource_manifest_service()

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
            manifest = await self.service.load(session_id)
        except ManifestPersistenceError:
            return {"success": False, "error": "manifest_persistence_unavailable", "data": []}
        matches = filter_session_resources(
            manifest.refs,
            kind=kind_filter,
            status=status_filter,
            label=label,
            tool_name=tool_name,
            run_id=run_id,
            logical_key=logical_key,
        )
        bounded_limit = min(max(int(limit), 1), 100)
        return {
            "success": True,
            "data": [ref.model_dump(mode="json", exclude_none=True) for ref in matches[:bounded_limit]],
            "total_matches": len(matches),
            "truncated": len(matches) > bounded_limit,
            "resource_refs_version": manifest.version,
        }
