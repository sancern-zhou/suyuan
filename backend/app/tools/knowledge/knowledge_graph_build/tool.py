"""Agent-facing controls for the per-knowledge-base graph build queue."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = logging.getLogger(__name__)


class KnowledgeGraphBuildTool(LLMTool):
    """Create and inspect graph build tasks without crossing KB boundaries."""

    def __init__(self, service=None) -> None:
        self.service = service
        super().__init__(
            name="knowledge_graph_build",
            description="增量构建或管理指定知识库自己的知识图谱任务。",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema={
                "name": "knowledge_graph_build",
                "description": "为指定知识库创建、查询、取消、重试或恢复知识图谱构建任务。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["build", "status", "cancel", "retry", "recover"]},
                        "knowledge_base_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1},
                        "task_id": {"type": "string"},
                        "mode": {"type": "string", "enum": ["pending", "reset_and_build"]},
                    },
                    "required": ["action", "knowledge_base_ids"],
                },
            },
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        action: str,
        knowledge_base_ids: list[str],
        task_id: str | None = None,
        mode: str = "pending",
        **_: Any,
    ) -> dict[str, Any]:
        kb_ids = list(dict.fromkeys(str(v).strip() for v in (knowledge_base_ids or []) if str(v).strip()))
        if len(kb_ids) != 1:
            return self._error("请明确指定一个知识库。", "knowledge_base_ids_must_contain_one")
        if action in {"cancel", "retry", "status"} and not task_id and action != "status":
            return self._error("该操作需要 task_id。", "missing_task_id")
        service = self.service or self._default_service()
        try:
            if action in {"cancel", "retry"}:
                existing = await service.get_status(task_id=task_id)
                if existing is None:
                    return self._error("未找到图谱构建任务。", "task_not_found")
                if str(getattr(existing, "kb_id", "")) != kb_ids[0]:
                    return self._error("任务不属于指定知识库。", "task_knowledge_base_mismatch")
            if action == "build":
                task = await service.create_task(kb_ids[0], mode=mode)
                # The task is durable; execution is best-effort and can be recovered by the worker.
                async def _runner():
                    try:
                        await service.run(task.id)
                    except Exception as exc:  # pragma: no cover - exercised by runner test
                        logger.exception("knowledge_graph_build_failed", extra={"task_id": str(task.id)})
                        if hasattr(service, "_mark_task_failed"):
                            await service._mark_task_failed(task.id, str(exc))
                asyncio.create_task(_runner())
            elif action == "status":
                task = await service.get_status(kb_id=kb_ids[0], task_id=task_id)
            elif action == "cancel":
                await service.cancel(task_id)
                task = await service.get_status(task_id=task_id)
            elif action == "retry":
                task = await service.retry(task_id=task_id, kb_id=kb_ids[0])
            elif action == "recover":
                recovered = await service.recover_expired_tasks(kb_id=kb_ids[0])
                return self._ok("已恢复过期图谱任务。", {"knowledge_base_id": kb_ids[0], "task_ids": recovered})
            else:
                return self._error("不支持的操作。", "invalid_action")
            if task is None:
                return self._error("未找到图谱构建任务。", "task_not_found")
            if str(getattr(task, "kb_id", kb_ids[0])) != kb_ids[0]:
                return self._error("任务不属于指定知识库。", "task_knowledge_base_mismatch")
            data = {"task_id": str(task.id), "knowledge_base_id": kb_ids[0], "status": task.status}
            return self._ok(f"图谱任务已{('创建' if action == 'build' else '更新')}。", data)
        except Exception as exc:
            return self._error(str(exc), "graph_build_operation_failed")

    @staticmethod
    def _ok(summary: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"status": "success", "success": True, "summary": summary, "data": data}

    @staticmethod
    def _error(summary: str, code: str) -> dict[str, Any]:
        return {"status": "failed", "success": False, "summary": summary, "data": {"error": code}}

    @staticmethod
    def _default_service():
        from app.db.database import async_session
        from app.knowledge_base.graph_build_service import GraphBuildService

        return GraphBuildService(session_factory=async_session)
