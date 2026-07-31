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
                        "query": {"type": "string", "description": "按名称、摘要或逻辑键搜索"},
                        "cursor": {"type": "string"},
                        "include_locator": {"type": "boolean", "default": False},
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
        query: str | None = None,
        cursor: str | None = None,
        include_locator: bool = False,
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
        bounded_limit = min(max(int(limit), 1), 100)
        try:
            match_offset = max(int(cursor or 0), 0)
        except ValueError:
            return {"success": False, "error": "invalid_cursor", "data": []}
        try:
            # Filtering belongs in the catalog query path. Until every filter
            # is represented by a DB column, scan bounded pages rather than
            # filtering only the first page and silently losing matches.
            scanned = []
            store_cursor = None
            while len(scanned) < 1000:
                page = await self.service.list_resources(
                    session_id,
                    kind=kind_filter.value if kind_filter else None,
                    status=status_filter.value if status_filter else None,
                    limit=100,
                    cursor=store_cursor,
                )
                scanned.extend(page.resources)
                store_cursor = page.next_cursor
                if not store_cursor:
                    break
            version = await self.service.catalog_version(session_id)
        except Exception:
            return {"success": False, "error": "resource_store_unavailable", "data": []}
        query_text = (query or "").casefold()
        matches = [
            r for r in scanned
            if (not label or label.casefold() in r.label.casefold())
            and (not tool_name or r.tool_name == tool_name)
            and (not run_id or r.run_id == run_id)
            and (not logical_key or r.resource_key == logical_key)
            and (
                not query_text
                or query_text in r.label.casefold()
                or query_text in r.resource_key.casefold()
                or query_text in str((r.metadata or {}).get("summary") or "").casefold()
            )
        ]

        def compact(resource):
            item = {
                "resource_id": resource.resource_id,
                "kind": resource.kind,
                "role": resource.role,
                "label": resource.label,
                "logical_key": resource.resource_key,
                "summary": (resource.metadata or {}).get("summary"),
                "mime_type": (resource.metadata or {}).get("mime_type"),
                "tool_name": resource.tool_name,
                "turn_sequence": resource.turn_sequence,
                "updated_at": resource.updated_at,
            }
            if include_locator:
                item["locator"] = resource.locator
            return item

        selected = matches[match_offset:match_offset + bounded_limit]
        next_match_cursor = (
            str(match_offset + bounded_limit)
            if match_offset + bounded_limit < len(matches)
            else None
        )
        return {
            "success": True,
            "data": [compact(r) for r in selected],
            "total_matches": len(matches),
            "truncated": next_match_cursor is not None or bool(store_cursor),
            "next_cursor": next_match_cursor,
            "resource_version": version,
        }
