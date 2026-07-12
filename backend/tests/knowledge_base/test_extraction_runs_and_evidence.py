import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.extraction_run_repository import (
    ExtractionRunContext,
    ExtractionRunRepository,
)
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.graph_schemas import EvidenceMismatch, ExtractedEvidence
from app.knowledge_base.models import Document, KnowledgeBase


def test_exact_evidence_must_match_chunk_text():
    evidence = ExtractedEvidence(quote="采样管路泄漏", start_char=0, end_char=6)
    evidence.validate_against("采样管路泄漏导致流量不足")
    with pytest.raises(EvidenceMismatch):
        evidence.validate_against("文本中没有该证据")


@pytest.mark.asyncio
async def test_failed_validation_still_persists_raw_extraction_run():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(KnowledgeBase(id="kb1", name="KB", qdrant_collection="kb1"))
        session.add(Document(id="doc1", knowledge_base_id="kb1", filename="a.md"))
        await session.flush()
        session.add(
            KnowledgeChunk(
                id="chunk1",
                kb_id="kb1",
                document_id="doc1",
                content_generation=1,
                chunk_key="c1",
                content_hash="h1",
                chunk_index=0,
                content="正文",
                embedding_text="正文",
            )
        )
        await session.commit()
        repo = ExtractionRunRepository(session)
        run_id = await repo.start(
            ExtractionRunContext(
                kb_id="kb1",
                document_id="doc1",
                chunk_id="chunk1",
                content_generation=1,
                scene_profile_version=1,
                schema_version=1,
                prompt_version="scene-kg-v1",
                model_name="fake",
                model_params={},
            )
        )
        await repo.fail(
            run_id,
            raw_response={"triplets": [{"bad": "payload"}]},
            validation_errors=["triplets.0.subject is required"],
            latency_ms=12,
        )
        run = await repo.get(run_id)
        assert run.raw_response["triplets"]
        assert run.status == "failed"
        assert run.prompt_version == "scene-kg-v1"
    await engine.dispose()
