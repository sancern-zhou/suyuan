"""Recoverable, coverage-balanced generation of unique enforcement-exam drafts."""

from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.exam.bank_generation import (
    QUESTION_TYPES,
    ExamBankGenerationService,
    SourceBatch,
    _knowledge_point_key,
)
from app.exam.catalog import enforcement_exam_knowledge_base_ids
from app.exam.models import ExamQuestion
from app.exam.source_policy import evaluate_exam_source
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.models import Document, DocumentStatus
from app.utils.path_config import get_data_registry

PLAN_VERSION = 1
DEFAULT_TYPE_WEIGHTS = {
    "single_choice": 0.40,
    "multiple_choice": 0.25,
    "judgment": 0.25,
    "short_answer": 0.10,
}


@dataclass(frozen=True)
class SourceGroupSpec:
    name: str
    filename_patterns: tuple[str, ...]
    primary_quota: int
    reserve_quota: int


DEFAULT_SOURCE_GROUPS = (
    SourceGroupSpec("生态环境法典", ("中华人民共和国生态环境法典",), 70, 21),
    SourceGroupSpec(
        "核心法律规范",
        (
            "中华人民共和国行政处罚法",
            "中华人民共和国行政强制法",
            "生态环境行政处罚办法",
            "生态环境行政处罚听证程序规定",
            "排污许可管理条例",
            "排污许可管理办法",
            "危险废物经营许可证管理办法",
            "环境保护行政执法与刑事司法衔接工作办法",
        ),
        55,
        14,
    ),
    SourceGroupSpec("行政执法文书", ("环境行政执法文书制作指南",), 45, 11),
    SourceGroupSpec("生态环境监测条例", ("生态环境监测条例",), 12, 0),
    SourceGroupSpec("自动监测数据传输", ("HJ 212",), 40, 10),
    SourceGroupSpec("烟气与非甲烷总烃监测", ("HJ 76", "HJ 1013"), 50, 12),
    SourceGroupSpec(
        "水污染源监测",
        ("HJ 353", "HJ 354", "HJ 355", "HJ 91.1"),
        48,
        12,
    ),
)


@dataclass(frozen=True)
class ChunkCandidate:
    document_id: str
    filename: str
    chunk_index: int
    text: str
    normalized_text: str


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalize_chunk_text(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(value or "")).casefold()


def chunk_text_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if min(len(left), len(right)) / max(len(left), len(right)) < 0.75:
        return 0.0
    return float(fuzz.ratio(left, right)) / 100.0


