"""Offline, source-grounded draft question generation from knowledge-base documents."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exam.models import ExamQuestion
from app.exam.outline import (
    OUTLINE_CATEGORIES,
    build_question_bank_outline,
)
from app.exam.source_policy import evaluate_exam_source
from app.knowledge_base.chunk_repository import KnowledgeChunkRepository
from app.knowledge_base.models import Document
from app.services.llm_service import llm_service

logger = structlog.get_logger(__name__)

QUESTION_TYPES = ("single_choice", "multiple_choice", "judgment", "short_answer")


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


def select_coverage_batches(
    batches: list[SourceBatch],
    requested_counts: dict[str, int],
) -> list[SourceBatch]:
    """Evenly sample the whole document while keeping the LLM call count bounded."""
    requested_total = sum(requested_counts.values())
    if len(batches) <= 1 or requested_total <= 0:
        return batches
    target_batch_count = min(len(batches), max(1, math.ceil(requested_total / 3)))
    if target_batch_count >= len(batches):
        return batches
    if target_batch_count == 1:
        return [batches[len(batches) // 2]]
    indices = [
        round(index * (len(batches) - 1) / (target_batch_count - 1))
        for index in range(target_batch_count)
    ]
    return [batches[index] for index in indices]


def allocate_batch_question_counts(
    remaining_counts: dict[str, int],
    *,
    remaining_batches: int,
) -> dict[str, int]:
    """Allocate a small current-batch target while preserving unmet type totals."""
    remaining_total = sum(remaining_counts.values())
    if remaining_total <= 0:
        return {}
    batch_capacity = max(1, math.ceil(remaining_total / max(1, remaining_batches)))
    allocated = {question_type: 0 for question_type in QUESTION_TYPES}
    candidates = dict(remaining_counts)
    for _ in range(batch_capacity):
        available = [item for item in QUESTION_TYPES if candidates.get(item, 0) > 0]
        if not available:
            break
        question_type = max(available, key=lambda item: (candidates[item], -QUESTION_TYPES.index(item)))
        allocated[question_type] += 1
        candidates[question_type] -= 1
    return {question_type: count for question_type, count in allocated.items() if count}


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
    elif question_type == "short_answer":
        scoring_points = candidate.get("scoring_points") or []
        if not scoring_points:
            errors.append("short_answer_requires_scoring_points")
        elif (
            not isinstance(scoring_points, list)
            or any(
                not isinstance(item, dict)
                or not str(item.get("point") or item.get("description") or "").strip()
                or not isinstance(item.get("score"), (int, float))
                or float(item.get("score")) <= 0
                for item in scoring_points
            )
        ):
            errors.append("short_answer_scoring_points_invalid")
        elif round(sum(float(item["score"]) for item in scoring_points), 4) != 100:
            errors.append("short_answer_scoring_points_must_sum_100")
        if not str(answer or "").strip():
            errors.append("short_answer_requires_reference_answer")
    return errors


def normalize_question_counts(question_counts: dict[str, Any] | None) -> dict[str, int]:
    """Validate the requested bank mix without allowing an unbounded LLM job."""
    if question_counts is None:
        return {}
    if not isinstance(question_counts, dict):
        raise ValueError("question_counts 必须是对象")
    normalized: dict[str, int] = {}
    for question_type, raw_count in question_counts.items():
        if question_type not in QUESTION_TYPES:
            raise ValueError(f"不支持的题型: {question_type}")
        try:
            count = int(raw_count)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"题型数量必须是整数: {question_type}") from exc
        if count < 0 or count > 20:
            raise ValueError(f"每种题型数量必须在 0 到 20 之间: {question_type}")
        if count:
            normalized[question_type] = count
    if normalized and sum(normalized.values()) > 40:
        raise ValueError("单次生成题目总数不能超过 40")
    return normalized


def validate_exam_priority(candidate: dict[str, Any]) -> list[str]:
    """Validate the lightweight importance metadata used to select useful questions."""
    errors: list[str] = []
    knowledge_point = str(candidate.get("knowledge_point") or "").strip()
    if not knowledge_point:
        errors.append("missing_knowledge_point")
    if candidate.get("outline_category") not in OUTLINE_CATEGORIES:
        errors.append("invalid_outline_category")
    importance_level = candidate.get("importance_level")
    if importance_level not in {"core", "normal", "skip"}:
        errors.append("invalid_importance_level")
    elif importance_level == "skip":
        errors.append("low_value_knowledge_point")
    reasons = candidate.get("importance_reasons")
    if (
        not isinstance(reasons, list)
        or not reasons
        or any(not str(item or "").strip() for item in reasons)
    ):
        errors.append("missing_importance_reasons")
    return errors


def _knowledge_point_key(value: Any) -> str:
    return "".join(str(value or "").split()).casefold()


def _normalized_text(value: Any) -> str:
    return "".join(str(value or "").split())


def evidence_quote_is_in_cited_chunks(
    batch: SourceBatch,
    evidence_chunk_indices: Any,
    evidence_quote: Any,
) -> bool:
    """Require the verbatim evidence to occur in the specifically cited chunks."""
    quote = _normalized_text(evidence_quote)
    if not quote:
        return False
    try:
        cited_indices = {int(index) for index in (evidence_chunk_indices or [])}
    except (TypeError, ValueError):
        return False
    if not cited_indices:
        return False

    marker = re.compile(r"(?m)^\[chunk_index=(-?\d+)\]\n")
    matches = list(marker.finditer(batch.text))
    cited_parts: list[str] = []
    for position, match in enumerate(matches):
        chunk_index = int(match.group(1))
        if chunk_index not in cited_indices:
            continue
        content_start = match.end()
        content_end = matches[position + 1].start() if position + 1 < len(matches) else len(batch.text)
        cited_parts.append(batch.text[content_start:content_end])
    return quote in _normalized_text("\n".join(cited_parts))


class ExamBankGenerationService:
    """Generate draft questions exhaustively; never auto-publish model output."""

    def __init__(self, session: AsyncSession, *, llm=None):
        self.session = session
        self.llm = llm or llm_service

    async def _call_pro_json(self, prompt: str) -> tuple[dict[str, Any], str]:
        """Route exam generation and review through the configured Pro chain."""
        use_model_tier = getattr(self.llm, "use_model_tier", None)
        if not callable(use_model_tier):
            raise RuntimeError("题库生成模型不支持 PRO 模型链")
        with use_model_tier("pro"):
            result = await self.llm.call_llm_with_json_response(
                prompt,
                max_retries=2,
            )
            selected_model = str(getattr(self.llm, "model", "pro-model"))
        return result, selected_model

    async def generate_document(
        self,
        *,
        knowledge_base_id: str,
        document_id: str,
        user_id: str | None = None,
        max_chars_per_batch: int = 12_000,
        question_counts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document = await self.session.get(Document, document_id)
        if not document or document.knowledge_base_id != knowledge_base_id:
            raise ValueError("knowledge-base document not found")
        eligible, eligibility_reason = evaluate_exam_source(document)
        if not eligible:
            raise ValueError(f"该文档暂不能生成现行题库：{eligibility_reason}")
        chunks = await self._load_document_chunks(document_id)
        batches = build_source_batches(
            document_id,
            document.filename,
            chunks,
            max_chars=max_chars_per_batch,
        )
        requested_counts = normalize_question_counts(question_counts)
        if requested_counts:
            batches = select_coverage_batches(batches, requested_counts)
        remaining_counts = dict(requested_counts)
        created = 0
        rejected = 0
        generated_questions: list[dict[str, Any]] = []
        seen_knowledge_points: set[str] = set()
        for batch_index, batch in enumerate(batches):
            if requested_counts and not any(remaining_counts.values()):
                break
            batch_counts = (
                allocate_batch_question_counts(
                    remaining_counts,
                    remaining_batches=len(batches) - batch_index,
                )
                if requested_counts
                else requested_counts
            )
            result = await self._generate_batch(
                batch,
                document,
                requested_counts=batch_counts,
                excluded_knowledge_points=seen_knowledge_points,
            )
            created += result["created"]
            rejected += result["rejected"]
            generated_questions.extend(result.get("questions") or [])
            seen_knowledge_points.update(result.get("created_knowledge_points") or [])
            for question_type, count in (result.get("created_by_type") or {}).items():
                if question_type in remaining_counts:
                    remaining_counts[question_type] = max(0, remaining_counts[question_type] - count)
        return {
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
            "filename": document.filename,
            "batch_count": len(batches),
            "created_drafts": created,
            "rejected_candidates": rejected,
            "review_status": "draft",
            "requested_question_counts": requested_counts,
            "remaining_question_counts": remaining_counts,
            "questions": generated_questions,
            "outline": build_question_bank_outline(
                generated_questions,
                title=f"{document.filename}题库大纲",
            ),
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

    async def _generate_batch(
        self,
        batch: SourceBatch,
        document: Document,
        *,
        requested_counts: dict[str, int] | None = None,
        excluded_knowledge_points: set[str] | None = None,
    ) -> dict[str, Any]:
        generation, generation_model = await self._call_pro_json(
            self._generation_prompt(batch, requested_counts=requested_counts)
        )
        candidates = generation.get("questions") or []
        if not isinstance(candidates, list):
            candidates = []
        locally_valid: list[dict[str, Any]] = []
        rejected = 0
        accepted_by_type: dict[str, int] = {}
        accepted_knowledge_points = set(excluded_knowledge_points or set())
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                rejected += 1
                continue
            candidate.setdefault("candidate_id", f"candidate-{index + 1}")
            errors = validate_candidate(candidate, set(batch.chunk_indices))
            errors.extend(validate_exam_priority(candidate))
            evidence_quote = candidate.get("evidence_quote")
            if not _normalized_text(evidence_quote):
                errors.append("missing_evidence_quote")
            elif not evidence_quote_is_in_cited_chunks(
                batch,
                candidate.get("evidence_chunk_indices"),
                evidence_quote,
            ):
                errors.append("evidence_quote_not_in_source")
            question_type = str(candidate.get("question_type") or "")
            knowledge_point_key = _knowledge_point_key(candidate.get("knowledge_point"))
            if knowledge_point_key and knowledge_point_key in accepted_knowledge_points:
                errors.append("duplicate_knowledge_point")
            if requested_counts:
                if question_type not in requested_counts:
                    errors.append("question_type_not_requested")
                elif accepted_by_type.get(question_type, 0) >= requested_counts[question_type]:
                    errors.append("question_type_target_reached")
            if errors:
                rejected += 1
                logger.warning("exam_question_candidate_rejected", errors=errors)
                continue
            locally_valid.append(candidate)
            accepted_by_type[question_type] = accepted_by_type.get(question_type, 0) + 1
            accepted_knowledge_points.add(knowledge_point_key)
        if not locally_valid:
            return {
                "created": 0,
                "rejected": rejected,
                "questions": [],
                "created_by_type": {},
                "created_knowledge_points": [],
            }

        verification, verification_model = await self._call_pro_json(
            self._verification_prompt(batch, locally_valid)
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
        created_by_type: dict[str, int] = {}
        created_questions: list[dict[str, Any]] = []
        created_knowledge_points: list[str] = []
        metadata = dict(document.extra_metadata or {})
        source_version = str(
            metadata.get("effective_date") or metadata.get("version") or document.file_checksum or ""
        )
        for candidate in locally_valid:
            verdict = verdicts.get(str(candidate["candidate_id"])) or {}
            approved = all(
                verdict.get(key) is True
                for key in (
                    "answer_supported",
                    "unambiguous",
                    "source_match",
                    "worth_testing",
                )
            )
            if not approved or str(candidate["stem"]).strip() in existing_stems:
                rejected += 1
                continue
            evidence_indices = [int(item) for item in candidate["evidence_chunk_indices"]]
            knowledge_point = str(candidate.get("knowledge_point") or "").strip()
            knowledge_point_id = hashlib.sha256(knowledge_point.encode("utf-8")).hexdigest()[:24] if knowledge_point else None
            exam_outline = {
                "category": candidate["outline_category"],
                "knowledge_point": knowledge_point,
                "importance_level": candidate["importance_level"],
                "importance_reasons": [
                    str(item).strip() for item in candidate["importance_reasons"]
                ],
                "model_tier": "pro",
                "generation_model": generation_model,
                "verification_model": verification_model,
            }
            question = ExamQuestion(
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
                    "exam_outline": exam_outline,
                }],
                source_snapshot=str(candidate.get("evidence_quote") or ""),
                source_version=source_version,
                explanation_hint=str(candidate.get("explanation_hint") or ""),
                difficulty=str(candidate.get("difficulty") or "medium"),
                review_status="draft",
                enabled=True,
                generated_by=generation_model,
            )
            self.session.add(question)
            existing_stems.add(str(candidate["stem"]).strip())
            created += 1
            created_by_type[question.question_type] = created_by_type.get(question.question_type, 0) + 1
            created_knowledge_points.append(_knowledge_point_key(knowledge_point))
            created_questions.append({
                "id": question.id,
                "question_type": question.question_type,
                "topic": question.topic,
                "stem": question.stem,
                "options": question.options or {},
                "correct_answer": question.correct_answer,
                "scoring_points": question.scoring_points or [],
                "source_refs": question.source_refs or [],
                "source_snapshot": question.source_snapshot,
                "source_version": question.source_version,
                "explanation_hint": question.explanation_hint,
                "difficulty": question.difficulty,
                "review_status": question.review_status,
                "outline_category": exam_outline["category"],
                "knowledge_point": exam_outline["knowledge_point"],
                "importance_level": exam_outline["importance_level"],
                "importance_reasons": exam_outline["importance_reasons"],
            })
        await self.session.flush()
        return {
            "created": created,
            "rejected": rejected,
            "questions": created_questions,
            "created_by_type": created_by_type,
            "created_knowledge_points": created_knowledge_points,
        }

    @staticmethod
    def _generation_prompt(
        batch: SourceBatch,
        *,
        requested_counts: dict[str, int] | None = None,
    ) -> str:
        mix_instruction = ""
        if requested_counts:
            mix_instruction = (
                "本次优先生成以下数量的题目（数量是目标，不足以被原文支持的题目宁缺毋滥）："
                + json.dumps(requested_counts, ensure_ascii=False)
                + "。"
            )
        return f"""你是生态环境执法考试题库编辑。只依据给定政策原文生成候选题，不使用外部记忆。

