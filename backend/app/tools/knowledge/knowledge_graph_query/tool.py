"""Agent tool for trusted graph-augmented knowledge-base retrieval."""

from __future__ import annotations

from typing import Any

from app.tools.base.tool_interface import LLMTool, ToolCategory


class KnowledgeGraphQueryTool(LLMTool):
    def __init__(self, service=None) -> None:
        self.service = service
        super().__init__(
            name="knowledge_graph_query",
            description=(
                "在已选择知识库内做可信实体关系检索，返回可追溯原文分块、业务规则和图路径。"
                "适用场景：设备原理与操作规程等背景知识、故障症状—部件—原因等候选关系、"
                "文档中抽取的人员/组织/业务关系。图路径与规则只是候选线索，"
                "必须用实测数据或接口事实核验后才能作为结论。"
            ),
            category=ToolCategory.QUERY,
            function_schema={
                "name": "knowledge_graph_query",
                "description": (
                    "在已选择知识库内进行可信实体关系检索，返回可追溯原文分块、业务规则和图路径。"
                    "适用于检索设备原理、故障处置经验、运维业务关系等背景知识，"
                    "以及症状—部件—原因等候选关系。图路径不能直接当成事实结论，"
                    "须再用监测数据、告警、工单等接口事实核验；未选择知识库时先请用户选择。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "自然语言实体或关系问题，如“CO仪器供电异常的常见原因”“某站点责任运维单位”。",
                        },
                        "knowledge_base_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "目标知识库 ID 列表；通常由会话已选知识库自动注入。",
                        },
                        "depth": {"type": "integer", "minimum": 1, "maximum": 2, "description": "图关系展开深度。"},
                        "top_k": {"type": "integer", "minimum": 1, "maximum": 50, "description": "召回分块数量。"},
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
        business_rules = self._unique_nested(chunks, "business_rules", "summary")
        graph_paths = self._unique_nested(chunks, "graph_paths", "relation_id")
        return {
            "status": "success" if chunks else "failed",
            "success": bool(chunks),
            "summary": f"从 {len(kb_ids)} 个知识库召回 {len(chunks)} 个可追溯分块。",
            "data": {
                "chunks": chunks,
                "evidence_chunks": chunks,
                "business_rules": business_rules,
                "graph_paths": graph_paths,
                "knowledge_base_ids": kb_ids,
            },
            "metadata": {"tool_name": self.name},
        }

    @staticmethod
    def _unique_nested(
        chunks: list[dict[str, Any]], field: str, identity: str
    ) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for chunk in chunks:
            for item in chunk.get(field) or []:
                key = str(item.get(identity) or item)
                unique.setdefault(key, item)
        return list(unique.values())

    @staticmethod
    def _default_service():
        from app.db.database import async_session
        from app.knowledge_base import get_vector_store
        from app.knowledge_base.retrieval_service import KnowledgeRetrievalService

        return KnowledgeRetrievalService(
            session_factory=async_session,
            vector_store=get_vector_store(),
        )
