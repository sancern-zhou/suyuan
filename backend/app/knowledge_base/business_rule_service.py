"""Parse and manage confirmed natural-language business rules."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.models import KnowledgeBase
from app.knowledge_base.scene_models import KnowledgeBusinessRule
from app.knowledge_base.scene_schemas import StructuredBusinessRule


class BusinessRuleService:
    def __init__(self, session: AsyncSession, *, llm):
        self.session = session
        self.llm = llm

    async def parse_rule(
        self,
        kb_id: str,
        raw_text: str,
        *,
        created_by: str,
    ) -> KnowledgeBusinessRule:
        kb = await self.session.get(KnowledgeBase, kb_id)
        if kb is None:
            raise ValueError(f"Knowledge base not found: {kb_id}")
        if kb.scene_status != "ready":
            raise ValueError("scene_confirmation_required")
        prompt = self._prompt(raw_text, kb.graph_schema or {})
        payload = await self.llm.call_llm_with_json_response(prompt, max_retries=2)
        structured = StructuredBusinessRule.model_validate(payload)
        rule = KnowledgeBusinessRule(
            kb_id=kb_id,
            raw_text=raw_text.strip(),
            structured_rule=structured.model_dump(mode="json"),
            status="draft",
            version=0,
            created_by=created_by,
        )
        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def confirm_rule(
        self,
        rule_id: str,
        *,
        expected_version: int,
    ) -> KnowledgeBusinessRule:
        rule = await self.session.scalar(
            select(KnowledgeBusinessRule)
            .where(KnowledgeBusinessRule.id == rule_id)
            .with_for_update()
        )
        if rule is None:
            raise ValueError(f"Business rule not found: {rule_id}")
        if rule.status != "draft":
            raise ValueError("business_rule_not_draft")
        kb = await self.session.scalar(
            select(KnowledgeBase)
            .where(KnowledgeBase.id == rule.kb_id)
            .with_for_update()
        )
        next_version = int(kb.rule_version or 0) + 1
        if expected_version != next_version:
            raise ValueError("stale_rule_version")
        kb.rule_version = next_version
        rule.version = next_version
        rule.status = "confirmed"
        rule.confirmed_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def archive_rule(self, rule_id: str) -> KnowledgeBusinessRule:
        rule = await self.session.get(KnowledgeBusinessRule, rule_id)
        if rule is None:
            raise ValueError(f"Business rule not found: {rule_id}")
        rule.status = "archived"
        await self.session.commit()
        return rule

    async def list_rules(
        self,
        kb_id: str,
        *,
        include_archived: bool = False,
    ) -> list[KnowledgeBusinessRule]:
        query = select(KnowledgeBusinessRule).where(KnowledgeBusinessRule.kb_id == kb_id)
        if not include_archived:
            query = query.where(KnowledgeBusinessRule.status != "archived")
        return list((await self.session.scalars(query.order_by(KnowledgeBusinessRule.created_at))).all())

    async def active_rule_context(self, kb_id: str) -> list[dict]:
        rows = await self.session.scalars(
            select(KnowledgeBusinessRule)
            .where(
                KnowledgeBusinessRule.kb_id == kb_id,
                KnowledgeBusinessRule.status == "confirmed",
            )
            .order_by(KnowledgeBusinessRule.version)
        )
        return [dict(item.structured_rule or {}) for item in rows]

    @staticmethod
    def _prompt(raw_text: str, schema: dict) -> str:
        return f"""你是业务规则解析器。只解释规则，不从规则臆造具体企业、站点、设备或事件事实。
请返回 JSON：kind、summary、applies_to、conditions、required_logic、forbidden_logic。
kind 只能是 relationship_constraint、conditional_constraint、normalization、exclusion。
当前场景 Schema：{json.dumps(schema, ensure_ascii=False)}
用户规则：{raw_text}
"""