要求：
1. 先识别可考知识点，再生成少量高质量题；不能从原文唯一推出答案时不要出题，不得为了满足数量硬凑。
{mix_instruction}
2. 题型可为 single_choice、multiple_choice、judgment、short_answer。
3. 选择题固定 A-D；多选至少两个正确项；简答题必须提供参考答案和 scoring_points，所有评分点分值合计 100 分。
4. 每题提供 evidence_chunk_indices、evidence_quote、topic、knowledge_point、article、explanation_hint、difficulty。
5. evidence_chunk_indices 必须来自本批次标签。
6. 将知识点归入 outline_category：思想政治素质、环境执法队伍建设管理、生态环境专业知识、法学基础和法律法规、生态环境执法实践。
7. importance_level 只使用 core 或 normal。core 表示考试大纲明确覆盖，且属于核心程序、违法认定、法律责任、现场检查或应当掌握的内容；normal 表示大纲相关、原文明确且有实际学习价值。背景介绍、宽泛原则、答案不唯一、依赖常识或重复知识点属于 skip，不要为其生成题目。
8. 每题提供简短、具体的 importance_reasons；同一 knowledge_point 最多生成一道题。
9. 重点判断遵循以下基础规则：法学基础和法律法规、生态环境执法实践优先；执法主体、权限、程序、期限、调查取证、违法认定、法律责任、现场检查和文书制作优先；危险废物、自动监测数据弄虚作假、第三方机构弄虚作假、排污许可和非现场执法可适度提高重要性。以上信息只用于判断是否值得考，答案和解析仍只能依据本批原文。
10. 字段名必须严格遵循下列结构，不得改名、翻译字段名或增加外层包装：
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
      "outline_category": "法学基础和法律法规",
      "importance_level": "core",
      "importance_reasons": ["属于行政处罚核心程序", "涉及当事人法定权利"],
      "article": "条款或章节",
      "explanation_hint": "解析要点",
      "difficulty": "medium"
    }}
  ]
}}
11. 判断题 options 使用空对象、correct_answer 使用布尔值；多选题 correct_answer 使用字符串数组；简答题 correct_answer 使用参考答案文本并提供 scoring_points。
12. 只返回 JSON，不要使用 Markdown 代码块或补充说明。

文件：{batch.filename}
原文：
{batch.text}
"""

    @staticmethod
    def _verification_prompt(batch: SourceBatch, candidates: list[dict[str, Any]]) -> str:
        return f"""你是独立题库复核员。逐题检查答案是否完全由原文支持、选项是否无歧义、证据定位是否匹配，以及知识点是否具有实际考试和执法学习价值。背景介绍、宽泛原则、重复知识点或依赖常识的题目不值得进入题库。
不要改题，只返回 JSON：
{{"verdicts":[{{"candidate_id":"...","answer_supported":true,"unambiguous":true,"source_match":true,"worth_testing":true,"risk_flags":[]}}]}}

原文：
{batch.text}

候选题：
{json.dumps(candidates, ensure_ascii=False)}
"""
