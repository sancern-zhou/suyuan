import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.entity_linker import EntityLinkDecision
from app.knowledge_base.graph_models import KnowledgeGraphRelation, KnowledgeIndexOutbox
from app.knowledge_base.models import KnowledgeBase
from app.knowledge_base.user_fact_service import FactResolutionRequired, UserFactService


class FakeFactParser:
    async def parse(self, raw_text, schema):
        return {
            "subject": {"local_id": "s1", "entity_type": "enterprise", "name": "企业A"},
            "relation_type": "has_noise_source",
            "object": {"local_id": "o1", "entity_type": "noise_source", "name": "1号空压机"},
            "statement": raw_text,
        }


class CreateLinker:
    async def link(self, *, kb_id, entity_type, name):
        return EntityLinkDecision(
            action="create",
            canonical_name=name,
            reason="no_matching_entity",
            confidence=1.0,
        )


class AmbiguousLinker:
    async def link(self, *, kb_id, entity_type, name):
        return EntityLinkDecision(
            action="ambiguous",
            canonical_name=name,
            reason="multiple",
            confidence=0.5,
            candidates=[],
        )


@pytest.fixture
async def fact_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            KnowledgeBase(
                id="kb1",
                name="事实知识库",
                qdrant_collection="kb1",
                scene_status="ready",
                scene_profile_version=1,
                schema_version=1,
                graph_schema={
                    "allowed_entity_types": ["enterprise", "noise_source"],
                    "allowed_relation_types": ["has_noise_source"],
                    "allowed_relation_triplets": [["enterprise", "has_noise_source", "noise_source"]],
                },
            )
        )
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_confirmed_user_fact_creates_confirmed_relation(fact_session):
    service = UserFactService(fact_session, parser=FakeFactParser(), linker=CreateLinker())
    preview = await service.parse_fact("kb1", "企业A的主要噪声源是1号空压机", created_by="u1")
    fact = await service.confirm_fact(preview.id, resolutions={})
    relation = await fact_session.get(KnowledgeGraphRelation, fact.structured_fact["relation_id"])
    assert relation.review_status == "confirmed"
    assert relation.source_type == "user_asserted"
    assert fact.review_status == "confirmed"
    assert len((await fact_session.scalars(KnowledgeIndexOutbox.__table__.select())).all()) >= 3


@pytest.mark.asyncio
async def test_ambiguous_fact_cannot_confirm_without_resolution(fact_session):
    service = UserFactService(fact_session, parser=FakeFactParser(), linker=AmbiguousLinker())
    preview = await service.parse_fact("kb1", "南站发生设备故障", created_by="u1")
    with pytest.raises(FactResolutionRequired):
        await service.confirm_fact(preview.id, resolutions={})
