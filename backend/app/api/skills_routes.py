"""
技能管理 API

技能是MD文档，描述多步骤工作流。
"""

from fastapi import APIRouter, HTTPException
from pathlib import Path
import sys
import subprocess

router = APIRouter(prefix="/api/skills", tags=["skills"])

# 技能目录路径
SKILLS_DIR = Path(__file__).parent.parent.parent / "docs" / "skills"


@router.get("")
async def list_skills(keyword: str = None):
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
            return {
                "success": True,
                "data": result["data"],
                "summary": result["summary"]
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error"))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list skills: {str(e)}")


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
        # 运行索引生成脚本
        script_path = Path(__file__).parent.parent.parent / "scripts" / "generate_skills_index.py"

        if not script_path.exists():
            raise HTTPException(status_code=404, detail=f"Script not found: {script_path}")

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(script_path.parent)
        )

        if result.returncode == 0:
            return {
                "success": True,
                "message": "技能索引刷新成功"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to refresh index: {result.stderr}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh index: {str(e)}")