def deduplicate_chunk_candidates(
    candidates: list[ChunkCandidate],
    *,
    threshold: float,
) -> tuple[list[ChunkCandidate], dict[str, int]]:
    """Cluster near-identical chunks and keep the longest representative."""
    if not candidates:
        return [], {"groups": 0, "removed": 0, "largest_group": 0}
    parent = list(range(len(candidates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, left in enumerate(candidates):
        for right_index in range(left_index + 1, len(candidates)):
            right = candidates[right_index]
            if chunk_text_similarity(left.normalized_text, right.normalized_text) >= threshold:
                union(left_index, right_index)

    groups: dict[int, list[ChunkCandidate]] = defaultdict(list)
    for index, candidate in enumerate(candidates):
        groups[find(index)].append(candidate)
    representatives = [
        sorted(
            group,
            key=lambda item: (-len(item.normalized_text), item.filename, item.chunk_index),
        )[0]
        for group in groups.values()
    ]
    representatives.sort(key=lambda item: (item.filename, item.chunk_index))
    duplicate_groups = [group for group in groups.values() if len(group) > 1]
    return representatives, {
        "groups": len(duplicate_groups),
        "removed": len(candidates) - len(representatives),
        "largest_group": max((len(group) for group in duplicate_groups), default=0),
    }


def _evenly_select(items: list[ChunkCandidate], count: int) -> list[ChunkCandidate]:
    if count <= 0 or not items:
        return []
    if count >= len(items):
        return list(items)
    if count == 1:
        return [items[len(items) // 2]]
    indices = {
        round(index * (len(items) - 1) / (count - 1))
        for index in range(count)
    }
    if len(indices) < count:
        indices.update(index for index in range(len(items)) if index not in indices)
    return [items[index] for index in sorted(indices)[:count]]


def _allocate_document_quotas(
    candidates_by_document: dict[str, list[ChunkCandidate]],
    total: int,
) -> dict[str, int]:
    """Allocate group capacity using square-root weights to avoid giant-source dominance."""
    capacities = {key: len(items) for key, items in candidates_by_document.items() if items}
    if total <= 0 or not capacities:
        return {}
    total = min(total, sum(capacities.values()))
    weights = {key: math.sqrt(capacity) for key, capacity in capacities.items()}
    weight_sum = sum(weights.values())
    raw = {key: total * weights[key] / weight_sum for key in capacities}
    allocated = {key: min(capacities[key], int(math.floor(raw[key]))) for key in capacities}
    remaining = total - sum(allocated.values())
    while remaining > 0:
        available = [key for key in capacities if allocated[key] < capacities[key]]
        if not available:
            break
        key = max(available, key=lambda item: (raw[item] - allocated[item], capacities[item]))
        allocated[key] += 1
        remaining -= 1
    return allocated


def _select_group_candidates(
    candidates: list[ChunkCandidate],
    count: int,
) -> list[ChunkCandidate]:
    by_document: dict[str, list[ChunkCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_document[candidate.document_id].append(candidate)
    for values in by_document.values():
        values.sort(key=lambda item: item.chunk_index)
    quotas = _allocate_document_quotas(by_document, count)
    selected: list[ChunkCandidate] = []
    for document_id in sorted(by_document):
        selected.extend(_evenly_select(by_document[document_id], quotas.get(document_id, 0)))
    return selected


def _source_group(filename: str, specs: Iterable[SourceGroupSpec]) -> SourceGroupSpec | None:
    return next(
        (
            spec
            for spec in specs
            if any(pattern.casefold() in filename.casefold() for pattern in spec.filename_patterns)
        ),
        None,
    )


def allocate_question_types(total: int) -> list[str]:
    raw = {name: total * DEFAULT_TYPE_WEIGHTS[name] for name in QUESTION_TYPES}
    counts = {name: int(math.floor(raw[name])) for name in QUESTION_TYPES}
    remaining = total - sum(counts.values())
    while remaining > 0:
        name = max(QUESTION_TYPES, key=lambda item: (raw[item] - counts[item], -QUESTION_TYPES.index(item)))
        counts[name] += 1
        remaining -= 1
    pool: list[str] = []
    mutable = dict(counts)
    while sum(mutable.values()) > 0:
        for name in QUESTION_TYPES:
            if mutable[name] > 0:
                pool.append(name)
                mutable[name] -= 1
    return pool


def generation_job_dir() -> Path:
    return get_data_registry() / "exam_generation"


def generation_job_path(job_id: str) -> Path:
    return generation_job_dir() / f"{job_id}.json"


def save_generation_job(job: dict[str, Any]) -> Path:
    directory = generation_job_dir()
    directory.mkdir(parents=True, exist_ok=True)
    job["updated_at"] = utc_now_iso()
    path = generation_job_path(str(job["job_id"]))
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def load_generation_job(job_id: str) -> dict[str, Any]:
    path = generation_job_path(job_id)
    if not path.is_file():
        raise ValueError(f"题库生成任务不存在: {job_id}")
    return json.loads(path.read_text(encoding="utf-8"))


async def create_generation_job(
    session: AsyncSession,
    *,
    target_count: int = 200,
    primary_count: int = 320,
    reserve_count: int = 80,
    model_tier: str = "auto",
    min_chunk_chars: int = 100,
    chunk_similarity_threshold: float = 0.90,
    question_similarity_threshold: float = 0.90,
    source_groups: tuple[SourceGroupSpec, ...] = DEFAULT_SOURCE_GROUPS,
) -> dict[str, Any]:
    if target_count <= 0 or primary_count < target_count or reserve_count < 0:
        raise ValueError("生成目标和候选余量配置无效")
    if sum(spec.primary_quota for spec in source_groups) != primary_count:
        raise ValueError("题源组 primary_quota 合计必须等于 primary_count")
    if sum(spec.reserve_quota for spec in source_groups) != reserve_count:
        raise ValueError("题源组 reserve_quota 合计必须等于 reserve_count")

    allowed_kb_ids = set(await enforcement_exam_knowledge_base_ids(session))
    documents = list(
        (
            await session.scalars(
                select(Document).where(
                    Document.knowledge_base_id.in_(allowed_kb_ids),
                    Document.status == DocumentStatus.COMPLETED,
                )
            )
        ).all()
    ) if allowed_kb_ids else []
    eligible_documents = {
        str(document.id): document
        for document in documents
        if evaluate_exam_source(document)[0]
    }
    questions = list((await session.scalars(select(ExamQuestion))).all())
    cited_chunks: set[tuple[str, int]] = set()
    for question in questions:
        for ref in question.source_refs or []:
            if not isinstance(ref, dict):
                continue
            document_id = str(ref.get("document_id") or "")
            for raw_index in ref.get("chunk_indices") or []:
                try:
                    cited_chunks.add((document_id, int(raw_index)))
                except (TypeError, ValueError):
                    continue

    chunk_rows = list(
        (
            await session.scalars(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.document_id.in_(eligible_documents)
                )
            )
        ).all()
    ) if eligible_documents else []
    short_chunks = 0
    raw_candidates: list[ChunkCandidate] = []
    for chunk in chunk_rows:
        document_id = str(chunk.document_id)
        chunk_index = int(chunk.chunk_index)
        if (document_id, chunk_index) in cited_chunks:
            continue
        normalized = normalize_chunk_text(chunk.content)
        if len(normalized) < min_chunk_chars:
            short_chunks += 1
            continue
        document = eligible_documents[document_id]
        raw_candidates.append(
            ChunkCandidate(
                document_id=document_id,
                filename=str(document.filename),
                chunk_index=chunk_index,
                text=str(chunk.content or "").strip(),
                normalized_text=normalized,
            )
        )

    unique_candidates, duplicate_stats = deduplicate_chunk_candidates(
        raw_candidates,
        threshold=chunk_similarity_threshold,
    )
    by_group: dict[str, list[ChunkCandidate]] = defaultdict(list)
    unmatched: list[str] = []
    for candidate in unique_candidates:
        spec = _source_group(candidate.filename, source_groups)
        if spec is None:
            unmatched.append(candidate.filename)
            continue
        by_group[spec.name].append(candidate)

    selected_rows: list[dict[str, Any]] = []
    primary_types = allocate_question_types(primary_count)
    reserve_types = allocate_question_types(reserve_count)
    primary_type_index = 0
    reserve_type_index = 0
    group_summary: list[dict[str, Any]] = []
    for spec in source_groups:
        available = sorted(
            by_group.get(spec.name, []),
            key=lambda item: (item.filename, item.chunk_index),
        )
        primary = _select_group_candidates(available, spec.primary_quota)
        primary_keys = {(item.document_id, item.chunk_index) for item in primary}
        remaining = [
            item
            for item in available
            if (item.document_id, item.chunk_index) not in primary_keys
        ]
        reserve = _select_group_candidates(remaining, spec.reserve_quota)
        if len(primary) != spec.primary_quota or len(reserve) != spec.reserve_quota:
            raise ValueError(
                f"题源组“{spec.name}”候选分块不足："
                f"需要 {spec.primary_quota + spec.reserve_quota}，"
                f"实际 {len(available)}"
            )
        for pool, values in (("primary", primary), ("reserve", reserve)):
            for candidate in values:
                if pool == "primary":
                    planned_type = primary_types[primary_type_index]
                    primary_type_index += 1
                    status = "pending"
                else:
                    planned_type = reserve_types[reserve_type_index]
                    reserve_type_index += 1
                    status = "reserve"
                selected_rows.append(
                    {
                        "source_group": spec.name,
                        "pool": pool,
                        "document_id": candidate.document_id,
                        "filename": candidate.filename,
                        "chunk_index": candidate.chunk_index,
                        "planned_question_type": planned_type,
                        "status": status,
                        "attempts": 0,
                        "question_id": None,
                        "last_error": None,
                        "rejection_reasons": [],
                    }
                )
        group_summary.append(
            {
                "name": spec.name,
                "available_unique_chunks": len(available),
                "primary": len(primary),
                "reserve": len(reserve),
            }
        )

    job_id = f"exam-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    job = {
        "version": PLAN_VERSION,
        "job_id": job_id,
        "status": "planned",
        "target_count": target_count,
        "primary_count": primary_count,
        "reserve_count": reserve_count,
        "model_tier": model_tier,
        "min_chunk_chars": min_chunk_chars,
        "chunk_similarity_threshold": chunk_similarity_threshold,
        "question_similarity_threshold": question_similarity_threshold,
        "existing_question_count": len(questions),
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "filters": {
            "eligible_document_count": len(eligible_documents),
            "eligible_chunk_count": len(chunk_rows),
            "already_cited_chunk_count": len(cited_chunks),
            "short_chunk_count": short_chunks,
            "candidate_before_near_dedup": len(raw_candidates),
            "candidate_after_near_dedup": len(unique_candidates),
            "near_duplicate_groups": duplicate_stats["groups"],
            "near_duplicate_chunks_removed": duplicate_stats["removed"],
            "largest_near_duplicate_group": duplicate_stats["largest_group"],
            "unmatched_documents": sorted(set(unmatched)),
        },
        "source_groups": group_summary,
        "chunks": selected_rows,
        "batches_completed": 0,
        "accepted_count": 0,
        "rejected_count": 0,
        "failed_count": 0,
    }
    save_generation_job(job)
    return job


def generation_job_summary(job: dict[str, Any]) -> dict[str, Any]:
    statuses = Counter(str(item.get("status") or "unknown") for item in job.get("chunks") or [])
    types = Counter(
        str(item.get("planned_question_type") or "unknown")
        for item in job.get("chunks") or []
        if item.get("pool") == "primary"
    )
    rejection_reasons = Counter(
        str(reason)
        for item in job.get("chunks") or []
        for reason in (item.get("rejection_reasons") or [])
    )
    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "model_tier": job.get("model_tier"),
        "target_count": job.get("target_count"),
        "statuses": dict(statuses),
        "primary_question_type_plan": dict(types),
        "batches_completed": int(job.get("batches_completed") or 0),
        "rejection_reasons": dict(rejection_reasons),
        "filters": job.get("filters") or {},
        "source_groups": job.get("source_groups") or [],
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "path": str(generation_job_path(str(job.get("job_id")))),
    }


def _question_job_anchor(question: ExamQuestion, job_id: str) -> tuple[str, int] | None:
    for ref in question.source_refs or []:
        if not isinstance(ref, dict):
            continue
        outline = ref.get("exam_outline")
        if not isinstance(outline, dict) or outline.get("generation_job_id") != job_id:
            continue
        indices = ref.get("chunk_indices") or []
        if len(indices) != 1:
            continue
        try:
            return str(ref.get("document_id") or ""), int(indices[0])
        except (TypeError, ValueError):
            continue
    return None


async def _reconcile_job(session: AsyncSession, job: dict[str, Any]) -> None:
    questions = list((await session.scalars(select(ExamQuestion))).all())
    anchors = {
        anchor: str(question.id)
        for question in questions
        if (anchor := _question_job_anchor(question, str(job["job_id"]))) is not None
    }
    for item in job.get("chunks") or []:
        key = (str(item["document_id"]), int(item["chunk_index"]))
        if key in anchors:
            item["status"] = "accepted"
            item["question_id"] = anchors[key]


def _excluded_knowledge_points(questions: list[ExamQuestion]) -> set[str]:
    values: set[str] = set()
    for question in questions:
        for ref in question.source_refs or []:
            if not isinstance(ref, dict):
                continue
            outline = ref.get("exam_outline")
            if isinstance(outline, dict):
                key = _knowledge_point_key(outline.get("knowledge_point"))
                if key:
                    values.add(key)
    return values


def _activate_reserve(job: dict[str, Any], count: int = 20) -> int:
    activated = 0
    for item in job.get("chunks") or []:
        if item.get("status") != "reserve":
            continue
        item["status"] = "pending"
        activated += 1
        if activated >= count:
            break
    return activated


async def run_generation_job(
    session_factory: async_sessionmaker,
    *,
    job_id: str,
    batch_size: int = 8,
    max_batches: int | None = None,
) -> dict[str, Any]:
    """Run short, committed batches and persist enough state to resume safely."""
    if batch_size < 1 or batch_size > 12:
        raise ValueError("batch_size 必须在 1 到 12 之间")
    job = load_generation_job(job_id)
    job["status"] = "running"
    save_generation_job(job)
    completed_this_run = 0

    while True:
        async with session_factory() as session:
            await _reconcile_job(session, job)
        accepted_count = sum(1 for item in job["chunks"] if item.get("status") == "accepted")
        if accepted_count >= int(job["target_count"]):
            job["status"] = "completed"
            break
        pending = [item for item in job["chunks"] if item.get("status") == "pending"]
        if not pending:
            if _activate_reserve(job) == 0:
                job["status"] = "exhausted"
                break
            save_generation_job(job)
            continue
        if max_batches is not None and completed_this_run >= max_batches:
            job["status"] = "paused"
            break

        first_document_id = str(pending[0]["document_id"])
        remaining_target = int(job["target_count"]) - accepted_count
        batch_items = [
            item
            for item in pending
            if str(item["document_id"]) == first_document_id
        ][: min(batch_size, remaining_target)]
        batch_indices = {int(item["chunk_index"]) for item in batch_items}

        try:
            async with session_factory() as session:
                async with session.begin():
                    document = await session.get(Document, first_document_id)
                    if document is None:
                        raise ValueError(f"题源文档不存在: {first_document_id}")
                    chunks = list(
                        (
                            await session.scalars(
                                select(KnowledgeChunk)
                                .where(
                                    KnowledgeChunk.document_id == first_document_id,
                                    KnowledgeChunk.chunk_index.in_(batch_indices),
                                )
                                .order_by(KnowledgeChunk.chunk_index)
                            )
                        ).all()
                    )
                    if {int(chunk.chunk_index) for chunk in chunks} != batch_indices:
                        raise ValueError("计划中的题源分块缺失")
                    source_batch = SourceBatch(
                        document_id=first_document_id,
                        filename=str(document.filename),
                        chunk_indices=tuple(int(chunk.chunk_index) for chunk in chunks),
                        text="\n\n".join(
                            f"[chunk_index={int(chunk.chunk_index)}]\n{str(chunk.content or '').strip()}"
                            for chunk in chunks
                        ),
                    )
                    all_questions = list((await session.scalars(select(ExamQuestion))).all())
                    requested_counts = Counter(
                        str(item["planned_question_type"]) for item in batch_items
                    )
                    service = ExamBankGenerationService(
                        session,
                        model_tier=str(job["model_tier"]),
                        semantic_duplicate_threshold=float(job["question_similarity_threshold"]),
                        generation_job_id=job_id,
                    )
                    result = await service._generate_batch(
                        source_batch,
                        document,
                        requested_counts=dict(requested_counts),
                        excluded_knowledge_points=_excluded_knowledge_points(all_questions),
                        one_question_per_chunk=True,
                    )
            accepted_by_chunk = {
                int(question["source_refs"][0]["chunk_indices"][0]): str(question["id"])
                for question in result.get("questions") or []
                if question.get("source_refs")
                and len(question["source_refs"][0].get("chunk_indices") or []) == 1
            }
            rejection_by_chunk: dict[int, list[str]] = defaultdict(list)
            for rejection in result.get("rejections") or []:
                indices = rejection.get("evidence_chunk_indices") or []
                if len(indices) != 1:
                    continue
                try:
                    chunk_index = int(indices[0])
                except (TypeError, ValueError):
                    continue
                rejection_by_chunk[chunk_index].extend(
                    str(error) for error in (rejection.get("errors") or [])
                )
            for item in batch_items:
                item["attempts"] = int(item.get("attempts") or 0) + 1
                index = int(item["chunk_index"])
                if index in accepted_by_chunk:
                    item["status"] = "accepted"
                    item["question_id"] = accepted_by_chunk[index]
                else:
                    item["status"] = "rejected"
                    item["rejection_reasons"] = list(
                        dict.fromkeys(
                            rejection_by_chunk.get(index)
                            or ["model_skipped_or_unattributed"]
                        )
                    )
            job["batches_completed"] = int(job.get("batches_completed") or 0) + 1
            completed_this_run += 1
        except Exception as exc:
            for item in batch_items:
                item["attempts"] = int(item.get("attempts") or 0) + 1
                item["last_error"] = str(exc)[:500]
                if item["attempts"] >= 2:
                    item["status"] = "failed"
            job["last_error"] = str(exc)[:500]
            completed_this_run += 1

        job["accepted_count"] = sum(
            1 for item in job["chunks"] if item.get("status") == "accepted"
        )
        job["rejected_count"] = sum(
            1 for item in job["chunks"] if item.get("status") == "rejected"
        )
        job["failed_count"] = sum(
            1 for item in job["chunks"] if item.get("status") == "failed"
        )
        save_generation_job(job)

    job["accepted_count"] = sum(
        1 for item in job["chunks"] if item.get("status") == "accepted"
    )
    job["rejected_count"] = sum(
        1 for item in job["chunks"] if item.get("status") == "rejected"
    )
    job["failed_count"] = sum(
        1 for item in job["chunks"] if item.get("status") == "failed"
    )
    save_generation_job(job)
    return generation_job_summary(job)
