import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase
from app.knowledge_base.scene_repository import RepresentativeDocumentRequired, SceneRepository
from app.knowledge_base.scene_schemas import SceneDraft
from app.knowledge_base.schema_compiler import SceneSchemaCompiler


def scene_draft_payload() -> SceneDraft:
    return SceneDraft.model_validate(
        {
            "scene_goal": "分析企业噪声投诉与整改闭环",
            "business_objects": [
                {"key": "enterprise", "name": "企业"},
                {"key": "noise_source", "name": "噪声源"},
            ],
            "business_logic": [
                {
                    "key": "enterprise_has_noise_source",
                    "statement": "企业拥有噪声源",
                    "source_key": "enterprise",
                    "relation_key": "has_noise_source",
                    "target_key": "noise_source",
                    "policy": "allowed",
                }
            ],
            "source_document_ids": ["doc1"],
        }
    )


@pytest.fixture
async def scene_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_begin_discovery_requires_completed_representative_document(scene_session):
    scene_session.add(
        KnowledgeBase(id="kb1", name="KB", qdrant_collection="kb1")
    )
    await scene_session.commit()
    repo = SceneRepository(scene_session)
    with pytest.raises(RepresentativeDocumentRequired):
        await repo.begin_discovery("kb1", created_by="u1")


@pytest.mark.asyncio
async def test_confirm_profile_atomically_updates_versions(scene_session):
    kb = KnowledgeBase(id="kb1", name="KB", qdrant_collection="kb1")
    document = Document(
        id="doc1",
        knowledge_base_id="kb1",
        filename="noise.md",
        status=DocumentStatus.COMPLETED,
        ingestion_status="completed",
        chunk_count=1,
    )
    scene_session.add_all([kb, document])
    await scene_session.flush()
    scene_session.add(
        KnowledgeChunk(
            id="chunk1",
            kb_id="kb1",
            document_id="doc1",
            content_generation=1,
            chunk_key="chunk1",
            content_hash="hash1",
            chunk_index=0,
            content="企业拥有空压机",
            embedding_text="企业拥有空压机",
        )
    )
    await scene_session.commit()

    repo = SceneRepository(scene_session)
    profile = await repo.create_draft(
        "kb1", scene_draft_payload(), created_by="u1"
    )
    confirmed = await repo.confirm_profile(
        profile.id, SceneSchemaCompiler().compile(scene_draft_payload())
    )
    await scene_session.refresh(kb)
    assert confirmed.status == "confirmed"
    assert kb.scene_status == "ready"
    assert kb.scene_profile_version == 1
    assert kb.schema_version == 1
    assert kb.graph_schema["scene_profile_version"] == 1
    assert kb.graph_schema["schema_version"] == 1
