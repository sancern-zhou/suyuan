"""Offline, source-grounded draft question generation from knowledge-base documents."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exam.models import ExamQuestion
from app.knowledge_base.chunk_repository import KnowledgeChunkRepository
from app.knowledge_base.models import Document
from app.services.llm_service import llm_service

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SourceBatch:
    document_id: str
    filename: str
    chunk_indices: tuple[int, ...]
    text: str


def build_source_batches(
    document_id: str,
    filename: str,
    chunks: list[dict[str, Any]],
    *,
    max_chars: int = 12_000,
) -> list[SourceBatch]:
    batches: list[SourceBatch] = []
    indices: list[int] = []
    parts: list[str] = []
    size = 0
    for chunk in chunks:
        index = int(chunk.get("chunk_index", len(indices)))
        content = str(chunk.get("content") or chunk.get("original_content") or "").strip()
        if not content:
            continue
        tagged = f"[chunk_index={index}]\n{content}"
        if parts and size + len(tagged) > max_chars:
            batches.append(SourceBatch(document_id, filename, tuple(indices), "\n\n".join(parts)))
            indices, parts, size = [], [], 0
        indices.append(index)
        parts.append(tagged)
        size += len(tagged)
    if parts:
        batches.append(SourceBatch(document_id, filename, tuple(indices), "\n\n".join(parts)))
    return batches


def validate_candidate(candidate: dict[str, Any], allowed_chunks: set[int]) -> list[str]:
    errors: list[str] = []
    question_type = candidate.get("question_type")
    if question_type not in {"single_choice", "multiple_choice", "judgment", "short_answer"}:
        errors.append("invalid_question_type")
    if not str(candidate.get("stem") or "").strip():
        errors.append("missing_stem")
    evidence = candidate.get("evidence_chunk_indices") or []
    try:
        evidence_set = {int(index) for index in evidence}
    except (TypeError, ValueError):
        evidence_set = set()
    if not evidence_set:
        errors.append("missing_evidence_chunks")
    elif not evidence_set.issubset(allowed_chunks):
        errors.append("evidence_outside_source_batch")

    options = candidate.get("options") or {}
    answer = candidate.get("correct_answer")
    if question_type in {"single_choice", "multiple_choice"}:
        if set(options) != {"A", "B", "C", "D"}:
            errors.append("choice_options_must_be_abcd")
        answers = [answer] if isinstance(answer, str) else list(answer or [])
        if not answers or any(item not in options for item in answers):
            errors.append("invalid_choice_answer")
        if question_type == "single_choice" and len(answers) != 1:
            errors.append("single_choice_requires_one_answer")
        if question_type == "multiple_choice" and len(set(answers)) < 2:
            errors.append("multiple_choice_requires_multiple_answers")
    elif question_type == "judgment" and not isinstance(answer, bool):
        errors.append("judgment_answer_must_be_boolean")
    elif question_type == "short_answer" and not candidate.get("scoring_points"):
        errors.append("short_answer_requires_scoring_points")
    return errors


class ExamBankGenerationService:
    """Generate draft questions exhaustively; never auto-publish model output."""

    def __init__(self, session: AsyncSession, *, llm=None):
        self.session = session
        self.llm = llm or llm_service

    async def generate_document(
        self,
        *,
        knowledge_base_id: str,
        document_id: str,
        user_id: str | None = None,
        max_chars_per_batch: int = 12_000,
    ) -> dict[str, Any]:
        document = await self.session.get(Document, document_id)
        if not document or document.knowledge_base_id != knowledge_base_id:
            raise ValueError("knowledge-base document not found")
        chunks = await self._load_document_chunks(document_id)
        batches = build_source_batches(
            document_id,
            document.filename,
            chunks,
            max_chars=max_chars_per_batch,
        )
        created = 0
        rejected = 0
        for batch in batches:
            result = await self._generate_batch(batch, document)
            created += result["created"]
            rejected += result["rejected"]
        return {
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
            "filename": document.filename,
            "batch_count": len(batches),
            "created_drafts": created,
            "rejected_candidates": rejected,
            "review_status": "draft",
        }

    async def _load_document_chunks(self, document_id: str) -> list[dict[str, Any]]:
        """Read canonical chunks without initializing vector or embedding services."""
        records = await KnowledgeChunkRepository(self.session).list_by_document(document_id)
        return [
            {
                "chunk_index": record.chunk_index,
                "content": record.content,
                "original_content": record.content,
            }
            for record in records
        ]

    async def _generate_batch(self, batch: SourceBatch, document: Document) -> dict[str, int]:
        generation = await self.llm.call_llm_with_json_response(self._generation_prompt(batch), max_retries=2)
        candidates = generation.get("questions") or []
        if not isinstance(candidates, list):
            candidates = []
        locally_valid: list[dict[str, Any]] = []
        rejected = 0
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                rejected += 1
                continue
            candidate.setdefault("candidate_id", f"candidate-{index + 1}")
            errors = validate_candidate(candidate, set(batch.chunk_indices))
            if errors:
                rejected += 1
                logger.warning("exam_question_candidate_rejected", errors=errors)
                continue
            locally_valid.append(candidate)
        if not locally_valid:
            return {"created": 0, "rejected": rejected}

        verification = await self.llm.call_llm_with_json_response(
            self._verification_prompt(batch, locally_valid), max_retries=2
        )
        verdicts = {
            str(item.get("candidate_id")): item
            for item in verification.get("verdicts") or []
            if isinstance(item, dict)
        }
        existing_stems = set(
            await self.session.scalars(
                select(ExamQuestion.stem).where(
                    ExamQuestion.stem.in_([str(item["stem"]).strip() for item in locally_valid])
                )
            )
        )
        created = 0
        metadata = dict(document.extra_metadata or {})
        source_version = str(
            metadata.get("effective_date") or metadata.get("version") or document.file_checksum or ""
        )
        for candidate in locally_valid:
            verdict = verdicts.get(str(candidate["candidate_id"])) or {}
            approved = all(
                verdict.get(key) is True
                for key in ("answer_supported", "unambiguous", "source_match")
            )
            if not approved or str(candidate["stem"]).strip() in existing_stems:
                rejected += 1
                continue
            evidence_indices = [int(item) for item in candidate["evidence_chunk_indices"]]
            knowledge_point = str(candidate.get("knowledge_point") or "").strip()
            knowledge_point_id = hashlib.sha256(knowledge_point.encode("utf-8")).hexdigest()[:24] if knowledge_point else None
            self.session.add(ExamQuestion(
                id=str(uuid.uuid4()),
                question_type=candidate["question_type"],
                topic=str(candidate.get("topic") or "未分类").strip(),
                knowledge_point_id=knowledge_point_id,
                stem=str(candidate["stem"]).strip(),
                options=candidate.get("options") or {},
                correct_answer=candidate.get("correct_answer"),
                scoring_points=candidate.get("scoring_points") or [],
                source_refs=[{
                    "knowledge_base_id": document.knowledge_base_id,
                    "document_id": document.id,
                    "chunk_indices": evidence_indices,
                    "document_title": document.filename,
                    "article": str(candidate.get("article") or ""),
                }],
                source_snapshot=str(candidate.get("evidence_quote") or ""),
                source_version=source_version,
                explanation_hint=str(candidate.get("explanation_hint") or ""),
                difficulty=str(candidate.get("difficulty") or "medium"),
                review_status="draft",
                enabled=True,
                generated_by=str(getattr(self.llm, "model", "llm")),
            ))
            existing_stems.add(str(candidate["stem"]).strip())
            created += 1
        await self.session.flush()
        return {"created": created, "rejected": rejected}

    @staticmethod
    def _generation_prompt(batch: SourceBatch) -> str:
        return f"""你是生态环境执法考试题库编辑。只依据给定政策原文生成候选题，不使用外部记忆。

