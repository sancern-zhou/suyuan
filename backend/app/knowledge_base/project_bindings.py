"""Resolve project-level logical knowledge-base bindings at runtime."""

from __future__ import annotations

import os

import structlog
from sqlalchemy import or_, select

from app.db.database import async_session
from app.knowledge_base.models import KnowledgeBase, KnowledgeBaseStatus

logger = structlog.get_logger()


async def resolve_project_knowledge_base_ids(binding_key: str | None) -> list[str]:
    """Resolve one project binding to an active, graph-enabled KB id.

    Bindings are intentionally resolved at execution time because ids differ
    between deployments. A deployment-specific environment override is
    supported for the station-fault binding; manifest values may be ids or
    exact names. Missing/invalid bindings degrade to an empty list.
    """
    if not binding_key:
        return []

    try:
        from config.settings import settings
        from app.project_config.loader import load_project_context

        target = load_project_context(settings.project_id).manifest.knowledge.bindings.get(
            binding_key
        )
        if binding_key == "station_fault_diagnosis":
            target = os.getenv("JIANGSU_STATION_FAULT_KB_ID") or target
    except Exception as exc:
        logger.warning("knowledge_base_binding_config_failed", binding=binding_key, error=str(exc))
        return []

    if not target:
        logger.warning("knowledge_base_binding_missing", binding=binding_key)
        return []

    try:
        async with async_session() as session:
            result = await session.execute(
                select(KnowledgeBase.id, KnowledgeBase.name).where(
                    KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE,
                    KnowledgeBase.graph_enabled.is_(True),
                    or_(KnowledgeBase.id == target, KnowledgeBase.name == target),
                )
            )
            rows = result.all()
    except Exception as exc:
        logger.warning("knowledge_base_binding_lookup_failed", binding=binding_key, error=str(exc))
        return []

    if not rows:
        logger.warning(
            "knowledge_base_binding_unavailable",
            binding=binding_key,
            target=target,
        )
        return []

    # Exact ids are unique; names can be duplicated, so choose the first
    # stable result and make the decision visible in logs.
    kb_id, kb_name = rows[0]
    if len(rows) > 1:
        logger.warning(
            "knowledge_base_binding_ambiguous",
            binding=binding_key,
            target=target,
            match_count=len(rows),
        )
    logger.info(
        "knowledge_base_binding_resolved",
        binding=binding_key,
        knowledge_base_id=kb_id,
        knowledge_base_name=kb_name,
    )
    return [str(kb_id)]
