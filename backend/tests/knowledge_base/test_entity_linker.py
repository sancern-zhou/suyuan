import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.entity_linker import EntityLinker
from app.knowledge_base.graph_models import KnowledgeGraphEntity
from app.knowledge_base.models import KnowledgeBase


@pytest.fixture
async def link_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(KnowledgeBase(id="kb1", name="KB", qdrant_collection="kb1"))
        session.add_all(
            [
                KnowledgeGraphEntity(
                    id="pm25",
                    kb_id="kb1",
                    entity_type="pollutant",
                    name="PM2.5",
                    normalized_name="pm2.5",
                    aliases=["PM25", "细颗粒物"],
                    review_status="confirmed",
                ),
                KnowledgeGraphEntity(
                    id="south-station",
                    kb_id="kb1",
                    entity_type="station",
                    name="南站",
                    normalized_name="南站",
                    aliases=[],
                ),
                KnowledgeGraphEntity(
                    id="south-company",
                    kb_id="kb1",
                    entity_type="enterprise",
                    name="南站",
                    normalized_name="南站",
                    aliases=[],
                ),
            ]
        )
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_alias_match_links_without_llm(link_session):
    decision = await EntityLinker(link_session).link(
        kb_id="kb1", entity_type="pollutant", name="PM25"
    )
    assert decision.action == "link"
    assert decision.entity_id == "pm25"
    assert decision.reason == "confirmed_alias"


@pytest.mark.asyncio
async def test_unknown_type_with_same_name_requires_user_resolution(link_session):
    decision = await EntityLinker(link_session).link(
        kb_id="kb1", entity_type="unknown", name="南站"
    )
    assert decision.action == "ambiguous"
    assert len(decision.candidates) == 2


@pytest.mark.asyncio
async def test_unseen_entity_is_created(link_session):
    decision = await EntityLinker(link_session).link(
        kb_id="kb1", entity_type="device", name="1号空压机"
    )
    assert decision.action == "create"
    assert decision.canonical_name == "1号空压机"
