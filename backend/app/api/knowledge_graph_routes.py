"""Knowledge graph subresources scoped to one knowledge base."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.knowledge_base.graph_models import (
    KnowledgeGraphEntity,
    KnowledgeGraphRelation,
    KnowledgeIndexOutbox,
)
from app.knowledge_base.graph_repository import KnowledgeGraphRepository
from app.knowledge_base.graph_schemas import (
    GraphEntityCreate,
    GraphEntityUpdate,
    GraphMergeRequest,
    GraphQueryRequest,
    GraphRelationCreate,
    GraphRelationUpdate,
    GraphSchemaUpdate,
)
from app.knowledge_base.index_outbox import KnowledgeIndexOutboxRepository
from app.knowledge_base.ingestion_service import KnowledgeIngestionService
from app.knowledge_base.models import Document, KnowledgeBase
from app.knowledge_base.permissions import KnowledgeBasePermissions

router = APIRouter(
    prefix="/knowledge-base/{kb_id}/graph",
    tags=["Knowledge Graph"],
)


async def _knowledge_base(db: AsyncSession, kb_id: str) -> KnowledgeBase:
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


async def _readable_kb(db: AsyncSession, kb_id: str, user_id: str | None) -> KnowledgeBase:
    kb = await _knowledge_base(db, kb_id)
    if not KnowledgeBasePermissions.can_search(kb, user_id):
        raise HTTPException(status_code=403, detail="No permission to query this knowledge base")
    return kb


async def _manageable_kb(
    db: AsyncSession,
    kb_id: str,
    user_id: str | None,
    is_admin: bool,
) -> KnowledgeBase:
    kb = await _knowledge_base(db, kb_id)
    if not KnowledgeBasePermissions.can_manage(kb, user_id or "anonymous", is_admin):
        raise HTTPException(status_code=403, detail="No permission to manage this knowledge base")
    return kb


def _entity_data(entity: KnowledgeGraphEntity) -> dict:
    return {
        "id": entity.id,
        "entity_type": entity.entity_type,
        "name": entity.name,
        "canonical_name": entity.canonical_name,
        "aliases": list(entity.aliases or []),
        "description": entity.description,
        "attributes": dict(entity.attributes or {}),
        "review_status": entity.review_status,
        "locked_by_user": entity.locked_by_user,
        "mention_count": entity.mention_count,
        "merged_into_id": entity.merged_into_id,
    }


def _relation_data(relation: KnowledgeGraphRelation) -> dict:
    return {
        "id": relation.id,
        "source_entity_id": relation.source_entity_id,
        "target_entity_id": relation.target_entity_id,
        "relation_type": relation.relation_type,
        "description": relation.description,
        "attributes": dict(relation.attributes or {}),
        "review_status": relation.review_status,
        "locked_by_user": relation.locked_by_user,
        "mention_count": relation.mention_count,
    }


async def _next_payload_version(db: AsyncSession, record_type: str, record_id: str) -> int:
    latest = await db.scalar(
        select(func.max(KnowledgeIndexOutbox.payload_version)).where(
            KnowledgeIndexOutbox.record_type == record_type,
            KnowledgeIndexOutbox.record_id == record_id,
        )
    )
    return int(latest or 0) + 1


async def _index_entity(db: AsyncSession, entity: KnowledgeGraphEntity) -> None:
    outbox = KnowledgeIndexOutboxRepository.for_session(db)
    version = await _next_payload_version(db, "entity", entity.id)
    if entity.review_status in {"rejected", "archived", "merged"}:
        await outbox.enqueue_delete(entity.kb_id, "entity", entity.id, version)
    else:
        await outbox.enqueue_upsert(
            entity.kb_id,
            "entity",
            entity.id,
            version,
            KnowledgeIngestionService._entity_payload(entity),
        )


async def _index_relation(db: AsyncSession, relation: KnowledgeGraphRelation) -> None:
    outbox = KnowledgeIndexOutboxRepository.for_session(db)
    version = await _next_payload_version(db, "relation", relation.id)
    if relation.review_status in {"rejected", "archived", "merged"}:
        await outbox.enqueue_delete(relation.kb_id, "relation", relation.id, version)
        return
    source = await db.get(KnowledgeGraphEntity, relation.source_entity_id)
    target = await db.get(KnowledgeGraphEntity, relation.target_entity_id)
    await outbox.enqueue_upsert(
        relation.kb_id,
        "relation",
        relation.id,
        version,
        KnowledgeIngestionService._relation_payload(relation, source, target),
    )


@router.get("/status")
async def graph_status(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    kb = await _readable_kb(db, kb_id, user_id)
    entity_count = await db.scalar(
        select(func.count())
        .select_from(KnowledgeGraphEntity)
        .where(KnowledgeGraphEntity.kb_id == kb_id)
    )
    relation_count = await db.scalar(
        select(func.count())
        .select_from(KnowledgeGraphRelation)
        .where(KnowledgeGraphRelation.kb_id == kb_id)
    )
    failed_documents = await db.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.graph_status == "failed",
        )
    )
    return {
        "knowledge_base_id": kb_id,
        "enabled": kb.graph_enabled,
        "entity_count": int(entity_count or 0),
        "relation_count": int(relation_count or 0),
        "failed_documents": int(failed_documents or 0),
        "updated_at": kb.graph_updated_at,
    }


@router.get("/schema")
async def get_graph_schema(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    kb = await _readable_kb(db, kb_id, user_id)
    return {
        "graph_enabled": kb.graph_enabled,
        "schema": dict(kb.graph_schema or {}),
        "extractor_config": dict(kb.graph_extractor_config or {}),
    }


@router.put("/schema")
async def update_graph_schema(
    kb_id: str,
    request: GraphSchemaUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    kb = await _manageable_kb(db, kb_id, user_id, is_admin)
    if request.graph_enabled is not None:
        kb.graph_enabled = request.graph_enabled
    kb.graph_schema = dict(request.graph_schema)
    if request.extractor_config is not None:
        kb.graph_extractor_config = dict(request.extractor_config)
    kb.graph_updated_at = datetime.utcnow()
    return await get_graph_schema(kb_id, db, user_id)


@router.post("/query")
async def query_graph(
    kb_id: str,
    request: GraphQueryRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    await _readable_kb(db, kb_id, user_id)
    repository = KnowledgeGraphRepository(db)
    statuses = set(request.review_statuses)
    seeds = await repository.query_entities(
        kb_id=kb_id,
        text=request.query or None,
        statuses=statuses,
        limit=request.limit,
    )
    entities, relations = await repository.traverse(
        kb_id=kb_id,
        seed_entity_ids=[entity.id for entity in seeds],
        statuses=statuses,
        depth=request.depth,
        limit=request.limit,
    )
    return {
        "entities": [_entity_data(entity) for entity in entities],
        "relations": [_relation_data(relation) for relation in relations],
    }


@router.get("/entities")
async def list_entities(
    kb_id: str,
    review_statuses: list[str] = Query(default=["candidate", "confirmed", "published"]),
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    await _readable_kb(db, kb_id, user_id)
    entities = await KnowledgeGraphRepository(db).query_entities(
        kb_id=kb_id,
        text=None,
        statuses=set(review_statuses),
        limit=limit,
    )
    return {"entities": [_entity_data(entity) for entity in entities]}


@router.post("/entities", status_code=status.HTTP_201_CREATED)
async def create_entity(
    kb_id: str,
    request: GraphEntityCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    normalized = KnowledgeGraphRepository.normalize_entity_name(
        request.canonical_name or request.name
    )
    existing = await db.scalar(
        select(KnowledgeGraphEntity).where(
            KnowledgeGraphEntity.kb_id == kb_id,
            KnowledgeGraphEntity.entity_type == request.entity_type,
            KnowledgeGraphEntity.normalized_name == normalized,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Entity already exists")
    entity = KnowledgeGraphEntity(
        kb_id=kb_id,
        entity_type=request.entity_type,
        name=request.name,
        normalized_name=normalized,
        canonical_name=request.canonical_name,
        aliases=request.aliases,
        description=request.description,
        attributes=request.attributes,
        review_status=request.review_status,
        created_by="user",
        locked_by_user=True,
    )
    db.add(entity)
    await db.flush()
    await _index_entity(db, entity)
    return _entity_data(entity)


@router.patch("/entities/{entity_id}")
async def update_entity(
    kb_id: str,
    entity_id: str,
    request: GraphEntityUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    entity = await db.get(KnowledgeGraphEntity, entity_id)
    if entity is None or entity.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="Entity not found")
    changes = request.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(entity, field, value)
    if request.name is not None or request.canonical_name is not None:
        entity.normalized_name = KnowledgeGraphRepository.normalize_entity_name(
            entity.canonical_name or entity.name
        )
    entity.locked_by_user = True
    await _index_entity(db, entity)
    return _entity_data(entity)


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(
    kb_id: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    entity = await db.get(KnowledgeGraphEntity, entity_id)
    if entity is None or entity.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="Entity not found")
    entity.review_status = "archived"
    entity.locked_by_user = True
    await _index_entity(db, entity)


@router.get("/relations")
async def list_relations(
    kb_id: str,
    review_statuses: list[str] = Query(default=["candidate", "confirmed", "published"]),
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    await _readable_kb(db, kb_id, user_id)
    result = await db.execute(
        select(KnowledgeGraphRelation)
        .where(
            KnowledgeGraphRelation.kb_id == kb_id,
            KnowledgeGraphRelation.review_status.in_(review_statuses),
        )
        .limit(limit)
    )
    return {"relations": [_relation_data(relation) for relation in result.scalars()]}


@router.post("/relations", status_code=status.HTTP_201_CREATED)
async def create_relation(
    kb_id: str,
    request: GraphRelationCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    source = await db.get(KnowledgeGraphEntity, request.source_entity_id)
    target = await db.get(KnowledgeGraphEntity, request.target_entity_id)
    if source is None or target is None or source.kb_id != kb_id or target.kb_id != kb_id:
        raise HTTPException(
            status_code=400, detail="Relation endpoints must belong to knowledge base"
        )
    relation = KnowledgeGraphRelation(
        kb_id=kb_id,
        source_entity_id=source.id,
        target_entity_id=target.id,
        relation_type=KnowledgeGraphRepository.normalize_relation_type(request.relation_type),
        description=request.description,
        attributes=request.attributes,
        review_status=request.review_status,
        created_by="user",
        locked_by_user=True,
    )
    db.add(relation)
    await db.flush()
    await _index_relation(db, relation)
    return _relation_data(relation)


@router.patch("/relations/{relation_id}")
async def update_relation(
    kb_id: str,
    relation_id: str,
    request: GraphRelationUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    relation = await db.get(KnowledgeGraphRelation, relation_id)
    if relation is None or relation.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="Relation not found")
    changes = request.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(relation, field, value)
    if request.relation_type is not None:
        relation.relation_type = KnowledgeGraphRepository.normalize_relation_type(
            request.relation_type
        )
    relation.locked_by_user = True
    await _index_relation(db, relation)
    return _relation_data(relation)


@router.delete("/relations/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relation(
    kb_id: str,
    relation_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    relation = await db.get(KnowledgeGraphRelation, relation_id)
    if relation is None or relation.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="Relation not found")
    relation.review_status = "archived"
    relation.locked_by_user = True
    await _index_relation(db, relation)


@router.post("/merge")
async def merge_entities(
    kb_id: str,
    request: GraphMergeRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    repository = KnowledgeGraphRepository(db)
    await repository.merge_entities(
        kb_id=kb_id,
        source_id=request.source_id,
        target_id=request.target_id,
    )
    source = await db.get(KnowledgeGraphEntity, request.source_id)
    target = await db.get(KnowledgeGraphEntity, request.target_id)
    if source is not None:
        await _index_entity(db, source)
    if target is not None:
        await _index_entity(db, target)
    return {"source_id": request.source_id, "target": _entity_data(target)}


@router.post("/retry-failed")
async def retry_failed_graphs(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    documents = list(
        (
            await db.execute(
                select(Document).where(
                    Document.knowledge_base_id == kb_id,
                    Document.graph_status == "failed",
                )
            )
        ).scalars()
    )
    from app.knowledge_base.service import KnowledgeBaseService

    for document in documents:
        await KnowledgeBaseService(db=db).ingest_document(document.id)
    return {"retried_documents": len(documents)}


@router.post("/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex_graph(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    kb = await _manageable_kb(db, kb_id, user_id, is_admin)
    entities = list(
        (
            await db.execute(
                select(KnowledgeGraphEntity).where(KnowledgeGraphEntity.kb_id == kb_id)
            )
        ).scalars()
    )
    relations = list(
        (
            await db.execute(
                select(KnowledgeGraphRelation).where(KnowledgeGraphRelation.kb_id == kb_id)
            )
        ).scalars()
    )
    for entity in entities:
        await _index_entity(db, entity)
    for relation in relations:
        await _index_relation(db, relation)
    kb.graph_updated_at = datetime.utcnow()
    return {"queued_entities": len(entities), "queued_relations": len(relations)}
