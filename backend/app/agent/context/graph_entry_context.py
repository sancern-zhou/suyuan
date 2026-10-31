"""Query-entry entity linking over the project knowledge graph.

Deterministic, bounded context injection for data-query modes: match the user
question against trusted graph entities (name/alias containment, no LLM, no
vector search), expand their adjacent relations, and render a compact layer
so the agent gets metric calibers and tool routing without calling a graph
tool by itself.

Enabled per project via ``knowledge.graph_entry_modes``; the graph is resolved
from ``knowledge.bindings.data_semantics``. Every failure degrades to "" —
the layer is a hint source and must never break the conversation.
"""
from __future__ import annotations

import structlog
from sqlalchemy import select

from app.db.knowledge_database import knowledge_async_session as async_session
from app.knowledge_base.graph_models import KnowledgeGraphEntity, KnowledgeGraphRelation
from app.knowledge_base.graph_schemas import TRUSTED_REVIEW_STATUSES

logger = structlog.get_logger()

GRAPH_ENTRY_BINDING_KEY = "data_semantics"

# 与 graph_guidance 相同的快照上限：BFS/匹配都在内存做，必须限流。
_MAX_ENTITIES_IN_SNAPSHOT = 2000
_MAX_RELATIONS_IN_SNAPSHOT = 4000

_MAX_MATCHED_ENTITIES = 4
_MAX_RENDERED_RELATIONS = 10
_MAX_ENTITY_LINE_CHARS = 220
_MAX_LAYER_CHARS = 1800

_MIN_ALIAS_CHARS = 2

_ENTITY_LAYER_HEADER = (
    "以下条目命中本项目知识图谱（确定性业务口径，可直接采用；"
    "与接口实测数据冲突时以实测为准）："
)


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _match_entities(
    question: str, entities: list[KnowledgeGraphEntity]
) -> list[KnowledgeGraphEntity]:
    """按名称/别名在问题中的出现匹配实体，命中串越长越靠前。"""
    normalized_question = _normalize(question)
    if not normalized_question:
        return []
    scored: list[tuple[int, str, KnowledgeGraphEntity]] = []
    for entity in entities:
        candidates = [entity.name, *(entity.aliases or [])]
        best = 0
        for candidate in candidates:
            term = _normalize(candidate)
            if len(term) < _MIN_ALIAS_CHARS or term not in normalized_question:
                continue
            best = max(best, len(term))
        if best:
            scored.append((best, entity.name, entity))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [entity for _, _, entity in scored[:_MAX_MATCHED_ENTITIES]]


def _render_attributes(entity: KnowledgeGraphEntity) -> str:
    parts: list[str] = []
    for key, value in (entity.attributes or {}).items():
        if key.startswith("_") or value in (None, "", [], {}):
            continue
        parts.append(f"{key}={value}")
        if len(parts) == 3:
            break
    return f"（{'；'.join(parts)}）" if parts else ""


def _render_entity_line(entity: KnowledgeGraphEntity) -> str:
    description = (entity.description or "").strip()
    line = f"- 「{entity.name}」({entity.entity_type})"
    if description:
        line += f"：{description}"
    line += _render_attributes(entity)
    return line[:_MAX_ENTITY_LINE_CHARS]


def build_graph_entry_layer(
    question: str,
    entities: list[KnowledgeGraphEntity],
    relations: list[KnowledgeGraphRelation],
) -> str:
    """从实体/关系快照渲染入口上下文层（纯函数，便于测试）。"""
    matched = _match_entities(question, entities)
    if not matched:
        return ""

    matched_ids = {entity.id for entity in matched}
    name_by_id = {entity.id: entity.name for entity in entities}
    rendered_relations: list[str] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for relation in relations:
        if len(rendered_relations) >= _MAX_RENDERED_RELATIONS:
            break
        source_id = relation.source_entity_id
        target_id = relation.target_entity_id
        if source_id not in matched_ids and target_id not in matched_ids:
            continue
        source_name = name_by_id.get(source_id)
        target_name = name_by_id.get(target_id)
        if not source_name or not target_name:
            continue
        pair_key = (source_name, relation.relation_type, target_name)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        description = (relation.description or "").strip()
        arrow = f"{source_name} -[{relation.relation_type}]-> {target_name}"
        rendered_relations.append(f"  - {arrow}" + (f"：{description}" if description else ""))

    lines = [_ENTITY_LAYER_HEADER]
    for entity in matched:
        lines.append(_render_entity_line(entity))
    if rendered_relations:
        lines.append("  关联关系：")
        lines.extend(rendered_relations)

    layer = "\n".join(lines)
    if len(layer) > _MAX_LAYER_CHARS:
        layer = layer[:_MAX_LAYER_CHARS].rstrip() + "\n  …（已截断）"
    return layer


async def build_graph_entry_context(question: str) -> str:
    """解析项目绑定知识库并对问题做实体匹配，返回有界上下文层文本。"""
    try:
        from app.knowledge_base.project_bindings import resolve_project_knowledge_base_ids

        kb_ids = await resolve_project_knowledge_base_ids(GRAPH_ENTRY_BINDING_KEY)
        if not kb_ids:
            return ""
        async with async_session() as session:
            entity_rows = (
                await session.execute(
                    select(KnowledgeGraphEntity).where(
                        KnowledgeGraphEntity.kb_id.in_(kb_ids),
                        KnowledgeGraphEntity.review_status.in_(TRUSTED_REVIEW_STATUSES),
                    ).limit(_MAX_ENTITIES_IN_SNAPSHOT)
                )
            ).scalars().all()
            relation_rows = (
                await session.execute(
                    select(KnowledgeGraphRelation).where(
                        KnowledgeGraphRelation.kb_id.in_(kb_ids),
                        KnowledgeGraphRelation.review_status.in_(TRUSTED_REVIEW_STATUSES),
                    ).limit(_MAX_RELATIONS_IN_SNAPSHOT)
                )
            ).scalars().all()
    except Exception as exc:
        logger.warning("graph_entry_context_failed", error=str(exc))
        return ""

    layer = build_graph_entry_layer(question, list(entity_rows), list(relation_rows))
    if layer:
        logger.info(
            "graph_entry_hit",
            binding=GRAPH_ENTRY_BINDING_KEY,
            matched_entities=[entity.name for entity in _match_entities(question, list(entity_rows))],
            relations=len(relation_rows),
            chars=len(layer),
        )
    else:
        logger.debug("graph_entry_miss", binding=GRAPH_ENTRY_BINDING_KEY)
    return layer
