"""Knowledge-base scope helpers for the enforcement exam runtime."""

from __future__ import annotations

from app.knowledge_base.models import KnowledgeBaseStatus


ENFORCEMENT_EXAM_KNOWLEDGE_BASE_NAME = "执法知识"


def is_enforcement_exam_context(context) -> bool:
    return getattr(context, "runtime_mode", None) == "enforcement_exam"


async def resolve_enforcement_exam_knowledge_base_ids(user_id: str | None) -> list[str]:
    from app.db.database import async_session
    from app.knowledge_base.service import KnowledgeBaseService

    async with async_session() as db:
        knowledge_bases = await KnowledgeBaseService(db=db).list_knowledge_bases(
            user_id=user_id,
            include_public=True,
            status=KnowledgeBaseStatus.ACTIVE,
        )
    return [
        kb.id
        for kb in knowledge_bases
        if str(kb.name or "").strip() == ENFORCEMENT_EXAM_KNOWLEDGE_BASE_NAME
    ]
