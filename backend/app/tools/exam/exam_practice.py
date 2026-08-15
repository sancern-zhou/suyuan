"""Single agent-facing tool for retrieving questions and tracking practice."""

from __future__ import annotations

from typing import Any

import structlog

from app.db.database import async_session
from app.exam.service import ExamPracticeError, ExamPracticeService
from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class ExamPracticeTool(LLMTool):
    """Keep question selection, grading, progress and timing out of model memory."""

    def __init__(self, session_factory=None):
        super().__init__(
            name="exam_practice",
            description=(
                "管理当前用户的生态环境执法备考练习：开始/恢复练习、获取下一题、"
                "提交或跳过答案、记录服务端答题时间、完成练习和查询进度。"
                "正式练习题必须从本工具获取；工具在出题阶段不会返回正确答案。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=True,
            function_schema={
                "name": "exam_practice",
                "description": (
                    "管理当前用户的执法备考刷题状态，可先用 list_banks 选择题库。客观题优先用 submit_and_next 一次完成"
                    "判分和推进。该动作返回一个组合结果：data.last_result 是刚提交题目的判分解析依据，"
                    "data.question 是下一题；模型必须在同一条最终回复中自主生成‘上一题解析 + 下一题’，"
                    "不得拆成两条消息或只输出下一题。简答题 submit 后返回评分点，再由模型调用 grade_and_next。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "start", "current", "submit", "submit_and_next",
                                "grade", "grade_and_next", "next", "skip", "finish",
                                "progress", "list_banks",
                            ],
                            "description": (
                                "要执行的刷题动作。客观题答题使用 submit_and_next；"
                                "简答题先 submit，再使用 grade_and_next。"
                            ),
                        },
                        "practice_mode": {
                            "type": "string",
                            "enum": ["random", "daily", "wrong_review", "unseen", "mock_exam"],
                            "description": "start 时的练习模式，默认 unseen。",
                        },
                        "question_types": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "single_choice", "multiple_choice", "judgment", "short_answer"
                                ],
                            },
                            "description": "start 时可选题型；留空表示不限。",
                        },
                        "topics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "start 时可选知识主题；留空表示不限。",
                        },
                        "bank_id": {
                            "type": "string",
                            "description": "start 时选择的题库 ID（通常是题库来源文档 ID）；不填则从全部已发布题库抽题。",
                        },
                        "count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 62,
                            "description": "start 时题目数量，默认10。",
                        },
                        "answer": {
                            "description": "submit 或 submit_and_next 时的用户答案。",
                        },
                        "run_id": {
                            "type": "string",
                            "description": "工具之前返回的练习ID。",
                        },
                        "question_id": {
                            "type": "string",
                            "description": "工具之前返回的当前题目ID。",
                        },
                        "is_correct": {
                            "type": "boolean",
                            "description": "grade 简答题时的综合正确性。",
                        },
                        "score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "grade 简答题时的百分制得分。",
                        },
                        "evaluation": {
                            "type": "object",
                            "description": "grade 简答题时保存的命中要点、遗漏要点和简短反馈。",
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
        practice_mode: str | None = None,
        question_types: list[str] | None = None,
        topics: list[str] | None = None,
        bank_id: str | None = None,
        count: int | None = None,
        answer: Any = None,
        run_id: str | None = None,
        question_id: str | None = None,
        is_correct: bool | None = None,
        score: float | None = None,
        evaluation: dict | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        user_id = str(getattr(context, "user_identifier", "") or "").strip()
        if not user_id:
            return self._result(False, "缺少当前用户身份，无法隔离保存刷题记录")
        if not action:
            return self._result(False, "缺少 action")

        try:
            async with self.session_factory() as session:
                async with session.begin():
                    data = await ExamPracticeService(session).execute(
                        user_id=user_id,
                        action=action,
                        practice_mode=practice_mode,
                        question_types=question_types,
                        topics=topics,
                        bank_id=bank_id,
                        count=count,
                        answer=answer,
                        run_id=run_id,
                        question_id=question_id,
                        is_correct=is_correct,
                        score=score,
                        evaluation=evaluation,
                    )
            return {
                "status": "success",
                "success": True,
                "data": data,
                "metadata": {"tool_name": self.name, "user_scoped": True},
                "summary": self._summary(action, data),
            }
        except ExamPracticeError as exc:
            return self._result(False, str(exc))
        except Exception as exc:
            logger.exception("exam_practice_failed", action=action, user_id=user_id)
            return self._result(False, f"刷题操作失败：{str(exc)[:160]}")

    @staticmethod
    def _summary(action: str, data: dict[str, Any]) -> str:
        stage = data.get("stage")
        if stage == "question":
            question = data.get("question") or {}
            return f"已取得第{question.get('sequence')}题，共{question.get('total')}题；等待用户作答"
        if stage in {"result", "awaiting_grade"}:
            if stage == "awaiting_grade":
                return "已接收简答题答案但不持久化原文；请依据题库评分点完成评分"
            return "已记录答案和服务端答题时间，并返回判题结果与政策来源定位"
        if stage == "completed":
            return "本组练习已完成，已返回练习统计"
        if stage == "progress":
            return "已返回当前用户的刷题进度和薄弱主题"
        if stage == "banks":
            return f"已返回 {len(data.get('banks') or [])} 个可选择的已发布题库"
        return str(data.get("summary") or f"刷题动作 {action} 已完成")

    @staticmethod
    def _result(success: bool, summary: str) -> dict[str, Any]:
        return {
            "status": "success" if success else "failed",
            "success": success,
            "data": {},
            "metadata": {"tool_name": "exam_practice"},
            "summary": summary,
        }
