"""Model-facing structured question handoff."""

from app.agent.user_questions import QuestionSet
from app.tools.base.tool_interface import LLMTool, ToolCategory


class AskUserQuestionTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="ask_user_question",
            description="仅在必须由用户决定且无法从上下文确认时，提出结构化选择题并等待回答。不要用来询问可自行查证的事实。",
            category=ToolCategory.PLANNING,
            function_schema={
                "name": "ask_user_question",
                "description": "向用户提出 1-4 道选择题并暂停当前任务。每题 2-4 个选项；界面自动提供其他/自由输入。推荐项放首位。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "questions": {
                            "type": "array", "minItems": 1, "maxItems": 4,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string"},
                                    "header": {"type": "string", "maxLength": 12},
                                    "options": {
                                        "type": "array", "minItems": 2, "maxItems": 4,
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "label": {"type": "string"},
                                                "description": {"type": "string"},
                                                "preview": {"type": "string"},
                                            },
                                            "required": ["label", "description"],
                                        },
                                    },
                                    "multiSelect": {"type": "boolean"},
                                },
                                "required": ["question", "header", "options"],
                            },
                        },
                    },
                    "required": ["questions"],
                },
            },
            requires_context=True,
        )

    async def execute(self, context=None, questions: list[dict] | None = None, **kwargs) -> dict:
        runtime_metadata = getattr(context, "runtime_metadata", {}) or {}
        if runtime_metadata.get("scheduled_task") or runtime_metadata.get("agent_depth", 0) > 0:
            return {
                "success": False,
                "status": "failed",
                "data": {},
                "metadata": {"schema_version": "v2.0"},
                "summary": "无人值守任务不能直接向用户提问；请在结果中列出需要用户决定的问题。",
            }
        try:
            validated = QuestionSet.model_validate({"questions": questions})
        except ValueError as exc:
            return {
                "success": False,
                "status": "failed",
                "data": {},
                "metadata": {"schema_version": "v2.0"},
                "summary": str(exc),
            }
        return {
            "success": True,
            "status": "awaiting_user",
            "data": {},
            "summary": "等待用户回答结构化问题",
            "metadata": {
                "schema_version": "v2.0",
                "interaction_required": {
                    "kind": "structured_question",
                    "title": "需要你的选择",
                    "questions": validated.model_dump()["questions"],
                },
            },
        }
