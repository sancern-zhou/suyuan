from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.models import Document, KnowledgeBase
from app.knowledge_base.retrieval_service import KnowledgeRetrievalService


def test_rrf_promotes_chunk_supported_by_both_retrievers():
    chunk_results = [
        {"chunk_id": "plain", "content": "普通命中"},
        {"chunk_id": "supported", "content": "图支持命中"},
    ]
    graph_results = [
        {
            "chunk_id": "supported",
            "matched_entity_ids": ["e1"],
            "graph_paths": [{"kb_id": "kb1"}],
        }
    ]

    fused = KnowledgeRetrievalService.reciprocal_rank_fusion(
        chunk_results,
        graph_results,
        graph_weight=1.0,
    )

    assert fused[0]["chunk_id"] == "supported"
    assert fused[0]["fusion_sources"] == ["chunk", "graph"]
    assert fused[0]["matched_entity_ids"] == ["e1"]


class _CrossKbService(KnowledgeRetrievalService):
    async def _search_one_kb(self, *, kb_id, **kwargs):
        return [
            {
                "chunk_id": f"{kb_id}-chunk",
                "knowledge_base_id": kb_id,
                "content": kb_id,
                "fusion_sources": ["graph"],
                "graph_paths": [{"kb_id": kb_id}],
                "rrf_score": 1.0,
            }
        ]


@pytest.mark.asyncio
async def test_cross_kb_search_never_mixes_graph_paths():
    service = _CrossKbService(session_factory=None, vector_store=SimpleNamespace())

    results = await service.search(query="臭氧", kb_ids=["kb1", "kb2"], top_k=10)

    assert {item["knowledge_base_id"] for item in results} == {"kb1", "kb2"}
    assert all(
        path["kb_id"] == item["knowledge_base_id"]
        for item in results
        for path in item["graph_paths"]
    )


@pytest.mark.asyncio
async def test_search_filters_deleted_and_unacknowledged_qdrant_points(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retrieval.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session, session.begin():
        session.add(
            KnowledgeBase(
                id="kb1",
                name="KB1",
                qdrant_collection="kb1",
                graph_enabled=False,
            )
        )
        session.add(Document(id="doc1", knowledge_base_id="kb1", filename="a.md"))
        session.add_all(
            [
                KnowledgeChunk(
                    id="indexed",
                    kb_id="kb1",
                    document_id="doc1",
                    content_generation=1,
                    chunk_key="i",
                    content_hash="i",
                    chunk_index=0,
                    content="current",
                    embedding_text="current",
                    vector_status="indexed",
                ),
                KnowledgeChunk(
                    id="pending",
                    kb_id="kb1",
                    document_id="doc1",
                    content_generation=1,
                    chunk_key="p",
                    content_hash="p",
                    chunk_index=1,
                    content="pending",
                    embedding_text="pending",
                    vector_status="pending",
                ),
            ]
        )

    class _VectorStore:
        async def hybrid_search(self, **_kwargs):
            return [
                {"chunk_id": "deleted", "content": "stale"},
                {"chunk_id": "pending", "content": "not acknowledged"},
                {"chunk_id": "indexed", "content": "current"},
            ]

    service = KnowledgeRetrievalService(session_factory=factory, vector_store=_VectorStore())
    results = await service.search(query="current", kb_ids=["kb1"], top_k=10)

    assert [item["chunk_id"] for item in results] == ["indexed"]
    await engine.dispose()