要求：
1. 先识别可考知识点，再生成少量高质量题；不能从原文唯一推出答案时不要出题。
2. 题型可为 single_choice、multiple_choice、judgment、short_answer。
3. 选择题固定 A-D；多选至少两个正确项；简答题必须提供 scoring_points。
4. 每题提供 evidence_chunk_indices、evidence_quote、topic、knowledge_point、article、explanation_hint、difficulty。
5. evidence_chunk_indices 必须来自本批次标签。
6. 字段名必须严格遵循下列结构，不得改名、翻译字段名或增加外层包装：
{{
  "questions": [
    {{
      "candidate_id": "q1",
      "question_type": "single_choice",
      "stem": "题干",
      "options": {{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}},
      "correct_answer": "A",
      "scoring_points": [],
      "evidence_chunk_indices": [0],
      "evidence_quote": "能够直接支持答案的原文",
      "topic": "主题",
      "knowledge_point": "知识点",
      "article": "条款或章节",
      "explanation_hint": "解析要点",
      "difficulty": "medium"
    }}
  ]
}}
7. 判断题 options 使用空对象、correct_answer 使用布尔值；多选题 correct_answer 使用字符串数组；简答题 correct_answer 使用参考答案文本并提供 scoring_points。
8. 只返回 JSON，不要使用 Markdown 代码块或补充说明。

文件：{batch.filename}
原文：
{batch.text}
"""

    @staticmethod
    def _verification_prompt(batch: SourceBatch, candidates: list[dict[str, Any]]) -> str:
        return f"""你是独立题库复核员。逐题检查答案是否完全由原文支持、选项是否无歧义、证据定位是否匹配。
不要改题，只返回 JSON：
{{"verdicts":[{{"candidate_id":"...","answer_supported":true,"unambiguous":true,"source_match":true,"risk_flags":[]}}]}}

原文：
{batch.text}

候选题：
{json.dumps(candidates, ensure_ascii=False)}
"""
