"""Consistent cursor paging for complete knowledge-base graph snapshots."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from sqlalchemy import func, select

from app.knowledge_base.graph_models import KnowledgeGraphEntity, KnowledgeGraphRelation
from app.knowledge_base.models import KnowledgeBase


class InvalidGraphSnapshotCursor(ValueError):
    pass


class GraphSnapshotChanged(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphSnapshotPage:
    knowledge_base_id: str
    snapshot_version: int
    entities: list[KnowledgeGraphEntity]
    relations: list[KnowledgeGraphRelation]
    next_cursor: str | None
    entity_total: int
    relation_total: int


def _encode_cursor(*, kb_id: str, phase: str, last_id: str, revision: int) -> str:
    raw = json.dumps(
        {"kb": kb_id, "phase": phase, "last_id": last_id, "revision": revision},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str) -> dict:
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode())
        if data.get("phase") not in {"entities", "relations"}:
            raise ValueError("invalid phase")
        if not isinstance(data.get("last_id"), str) or not isinstance(data.get("revision"), int):
            raise ValueError("invalid cursor fields")
        return data
    except Exception as exc:
        raise InvalidGraphSnapshotCursor("Invalid graph snapshot cursor") from exc


class GraphSnapshotRepository:
    def __init__(self, session):
        self.session = session

    async def page(
        self, *, kb_id: str, statuses: set[str], cursor: str | None,
        expected_revision: int | None, page_size: int,
    ) -> GraphSnapshotPage:
        kb = await self.session.scalar(
            select(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id)
            .with_for_update(read=True)
        )
        if kb is None:
            raise ValueError(f"Knowledge base not found: {kb_id}")
        revision = int(kb.graph_revision or 0)
        cursor_data = _decode_cursor(cursor) if cursor else None
        if cursor_data and cursor_data.get("kb") != kb_id:
            raise InvalidGraphSnapshotCursor("Cursor belongs to another knowledge base")
        cursor_revision = cursor_data["revision"] if cursor_data else revision
        if expected_revision is not None and int(expected_revision) != revision:
            raise GraphSnapshotChanged("graph_snapshot_changed")
        if cursor_revision != revision:
            raise GraphSnapshotChanged("graph_snapshot_changed")

        entity_total = int(await self.session.scalar(
            select(func.count()).select_from(KnowledgeGraphEntity).where(
                KnowledgeGraphEntity.kb_id == kb_id,
                KnowledgeGraphEntity.review_status.in_(statuses),
            )
        ) or 0)
        relation_filter = (
            (KnowledgeGraphRelation.kb_id == kb_id)
            & KnowledgeGraphRelation.review_status.in_(statuses)
            & KnowledgeGraphRelation.source_entity_id.in_(
                select(KnowledgeGraphEntity.id).where(
                    KnowledgeGraphEntity.kb_id == kb_id,
                    KnowledgeGraphEntity.review_status.in_(statuses),
                )
            )
            & KnowledgeGraphRelation.target_entity_id.in_(
                select(KnowledgeGraphEntity.id).where(
                    KnowledgeGraphEntity.kb_id == kb_id,
                    KnowledgeGraphEntity.review_status.in_(statuses),
                )
            )
        )
        relation_total = int(await self.session.scalar(
            select(func.count()).select_from(KnowledgeGraphRelation).where(relation_filter)
        ) or 0)

        phase = cursor_data["phase"] if cursor_data else "entities"
        last_id = cursor_data["last_id"] if cursor_data else ""
        entities: list[KnowledgeGraphEntity] = []
        relations: list[KnowledgeGraphRelation] = []
        next_cursor = None
        if phase == "entities":
            rows = list((await self.session.scalars(
                select(KnowledgeGraphEntity).where(
                    KnowledgeGraphEntity.kb_id == kb_id,
                    KnowledgeGraphEntity.review_status.in_(statuses),
                    KnowledgeGraphEntity.id > last_id,
                ).order_by(KnowledgeGraphEntity.id).limit(page_size + 1)
            )).all())
            entities = rows[:page_size]
            if len(rows) > page_size:
                next_cursor = _encode_cursor(
                    kb_id=kb_id, phase="entities", last_id=entities[-1].id, revision=revision
                )
            elif relation_total:
                next_cursor = _encode_cursor(
                    kb_id=kb_id, phase="relations", last_id="", revision=revision
                )
        else:
            rows = list((await self.session.scalars(
                select(KnowledgeGraphRelation).where(
                    relation_filter,
                    KnowledgeGraphRelation.id > last_id,
                ).order_by(KnowledgeGraphRelation.id).limit(page_size + 1)
            )).all())
            relations = rows[:page_size]
            if len(rows) > page_size:
                next_cursor = _encode_cursor(
                    kb_id=kb_id, phase="relations", last_id=relations[-1].id, revision=revision
                )
        return GraphSnapshotPage(
            knowledge_base_id=kb_id,
            snapshot_version=revision,
            entities=entities,
            relations=relations,
            next_cursor=next_cursor,
            entity_total=entity_total,
            relation_total=relation_total,
        )
