"""Atomic knowledge-base graph revision updates."""

from datetime import datetime

from sqlalchemy import update

from app.knowledge_base.models import KnowledgeBase


async def bump_graph_revision(session, kb_id: str) -> int:
    revision = await session.scalar(
        update(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id)
        .values(
            graph_revision=KnowledgeBase.graph_revision + 1,
            graph_updated_at=datetime.utcnow(),
        )
        .returning(KnowledgeBase.graph_revision)
    )
    if revision is None:
        raise ValueError(f"Knowledge base not found: {kb_id}")
    return int(revision)
