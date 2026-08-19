"""Discover a business-facing scene model from representative documents."""

from __future__ import annotations

import json
from typing import Any

from app.knowledge_base.scene_schemas import SceneDraft


class SceneDiscoveryError(ValueError):
    """Raised when representative content cannot produce a useful scene draft."""


def select_representative_chunks(
    chunks: list[Any],
    *,
    max_chunks: int = 6,
    max_chars: int = 12_000,
) -> list[Any]:
    ordered = sorted(
        (chunk for chunk in chunks if str(getattr(chunk, "content", "")).strip()),
        key=lambda item: (int(getattr(item, "chunk_index", 0)), str(getattr(item, "id", ""))),
    )
    if not ordered or max_chunks <= 0 or max_chars <= 0:
        return []

    candidate_indexes = [0]
    section_seen: set[tuple[str, ...]] = set()
    for index, chunk in enumerate(ordered):
        path = tuple(getattr(chunk, "section_path", None) or ())
        if path and path not in section_seen:
            candidate_indexes.append(index)
            section_seen.add(path)
    if len(ordered) > 1:
        for offset in range(1, min(4, len(ordered))):
            candidate_indexes.append(round(offset * (len(ordered) - 1) / min(3, len(ordered) - 1)))
    candidate_indexes.extend(range(len(ordered)))

    selected: list[Any] = []
    selected_ids: set[str] = set()
    used_chars = 0
    for index in candidate_indexes:
        chunk = ordered[index]
        chunk_id = str(getattr(chunk, "id", index))
        if chunk_id in selected_ids:
            continue
        content_length = len(str(chunk.content))
        if selected and used_chars + content_length > max_chars:
            continue
        if not selected and content_length > max_chars:
            selected.append(chunk)
            break
        selected.append(chunk)
        selected_ids.add(chunk_id)
        used_chars += content_length
        if len(selected) >= max_chunks:
            break
    return selected


class SceneDiscoveryService:
    def __init__(self, *, llm, chunk_repository):
        self.llm = llm
        self.chunk_repository = chunk_repository

    async def discover(
        self,
        *,
        kb_id: str,
        scene_goal: str,
        desired_questions: list[str],
        documents: list[Any],
    ) -> SceneDraft:
        source_document_ids = [str(document.id) for document in documents]
        samples: list[str] = []
        total_chars = 0
        for document in documents:
            chunks = await self.chunk_repository.list_by_document(document.id)
            chosen = select_representative_chunks(chunks)
            rendered = self._render_document(document, chosen)
            if total_chars + len(rendered) > 36_000:
                rendered = rendered[: max(0, 36_000 - total_chars)]
            if rendered:
                samples.append(rendered)
                total_chars += len(rendered)
            if total_chars >= 36_000:
                break

        prompt = self._build_prompt(scene_goal, desired_questions, samples)
        payload = await self._call_json(prompt)
        if not payload.get("business_objects") or not payload.get("business_logic"):
            raise SceneDiscoveryError(
                json.dumps(payload.get("diagnostics") or {}, ensure_ascii=False)
            )
        return SceneDraft.model_validate(
            {
                **payload,
                "scene_goal": scene_goal,
                "desired_questions": desired_questions,
                "source_document_ids": source_document_ids,
            }
        )

    async def _call_json(self, prompt: str) -> dict[str, Any]:
        if hasattr(self.llm, "call_llm_with_json_response"):
            return await self.llm.call_llm_with_json_response(prompt, max_retries=2)
        raise SceneDiscoveryError("scene discovery LLM does not support JSON responses")

    @staticmethod
    def _render_document(document: Any, chunks: list[Any]) -> str:
        lines = [f"代表性文档：{getattr(document, 'filename', document.id)}"]
        for chunk in chunks:
            section = "/".join(getattr(chunk, "section_path", None) or [])
            label = f"章节：{section}" if section else f"Chunk {chunk.chunk_index}"
            lines.append(f"[{label}]\n{chunk.content}")
        return "\n\n".join(lines)

    @staticmethod
    def _build_prompt(
        scene_goal: str,
        desired_questions: list[str],
        samples: list[str],
    ) -> str:
        questions = "\n".join(f"- {item}" for item in desired_questions) or "- 未提供"
        documents = "\n\n".join(samples)
        return f"""你是业务知识建模助手。用户不需要理解知识图谱 Schema。
根据场景目标、希望回答的问题和代表性文档，识别：
1. 对 Agent 推理有稳定意义的业务对象；
2. 用户能够理解和确认的业务逻辑；
3. 同义词和缩写；
4. 应忽略的版式或背景信息；
5. 样本文档覆盖不足或存在歧义的部分。
不要把具体实例误当成对象类型。中文业务含义放在 name、statement、description、aliases 中，
不要把内部技术标识直接当作面向用户的展示文本。
只返回 JSON，字段为 business_objects、business_logic、ignored_content、diagnostics。
business_objects 每项包含 key、name、description、aliases。
business_logic 每项包含 key、statement、source_key、relation_key、target_key、policy；policy 只能是 required、allowed、forbidden。
key、source_key、target_key、relation_key 是仅供系统内部引用的技术标识，必须满足以下规则：
1. 只能使用 ASCII 小写英文字母、数字和下划线（snake_case），且必须以小写英文字母开头；
2. business_objects.key 应使用稳定的英文类型标识，例如 monitoring_station、monitoring_device；
3. business_logic.key 和 relation_key 应使用稳定的英文关系标识，例如 station_contains_device、contains；
4. source_key、target_key 必须精确引用某个 business_objects.key，禁止填写中文名称或未定义标识。
diagnostics 必须是 JSON 对象，不能是数组；建议包含 coverage、uncertainties 等字段。
例如：
{{
  "business_objects": [
    {{"key": "monitoring_station", "name": "监测站房", "description": "环境空气监测站房", "aliases": ["站房"]}},
    {{"key": "monitoring_device", "name": "监测设备", "description": "站房内的监测仪器", "aliases": ["仪器"]}}
  ],
  "business_logic": [
    {{"key": "station_contains_device", "statement": "监测站房包含监测设备", "source_key": "monitoring_station", "relation_key": "contains", "target_key": "monitoring_device", "policy": "allowed"}}
  ],
  "ignored_content": ["页眉页脚"],
  "diagnostics": {{"coverage": "partial", "uncertainties": []}}
}}

场景目标：
{scene_goal}

希望回答的问题：
{questions}

代表性文档：
{documents}
"""
