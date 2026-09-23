from __future__ import annotations

from typing import Any, Dict

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.utility.skill_management.skill_paths import (
    active_skill_paths,
    list_skill_titles,
    parse_skill_metadata,
    resolve_skill_file,
)


class ViewSkillTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="view_skill",
            description=(
                "读取技能文档完整内容。用于在 list_skills 找到相关技能后查看详细流程；"
                "支持按技能标题（如「分析报告通用工作流」）或文件名读取；"
                "默认只读正式技能，include_drafts=true 时也可读取候选草稿。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False,
            function_schema={
                "name": "view_skill",
                "description": "读取指定技能文档的完整内容，支持按技能标题或文件名查找。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "技能标题或文件名，例如「分析报告通用工作流」、excel 或 excel.md。",
                        },
                        "include_drafts": {
                            "type": "boolean",
                            "description": "是否允许读取 .drafts 候选技能草稿。",
                            "default": False,
                        },
                    },
                    "required": ["name"],
                },
            },
        )

    async def execute(self, name: str, include_drafts: bool = False, **kwargs) -> Dict[str, Any]:
        skills_dir = drafts_dir = None
        try:
            skills_dir, drafts_dir = active_skill_paths()
            skill_file = resolve_skill_file(
                name,
                include_drafts=include_drafts,
                skills_dir=skills_dir,
                drafts_dir=drafts_dir,
            )
            content = skill_file.read_text(encoding="utf-8")
            metadata = parse_skill_metadata(content, skill_file.name)
            is_draft = drafts_dir.resolve() in skill_file.resolve().parents

            return {
                "success": True,
                "data": {
                    "name": metadata["title"],
                    "description": metadata["description"],
                    "file": str(skill_file),
                    "is_draft": is_draft,
                    "content": content,
                },
                "summary": f"已读取技能文档：{metadata['title']}",
            }
        except FileNotFoundError:
            try:
                titles = list_skill_titles(
                    skills_dir=skills_dir,
                    drafts_dir=drafts_dir,
                    include_drafts=include_drafts,
                )
            except Exception:
                titles = []
            hint = f"。可用技能：{'、'.join(titles)}" if titles else ""
            return {
                "success": False,
                "error": f"Skill not found: {name}",
                "summary": f"未找到技能文档：{name}{hint}",
            }
        except ValueError as exc:
            return {
                "success": False,
                "error": str(exc),
                "summary": f"技能名称或路径不安全：{exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "summary": f"读取技能失败：{str(exc)[:80]}",
            }
