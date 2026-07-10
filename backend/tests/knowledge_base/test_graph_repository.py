import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeChunk, KnowledgeGraphEntity
from app.knowledge_base.graph_schemas import (
    ChunkGraphExtraction,
    ExtractedEntity,
    ExtractedRelation,
)
from app.knowledge_base.models import Document, KnowledgeBase


def extraction(chunk_id: str) -> ChunkGraphExtraction:
    return ChunkGraphExtraction(
        chunk_id=chunk_id,
        extractor_name="test-extractor",
        entities=[
            ExtractedEntity(
                local_id="station",
                entity_type="Station",
                name="  广州站  ",
                evidence_text="广州站监测臭氧",
            ),
            ExtractedEntity(
                local_id="ozone",
                entity_type="Pollutant",
                name="臭氧",
                aliases=["O3"],
                evidence_text="广州站监测臭氧",
            ),
        ],
        relations=[
            ExtractedRelation(
                source_local_id="station",
                target_local_id="ozone",
                relation_type="measures",
                evidence_text="广州站监测臭氧",
            )
        ],
    )


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(
            [
                KnowledgeBase(id="kb1", name="KB1", qdrant_collection="kb1"),
                KnowledgeBase(id="kb2", name="KB2", qdrant_collection="kb2"),
                Document(id="doc1", knowledge_base_id="kb1", filename="a.md"),
                Document(id="doc2", knowledge_base_id="kb1", filename="b.md"),
                Document(id="doc3", knowledge_base_id="kb2", filename="c.md"),
            ]
        )
        await session.flush()
        session.add_all(
            [
                KnowledgeChunk(
                    id="chunk1",
                    kb_id="kb1",
                    document_id="doc1",
                    content_generation=1,
                    chunk_key="c1",
                    content_hash="h1",
                    chunk_index=0,
                    content="广州站监测臭氧",
                    embedding_text="广州站监测臭氧",
                ),
                KnowledgeChunk(
                    id="chunk2",
                    kb_id="kb1",
                    document_id="doc2",
                    content_generation=1,
                    chunk_key="c2",
                    content_hash="h2",
                    chunk_index=0,
                    content="广州站监测臭氧",
                    embedding_text="广州站监测臭氧",
                ),
                KnowledgeChunk(
                    id="chunk3",
                    kb_id="kb2",
                    document_id="doc3",
                    content_generation=1,
                    chunk_key="c3",
                    content_hash="h3",
                    chunk_index=0,
                    content="广州站监测臭氧",
                    embedding_text="广州站监测臭氧",
                ),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_same_identity_reuses_within_kb_but_not_across_kbs(db_session):
    from app.knowledge_base.graph_repository import KnowledgeGraphRepository

    repository = KnowledgeGraphRepository(db_session)
    first = await repository.upsert_chunk_extraction(
        kb_id="kb1",
        document_id="doc1",
        extraction=extraction("chunk1"),
        extraction_run_id="run1",
    )
    second = await repository.upsert_chunk_extraction(
        kb_id="kb1",
        document_id="doc2",
        extraction=extraction("chunk2"),
        extraction_run_id="run2",
    )
    other_kb = await repository.upsert_chunk_extraction(
        kb_id="kb2",
        document_id="doc3",
        extraction=extraction("chunk3"),
        extraction_run_id="run3",
    )

    assert first.entity_ids == second.entity_ids
    assert first.relation_ids == second.relation_ids
    assert set(first.entity_ids).isdisjoint(other_kb.entity_ids)
    assert first.relation_ids != other_kb.relation_ids
    entities = await repository.query_entities(
        kb_id="kb1",
        text="广州站",
        statuses={"candidate"},
        limit=10,
    )
    assert entities[0].normalized_name == "广州站"
    assert entities[0].mention_count == 2


@pytest.mark.asyncio
async def test_removing_one_document_preserves_shared_relation_and_last_removal_cleans_it(
    db_session,
):
    from app.knowledge_base.graph_repository import KnowledgeGraphRepository

    repository = KnowledgeGraphRepository(db_session)
    first = await repository.upsert_chunk_extraction(
        kb_id="kb1",
        document_id="doc1",
        extraction=extraction("chunk1"),
        extraction_run_id="run1",
    )
    await repository.upsert_chunk_extraction(
        kb_id="kb1",
        document_id="doc2",
        extraction=extraction("chunk2"),
        extraction_run_id="run2",
    )

    await repository.remove_chunk_contributions(kb_id="kb1", chunk_ids=["chunk1"])
    relation = await repository.get_relation(first.relation_ids[0])
    assert relation is not None
    assert relation.mention_count == 1

    removed_entities, removed_relations = await repository.remove_chunk_contributions(
        kb_id="kb1",
        chunk_ids=["chunk2"],
    )
    assert first.relation_ids[0] in removed_relations
    assert await repository.get_relation(first.relation_ids[0]) is None
    assert set(first.entity_ids) <= set(removed_entities)


@pytest.mark.asyncio
async def test_confirmed_entity_is_archived_when_its_last_source_is_removed(db_session):
    from app.knowledge_base.graph_repository import KnowledgeGraphRepository

    repository = KnowledgeGraphRepository(db_session)
    result = await repository.upsert_chunk_extraction(
        kb_id="kb1",
        document_id="doc1",
        extraction=extraction("chunk1"),
        extraction_run_id="run1",
    )
    entity_id = result.entity_ids[0]
    await repository.set_review_status(
        kb_id="kb1",
        kind="entity",
        record_id=entity_id,
        status="confirmed",
    )

    removed_entities, _ = await repository.remove_chunk_contributions(
        kb_id="kb1",
        chunk_ids=["chunk1"],
    )
    entity = await db_session.get(KnowledgeGraphEntity, entity_id)

    assert entity is not None
    assert entity.review_status == "archived"
    assert entity_id in removed_entities


@pytest.mark.asyncio
async def test_merge_entities_rewrites_relations_and_mentions(db_session):
    from app.knowledge_base.graph_repository import KnowledgeGraphRepository

    repository = KnowledgeGraphRepository(db_session)
    result = await repository.upsert_chunk_extraction(
        kb_id="kb1",
        document_id="doc1",
        extraction=extraction("chunk1"),
        extraction_run_id="run1",
    )
    source_id, target_id = result.entity_ids

    await repository.merge_entities(kb_id="kb1", source_id=source_id, target_id=target_id)
    source = await db_session.get(KnowledgeGraphEntity, source_id)
    target = await db_session.get(KnowledgeGraphEntity, target_id)
    relations = await repository.traverse(
        kb_id="kb1",
        seed_entity_ids=[target_id],
        statuses={"candidate"},
        depth=2,
        limit=10,
    )

    assert source.review_status == "merged"
    assert source.merged_into_id == target_id
    assert "广州站" in target.aliases
    assert relations[1] == []


@pytest.mark.asyncio
async def test_traverse_returns_two_hop_trusted_subgraph_and_chunk_sources(db_session):
    from app.knowledge_base.graph_repository import KnowledgeGraphRepository

    repository = KnowledgeGraphRepository(db_session)
    result = await repository.upsert_chunk_extraction(
        kb_id="kb1",
        document_id="doc1",
        extraction=extraction("chunk1"),
        extraction_run_id="run1",
    )
    for entity_id in result.entity_ids:
        await repository.set_review_status(
            kb_id="kb1",
            kind="entity",
            record_id=entity_id,
            status="confirmed",
        )
    await repository.set_review_status(
        kb_id="kb1",
        kind="relation",
        record_id=result.relation_ids[0],
        status="confirmed",
    )

    entities, relations = await repository.traverse(
        kb_id="kb1",
        seed_entity_ids=[result.entity_ids[0]],
        statuses={"confirmed"},
        depth=2,
        limit=10,
    )
    chunk_ids = await repository.chunk_ids_for_graph_records(
        kb_id="kb1",
        entity_ids=[entity.id for entity in entities],
        relation_ids=[relation.id for relation in relations],
    )

    assert {entity.id for entity in entities} == set(result.entity_ids)
    assert [relation.id for relation in relations] == result.relation_ids
    assert chunk_ids == ["chunk1"]


@pytest.mark.asyncio
async def test_query_entities_filters_status_and_kb(db_session):
    from app.knowledge_base.graph_repository import KnowledgeGraphRepository

    repository = KnowledgeGraphRepository(db_session)
    await repository.upsert_chunk_extraction(
        kb_id="kb1",
        document_id="doc1",
        extraction=extraction("chunk1"),
        extraction_run_id="run1",
    )
    await repository.upsert_chunk_extraction(
        kb_id="kb2",
        document_id="doc3",
        extraction=extraction("chunk3"),
        extraction_run_id="run2",
    )

    confirmed = list(
        (
            await db_session.execute(
                select(KnowledgeGraphEntity).where(KnowledgeGraphEntity.kb_id == "kb1")
            )
        )
        .scalars()
        .all()
    )[0]
    await repository.set_review_status(
        kb_id="kb1",
        kind="entity",
        record_id=confirmed.id,
        status="confirmed",
    )

    entities = await repository.query_entities(
        kb_id="kb1",
        text=None,
        statuses={"confirmed"},
        limit=10,
    )
    assert [entity.id for entity in entities] == [confirmed.id]
