"""
技能管理 API

技能是MD文档，描述多步骤工作流。
"""

from fastapi import APIRouter, HTTPException
from app.services.skills_index import generate_skills_index
from app.tools.utility.skill_management.skill_paths import (
    DRAFTS_DIR,
    SKILLS_DIR,
    parse_skill_metadata,
    resolve_skill_file,
)

router = APIRouter(prefix="/api/skills", tags=["skills"])

@router.get("")
async def list_skills(keyword: str = None, mode: str = None):
    """
    列出所有技能文档

    参数:
        keyword: 可选，过滤关键词

    返回:
        {
            "success": true,
            "data": {
                "skills": [...],
                "count": 3
            },
            "summary": "找到 3 个技能文档"
        }
    """
    try:
        from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool

        tool = ListSkillsTool()
        result = await tool.execute(keyword=keyword)

        if result.get("success"):
            from app.agent.prompts.tool_registry import get_tools_by_mode
            from app.agent.selection_context import describe_skill_item

            available_tools = set(get_tools_by_mode(mode)) if mode else None
            data = dict(result["data"])
            data["skills"] = [
                describe_skill_item(item, available_tools=available_tools)
                for item in data.get("skills", [])
            ]
            data["skills"] = [item for item in data["skills"] if item["enabled"]]
            data["count"] = len(data["skills"])
            return {
                "success": True,
                "data": data,
                "summary": result["summary"]
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error"))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list skills: {str(e)}")


@router.get("/drafts")
async def list_skill_drafts():
    """列出候选技能草稿。"""
    try:
        if not DRAFTS_DIR.exists():
            return {
                "success": True,
                "data": {"drafts": [], "count": 0, "drafts_dir": str(DRAFTS_DIR)},
                "summary": "当前没有候选技能草稿",
            }

        drafts = []
        for draft_file in sorted(DRAFTS_DIR.glob("*.md")):
            content = draft_file.read_text(encoding="utf-8")
            metadata = parse_skill_metadata(content, draft_file.name)
            drafts.append({
                "name": metadata["title"],
                "description": metadata["description"],
                "file": str(draft_file),
                "is_draft": True,
            })

        return {
            "success": True,
            "data": {"drafts": drafts, "count": len(drafts), "drafts_dir": str(DRAFTS_DIR)},
            "summary": f"找到 {len(drafts)} 个候选技能草稿",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list skill drafts: {str(e)}")


@router.get("/drafts/{draft_name}")
async def get_skill_draft_detail(draft_name: str):
    """读取候选技能草稿详情。"""
    try:
        draft_file = resolve_skill_file(
            draft_name,
            include_drafts=True,
            skills_dir=DRAFTS_DIR,
            drafts_dir=DRAFTS_DIR,
        )
        content = draft_file.read_text(encoding="utf-8")
        metadata = parse_skill_metadata(content, draft_file.name)
        return {
            "success": True,
            "data": {
                "name": metadata["title"],
                "description": metadata["description"],
                "file": str(draft_file),
                "is_draft": True,
                "content": content,
            },
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Draft not found: {draft_name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get skill draft: {str(e)}")


@router.put("/drafts/{draft_name}")
async def update_skill_draft_detail(draft_name: str, content: dict):
    """更新候选技能草稿内容。"""
    try:
        new_content = content.get("content")
        if not new_content:
            raise HTTPException(status_code=400, detail="Content is required")

        draft_file = resolve_skill_file(
            draft_name,
            include_drafts=True,
            skills_dir=DRAFTS_DIR,
            drafts_dir=DRAFTS_DIR,
        )
        draft_file.write_text(new_content, encoding="utf-8")
        metadata = parse_skill_metadata(new_content, draft_file.name)
        return {
            "success": True,
            "data": {
                "name": metadata["title"],
                "description": metadata["description"],
                "file": str(draft_file),
                "is_draft": True,
                "content": new_content,
            },
            "message": "候选技能草稿保存成功",
        }
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Draft not found: {draft_name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update skill draft: {str(e)}")


@router.get("/{skill_name}")
async def get_skill_detail(skill_name: str):
    """
    获取单个技能的详细内容

    参数:
        skill_name: 技能名称（如 "excel.md" 或 "excel"）

    返回:
        {
            "success": true,
            "data": {
                "name": "技能名称",
                "file": "文件路径",
                "description": "描述",
                "content": "文档内容"
            }
        }
    """
    try:
        # 标准化文件名
        if not skill_name.endswith('.md'):
            skill_name = f"{skill_name}.md"

        skill_file = SKILLS_DIR / skill_name

        if not skill_file.exists():
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")

        # 读取文件内容
        content = skill_file.read_text(encoding='utf-8')

        # 提取基本信息（第一级标题作为名称）
        lines = content.split('\n')
        name = skill_file.stem
        description = "暂无描述"

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if line_stripped.startswith("# ") and name == skill_file.stem:
                name = line_stripped[2:].strip()
            elif line_stripped.startswith("## 概述") or line_stripped.startswith("概述："):
                # 尝试读取下一行作为描述
                if i + 1 < len(lines):
                    desc_line = lines[i + 1].strip()
                    if desc_line and not desc_line.startswith("#"):
                        description = desc_line
                break

        return {
            "success": True,
            "data": {
                "name": name,
                "file": str(skill_file),
                "description": description,
                "content": content
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get skill detail: {str(e)}")


@router.put("/{skill_name}")
async def update_skill(skill_name: str, content: dict):
    """
    更新技能文档内容

    参数:
        skill_name: 技能名称（如 "excel.md" 或 "excel"）
        content: {"content": "新的文档内容"}

    返回:
        {
            "success": true,
            "message": "技能文档保存成功"
        }
    """
    try:
        # 标准化文件名
        if not skill_name.endswith('.md'):
            skill_name = f"{skill_name}.md"

        skill_file = SKILLS_DIR / skill_name

        if not skill_file.exists():
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")

        # 获取新的内容
        new_content = content.get("content")
        if not new_content:
            raise HTTPException(status_code=400, detail="Content is required")

        # 写入文件
        skill_file.write_text(new_content, encoding='utf-8')

        return {
            "success": True,
            "message": "技能文档保存成功"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {str(e)}")


@router.post("/refresh-index")
async def refresh_skills_index():
    """
    重新生成技能索引

    返回:
        {
            "success": true,
            "message": "技能索引刷新成功"
        }
    """
    try:
        result = generate_skills_index(SKILLS_DIR)
        return {
            "success": True,
            "message": "技能索引刷新成功",
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh index: {str(e)}")
