"""Lightweight question-bank outline aggregation."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


OUTLINE_CATEGORIES = (
    "思想政治素质",
    "环境执法队伍建设管理",
    "生态环境专业知识",
    "法学基础和法律法规",
    "生态环境执法实践",
)


def _value(question: Any, field: str, default: Any = None) -> Any:
    if isinstance(question, dict):
        return question.get(field, default)
    return getattr(question, field, default)


def _exam_outline_metadata(question: Any) -> dict[str, Any]:
    for ref in _value(question, "source_refs", []) or []:
        if not isinstance(ref, dict):
            continue
        metadata = ref.get("exam_outline")
        if isinstance(metadata, dict):
            return metadata
    return {}


def build_question_bank_outline(
    questions: Iterable[Any],
    *,
    title: str,
) -> dict[str, Any]:
    """Build a compact, user-facing outline from persisted question metadata."""
    items = list(questions)
    category_rows: dict[str, dict[str, Any]] = {}
    total_type_counts: Counter[str] = Counter()
    total_importance_counts: Counter[str] = Counter()

    for question in items:
        metadata = _exam_outline_metadata(question)
        category = str(metadata.get("category") or "未分类").strip() or "未分类"
        topic = str(_value(question, "topic", "未分类") or "未分类").strip()
        knowledge_point = str(metadata.get("knowledge_point") or topic).strip()
        question_type = str(_value(question, "question_type", "") or "")
        importance = str(metadata.get("importance_level") or "normal").strip()

        category_row = category_rows.setdefault(
            category,
            {
                "name": category,
                "question_count": 0,
                "question_type_counts": Counter(),
                "importance_counts": Counter(),
                "topics": {},
            },
        )
        category_row["question_count"] += 1
        category_row["question_type_counts"][question_type] += 1
        category_row["importance_counts"][importance] += 1
        total_type_counts[question_type] += 1
        total_importance_counts[importance] += 1

        topic_row = category_row["topics"].setdefault(
            topic,
            {"name": topic, "question_count": 0, "knowledge_points": set()},
        )
        topic_row["question_count"] += 1
        if knowledge_point:
            topic_row["knowledge_points"].add(knowledge_point)

    category_order = {name: index for index, name in enumerate(OUTLINE_CATEGORIES)}
    categories = []
    for category_row in sorted(
        category_rows.values(),
        key=lambda row: (category_order.get(row["name"], len(category_order)), row["name"]),
    ):
        topics = [
            {
                "name": topic_row["name"],
                "question_count": topic_row["question_count"],
                "knowledge_points": sorted(topic_row["knowledge_points"]),
            }
            for topic_row in sorted(
                category_row["topics"].values(), key=lambda row: row["name"]
            )
        ]
        categories.append(
            {
                "name": category_row["name"],
                "question_count": category_row["question_count"],
                "question_type_counts": dict(
                    sorted(category_row["question_type_counts"].items())
                ),
                "importance_counts": dict(
                    sorted(category_row["importance_counts"].items())
                ),
                "topics": topics,
            }
        )

    return {
        "title": title,
        "question_count": len(items),
        "question_type_counts": dict(sorted(total_type_counts.items())),
        "importance_counts": dict(sorted(total_importance_counts.items())),
        "categories": categories,
    }
