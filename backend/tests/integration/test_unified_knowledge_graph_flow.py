from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.cognition.models import CognitiveSchema
from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeGraphRelation
from app.knowledge_base.graph_schemas import (
    ChunkGraphExtraction,
    ExtractedEntity,
    ExtractedRelation,
)
from app.knowledge_base.index_outbox import (
    KnowledgeIndexOutboxRepository,
    KnowledgeIndexOutboxWorker,
)
from app.knowledge_base.ingestion_service import KnowledgeIngestionService
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase


class _Processor:
    async def parse(self, file_path):
        return Path(file_path).stem

    async def chunk(self, content, **kwargs):
        return [{"content": f"{content}：前体物影响臭氧"}]


class _Extractor:
    async def extract_chunk(self, *, kb_id, chunk, schema: CognitiveSchema):
        return ChunkGraphExtraction(
            chunk_id=chunk.id,
            extractor_name="integration",
            entities=[
                ExtractedEntity(
                    local_id="precursor",
                    entity_type="Pollutant",
                    name="前体物",
                    evidence_text=chunk.content,
                ),
                ExtractedEntity(
                    local_id="o3", entity_type="Pollutant", name="臭氧", evidence_text=chunk.content
                ),
            ],
            relations=[
                ExtractedRelation(
                    source_local_id="precursor",
                    target_local_id="o3",
                    relation_type="affects",
                    evidence_text=chunk.content,
                )
            ],
        )


class _VectorStore:
    def __init__(self):
        self.upserts = []
        self.deletes = []

    async def upsert_records(self, collection_name, records):
        self.upserts.extend(records)
        return len(records)

    async def delete_records(self, collection_name, record_type, record_ids):
        self.deletes.extend((record_type, record_id) for record_id in record_ids)


@pytest.mark.asyncio
async def test_document_lifecycle_keeps_shared_graph_and_rebuilds_index(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'flow.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add(KnowledgeBase(id="kb1", name="KB", qdrant_collection="kb_kb1"))
        session.add_all(
            [
                Document(
                    id="docA",
                    knowledge_base_id="kb1",
                    filename="A.md",
                    file_path="A.md",
                    status=DocumentStatus.PROCESSING,
                ),
                Document(
                    id="docB",
                    knowledge_base_id="kb1",
                    filename="B.md",
                    file_path="B.md",
                    status=DocumentStatus.PROCESSING,
                ),
            ]
        )
        await session.commit()
    service = KnowledgeIngestionService(
        session_factory=factory,
        processor=_Processor(),
        extractor=_Extractor(),
        file_storage=None,
    )

    await service.ingest_document("docA")
    await service.ingest_document("docB")
    async with factory() as session:
        relation = await session.scalar(select(KnowledgeGraphRelation))
        assert relation.mention_count == 2

    await service.replace_document(
        "docA",
        "A-replacement.md",
        {"filename": "A-replacement.md", "file_type": "md", "file_size": 1},
    )
    await service.delete_document("kb1", "docB")
    async with factory() as session:
        relation = await session.scalar(select(KnowledgeGraphRelation))
        assert relation is not None
        assert relation.mention_count == 1
        assert await session.get(Document, "docB") is None

    vector_store = _VectorStore()
    worker = KnowledgeIndexOutboxWorker(
        repository=KnowledgeIndexOutboxRepository(factory),
        vector_store=vector_store,
        collection_resolver=lambda _kb_id: "kb_kb1",
        batch_size=100,
    )
    while await worker.run_once():
        pass
    assert {item["record_type"] for item in vector_store.upserts} >= {"chunk", "entity", "relation"}
    assert ("chunk",) == tuple({kind for kind, _record_id in vector_store.deletes})
    await engine.dispose()
