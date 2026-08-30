"""Export generated exam questions to a review-friendly Markdown document."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db.database import async_session
from app.exam.models import ExamQuestion


def _outline(question: ExamQuestion) -> dict:
    for ref in question.source_refs or []:
        if isinstance(ref, dict) and isinstance(ref.get("exam_outline"), dict):
            return ref["exam_outline"]
    return {}


def _job_id(question: ExamQuestion) -> str:
    return str(_outline(question).get("generation_job_id") or "")


def _type_name(value: str) -> str:
    return {
        "single_choice": "单选题",
        "multiple_choice": "多选题",
        "judgment": "判断题",
        "short_answer": "简答题",
    }.get(value, value)


def _difficulty_name(value: str) -> str:
    return {"easy": "简单", "medium": "中等", "hard": "困难"}.get(value, value)


def _quote_markdown(value: str) -> str:
    lines = str(value or "").strip().splitlines()
    return "\n".join(f"> {line}" for line in lines) if lines else "> （无）"


def _source(question: ExamQuestion) -> dict:
    refs = [ref for ref in question.source_refs or [] if isinstance(ref, dict)]
    return refs[0] if refs else {}


def render_markdown(questions: list[ExamQuestion], job_id: str) -> str:
    type_counts = Counter(question.question_type for question in questions)
    category_counts = Counter(_outline(question).get("category") or "未分类" for question in questions)
    lines = [
        "# 执法考试新增题目（200题）",
        "",
        f"> 生成任务：{job_id}",
        f"> 导出时间：{datetime.now(UTC).astimezone().isoformat(timespec='seconds')}",
        "> 状态：草稿，未发布",
        "",
        "## 导出说明",
        "",
        "本文件包含本次生成任务新增的题目。每道题均保留题型、答案、解析、知识点和原文证据，供人工复核使用。",
        "",
        "## 统计",
        "",
        f"- 题目总数：{len(questions)}",
        "- 题型分布：" + "、".join(f"{_type_name(key)} {value} 道" for key, value in type_counts.items()),
        "- 大纲分类：" + "、".join(f"{key} {value} 道" for key, value in category_counts.items()),
        "",
    ]

    for number, question in enumerate(questions, start=1):
        outline = _outline(question)
        source = _source(question)
        options = question.options or {}
        lines.extend(
            [
                f"## {number}. {question.stem.strip()}",
                "",
                f"- **题型**：{_type_name(question.question_type)}",
                f"- **主题**：{question.topic or '未分类'}",
                f"- **大纲分类**：{outline.get('category') or '未分类'}",
                f"- **知识点**：{outline.get('knowledge_point') or '未填写'}",
                f"- **重要性**：{outline.get('importance_level') or '未填写'}",
                f"- **难度**：{_difficulty_name(question.difficulty)}",
                "",
            ]
        )
        if options:
            lines.extend(["**选项**", ""])
            for key in ("A", "B", "C", "D"):
                if key in options:
                    lines.append(f"- **{key}**：{options[key]}")
            lines.append("")
        lines.extend([f"**答案**：{question.correct_answer}", ""])
        if question.scoring_points:
            lines.extend(["**评分要点**", ""])
            for point in question.scoring_points:
                if isinstance(point, dict):
                    description = point.get("point") or point.get("description") or ""
                    lines.append(f"- {description}（{point.get('score', 0)}分）")
                else:
                    lines.append(f"- {point}")
            lines.append("")
        lines.extend(
            [
                f"**解析**：{question.explanation_hint or '未填写'}",
                "",
                f"**依据文档**：{source.get('document_title') or '未填写'}",
                f"**条款/章节**：{source.get('article') or '未填写'}",
                "",
                "**原文证据**：",
                _quote_markdown(question.source_snapshot),
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


async def export(job_id: str, output: Path) -> int:
    async with async_session() as session:
        all_questions = list((await session.scalars(select(ExamQuestion))).all())
    questions = [question for question in all_questions if _job_id(question) == job_id]
    if not questions:
        raise ValueError(f"未找到生成任务 {job_id} 的题目")
    questions.sort(key=lambda question: (question.created_at or datetime.min, question.id))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(questions, job_id), encoding="utf-8")
    return len(questions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    count = asyncio.run(export(args.job_id, args.output))
    print(f"exported {count} questions to {args.output}")


if __name__ == "__main__":
    main()
