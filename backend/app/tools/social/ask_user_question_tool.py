"""Model-facing structured question handoff."""

from app.agent.user_questions import QuestionSet
from app.tools.base.tool_interface import LLMTool, ToolCategory


class AskUserQuestionTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="ask_user_question",
            description=(
                "需要用户决策、确认口径或补充关键信息时，必须调用本工具以结构化选择题提问，"
                "禁止在对话回复中以自由文本追问后停止。仅用于答案会改变后续做法、且无法从"
                "上下文或合理默认值中确认的决策；存在常规默认值或可自行查证的事实时不要提问——"
                "选择显而易见的选项、在回复中说明并继续执行。"
            ),
            category=ToolCategory.PLANNING,
            function_schema={
                "name": "ask_user_question",
                "description": (
                    "向用户提问的唯一方式：提出 1-4 道选择题并暂停当前任务，等待回答后继续。"
                    "每题 2-4 个选项；界面自动提供其他/自由输入。推荐项放首位并在标签末尾标注（推荐）。"
                    "有合理默认值的事项不要用本工具提问；需要用户决定的事项禁止用普通对话文本直接确认。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "questions": {
                            "type": "array", "minItems": 1, "maxItems": 4,
                            "description": "要向用户提出的问题列表（1-4 道）",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {
                                        "type": "string",
                                        "description": (
                                            "完整、具体的问题，以问号结尾；"
                                            "multiSelect=true 时措辞相应调整，如\"希望启用哪些功能？\""
                                        ),
                                    },
                                    "header": {
                                        "type": "string",
                                        "maxLength": 12,
                                        "description": "展示为题头的极短标签（≤12字符），如\"输出格式\"\"技术选型\"",
                                    },
                                    "options": {
                                        "type": "array", "minItems": 2, "maxItems": 4,
                                        "description": (
                                            "该题的可选项，2-4 个；每个选项应是互斥的独立选择"
                                            "（multiSelect 时可并列）；label 在同一题内必须唯一；"
                                            "不要提供\"其他\"选项，界面会自动提供"
                                        ),
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "label": {
                                                    "type": "string",
                                                    "description": "选项展示文本，简洁（1-5个词）；推荐项放首位并在末尾标注（推荐）",
                                                },
                                                "description": {
                                                    "type": "string",
                                                    "description": "说明该选项的含义或选中后的后果，帮助用户权衡取舍",
                                                },
                                                "preview": {
                                                    "type": "string",
                                                    "description": (
                                                        "可选预览内容，聚焦该选项时展示：UI 布局 ASCII 示意、"
                                                        "代码片段、配置示例等；只能是不含 html/body/doctype/"
                                                        "script/style 标签的 HTML 片段；仅单选题支持"
                                                    ),
                                                },
                                            },
                                            "required": ["label", "description"],
                                        },
                                    },
                                    "multiSelect": {
                                        "type": "boolean",
                                        "description": "true 表示允许多选，用于彼此不互斥的选项；默认 false",
                                    },
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
