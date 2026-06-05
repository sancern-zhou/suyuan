from __future__ import annotations

from typing import Any, Dict

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.utility.skill_management.skill_paths import (
    DRAFTS_DIR,
    ensure_within_directory,
    render_skill_draft_markdown,
    sanitize_skill_filename,
)


class CreateSkillDraftTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="create_skill_draft",
            description=(
                "在用户明确同意后，将已完成任务中的可复用流程保存为候选技能草稿。"
                "只写入 backend/docs/skills/.drafts/，不会发布为正式技能。"
            ),
            category=ToolCategory.TASK_MANAGEMENT,
            version="1.0.0",
            requires_context=False,
            function_schema={
                "name": "create_skill_draft",
                "description": "创建候选技能草稿。必须在用户明确同意保存技能后调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "候选技能标题。"},
                        "description": {"type": "string", "description": "一句话描述技能价值。"},
                        "applicable_scenarios": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "适用场景列表。",
                        },
                        "required_tools": {
                            "type": "array",
                            "description": "所需工具列表，可传字符串或 {name, purpose} 对象。",
                            "items": {
                                "oneOf": [
                                    {"type": "string"},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "purpose": {"type": "string"},
                                        },
                                        "required": ["name"],
                                    },
                                ]
                            },
                        },
                        "workflow_steps": {
                            "type": "array",
                            "description": "有序流程步骤。",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "purpose": {"type": "string"},
                                    "operation": {"type": "string"},
                                },
                                "required": ["title", "operation"],
                            },
                        },
                        "notes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "注意事项、坑点或质量检查。",
                        },
                        "source_summary": {"type": "string", "description": "来源任务摘要。"},
                        "source_session_id": {"type": "string", "description": "来源会话ID。"},
                        "overwrite": {
                            "type": "boolean",
                            "description": "是否覆盖同名草稿，默认 false。",
                            "default": False,
                        },
                    },
                    "required": [
                        "title",
                        "description",
                        "applicable_scenarios",
                        "required_tools",
                        "workflow_steps",
                    ],
                },
            },
        )

    async def execute(
        self,
        title: str,
        description: str,
        applicable_scenarios: list[str],
        required_tools: list[Any],
        workflow_steps: list[dict[str, Any]],
        notes: list[str] | None = None,
        source_summary: str | None = None,
        source_session_id: str | None = None,
        overwrite: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            if not title or not str(title).strip():
                raise ValueError("title 不能为空")
            if not description or not str(description).strip():
                raise ValueError("description 不能为空")
            if not workflow_steps:
                raise ValueError("workflow_steps 不能为空")

            filename = sanitize_skill_filename(title)
            DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
            draft_file = ensure_within_directory(DRAFTS_DIR / filename, DRAFTS_DIR)
            if draft_file.exists() and not overwrite:
                return {
                    "success": False,
                    "error": f"Draft already exists: {draft_file}",
                    "summary": f"候选技能草稿已存在：{draft_file.name}",
                }

            content = render_skill_draft_markdown(
                title=title,
                description=description,
                applicable_scenarios=applicable_scenarios,
                required_tools=required_tools,
                workflow_steps=workflow_steps,
                notes=notes or [],
                source_summary=source_summary,
                source_session_id=source_session_id,
            )
            draft_file.write_text(content, encoding="utf-8")

            return {
                "success": True,
                "data": {
                    "title": title,
                    "description": description,
                    "file": str(draft_file),
                    "is_draft": True,
                    "next_action": "请审核候选技能内容，确认后再发布为正式技能。",
                },
                "summary": f"已创建候选技能草稿：{draft_file.name}",
            }
        except ValueError as exc:
            return {
                "success": False,
                "error": str(exc),
                "summary": f"候选技能参数无效：{exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "summary": f"创建候选技能草稿失败：{str(exc)[:80]}",
            }
