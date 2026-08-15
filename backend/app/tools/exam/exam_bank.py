"""Agent-facing question-bank generation and catalog tool."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session
from app.exam.bank_generation import ExamBankGenerationService, normalize_question_counts
from app.exam.catalog import (
    enforcement_exam_knowledge_base_ids,
    list_exam_question_banks,
)
from app.exam.review import publish_question_bank
from app.exam.source_policy import evaluate_exam_source
from app.knowledge_base.models import Document, DocumentStatus
from app.tools.base.tool_interface import LLMTool, ToolCategory


DEFAULT_QUESTION_COUNTS = {
    "single_choice": 1,
    "multiple_choice": 1,
    "judgment": 1,
    "short_answer": 1,
}


class GenerateExamBankTool(LLMTool):
    """Generate source-grounded draft questions and list selectable banks."""

    def __init__(self, session_factory=None):
        super().__init__(
            name="generate_exam_bank",
            description=(
                "从“执法知识”知识库指定文档生成经过原文证据复核的执法考试题库草稿，"
                "支持按用户要求选择单选、多选、判断和简答题型及数量，并返回题库大纲、答案、评分点、解析和来源；"
                "也可列出可生成或可练习的题库；发布草稿必须由用户明确同意。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=True,
            function_schema={
                "name": "generate_exam_bank",
                "description": (
                    "列出执法考试题库/原文文档，从指定文档生成题库草稿，或在用户明确同意后发布题库。"
                    "生成结果包含题库大纲、题干、选项、正确答案、答案解析、简答题评分点和原文来源；"
                    "生成的题目默认是 draft；用户明确同意发布并通过结构校验后才能用于正式刷题。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list_sources", "list_banks", "generate", "publish"],
                            "description": "list_sources 列出可用原文文档；list_banks 列出已生成题库；generate 生成题库草稿；publish 在用户明确同意后发布题库。",
                        },
                        "knowledge_base_id": {
                            "type": "string",
                            "description": "执法知识知识库 ID；不填时由工具校验并提示可用文档。",
                        },
                        "document_id": {
                            "type": "string",
                            "description": "作为题库来源的知识库文档 ID。",
                        },
                        "bank_id": {
                            "type": "string",
                            "description": "publish 时要发布的题库 ID，通常是来源文档 ID。",
                        },
                        "confirm_publish": {
                            "type": "boolean",
                            "default": False,
                            "description": "仅当用户明确同意将该草稿题库发布为正式题库时传 true；不得替用户推断同意。",
                        },
                        "question_counts": {
                            "type": "object",
                            "description": "按用户要求填写各题型目标数量；可只填写部分题型，未填写的题型不作为本次目标。键为 single_choice、multiple_choice、judgment、short_answer，单次总数最多40；完全省略时工具默认每种题型生成1题。",
                            "properties": {
                                "single_choice": {"type": "integer", "minimum": 0, "maximum": 20},
                                "multiple_choice": {"type": "integer", "minimum": 0, "maximum": 20},
                                "judgment": {"type": "integer", "minimum": 0, "maximum": 20},
                                "short_answer": {"type": "integer", "minimum": 0, "maximum": 20},
                            },
                            "additionalProperties": False,
                        },
                        "max_chars_per_batch": {
                            "type": "integer",
                            "minimum": 1000,
                            "maximum": 20000,
                            "default": 12000,
                        },
                    },
                    "required": ["action"],
                },
            },
        )
        self.session_factory = session_factory or async_session

    async def execute(
        self,
        context=None,
        action: str | None = None,
        knowledge_base_id: str | None = None,
        document_id: str | None = None,
        bank_id: str | None = None,
        confirm_publish: bool = False,
        question_counts: dict[str, Any] | None = None,
        max_chars_per_batch: int = 12_000,
        **_: Any,
    ) -> dict[str, Any]:
        if getattr(context, "runtime_mode", None) != "enforcement_exam":
            return self._result(False, "该工具仅允许在执法考试模式使用")
        action = str(action or "").strip().lower()
        if action not in {"list_sources", "list_banks", "generate", "publish"}:
            return self._result(False, "action 必须是 list_sources、list_banks、generate 或 publish")
        user_id = str(getattr(context, "user_identifier", "") or "").strip()
        if not user_id:
            return self._result(False, "缺少当前用户身份，无法生成或选择题库")
        if action == "publish":
            if not bank_id:
                return self._result(False, "publish 必须提供 bank_id")
            if confirm_publish is not True:
                return self._result(False, "发布题库需要用户明确同意，请先展示题库并确认后再调用")

        try:
            async with self.session_factory() as session:
                async with session.begin():
                    if action == "list_banks":
                        banks = await list_exam_question_banks(session, include_drafts=True)
                        return self._success(
                            {"stage": "banks", "banks": banks},
                            f"已列出 {len(banks)} 个执法考试题库",
                        )

                    allowed_kb_ids = set(await enforcement_exam_knowledge_base_ids(session))
                    if action == "publish":
                        result = await publish_question_bank(
                            session,
                            bank_id=bank_id,
                            allowed_kb_ids=allowed_kb_ids,
                        )
                        return self._success(
                            result,
                            f"已将题库发布为正式题库，共发布 {result['published_question_count']} 道题",
                        )
                    if action == "list_sources":
                        return await self._list_sources(session, allowed_kb_ids)

                    counts = normalize_question_counts(
                        DEFAULT_QUESTION_COUNTS if question_counts is None else question_counts
                    )
                    if not counts:
                        return self._result(False, "generate 至少需要一种题型的数量大于 0")
                    if not knowledge_base_id or not document_id:
                        return self._result(False, "generate 必须提供 knowledge_base_id 和 document_id")
                    if knowledge_base_id not in allowed_kb_ids:
                        return self._result(False, "执法考试模式只能使用“执法知识”知识库")
                    document = await session.scalar(
                        select(Document).where(
                            Document.id == document_id,
                            Document.knowledge_base_id == knowledge_base_id,
                        )
                    )
                    if not document:
                        return self._result(False, "知识库文档不存在或不可访问")
                    if document.status != DocumentStatus.COMPLETED:
                        return self._result(False, "文档尚未完成知识库处理，暂不能生成题库")
                    eligible, reason = evaluate_exam_source(document)
                    if not eligible:
                        return self._result(False, f"该文档暂不能生成现行题库：{reason}")
                    result = await ExamBankGenerationService(session).generate_document(
                        knowledge_base_id=knowledge_base_id,
                        document_id=document_id,
                        user_id=user_id,
                        max_chars_per_batch=max(1000, min(int(max_chars_per_batch or 12000), 20000)),
                        question_counts=counts,
                    )
                    result["stage"] = "generated"
                    result["draft_only"] = True
                    result["summary"] = (
                        f"已生成 {result['created_drafts']} 道题库草稿；"
                        "已同步生成题库大纲，题目包含答案解析和原文来源，待审核后才能用于正式练习"
                    )
                    return {"status": "success", "success": True, "data": result, "metadata": {"tool_name": self.name, "draft_only": True}, "summary": result["summary"]}
        except ValueError as exc:
            return self._result(False, str(exc))
        except Exception as exc:
            return self._result(False, f"题库操作失败：{str(exc)[:200]}")

    async def _list_sources(self, session: AsyncSession, allowed_kb_ids: set[str]) -> dict[str, Any]:
        if not allowed_kb_ids:
            return self._success({"stage": "sources", "sources": []}, "未找到可访问的“执法知识”知识库")
        documents = (
            await session.scalars(
                select(Document)
                .where(
                    Document.knowledge_base_id.in_(allowed_kb_ids),
                    Document.status == DocumentStatus.COMPLETED,
                )
                .order_by(Document.created_at.desc())
            )
        ).all()
        banks = await list_exam_question_banks(session, include_drafts=True)
        bank_by_document = {str(item["bank_id"]): item for item in banks}
        sources = []
        for document in documents:
            bank = bank_by_document.get(str(document.id), {})
            eligible, eligibility_reason = evaluate_exam_source(document)
            sources.append({
                "knowledge_base_id": str(document.knowledge_base_id),
                "document_id": str(document.id),
                "name": document.filename,
                "status": getattr(document.status, "value", str(document.status)),
                "chunk_count": int(document.chunk_count or 0),
                "generated_question_count": int(bank.get("question_count") or 0),
                "selectable_for_practice": bool(bank.get("selectable")),
                "exam_generation_eligible": eligible,
                "eligibility_reason": eligibility_reason,
            })
        eligible_count = sum(1 for item in sources if item["exam_generation_eligible"])
        return self._success(
            {"stage": "sources", "sources": sources},
            f"已列出 {len(sources)} 个原文文档，其中 {eligible_count} 个已通过题源准入",
        )

    def _success(self, data: dict[str, Any], summary: str) -> dict[str, Any]:
        return {"status": "success", "success": True, "data": data, "metadata": {"tool_name": self.name}, "summary": summary}

    def _result(self, success: bool, summary: str) -> dict[str, Any]:
        return {"status": "success" if success else "failed", "success": success, "data": {}, "metadata": {"tool_name": self.name}, "summary": summary}
