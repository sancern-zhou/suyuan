#!/usr/bin/env python3
"""Migrate legacy cognitive-map JSON into knowledge-base graph facts."""

from __future__ import annotations

import argparse
import asyncio
import json
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select

from app.knowledge_base.graph_models import (
    KnowledgeChunk,
    KnowledgeGraphEntity,
    KnowledgeGraphEntityMention,
    KnowledgeGraphRelation,
    KnowledgeGraphRelationMention,
)
from app.knowledge_base.graph_repository import KnowledgeGraphRepository
from app.knowledge_base.index_outbox import KnowledgeIndexOutboxRepository
from app.knowledge_base.ingestion_service import KnowledgeIngestionService
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase, KnowledgeBaseType


def _id(kind: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, ":".join(("suyuan", "migration", kind, *parts))))


class CognitiveMapMigrator:
    def __init__(self, session_factory, source_root: Path, map_to_kb: dict[str, str] | None = None):
        self.session_factory = session_factory
        self.source_root = Path(source_root)
        self.map_to_kb = dict(map_to_kb or {})

    def _maps(self) -> list[Path]:
        if not self.source_root.exists():
            return []
        return sorted(path for path in self.source_root.iterdir() if (path / "map.json").exists())

    async def migrate(self, *, apply: bool) -> list[dict]:
        bindings_path = self.source_root / "agent_bindings.json"
        bindings = json.loads(bindings_path.read_text()) if bindings_path.exists() else []
        enabled_maps = {item.get("map_id") for item in bindings if item.get("enabled", True)}
        reports = []
        for map_dir in self._maps():
            meta = json.loads((map_dir / "map.json").read_text())
            map_id = str(meta.get("id") or map_dir.name)
            schema_path = map_dir / "schema.json"
            extraction_path = map_dir / "extraction.json"
            schema = json.loads(schema_path.read_text()) if schema_path.exists() else {}
            extraction = json.loads(extraction_path.read_text()) if extraction_path.exists() else {}
            files_path = map_dir / "files.json"
            files = json.loads(files_path.read_text()) if files_path.exists() else []
            source_entity_ids = {
                str(item.get("entity_id") or item.get("id"))
                for item in extraction.get("candidate_entities") or []
            }
            relation_identities = {
                (
                    str(item.get("source_entity_id")),
                    KnowledgeGraphRepository.normalize_relation_type(
                        str(item.get("relation_type") or "related_to")
                    ),
                    str(item.get("target_entity_id")),
                )
                for item in extraction.get("candidate_relations") or []
                if str(item.get("source_entity_id")) in source_entity_ids
                and str(item.get("target_entity_id")) in source_entity_ids
            }
            relation_identity_by_source = {
                str(item.get("relation_id") or item.get("id")): (
                    str(item.get("source_entity_id")),
                    KnowledgeGraphRepository.normalize_relation_type(
                        str(item.get("relation_type") or "related_to")
                    ),
                    str(item.get("target_entity_id")),
                )
                for item in extraction.get("candidate_relations") or []
            }
            entity_mentions = set()
            relation_mentions = set()
            evidence_items = extraction.get("evidence") or []
            for evidence in evidence_items:
                evidence_id = str(evidence.get("evidence_id") or evidence.get("id"))
                supported_entities = set(evidence.get("supported_entity_ids") or [])
                supported_relations = set(evidence.get("supported_relation_ids") or [])
                supported_entities.update(
                    str(item.get("entity_id") or item.get("id"))
                    for item in extraction.get("candidate_entities") or []
                    if evidence_id in (item.get("source_evidence_ids") or [])
                )
                supported_relations.update(
                    str(item.get("relation_id") or item.get("id"))
                    for item in extraction.get("candidate_relations") or []
                    if evidence_id in (item.get("source_evidence_ids") or [])
                )
                entity_mentions.update(
                    (evidence_id, str(source_id))
                    for source_id in supported_entities
                    if str(source_id) in source_entity_ids
                )
                relation_mentions.update(
                    (evidence_id, relation_identity_by_source[str(source_id)])
                    for source_id in supported_relations
                    if str(source_id) in relation_identity_by_source
                )
            document_sources = {str(item.get("file_id") or item.get("id")) for item in files} | {
                str(item.get("source_file_id") or "migration") for item in evidence_items
            }
            report = {
                "map_id": map_id,
                "kb_id": self.map_to_kb.get(map_id) or _id("kb", map_id),
                "entities": len(extraction.get("candidate_entities") or []),
                "relations": len(relation_identities),
                "documents": len(document_sources),
                "entity_mentions": len(entity_mentions),
                "relation_mentions": len(relation_mentions),
                "schema": schema,
                "mode": "apply" if apply else "dry-run",
            }
            if apply:
                await self._apply_map(
                    meta, map_id, schema, extraction, files, map_id in enabled_maps
                )
            reports.append(report)
        return reports

    async def _apply_map(self, meta, map_id, schema, extraction, files, is_default):
        kb_id = self.map_to_kb.get(map_id) or _id("kb", map_id)
        async with self.session_factory() as session, session.begin():
            kb = await session.get(KnowledgeBase, kb_id)
            if kb is None:
                kb = KnowledgeBase(
                    id=kb_id,
                    name=str(meta.get("name") or f"Migrated {map_id}"),
                    description=str(meta.get("description") or ""),
                    kb_type=KnowledgeBaseType.PRIVATE,
                    qdrant_collection=f"kb_{kb_id.replace('-', '_')}",
                )
                session.add(kb)
            kb.graph_schema = schema
            kb.graph_enabled = True
            if is_default:
                kb.is_default = True

            files_by_id = {str(item.get("file_id") or item.get("id")): item for item in files}
            for source_file_id, file_data in files_by_id.items():
                document_id = _id("document", map_id, source_file_id)
                if await session.get(Document, document_id) is None:
                    session.add(
                        Document(
                            id=document_id,
                            knowledge_base_id=kb_id,
                            filename=str(file_data.get("filename") or f"{source_file_id}.txt"),
                            file_path=file_data.get("storage_path"),
                            file_type=str(file_data.get("content_type") or "migration"),
                            status=DocumentStatus.COMPLETED,
                            ingestion_status="completed",
                            graph_status="completed",
                        )
                    )
            evidence_by_id = {
                str(item.get("evidence_id") or item.get("id")): item
                for item in extraction.get("evidence") or []
            }
            chunk_by_evidence = {}
            for evidence_id, raw in evidence_by_id.items():
                source_file_id = str(raw.get("source_file_id") or "migration")
                document_id = _id("document", map_id, source_file_id)
                document = await session.get(Document, document_id)
                file_data = files_by_id.get(source_file_id, {})
                if document is None:
                    document = Document(
                        id=document_id,
                        knowledge_base_id=kb_id,
                        filename=str(file_data.get("filename") or f"{source_file_id}.txt"),
                        file_path=file_data.get("storage_path"),
                        file_type=str(file_data.get("content_type") or "migration"),
                        status=DocumentStatus.COMPLETED,
                        ingestion_status="completed",
                        graph_status="completed",
                    )
                    session.add(document)
                legacy_chunk_id = str(raw.get("chunk_id") or evidence_id)
                chunk_id = _id("chunk", map_id, legacy_chunk_id)
                chunk = await session.get(KnowledgeChunk, chunk_id)
                text_span = str(
                    raw.get("text_span") or raw.get("quote") or raw.get("normalized_summary") or ""
                )
                if chunk is None:
                    content_hash = sha256(" ".join(text_span.split()).encode()).hexdigest()
                    chunk = KnowledgeChunk(
                        id=chunk_id,
                        kb_id=kb_id,
                        document_id=document_id,
                        content_generation=1,
                        chunk_key=f"{content_hash}:0",
                        content_hash=content_hash,
                        chunk_index=len(chunk_by_evidence),
                        content=text_span,
                        embedding_text=text_span,
                        context_prefix="",
                        chunk_metadata={
                            "migration_source": f"cognitive-map:{map_id}:{legacy_chunk_id}"
                        },
                        vector_status="pending",
                        graph_status="completed",
                    )
                    session.add(chunk)
                chunk_by_evidence[evidence_id] = chunk
            await session.flush()

            entity_ids = {}
            for raw in extraction.get("candidate_entities") or []:
                source_id = str(raw.get("entity_id") or raw.get("id"))
                entity_id = _id("entity", map_id, source_id)
                entity_ids[source_id] = entity_id
                entity = await session.get(KnowledgeGraphEntity, entity_id)
                attributes = {
                    **dict(raw.get("attributes") or {}),
                    "migration_source": f"cognitive-map:{map_id}:{source_id}",
                }
                status = raw.get("review_status") or "candidate"
                if status == "needs_review":
                    status = "candidate"
                if entity is None:
                    entity = KnowledgeGraphEntity(
                        id=entity_id,
                        kb_id=kb_id,
                        entity_type=str(raw.get("entity_type") or "Entity"),
                        name=str(raw.get("name") or source_id),
                        normalized_name=KnowledgeGraphRepository.normalize_entity_name(
                            str(raw.get("canonical_name") or raw.get("name") or source_id)
                        ),
                        created_by="migration",
                    )
                    session.add(entity)
                entity.canonical_name = raw.get("canonical_name")
                entity.aliases = list(raw.get("aliases") or [])
                entity.description = raw.get("description")
                entity.attributes = attributes
                entity.review_status = status
                entity.merged_into_id = (
                    _id("entity", map_id, str(raw["merged_into_id"]))
                    if raw.get("merged_into_id")
                    else None
                )
            await session.flush()

            relation_ids = {}
            status_rank = {
                "archived": 0,
                "rejected": 1,
                "candidate": 2,
                "merged": 3,
                "confirmed": 4,
                "published": 5,
            }
            for raw in extraction.get("candidate_relations") or []:
                source_id = str(raw.get("relation_id") or raw.get("id"))
                relation_id = _id("relation", map_id, source_id)
                relation = await session.get(KnowledgeGraphRelation, relation_id)
                source_entity_id = entity_ids.get(str(raw.get("source_entity_id")))
                target_entity_id = entity_ids.get(str(raw.get("target_entity_id")))
                if not source_entity_id or not target_entity_id:
                    continue
                relation_type = KnowledgeGraphRepository.normalize_relation_type(
                    str(raw.get("relation_type") or "related_to")
                )
                if relation is None:
                    relation = await session.scalar(
                        select(KnowledgeGraphRelation).where(
                            KnowledgeGraphRelation.kb_id == kb_id,
                            KnowledgeGraphRelation.source_entity_id == source_entity_id,
                            KnowledgeGraphRelation.target_entity_id == target_entity_id,
                            KnowledgeGraphRelation.relation_type == relation_type,
                        )
                    )
                if relation is None:
                    relation = KnowledgeGraphRelation(
                        id=relation_id,
                        kb_id=kb_id,
                        source_entity_id=source_entity_id,
                        target_entity_id=target_entity_id,
                        relation_type=relation_type,
                        created_by="migration",
                    )
                    session.add(relation)
                    await session.flush()
                relation_ids[source_id] = relation.id
                relation.description = raw.get("description")
                migration_source = f"cognitive-map:{map_id}:{source_id}"
                existing_sources = list((relation.attributes or {}).get("migration_sources") or [])
                relation.attributes = {
                    **(relation.attributes or {}),
                    **dict(raw.get("attributes") or {}),
                    "migration_source": (relation.attributes or {}).get("migration_source")
                    or migration_source,
                    "migration_sources": list(dict.fromkeys([*existing_sources, migration_source])),
                }
                incoming_status = raw.get("review_status") or "candidate"
                if status_rank.get(incoming_status, 0) > status_rank.get(relation.review_status, 0):
                    relation.review_status = incoming_status
            await session.flush()

            entities_by_source = {
                str(raw.get("entity_id") or raw.get("id")): raw
                for raw in extraction.get("candidate_entities") or []
            }
            relations_by_source = {
                str(raw.get("relation_id") or raw.get("id")): raw
                for raw in extraction.get("candidate_relations") or []
            }
            for evidence_id, chunk in chunk_by_evidence.items():
                evidence = evidence_by_id[evidence_id]
                supported_entities = set(evidence.get("supported_entity_ids") or [])
                supported_relations = set(evidence.get("supported_relation_ids") or [])
                supported_entities.update(
                    source_id
                    for source_id, raw in entities_by_source.items()
                    if evidence_id in (raw.get("source_evidence_ids") or [])
                )
                supported_relations.update(
                    source_id
                    for source_id, raw in relations_by_source.items()
                    if evidence_id in (raw.get("source_evidence_ids") or [])
                )
                for source_id in supported_entities:
                    entity_id = entity_ids.get(str(source_id))
                    if not entity_id:
                        continue
                    mention_id = _id("entity-mention", map_id, evidence_id, str(source_id))
                    if await session.get(KnowledgeGraphEntityMention, mention_id) is None:
                        session.add(
                            KnowledgeGraphEntityMention(
                                id=mention_id,
                                kb_id=kb_id,
                                document_id=chunk.document_id,
                                chunk_id=chunk.id,
                                entity_id=entity_id,
                                evidence_text=chunk.content,
                                extractor_name="cognitive-map-migration",
                                extraction_run_id=_id("run", map_id),
                            )
                        )
                for source_id in supported_relations:
                    relation_id = relation_ids.get(str(source_id))
                    if relation_id is None or str(source_id) not in relations_by_source:
                        continue
                    mention_id = _id("relation-mention", map_id, evidence_id, str(source_id))
                    existing_mention = await session.scalar(
                        select(KnowledgeGraphRelationMention).where(
                            KnowledgeGraphRelationMention.relation_id == relation_id,
                            KnowledgeGraphRelationMention.chunk_id == chunk.id,
                        )
                    )
                    if existing_mention is None:
                        session.add(
                            KnowledgeGraphRelationMention(
                                id=mention_id,
                                kb_id=kb_id,
                                document_id=chunk.document_id,
                                chunk_id=chunk.id,
                                relation_id=relation_id,
                                evidence_text=chunk.content,
                                extractor_name="cognitive-map-migration",
                                extraction_run_id=_id("run", map_id),
                            )
                        )

            # Mention rows are the provenance truth. Recompute denormalized counters
            # after every idempotent run so partially completed migrations also heal.
            await session.flush()
            for entity_id in entity_ids.values():
                entity = await session.get(KnowledgeGraphEntity, entity_id)
                if entity is not None:
                    entity.mention_count = int(
                        await session.scalar(
                            select(func.count())
                            .select_from(KnowledgeGraphEntityMention)
                            .where(KnowledgeGraphEntityMention.entity_id == entity_id)
                        )
                        or 0
                    )
            for relation_id in set(relation_ids.values()):
                relation = await session.get(KnowledgeGraphRelation, relation_id)
                if relation is not None:
                    relation.mention_count = int(
                        await session.scalar(
                            select(func.count())
                            .select_from(KnowledgeGraphRelationMention)
                            .where(KnowledgeGraphRelationMention.relation_id == relation_id)
                        )
                        or 0
                    )

            outbox = KnowledgeIndexOutboxRepository.for_session(session)
            for chunk in {item.id: item for item in chunk_by_evidence.values()}.values():
                await outbox.enqueue_upsert(
                    kb_id,
                    "chunk",
                    chunk.id,
                    chunk.content_generation,
                    KnowledgeIngestionService._chunk_payload(chunk),
                )
            for entity_id in set(entity_ids.values()):
                entity = await session.get(KnowledgeGraphEntity, entity_id)
                if entity is not None:
                    await outbox.enqueue_upsert(
                        kb_id,
                        "entity",
                        entity.id,
                        1,
                        KnowledgeIngestionService._entity_payload(entity),
                    )
            for relation_id in set(relation_ids.values()):
                relation = await session.get(KnowledgeGraphRelation, relation_id)
                if relation is not None:
                    source = await session.get(KnowledgeGraphEntity, relation.source_entity_id)
                    target = await session.get(KnowledgeGraphEntity, relation.target_entity_id)
                    await outbox.enqueue_upsert(
                        kb_id,
                        "relation",
                        relation.id,
                        1,
                        KnowledgeIngestionService._relation_payload(relation, source, target),
                    )

    async def verify(self) -> bool:
        expected = await self.migrate(apply=False)
        async with self.session_factory() as session:
            for item in expected:
                entity_count = await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeGraphEntity)
                    .where(KnowledgeGraphEntity.kb_id == item["kb_id"])
                )
                relation_count = await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeGraphRelation)
                    .where(KnowledgeGraphRelation.kb_id == item["kb_id"])
                )
                document_count = await session.scalar(
                    select(func.count())
                    .select_from(Document)
                    .where(Document.knowledge_base_id == item["kb_id"])
                )
                entity_mention_count = await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeGraphEntityMention)
                    .where(KnowledgeGraphEntityMention.kb_id == item["kb_id"])
                )
                relation_mention_count = await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeGraphRelationMention)
                    .where(KnowledgeGraphRelationMention.kb_id == item["kb_id"])
                )
                kb = await session.get(KnowledgeBase, item["kb_id"])
                if (
                    kb is None
                    or dict(kb.graph_schema or {}) != item["schema"]
                    or int(entity_count or 0) != item["entities"]
                    or int(relation_count or 0) != item["relations"]
                    or int(document_count or 0) != item["documents"]
                    or int(entity_mention_count or 0) != item["entity_mentions"]
                    or int(relation_mention_count or 0) != item["relation_mentions"]
                ):
                    return False
        return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, default=Path("backend_data_registry/cognitive_maps")
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    mode.add_argument("--apply", action="store_true", help="Write knowledge-base graph facts")
    mode.add_argument("--verify", action="store_true", help="Verify migrated counts")
    parser.add_argument("--map-to-kb", action="append", default=[], metavar="MAP_ID=KB_ID")
    return parser


async def _run(args) -> int:
    from app.db.database import async_session

    mappings = dict(item.split("=", 1) for item in args.map_to_kb)
    migrator = CognitiveMapMigrator(async_session, args.source_root, mappings)
    if args.verify:
        return 0 if await migrator.verify() else 1
    for report in await migrator.migrate(apply=args.apply):
        print(json.dumps(report, ensure_ascii=False))
    return 0


def main() -> int:
    return asyncio.run(_run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
