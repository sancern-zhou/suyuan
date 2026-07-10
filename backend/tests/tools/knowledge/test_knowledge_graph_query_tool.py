import pytest

from app.tools.knowledge.knowledge_graph_query.tool import KnowledgeGraphQueryTool


class _FakeService:
    def __init__(self):
        self.kwargs = None

    async def search(self, **kwargs):
        self.kwargs = kwargs
        return [
            {
                "chunk_id": "chunk1",
                "knowledge_base_id": "kb1",
                "content": "臭氧零点漂移证据",
                "matched_entity_ids": ["e1"],
                "fusion_sources": ["chunk", "graph"],
            }
        ]


@pytest.mark.asyncio
async def test_tool_queries_selected_knowledge_bases_and_returns_chunks():
    service = _FakeService()
    tool = KnowledgeGraphQueryTool(service=service)

    result = await tool.execute(
        query="臭氧零漂",
        knowledge_base_ids=["kb1"],
        depth=2,
        top_k=5,
    )

    assert result["success"] is True
    assert result["data"]["chunks"][0]["knowledge_base_id"] == "kb1"
    assert service.kwargs["kb_ids"] == ["kb1"]
    assert service.kwargs["use_graph_retrieval"] is True


@pytest.mark.asyncio
async def test_tool_requires_explicit_knowledge_base_selection():
    result = await KnowledgeGraphQueryTool(service=_FakeService()).execute(
        query="臭氧",
        knowledge_base_ids=[],
    )

    assert result["success"] is False
    assert result["data"]["error"] == "missing_knowledge_base_ids"
