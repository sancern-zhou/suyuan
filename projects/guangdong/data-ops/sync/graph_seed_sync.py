# -*- coding: utf-8 -*-
"""Sync the Guangdong data-semantics graph seed into the project knowledge base.

流程（与许昌站点目录 sync_knowledge_graph 同构，全部确定性、不经 LLM 抽取）：
  1. 解析 knowledge.bindings.data_semantics 指向的知识库（不存在时 --ensure-kb 自动创建，
     graph_enabled 默认开启）；
  2. 上传 gen_graph_seed.py 生成的《广东数据语义契约.md》（替换同名旧文档）；
  3. reset_graph 清空旧图；
  4. 调用 backend/app/knowledge_base/graph_seed_service.seed_graph_extraction 一次性写入
     实体/关系并置 confirmed。

用法:
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/graph_seed_sync.py --ensure-kb
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/graph_seed_sync.py            # 知识库必须已存在
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys

from app.utils.path_config import get_data_registry, resolve_agent_path

SEED_PATH = resolve_agent_path("projects/guangdong/data-ops/graph/graph_seed.json")
DOC_PATH = resolve_agent_path("projects/guangdong/data-ops/graph/广东数据语义契约.md")


async def _resolve_or_create_kb(ensure: bool) -> tuple[str, str, bool]:
    from sqlalchemy import or_, select

    from app.db.database import async_session
    from app.knowledge_base.models import KnowledgeBase, KnowledgeBaseStatus
    from app.project_config.loader import load_project_context
    from config.settings import settings

    try:
        binding = load_project_context(settings.project_id).manifest.knowledge.bindings.get(
            "data_semantics"
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"解析项目清单失败: {exc}")
    if not binding:
        raise SystemExit(
            "项目 knowledge.bindings 未配置 data_semantics，无法定位目标知识库"
        )

    async with async_session() as session:
        row = (
            await session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE,
                    or_(KnowledgeBase.id == binding, KnowledgeBase.name == binding),
                )
            )
        ).scalars().first()
        if row is not None:
            return str(row.id), str(row.name), False
        if not ensure:
            raise SystemExit(
                f"知识库不存在：{binding}。先用 --ensure-kb 创建，或在部署环境建库后重试。"
            )
        from app.knowledge_base.service import KnowledgeBaseService

        service = KnowledgeBaseService(db=session)
        kb = await service.create_knowledge_base(
            name=str(binding),
            description="广东数据语义图谱（data-ops 管道生成的确定性种子，勿手工上传文档）",
            kb_type="public",
            vector_store_scope="shared",
        )
        kb.graph_enabled = True
        await session.commit()
        print("created knowledge base:", binding, "->", kb.id)
        return str(kb.id), str(kb.name), True


async def _merge_station_seed(entity_dicts: list[dict], relation_dicts: list[dict]) -> dict:
    """并入运行时站点台账（dim_station）；目录不可用时跳过站点，保留数据语义种子。"""
    import structlog

    try:
        from station_seed import build_station_seed
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from station_seed import build_station_seed

    logger = structlog.get_logger()
    try:
        station_entities, station_relations, stats = await build_station_seed()
    except Exception as exc:  # noqa: BLE001 — 站点台账不可用不阻断数据语义种子
        logger.warning("graph_seed_station_unavailable", error=str(exc))
        return {"skipped": True, "error": str(exc)}
    entity_dicts.extend(station_entities)
    relation_dicts.extend(station_relations)
    return stats


async def main_async(ensure_kb: bool) -> int:
    seed = json.loads(io.open(SEED_PATH, encoding="utf-8").read())
    markdown = io.open(DOC_PATH, encoding="utf-8").read()
    filename = seed["document_filename"]

    entity_dicts = list(seed["entities"])
    relation_dicts = list(seed["relations"])
    station_stats = await _merge_station_seed(entity_dicts, relation_dicts)

    kb_id, kb_name, created = await _resolve_or_create_kb(ensure_kb)

    from app.db.database import async_session
    from app.knowledge_base.service import KnowledgeBaseService

    doc_dir = get_data_registry() / "guangdong_data_semantics"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / filename
    doc_path.write_text(markdown, encoding="utf-8")

    async with async_session() as db:
        service = KnowledgeBaseService(db=db)
        existing = [
            doc
            for doc in await service.list_documents(kb_id)
            if str(getattr(doc, "filename", "")) == filename
        ]
        for doc in existing:
            await service.delete_document(kb_id, str(doc.id), user_id="system", is_admin=True)
        doc = await service.upload_document(
            kb_id,
            file_path=str(doc_path),
            filename=filename,
            user_id="system",
            is_admin=True,
            metadata={"source": "guangdong_data_semantics", "generated_by": "graph_seed_sync"},
            chunking_strategy="sentence",
        )
        document_id = str(getattr(doc, "id", "") or "")
    print(f"uploaded document: {filename} ({document_id}), replaced {len(existing)} previous")

    from app.knowledge_base.graph_build_service import GraphBuildService
    from app.knowledge_base.graph_seed_service import seed_graph_extraction
    from app.knowledge_base.graph_schemas import ExtractedEntity, ExtractedRelation

    async with async_session() as db:
        await GraphBuildService(async_session).reset_graph(kb_id)
    print("graph reset done")

    entities = [ExtractedEntity(**item) for item in entity_dicts]
    relations = [ExtractedRelation(**item) for item in relation_dicts]
    async with async_session() as db:
        result = await seed_graph_extraction(
            db,
            kb_id,
            document_id,
            entities,
            relations,
            prompt_version=seed["prompt_version"],
            extractor_name=seed["extractor_name"],
            anchor_chunk_marker=seed["anchor_marker"],
        )
    print(
        f"seeded graph: entities={result.entity_count} relations={result.relation_count} "
        f"stations={station_stats} kb={kb_name}({kb_id})"
    )
    return 0


def main() -> int:
    return asyncio.run(main_async("--ensure-kb" in sys.argv))


if __name__ == "__main__":
    sys.exit(main())
