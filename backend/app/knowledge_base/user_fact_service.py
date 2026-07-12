"""Parse and persist user-asserted business facts as trusted graph facts."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.entity_linker import EntityLinkDecision
from app.knowledge_base.graph_models import KnowledgeGraphEntity, KnowledgeGraphRelation
from app.knowledge_base.graph_repository import KnowledgeGraphRepository
from app.knowledge_base.index_outbox import KnowledgeIndexOutboxRepository
from app.knowledge_base.ingestion_service import KnowledgeIngestionService
from app.knowledge_base.models import KnowledgeBase
from app.knowledge_base.scene_models import KnowledgeUserFact
from app.knowledge_base.scene_schemas import UserFactDraft


class FactResolutionRequired(ValueError):
    def __init__(self, decisions: list[dict]):
        super().__init__("entity_resolution_required")
        self.decisions = decisions


class ProjectFactParser:
    def __init__(self, llm):
        self.llm = llm

    async def parse(self, raw_text: str, schema: dict) -> dict:
        prompt = f"""请把用户明确声明的业务事实解析成一个主体—关系—客体，只返回 JSON。
subject 和 object 包含 local_id、entity_type、name；同时返回 relation_type、statement。
只能使用当前 Schema 中的实体和关系类型；不能补充用户没有声明的事实。
Schema：{json.dumps(schema, ensure_ascii=False)}
用户事实：{raw_text}
"""
        return await self.llm.call_llm_with_json_response(prompt, max_retries=2)


class UserFactService:
    def __init__(self, session: AsyncSession, *, parser, linker):
        self.session = session
        self.parser = parser
        self.linker = linker

    async def parse_fact(
        self,
        kb_id: str,
        raw_text: str,
        *,
        created_by: str,
    ) -> KnowledgeUserFact:
        kb = await self.session.get(KnowledgeBase, kb_id)
        if kb is None:
            raise ValueError(f"Knowledge base not found: {kb_id}")
        if kb.scene_status != "ready":
            raise ValueError("scene_confirmation_required")
        draft = UserFactDraft.model_validate(await self.parser.parse(raw_text, kb.graph_schema or {}))
        self._validate_triplet(draft, kb.graph_schema or {})
        decisions = []
        for entity in (draft.subject, draft.object):
            decision = await self.linker.link(
                kb_id=kb_id,
                entity_type=entity.entity_type,
                name=entity.name,
            )
            decisions.append({"local_id": entity.local_id, **decision.model_dump(mode="json")})
        fact = KnowledgeUserFact(
            kb_id=kb_id,
            raw_text=raw_text.strip(),
            structured_fact=draft.model_dump(mode="json"),
            entity_link_decisions=decisions,
            review_status="draft",
            source_type="user_asserted",
            created_by=created_by,
        )
        self.session.add(fact)
        await self.session.commit()
        await self.session.refresh(fact)
        return fact

    async def confirm_fact(
        self,
        fact_id: str,
        *,
        resolutions: dict[str, str],
    ) -> KnowledgeUserFact:
        fact = await self.session.scalar(
            select(KnowledgeUserFact)
            .where(KnowledgeUserFact.id == fact_id)
            .with_for_update()
        )
        if fact is None:
            raise ValueError(f"User fact not found: {fact_id}")
        if fact.review_status != "draft":
            raise ValueError("user_fact_not_draft")
        kb = await self.session.get(KnowledgeBase, fact.kb_id)
        draft = UserFactDraft.model_validate(fact.structured_fact)
        decision_by_local = {
            item["local_id"]: EntityLinkDecision.model_validate(
                {key: value for key, value in item.items() if key != "local_id"}
            )
            for item in (fact.entity_link_decisions or [])
        }
        unresolved = [
            {"local_id": local_id, **decision.model_dump(mode="json")}
            for local_id, decision in decision_by_local.items()
            if decision.action == "ambiguous" and local_id not in resolutions
        ]
        if unresolved:
            raise FactResolutionRequired(unresolved)

        subject = await self._resolve_entity(draft.subject, decision_by_local[draft.subject.local_id], resolutions, kb)
        target = await self._resolve_entity(draft.object, decision_by_local[draft.object.local_id], resolutions, kb)
        relation = await self.session.scalar(
            select(KnowledgeGraphRelation).where(
                KnowledgeGraphRelation.kb_id == fact.kb_id,
                KnowledgeGraphRelation.source_entity_id == subject.id,
                KnowledgeGraphRelation.relation_type == draft.relation_type,
                KnowledgeGraphRelation.target_entity_id == target.id,
            )
        )
        if relation is None:
            relation = KnowledgeGraphRelation(
                kb_id=fact.kb_id,
                source_entity_id=subject.id,
                target_entity_id=target.id,
                relation_type=draft.relation_type,
            )
            self.session.add(relation)
            await self.session.flush()
        relation.description = draft.statement
        relation.review_status = "confirmed"
        relation.source_type = "user_asserted"
        relation.created_by = fact.created_by
        relation.locked_by_user = True
        relation.scene_profile_version = kb.scene_profile_version
        relation.schema_version = kb.schema_version
        relation.rule_version = kb.rule_version
        fact.review_status = "confirmed"
        fact.structured_fact = {**draft.model_dump(mode="json"), "relation_id": relation.id}

        outbox = KnowledgeIndexOutboxRepository.for_session(self.session)
        for entity in (subject, target):
            await outbox.enqueue_upsert(
                fact.kb_id,
                "entity",
                entity.id,
                await outbox.next_payload_version(fact.kb_id, "entity", entity.id),
                KnowledgeIngestionService._entity_payload(entity),
            )
        await outbox.enqueue_upsert(
            fact.kb_id,
            "relation",
            relation.id,
            await outbox.next_payload_version(fact.kb_id, "relation", relation.id),
            KnowledgeIngestionService._relation_payload(relation, subject, target),
        )
        await self.session.commit()
        await self.session.refresh(fact)
        return fact

    async def list_facts(self, kb_id: str) -> list[KnowledgeUserFact]:
        return list(
            (
                await self.session.scalars(
                    select(KnowledgeUserFact)
                    .where(KnowledgeUserFact.kb_id == kb_id)
                    .order_by(KnowledgeUserFact.created_at)
                )
            ).all()
        )

    async def _resolve_entity(self, draft_entity, decision, resolutions, kb):
        entity_id = resolutions.get(draft_entity.local_id)
        if entity_id or decision.action == "link":
            entity = await self.session.get(KnowledgeGraphEntity, entity_id or decision.entity_id)
            if entity is None or entity.kb_id != kb.id:
                raise ValueError("resolved_entity_not_found")
            return entity
        entity = KnowledgeGraphEntity(
            kb_id=kb.id,
            entity_type=draft_entity.entity_type,
            name=draft_entity.name,
            normalized_name=KnowledgeGraphRepository.normalize_entity_name(draft_entity.name),
            canonical_name=draft_entity.name,
            review_status="confirmed",
            source_type="user_asserted",
            created_by="user",
            locked_by_user=True,
            scene_profile_version=kb.scene_profile_version,
            schema_version=kb.schema_version,
            rule_version=kb.rule_version,
        )
        self.session.add(entity)
        await self.session.flush()
        return entity

    @staticmethod
    def _validate_triplet(draft: UserFactDraft, schema: dict) -> None:
        allowed = {tuple(item) for item in schema.get("allowed_relation_triplets") or []}
        triplet = (draft.subject.entity_type, draft.relation_type, draft.object.entity_type)
        if triplet not in allowed:
            raise ValueError("user_fact_violates_scene_schema")
