"""Agent tool for trusted graph-augmented knowledge-base retrieval."""

from __future__ import annotations

from typing import Any

from app.tools.base.tool_interface import LLMTool, ToolCategory


class KnowledgeGraphQueryTool(LLMTool):
    def __init__(self, service=None) -> None:
        self.service = service
        super().__init__(
            name="knowledge_graph_query",
            description="在已选择知识库内进行可信实体关系检索，并返回可追溯原文分块。",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "knowledge_graph_query",
                "description": "在已选择知识库内进行可信实体关系检索，并返回可追溯原文分块。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "knowledge_base_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "depth": {"type": "integer", "minimum": 1, "maximum": 2},
                        "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "required": ["query", "knowledge_base_ids"],
                },
            },
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        query: str,
        knowledge_base_ids: list[str],
        depth: int = 2,
        top_k: int = 10,
        **_: Any,
    ) -> dict[str, Any]:
        kb_ids = list(dict.fromkeys(str(item).strip() for item in knowledge_base_ids if item))
        if not kb_ids:
            return {
                "status": "failed",
                "success": False,
                "summary": "请先选择至少一个知识库。",
                "data": {"error": "missing_knowledge_base_ids", "chunks": []},
            }
        service = self.service or self._default_service()
        chunks = await service.search(
            query=query,
            kb_ids=kb_ids,
            top_k=max(1, min(int(top_k), 50)),
            use_graph_retrieval=True,
            graph_depth=max(1, min(int(depth), 2)),
        )
        return {
            "status": "success" if chunks else "failed",
            "success": bool(chunks),
            "summary": f"从 {len(kb_ids)} 个知识库召回 {len(chunks)} 个可追溯分块。",
            "data": {
                "chunks": chunks,
                "knowledge_base_ids": kb_ids,
            },
            "metadata": {"tool_name": self.name},
        }

    @staticmethod
    def _default_service():
        from app.db.database import async_session
        from app.knowledge_base import get_vector_store
        from app.knowledge_base.retrieval_service import KnowledgeRetrievalService

        return KnowledgeRetrievalService(
            session_factory=async_session,
            vector_store=get_vector_store(),
        )
