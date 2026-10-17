from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase
from app.knowledge_base.retrieval_service import KnowledgeRetrievalService
from app.knowledge_base.service import KnowledgeBaseService


class VectorStore:
    def __init__(self):
        self.calls = []

    async def hybrid_search(self, **kwargs):
        self.calls.append(("hybrid", kwargs))
        return self.hits(kwargs.get("filters"))

    async def search(self, **kwargs):
        self.calls.append(("dense", kwargs))
        return self.hits(kwargs.get("filters"))

    async def search_records(self, *args, **kwargs):
        return []

    def hits(self, filters=None):
        hits = [
            {"chunk_id": chunk, "content": chunk, "score": score,
             "document_id": doc, "metadata": metadata}
            for chunk, doc, score, metadata in [
                ("deleted", "doc", 0.99, {"record_type": "chunk"}),
                ("pending", "doc", 0.98, {"record_type": "chunk"}),
                ("good", "doc", 0.9, {"record_type": "chunk"}),
                ("old-untyped", "doc", 0.8, {}),
                ("legacy", "legacy-doc", 0.7, {}),
                ("orphan", "deleted-doc", 0.6, {}),
            ]]
        return [hit for hit in hits if all(hit.get(k) == v for k, v in (filters or {}).items())]


@pytest.fixture
async def retrieval_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retrieve.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db, db.begin():
        db.add(KnowledgeBase(id="kb", name="KB", qdrant_collection="kb", graph_enabled=True))
        for doc_id in ["doc", "legacy-doc"]:
            db.add(Document(id=doc_id, knowledge_base_id="kb", filename=doc_id,
                            status=DocumentStatus.COMPLETED))
        for chunk_id, status in [("good", "indexed"), ("pending", "pending")]:
            db.add(KnowledgeChunk(id=chunk_id, kb_id="kb", document_id="doc",
                content_generation=1, chunk_key=chunk_id, content_hash=chunk_id,
                chunk_index=0, content=chunk_id, embedding_text=chunk_id,
                vector_status=status))
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("graph", [False, True])
@pytest.mark.parametrize("hybrid", [False, True])
async def test_shared_recall_validates_facts_and_preserves_search_options(retrieval_db, graph, hybrid):
    store = VectorStore()
    retrieval = KnowledgeRetrievalService(session_factory=retrieval_db, vector_store=store)
    results = await retrieval.search(query="test", kb_ids=["kb"], top_k=5,
        use_graph_retrieval=graph, use_hybrid=hybrid, alpha=0.45,
        score_threshold=0.35, filters={"document_id": "doc"})
    assert {item["chunk_id"] for item in results} == {"good"}
    kind, options = store.calls[0]
    assert kind == ("hybrid" if hybrid else "dense")
    assert options["score_threshold"] == 0.35
    assert options["filters"] == {"document_id": "doc"}
    assert options.get("alpha") == (0.45 if hybrid else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("graph", [False, True])
async def test_service_uses_same_auto_rerank_decision_and_enriches_sources(retrieval_db, graph, monkeypatch):
    store = VectorStore()
    async with retrieval_db() as db:
        service = KnowledgeBaseService(db=db, session_factory=retrieval_db, vector_store=store)
        decisions = []
        monkeypatch.setattr(service, "_should_rerank", lambda q, items, k, mode:
            decisions.append(mode) or False)
        async def forbidden(*args):
            pytest.fail("auto decision disabled reranking")
        monkeypatch.setattr(service, "_rerank", forbidden)
        result = await service.search("test", knowledge_base_ids=["kb"], top_k=1,
                                      use_graph_retrieval=graph, use_reranker="auto")
    assert decisions == ["auto"]
    assert result[0]["chunk_id"] == "good"
    assert result[0]["document"]["filename"] == "doc"


@pytest.mark.asyncio
async def test_ingestion_uses_injected_knowledge_database_factory(retrieval_db, monkeypatch):
    monkeypatch.setattr("app.knowledge_base.graph_extractor.KnowledgeGraphExtractor", lambda: object())
    service = KnowledgeBaseService(session_factory=retrieval_db, vector_store=SimpleNamespace())
    assert service._create_ingestion_service().session_factory is retrieval_db


@pytest.mark.asyncio
async def test_unmigrated_legacy_document_is_readable_but_stale_and_orphan_points_are_not(retrieval_db):
    service = KnowledgeRetrievalService(session_factory=retrieval_db, vector_store=VectorStore())
    result = await service.search(query="test", kb_ids=["kb"], top_k=10)
    assert {item["chunk_id"] for item in result} == {"good", "legacy"}


@pytest.mark.asyncio
async def test_graph_expansion_cannot_bypass_document_filter(retrieval_db, monkeypatch):
    async with retrieval_db() as db, db.begin():
        db.add(KnowledgeChunk(id="outside", kb_id="kb", document_id="legacy-doc",
            content_generation=1, chunk_key="outside", content_hash="outside",
            chunk_index=1, content="outside", embedding_text="outside", vector_status="indexed"))

    class GraphRepository:
        def __init__(self, session):
            pass
        async def entity_ids_for_chunk_ids(self, **kwargs):
            return ["e"]
        async def traverse(self, **kwargs):
            return [SimpleNamespace(id="e")], []
        async def chunk_ids_for_graph_records(self, **kwargs):
            return ["good", "outside"]

    monkeypatch.setattr("app.knowledge_base.retrieval_service.KnowledgeGraphRepository", GraphRepository)
    service = KnowledgeRetrievalService(session_factory=retrieval_db, vector_store=VectorStore())
    results = await service.search(query="test", kb_ids=["kb"], top_k=10,
        use_graph_retrieval=True, filters={"document_id": "doc"})
    assert [item["chunk_id"] for item in results] == ["good"]
    assert set(results[0]["fusion_sources"]) == {"chunk", "graph"}
