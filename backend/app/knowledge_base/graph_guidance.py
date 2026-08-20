"""Small, synchronous graph snapshot used as optional fault-diagnosis guidance."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from sqlalchemy import select

from app.db.database import async_session
from app.knowledge_base.graph_models import KnowledgeGraphEntity, KnowledgeGraphRelation

logger = structlog.get_logger()


def _as_aliases(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


async def build_graph_guidance_provider(
    knowledge_base_ids: list[str],
    *,
    max_entities: int = 8,
    max_relations: int = 12,
) -> Callable[..., dict[str, Any]] | None:
    """Load a bounded graph snapshot and return a cheap local matcher.

    This deliberately avoids vector/LLM retrieval. It is only a hint source
    for the polling diagnosis path and is safe to omit when unavailable.
    """
    kb_ids = list(dict.fromkeys(str(item).strip() for item in knowledge_base_ids if str(item).strip()))
    if not kb_ids:
        return None
    try:
        async with async_session() as session:
            entity_rows = (
                await session.execute(
                    select(KnowledgeGraphEntity).where(
                        KnowledgeGraphEntity.kb_id.in_(kb_ids),
                        KnowledgeGraphEntity.review_status != "rejected",
                    ).limit(2000)
                )
            ).scalars().all()
            relation_rows = (
                await session.execute(
                    select(KnowledgeGraphRelation).where(
                        KnowledgeGraphRelation.kb_id.in_(kb_ids),
                        KnowledgeGraphRelation.review_status != "rejected",
                    ).limit(4000)
                )
            ).scalars().all()
    except Exception as exc:
        logger.warning("fault_graph_guidance_snapshot_failed", error=str(exc))
        return None

    entities = [
        {
            "id": str(entity.id),
            "name": entity.name,
            "canonical_name": entity.canonical_name,
            "aliases": _as_aliases(entity.aliases),
            "type": entity.entity_type,
            "description": entity.description or "",
        }
        for entity in entity_rows
    ]
    entity_by_id = {item["id"]: item for item in entities}
    relations = [
        {
            "source": entity_by_id.get(str(relation.source_entity_id), {}).get("name", str(relation.source_entity_id)),
            "target": entity_by_id.get(str(relation.target_entity_id), {}).get("name", str(relation.target_entity_id)),
            "relation": relation.relation_type,
            "description": relation.description or "",
        }
        for relation in relation_rows
    ]

    def provider(*, task: str, entity_hints: list[str]) -> dict[str, Any]:
        del task
        hints = [str(item).strip().lower() for item in entity_hints if str(item).strip()]
        matched = [
            entity
            for entity in entities
            if any(
                hint in " ".join(
                    [
                        str(entity.get("name") or ""),
                        str(entity.get("canonical_name") or ""),
                        *entity.get("aliases", []),
                    ]
                ).lower()
                for hint in hints
            )
        ][:max_entities]
        names = {item["name"] for item in matched}
        related = [
            relation
            for relation in relations
            if relation["source"] in names or relation["target"] in names
        ][:max_relations]
        used = bool(matched or related)
        return {
            "used": used,
            "matched": used,
            "knowledge_base_ids": kb_ids,
            "analysis_directions": [
                "图谱仅提供候选规程/关系线索，必须用事件证据和实时接口核验。"
            ] if used else [],
            "data_requirements": [
                "优先核验告警、监测、巡检和质控接口。"
            ] if used else [],
            "suggested_tools": ["knowledge_graph_query"] if used else [],
            "sources": {"entities": matched, "relations": related},
            "fallback_reason": "" if used else "no_graph_match",
        }

    return provider
