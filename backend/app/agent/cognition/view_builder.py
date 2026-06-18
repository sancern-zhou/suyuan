from __future__ import annotations

import hashlib

from app.agent.cognition.models import CognitiveMapQuery, CognitiveMapView, ExtractionResult


class CognitiveMapViewBuilder:
    """Builds the compact view that will be injected into Agent context."""

    def build_from_extraction(
        self,
        query: CognitiveMapQuery,
        extraction: ExtractionResult,
        max_entities: int = 20,
        max_relations: int = 20,
        max_evidence: int = 10,
    ) -> CognitiveMapView:
        entities = self._filter_entities(query, extraction)[:max_entities]
        entity_ids = {entity.entity_id for entity in entities}
        relations = [
            relation
            for relation in extraction.candidate_relations
            if relation.source_entity_id in entity_ids or relation.target_entity_id in entity_ids
        ][:max_relations]
        evidence_ids = {
            evidence_id
            for entity in entities
            for evidence_id in entity.source_evidence_ids
        }
        for relation in relations:
            evidence_ids.update(relation.source_evidence_ids)
        evidence = [
            item for item in extraction.evidence if item.evidence_id in evidence_ids
        ][:max_evidence]

        prompt_summary = self._render_prompt_summary(query, entities, relations, evidence)
        return CognitiveMapView(
            view_id=self._stable_id("view", query.task, extraction.map_id),
            map_id=extraction.map_id,
            task=query.task,
            agent_mode=query.agent_mode,
            agent_role=query.agent_role,
            entities=entities,
            relations=relations,
            evidence_summaries=evidence,
            limitations=["当前为 Spike 视图，仅包含候选认知地图内容，未经发布审核。"],
            prompt_summary=prompt_summary,
        )

    def _filter_entities(self, query: CognitiveMapQuery, extraction: ExtractionResult):
        if not query.entity_hints:
            return extraction.candidate_entities
        matched = [
            entity
            for entity in extraction.candidate_entities
            if any(hint in entity.name or hint in entity.aliases for hint in query.entity_hints)
        ]
        if not matched:
            return extraction.candidate_entities

        matched_ids = {entity.entity_id for entity in matched}
        related_ids = set(matched_ids)
        for relation in extraction.candidate_relations:
            if relation.source_entity_id in matched_ids:
                related_ids.add(relation.target_entity_id)
            if relation.target_entity_id in matched_ids:
                related_ids.add(relation.source_entity_id)
        return [
            entity
            for entity in extraction.candidate_entities
            if entity.entity_id in related_ids
        ]

    def _render_prompt_summary(self, query, entities, relations, evidence) -> str:
        lines = [
            "## 当前认知地图",
            "",
            f"任务目标：{query.task}",
            f"Agent 模式：{query.agent_mode}",
        ]
        if query.agent_role:
            lines.append(f"Agent 角色：{query.agent_role}")

        lines.extend(["", "相关实体："])
        lines.extend(
            f"- {entity.entity_type}: {entity.name} ({', '.join(entity.source_evidence_ids)})"
            for entity in entities
        )
        lines.extend(["", "关键关系："])
        entity_name_by_id = {entity.entity_id: entity.name for entity in entities}
        lines.extend(
            f"- {entity_name_by_id.get(relation.source_entity_id, relation.source_entity_id)} "
            f"--{relation.relation_type}--> "
            f"{entity_name_by_id.get(relation.target_entity_id, relation.target_entity_id)}"
            for relation in relations
        )
        lines.extend(["", "可引用证据："])
        lines.extend(
            f"- [{item.ref}] {item.source_file_id}:{item.location} {item.normalized_summary}"
            for item in evidence
        )
        lines.extend(
            [
                "",
                "输出约束：",
                "- 事实性结论必须引用 evidence_refs。",
                "- 无证据内容只能作为 hypothesis 或 open_question。",
            ]
        )
        return "\n".join(lines)

    def _stable_id(self, prefix: str, *parts: str) -> str:
        digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{digest}"
