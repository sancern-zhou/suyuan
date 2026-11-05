"""从知识图谱加载故障归因边集（fault relation edges）的有界提供器。

与 ``graph_guidance`` 同风格：确定性读取、不做向量/LLM 检索、不可用时安全降级。
边行经 ``fault_relation_registry`` 解析校验，非法边跳过并记录告警。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from sqlalchemy import select

from app.db.knowledge_database import knowledge_async_session as async_session
from app.knowledge_base.graph_models import KnowledgeGraphRelation
from app.services.fault_relation_registry import load_fault_edges

logger = structlog.get_logger()

MAX_FAULT_EDGES = 64


def make_fault_relation_provider(relation_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """把关系行（dict 形态）解析为提供器载荷；纯函数，便于测试。"""
    edges, warnings = load_fault_edges(relation_rows)
    for warning in warnings:
        logger.warning("fault_relation_edge_invalid", error=warning)
    return {
        "used": bool(edges),
        "edges": edges,
        "fallback_reason": "" if edges else "no_fault_edges",
    }


async def build_fault_relation_provider(
    knowledge_base_ids: list[str],
    *,
    max_edges: int = MAX_FAULT_EDGES,
) -> Callable[..., dict[str, Any]] | None:
    """加载项目知识库中 ``fault.`` 前缀的已确认关系，返回提供器；无库时返回 None。"""
    kb_ids = list(
        dict.fromkeys(str(item).strip() for item in knowledge_base_ids if str(item).strip())
    )
    if not kb_ids:
        return None
    try:
        async with async_session() as session:
            rows = (
                await session.execute(
                    select(KnowledgeGraphRelation)
                    .where(
                        KnowledgeGraphRelation.kb_id.in_(kb_ids),
                        KnowledgeGraphRelation.relation_type.like("fault.%"),
                        KnowledgeGraphRelation.review_status != "rejected",
                    )
                    .order_by(KnowledgeGraphRelation.relation_type, KnowledgeGraphRelation.id)
                    .limit(max_edges)
                )
            ).scalars().all()
    except Exception as exc:
        logger.warning("fault_relation_provider_load_failed", error=str(exc))
        return None

    relation_dicts = [
        {
            "relation_type": row.relation_type,
            "attributes": row.attributes if isinstance(row.attributes, dict) else {},
            "source_name": "",
            "target_name": "",
        }
        for row in rows
    ]
    payload = make_fault_relation_provider(relation_dicts)
    payload["knowledge_base_ids"] = kb_ids
    if payload["used"]:
        logger.info(
            "fault_relation_provider_loaded",
            knowledge_base_ids=kb_ids,
            edge_count=len(payload["edges"]),
        )
    return lambda **_kwargs: payload
