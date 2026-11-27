"""
站点目录知识库同步（许昌专属）

将站点目录渲染为 markdown 文档并上传到项目知识库，由知识库摄入管线
自动完成分块、向量化和图谱抽取，使 knowledge_graph_query 可以回答
“尚集镇属于哪个区”“襄城县有哪些乡镇站”等归属问题。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import or_, select

from app.knowledge_base.graph_schemas import ExtractedEntity, ExtractedRelation
from app.tools.xuchang.station_catalog.catalog import (
    CITY_CODE,
    CITY_NAME,
    StationCatalogError,
    load_catalog,
)

logger = structlog.get_logger()

DOCUMENT_FILENAME = "许昌市空气监测站点目录.md"

KB_BINDING_KEY = "station_directory"

PROMPT_VERSION = "xuchang_station_catalog_deterministic"

ANCHOR_MARKER = "## 站点归属关系"


def render_station_directory(catalog: dict[str, Any]) -> str:
    """将目录渲染为确定性 markdown 文档"""
    generated_at = datetime.fromtimestamp(
        float(catalog.get("generated_at") or 0)
    ).strftime("%Y-%m-%d %H:%M")

    lines: list[str] = [
        "# 许昌市空气监测站点目录",
        "",
        f"- 数据来源：大气环境监测数据接口中台（乡镇站视图 {catalog.get('_township_source', 'v_t_d_src')}）",
        f"- 更新时间：{generated_at}",
        f"- 城市编码：{CITY_CODE}",
        "",
        "站点编码说明：乡镇站编码为中台自定义编码（如 1107B），不是国标行政区划码；"
        "乡镇站归属区县记录在站点名称前缀中。",
        "",
    ]

    hidden_count = int(catalog.get("hidden_station_count") or 0)
    if hidden_count:
        lines.append(
            f"> 注：中台另有 {hidden_count} 个已登记但长期无数据上报的街道站，"
            "暂未列入本目录；待恢复数据上报后自动纳入。"
        )
        lines.append("")

    districts = catalog.get("districts") or []
    lines.append(f"## 区县（{len(districts)}）")
    lines.append("")
    lines.append("| 区县 | 行政区划编码 |")
    lines.append("| --- | --- |")
    for item in districts:
        lines.append(f"| {item['name']} | {item['areacode']} |")
    lines.append("")

    townships = catalog.get("townships") or []
    lines.append(f"## 乡镇站（{len(townships)}）")
    lines.append("")
    lines.append("| 站点名称 | 站点编码 | 归属区县 | 所属城市 | 经度 | 纬度 |")
    lines.append("| --- | --- | --- | --- | ---: | ---: |")
    for item in townships:
        lines.append(
            f"| {item['station_name']} | {item['station_code']} "
            f"| {item['district'] or '未知'} | {item['city']} "
            f"| {item.get('longitude') if item.get('longitude') is not None else ''} "
            f"| {item.get('latitude') if item.get('latitude') is not None else ''} |"
        )
    lines.append("")

    regular = catalog.get("regular_stations") or []
    lines.append(f"## 国控站（{len(regular)}）")
    lines.append("")
    lines.append("| 站点名称 | 站点编码 | 唯一编码 | 类型 | 归属区县 | 地址 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in regular:
        lines.append(
            f"| {item['station_name']} | {item['station_code']} "
            f"| {item.get('unique_code') or ''} | {item.get('type_name') or ''} "
            f"| {item.get('district') or ''} | {item.get('address') or ''} |"
        )
    lines.append("")

    relations: list[str] = []
    for item in townships:
        if item.get("district"):
            relations.append(
                f"- {item['station_name']}（{item['station_code']}）隶属于{item['district']}，"
                f"{item['district']}隶属于{CITY_NAME}。"
            )
    for item in regular:
        if item.get("district"):
            relations.append(
                f"- {item['station_name']}（{item['station_code']}）隶属于{item['district']}，"
                f"{item['district']}隶属于{CITY_NAME}。"
            )
    lines.append("## 站点归属关系")
    lines.append("")
    lines.extend(relations)
    lines.append("")
    return "\n".join(lines)


async def _resolve_target_kb() -> dict[str, Any]:
    """解析站点目录目标知识库：优先 station_directory 绑定，其次项目 collections"""
    from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

    from app.db.knowledge_database import knowledge_async_session as async_session
    from app.knowledge_base.models import KnowledgeBase, KnowledgeBaseStatus
    from app.project_config.loader import load_project_context
    from config.settings import settings

    binding: str | None = None
    collections: list[str] = []
    try:
        knowledge = load_project_context(settings.project_id).manifest.knowledge
        binding = knowledge.bindings.get(KB_BINDING_KEY)
        collections = [str(item) for item in (knowledge.collections or [])]
    except Exception as exc:
        logger.warning("xuchang_station_kb_resolve_manifest_failed", error=str(exc))

    candidates = [str(binding)] if binding else []
    candidates.extend(collections)

    async with async_session() as session:
        for target in candidates:
            if not target:
                continue
            row = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE,
                        or_(
                            KnowledgeBase.id == target,
                            KnowledgeBase.name == target,
                        ),
                    )
                )
            ).scalars().first()
            if row is not None:
                return {"kb_id": str(row.id), "kb_name": str(row.name)}

    raise StationCatalogError(
        "未找到站点目录目标知识库：请在项目 knowledge.bindings 配置 station_directory，"
        "或确保存在与知识库集合同名的知识库"
    )


def _build_catalog_extraction(
    catalog: dict[str, Any],
) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
    """按目录构建站点实体与 located_in 关系。

    LLM 对大表格的抽取是有损的（76 个乡镇站只能抽出少数），
    站点目录是结构化数据，直接构建实体和关系，由种子服务写入并置为 confirmed。
    """
    townships = catalog.get("townships") or []
    regular = catalog.get("regular_stations") or []
    districts = catalog.get("districts") or []

    entities: list[ExtractedEntity] = [
        ExtractedEntity(
            local_id="district_city",
            entity_type="Region",
            name=CITY_NAME,
            aliases=[CITY_CODE],
            description="许昌市（地级市）",
            attributes={"areacode": CITY_CODE},
            evidence_text=f"{CITY_NAME}（{CITY_CODE}）",
        )
    ]
    relations: list[ExtractedRelation] = []

    for item in districts:
        district = item["name"]
        entities.append(
            ExtractedEntity(
                local_id=f"district_{district}",
                entity_type="Region",
                name=district,
                aliases=[item["areacode"]],
                description="许昌市区县",
                attributes={"areacode": item["areacode"], "city": CITY_NAME},
                evidence_text=f"{district}（{item['areacode']}）",
            )
        )
        relations.append(
            ExtractedRelation(
                source_local_id=f"district_{district}",
                target_local_id="district_city",
                relation_type="located_in",
                description=f"{district} 隶属于 {CITY_NAME}",
                evidence_text=f"{district} 隶属于 {CITY_NAME}",
            )
        )

    def _ensure_district_entity(district: str) -> None:
        if not district:
            return
        if any(e.local_id == f"district_{district}" for e in entities):
            return
        entities.append(
            ExtractedEntity(
                local_id=f"district_{district}",
                entity_type="Region",
                name=district,
                description="许昌市功能区（中台区域表未登记，归属以站点名称前缀为准）",
                attributes={"city": CITY_NAME, "source": "station_name_prefix"},
                evidence_text=district,
            )
        )

    for item in townships:
        name = item["station_name"]
        district = item.get("district") or ""
        entities.append(
            ExtractedEntity(
                local_id=f"station_{item['station_code']}",
                entity_type="Station",
                name=name,
                aliases=[item["station_code"]],
                description=f"许昌市乡镇空气监测站，归属{district or '未知'}",
                attributes={
                    "station_code": item["station_code"],
                    "station_type": "township",
                    "district": district,
                    "city": CITY_NAME,
                },
                evidence_text=f"{name}（{item['station_code']}）",
            )
        )
        if district:
            _ensure_district_entity(district)
            relations.append(
                ExtractedRelation(
                    source_local_id=f"station_{item['station_code']}",
                    target_local_id=f"district_{district}",
                    relation_type="located_in",
                    description=f"{name} 隶属于 {district}",
                    evidence_text=f"{name}（{item['station_code']}）隶属于 {district}",
                )
            )

    for item in regular:
        name = item["station_name"]
        entities.append(
            ExtractedEntity(
                local_id=f"station_{item['station_code']}",
                entity_type="Station",
                name=name,
                aliases=[
                    alias
                    for alias in (item["station_code"], item.get("unique_code") or "")
                    if alias
                ],
                description="许昌市国控空气监测站",
                attributes={
                    "station_code": item["station_code"],
                    "station_type": "regular",
                    "type_name": item.get("type_name") or "",
                    "district": item.get("district") or "",
                    "city": CITY_NAME,
                },
                evidence_text=name,
            )
        )
        if item.get("district"):
            relations.append(
                ExtractedRelation(
                    source_local_id=f"station_{item['station_code']}",
                    target_local_id=f"district_{item['district']}",
                    relation_type="located_in",
                    description=f"{name} 隶属于 {item['district']}",
                    evidence_text=f"{name} 隶属于 {item['district']}",
                )
            )
            _ensure_district_entity(item["district"])
        else:
            relations.append(
                ExtractedRelation(
                    source_local_id=f"station_{item['station_code']}",
                    target_local_id="district_city",
                    relation_type="located_in",
                    description=f"{name} 隶属于 {CITY_NAME}",
                    evidence_text=name,
                )
            )

    return entities, relations


async def _seed_graph_deterministic(
    kb_id: str,
    document_id: str,
    catalog: dict[str, Any],
) -> dict[str, int]:
    """按目录确定性写入站点实体与 located_in 关系，绕过 LLM 抽取。

    LLM 对大表格的抽取是有损的（76 个乡镇站只能抽出少数），
    站点目录是结构化数据，经共享种子服务直接写入并置为 confirmed。
    """
    from app.db.knowledge_database import knowledge_async_session as async_session
    from app.knowledge_base.graph_seed_service import GraphSeedError, seed_graph_extraction

    entities, relations = _build_catalog_extraction(catalog)

    try:
        async with async_session() as db:
            result = await seed_graph_extraction(
                db,
                kb_id,
                document_id,
                entities,
                relations,
                prompt_version=PROMPT_VERSION,
                extractor_name="xuchang_station_catalog_seeder",
                anchor_chunk_marker=ANCHOR_MARKER,
            )
    except GraphSeedError as exc:
        raise StationCatalogError(str(exc)) from exc

    return {"entities": result.entity_count, "relations": result.relation_count}


async def sync_station_knowledge_graph(
    force_catalog_refresh: bool = False,
) -> dict[str, Any]:
    """构建站点目录文档、同步知识库并确定性生成站点归属图谱"""
    catalog = await asyncio.to_thread(load_catalog, force_catalog_refresh)
    catalog["_township_source"] = "v_t_d_src"
    markdown = render_station_directory(catalog)

    target = await _resolve_target_kb()
    kb_id = target["kb_id"]

    from app.utils.path_config import get_data_registry

    doc_dir = get_data_registry() / "xuchang_station_catalog"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / DOCUMENT_FILENAME
    doc_path.write_text(markdown, encoding="utf-8")

    from app.db.knowledge_database import knowledge_async_session as async_session
    from app.knowledge_base.service import KnowledgeBaseService

    deleted_previous = False
    document_id = ""
    async with async_session() as db:
        service = KnowledgeBaseService(db=db)
        try:
            existing = [
                doc
                for doc in await service.list_documents(kb_id)
                if str(getattr(doc, "filename", "")) == DOCUMENT_FILENAME
            ]
            for doc in existing:
                await service.delete_document(kb_id, str(doc.id), user_id="system", is_admin=True)
                deleted_previous = True
        except Exception as exc:
            logger.warning(
                "xuchang_station_graph_sync_replace_failed",
                error=str(exc),
            )

        doc = await service.upload_document(
            kb_id,
            file_path=str(doc_path),
            filename=DOCUMENT_FILENAME,
            user_id="system",
            is_admin=True,
            metadata={"source": "xuchang_station_catalog", "generated_by": "station_directory_sync"},
            chunking_strategy="sentence",
        )
        document_id = str(getattr(doc, "id", "") or "")

    from app.knowledge_base.graph_build_service import GraphBuildService

    async with async_session() as db:
        await GraphBuildService(async_session).reset_graph(kb_id)
    logger.info("xuchang_station_graph_reset_done", kb_id=kb_id)

    seeded = await _seed_graph_deterministic(kb_id, document_id, catalog)

    return {
        "kb_id": kb_id,
        "kb_name": target["kb_name"],
        "document_id": document_id,
        "filename": DOCUMENT_FILENAME,
        "deleted_previous": deleted_previous,
        "township_count": len(catalog.get("townships") or []),
        "regular_count": len(catalog.get("regular_stations") or []),
        "district_count": len(catalog.get("districts") or []),
        "graph_entities": seeded["entities"],
        "graph_relations": seeded["relations"],
        "document_path": str(doc_path),
    }
