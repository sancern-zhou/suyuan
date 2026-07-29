import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeGraphEntity, KnowledgeGraphRelation
from app.knowledge_base.models import KnowledgeBase


@pytest.mark.asyncio
async def test_snapshot_pages_cover_more_than_200_entities_and_all_relations():
    from app.knowledge_base.graph_snapshot import GraphSnapshotRepository

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session, session.begin():
        session.add(KnowledgeBase(id="kb", name="KB", qdrant_collection="qc"))
        entities = [
            KnowledgeGraphEntity(
                id=f"e-{index:03}", kb_id="kb", entity_type="thing",
                name=f"Entity {index}", normalized_name=f"entity-{index}",
                review_status="confirmed",
            )
            for index in range(205)
        ]
        session.add_all(entities)
        session.add_all([
            KnowledgeGraphRelation(
                id="r-loop", kb_id="kb", source_entity_id="e-000",
                target_entity_id="e-000", relation_type="SELF", review_status="confirmed",
            ),
            KnowledgeGraphRelation(
                id="r-link", kb_id="kb", source_entity_id="e-000",
                target_entity_id="e-001", relation_type="LINK", review_status="confirmed",
            ),
        ])
    found_entities, found_relations, cursor, revision = [], [], None, None
    async with sessions() as session:
        repository = GraphSnapshotRepository(session)
        while True:
            page = await repository.page(
                kb_id="kb", statuses={"confirmed"}, cursor=cursor,
                expected_revision=revision, page_size=50,
            )
            revision = page.snapshot_version
            found_entities.extend(item.id for item in page.entities)
            found_relations.extend(item.id for item in page.relations)
            cursor = page.next_cursor
            if cursor is None:
                break
    assert len(set(found_entities)) == 205
    assert set(found_relations) == {"r-loop", "r-link"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_snapshot_rejects_revision_change_between_pages():
    from app.knowledge_base.graph_snapshot import GraphSnapshotChanged, GraphSnapshotRepository

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session, session.begin():
        session.add(KnowledgeBase(id="kb", name="KB", qdrant_collection="qc", graph_revision=1))
        session.add_all([
            KnowledgeGraphEntity(id=f"e-{index}", kb_id="kb", entity_type="thing",
                                 name=f"E {index}", normalized_name=f"e-{index}",
                                 review_status="confirmed")
            for index in range(3)
        ])
    async with sessions() as session:
        first = await GraphSnapshotRepository(session).page(
            kb_id="kb", statuses={"confirmed"}, cursor=None,
            expected_revision=None, page_size=2,
        )
    async with sessions() as session, session.begin():
        kb = await session.get(KnowledgeBase, "kb")
        kb.graph_revision = 2
    async with sessions() as session:
        with pytest.raises(GraphSnapshotChanged):
            await GraphSnapshotRepository(session).page(
                kb_id="kb", statuses={"confirmed"}, cursor=first.next_cursor,
                expected_revision=first.snapshot_version, page_size=2,
            )
    await engine.dispose()
