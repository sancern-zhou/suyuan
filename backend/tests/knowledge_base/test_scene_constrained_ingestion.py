import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeGraphEntity, KnowledgeGraphRelation
from app.knowledge_base.graph_schemas import (
    ChunkGraphExtraction,
    ExtractedEntity,
    ExtractedEvidence,
    ExtractedRelation,
)
from app.knowledge_base.ingestion_service import KnowledgeIngestionService
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase
from app.knowledge_base.scene_models import KnowledgeGraphExtractionRun


class Processor:
    async def parse(self, file_path):
        return "企业A拥有1号空压机"

    async def chunk(self, **kwargs):
        return [{"content": "企业A拥有1号空压机"}]


class Extractor:
    provider = None

    async def extract_chunk(self, *, kb_id, chunk, schema):
        return ChunkGraphExtraction(
            chunk_id=chunk.id,
            extractor_name="fake",
            entities=[
                ExtractedEntity(
                    local_id="e1",
                    entity_type="enterprise",
                    name="企业A",
                    evidence_text="企业A",
                    evidence=ExtractedEvidence(quote="企业A", start_char=0, end_char=3),
                ),
                ExtractedEntity(
                    local_id="e2",
                    entity_type="noise_source",
                    name="1号空压机",
                    evidence_text="1号空压机",
                    evidence=ExtractedEvidence(quote="1号空压机", start_char=5, end_char=10),
                ),
            ],
            relations=[
                ExtractedRelation(
                    source_local_id="e1",
                    target_local_id="e2",
                    relation_type="has_noise_source",
                    evidence_text="企业A拥有1号空压机",
                    evidence=ExtractedEvidence(
                        quote="企业A拥有1号空压机", start_char=0, end_char=10
                    ),
                )
            ],
        )


@pytest.mark.asyncio
async def test_scene_ingestion_records_versions_exact_evidence_and_run(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scene-ingest.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add(
            KnowledgeBase(
                id="kb1",
                name="KB",
                qdrant_collection="kb1",
                scene_status="ready",
                scene_profile_version=1,
                schema_version=1,
                graph_enabled=True,
                graph_schema={
                    "allowed_entity_types": ["enterprise", "noise_source"],
                    "allowed_relation_types": ["has_noise_source"],
                    "allowed_relation_triplets": [
                        ["enterprise", "has_noise_source", "noise_source"]
                    ],
                    "scene_profile_version": 1,
                    "schema_version": 1,
                },
            )
        )
        session.add(
            Document(
                id="doc1",
                knowledge_base_id="kb1",
                filename="a.md",
                file_path="/tmp/a.md",
                status=DocumentStatus.PROCESSING,
            )
        )
        await session.commit()
    result = await KnowledgeIngestionService(
        session_factory=factory, processor=Processor(), extractor=Extractor()
    ).ingest_document("doc1")
    assert result.status == "completed"
    async with factory() as session:
        relation = await session.scalar(select(KnowledgeGraphRelation))
        entity = await session.scalar(
            select(KnowledgeGraphEntity).where(KnowledgeGraphEntity.name == "企业A")
        )
        run = await session.scalar(select(KnowledgeGraphExtractionRun))
        assert relation.source_type == "document_fact"
        assert relation.schema_version == 1
        assert entity.schema_version == 1
        assert run.status == "completed"
    await engine.dispose()
