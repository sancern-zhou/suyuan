"""Agent-managed case library tool."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agent.memory.agent_case_library import AgentCaseLibrary
from app.tools.base.tool_interface import LLMTool, ToolCategory


class AgentCaseLibraryTool(LLMTool):
    """Let an Agent decide which feedback-derived cases to record and reuse."""

    _current_mode: str | None = None

    def __init__(self) -> None:
        super().__init__(
            name="agent_case_library",
            description="Search or record reusable cases for the current Agent mode.",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema={
                "name": "agent_case_library",
                "description": (
                    "由 Agent 主动检索或记录当前模式的案例库；"
                    "仅沉淀经反馈确认且未来可复用的案例。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["search", "record"]},
                        "scenario": {"type": "string", "description": "案例所属场景。"},
                        "query": {"type": "string", "description": "检索关键词。"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                        "title": {"type": "string", "description": "案例标题。"},
                        "user_feedback": {
                            "type": "string",
                            "description": "用户判定和审核意见摘要。",
                        },
                        "lesson": {"type": "string", "description": "下次可直接复用的判断经验。"},
                        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                        "source_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 20,
                        },
                    },
                    "required": ["action"],
                },
            },
            version="1.0.0",
            requires_context=False,
        )

    @classmethod
    def set_case_context(cls, mode: str) -> None:
        cls._current_mode = mode

    @classmethod
    def clear_case_context(cls) -> None:
        cls._current_mode = None

    async def execute(
        self,
        action: str,
        scenario: str = "",
        query: str = "",
        limit: int = 10,
        title: str = "",
        user_feedback: str = "",
        lesson: str = "",
        tags: list[str] | None = None,
        source_refs: list[str] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        mode = self._current_mode
        if not mode:
            return {"success": False, "error": "case_library_context_missing"}
        library = AgentCaseLibrary(mode)
        if action == "search":
            cases = library.search(query=query, scenario=scenario, limit=limit)
            return {
                "success": True,
                "mode": mode,
                "cases": cases,
                "match_count": len(cases),
                "total_cases": library.count(),
            }
        if action != "record":
            return {"success": False, "error": "invalid_case_library_action"}
        if not title.strip() or not lesson.strip():
            return {"success": False, "error": "case_title_and_lesson_required"}
        record = {
            "case_id": f"case_{uuid4().hex}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "scenario": scenario.strip() or "generic",
            "title": title.strip()[:500],
            "user_feedback": user_feedback.strip()[:4000],
            "lesson": lesson.strip()[:4000],
            "tags": [
                str(tag).strip()[:120]
                for tag in (tags or [])
                if str(tag).strip()
            ][:20],
            "source_refs": [
                str(ref).strip()[:1000]
                for ref in (source_refs or [])
                if str(ref).strip()
            ][:20],
        }
        library.append(record)
        return {
            "success": True,
            "case_id": record["case_id"],
            "mode": mode,
            "total_cases": library.count(),
            "summary": f"案例已记录：{record['title']}",
        }
