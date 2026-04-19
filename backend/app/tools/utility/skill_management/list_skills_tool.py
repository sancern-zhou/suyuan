"""
技能管理工具 - 列出可用技能文档

技能是MD文档，描述如何使用多个工具完成复杂任务。
此工具用于发现和列出可用的技能文档。
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog
import re
from datetime import datetime

logger = structlog.get_logger()


class ListSkillsTool(LLMTool):
    """
    列出可用技能文档工具

    功能：
    - 扫描技能目录（backend/docs/skills/）
    - 读取技能索引（SKILLS_INDEX.md）
    - 支持关键词过滤
    - 返回技能列表（名称、描述、文件路径）
    """

    def __init__(self):
        super().__init__(
            name="list_skills",
            description="""列出可用的技能文档

技能是MD文档，描述如何使用多个工具完成复杂任务。
此工具帮助发现和浏览可用的技能文档。

功能：
- 列出所有可用的技能文档
- 支持关键词过滤（如 "Excel", "可视化"）
- 返回技能名称、描述和文件路径
- 读取自动生成的技能索引

使用场景：
- 需要完成复杂任务，不确定从何开始
- 想了解系统支持哪些工作流
- 寻找特定领域的技能（如Excel处理、数据可视化）

示例：
- list_skills()  # 列出所有技能
- list_skills(keyword="Excel")  # 查找Excel相关技能
- list_skills(keyword="可视化")  # 查找可视化相关技能

参数说明：
- keyword: 可选，过滤关键词（不区分大小写）
- category: 可选，分类过滤（预留字段，当前为扁平结构）

返回格式：
{
    "success": true,
    "data": {
        "skills": [
            {
                "name": "Excel处理技能",
                "file": "backend/docs/skills/excel.md",
                "description": "使用pandas和openpyxl处理Excel文件"
            }
        ],
        "count": 2
    },
    "summary": "找到2个技能文档"
}

注意：
- 技能文档位于 backend/docs/skills/ 目录
- 修改技能文档后无需重启服务（MD文档即代码）
- 找到相关技能后，使用 read_file() 阅读详细文档
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        # 技能目录路径
        self.skills_dir = Path(__file__).parent.parent.parent.parent.parent / "docs" / "skills"
        self.index_file = self.skills_dir / "SKILLS_INDEX.md"

    async def execute(
        self,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        列出可用技能文档

        Args:
            keyword: 可选，过滤关键词（不区分大小写）
            category: 可选，分类过滤（预留字段）

        Returns:
            {
                "success": bool,
                "data": {
                    "skills": [
                        {
                            "name": str,        # 技能名称
                            "file": str,        # 文件路径
                            "description": str  # 技能描述
                        }
                    ],
                    "count": int,              # 技能数量
                    "keyword": str,            # 搜索关键词（如果有）
                    "index_available": bool    # 索引文件是否可用
                },
                "summary": str
            }
        """
        try:
            # 1. 检查技能目录
            if not self.skills_dir.exists():
                logger.warning("skills_directory_not_found", path=str(self.skills_dir))
                return {
                    "success": False,
                    "error": f"技能目录不存在: {self.skills_dir}",
                    "summary": "技能目录未找到，请创建 backend/docs/skills/ 目录"
                }

            # 2. 尝试读取索引文件
            skills = self._load_skills_from_index()

            # 3. 如果索引不可用，直接扫描目录
            if not skills:
                skills = self._scan_skills_directory()
                index_available = False
            else:
                index_available = True

            # 4. 关键词过滤
            if keyword:
                keyword_lower = keyword.lower()
                skills = [
                    s for s in skills
                    if keyword_lower in s["name"].lower() or
                       keyword_lower in s.get("description", "").lower()
                ]

            logger.info(
                "list_skills_success",
                count=len(skills),
                keyword=keyword,
                index_available=index_available
            )

            return {
                "success": True,
                "data": {
                    "skills": skills,
                    "count": len(skills),
                    "keyword": keyword or "",
                    "index_available": index_available,
                    "skills_dir": str(self.skills_dir)
                },
                "summary": self._build_summary(len(skills), keyword)
            }

        except Exception as e:
            logger.error("list_skills_failed", keyword=keyword, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "summary": f"获取技能列表失败：{str(e)[:80]}"
            }

    def _load_skills_from_index(self) -> List[Dict[str, str]]:
        """从索引文件加载技能列表"""
        if not self.index_file.exists():
            return []

        try:
            content = self.index_file.read_text(encoding="utf-8")
            return self._parse_index_content(content)
        except Exception as e:
            logger.warning("load_index_failed", error=str(e))
            return []

    def _parse_index_content(self, content: str) -> List[Dict[str, str]]:
        """解析索引文件内容"""
        skills = []

        # 匹配格式: - [技能名称](文件路径.md) - 描述
        pattern = r'-\s+\[([^\]]+)\]\(([^)]+)\)\s+-\s*(.+)'
        matches = re.findall(pattern, content)

        for name, file_path, description in matches:
            # 转换为绝对路径
            full_path = str(self.skills_dir / file_path)
            skills.append({
                "name": name.strip(),
                "file": full_path,
                "description": description.strip()
            })

        return skills

    def _scan_skills_directory(self) -> List[Dict[str, str]]:
        """直接扫描技能目录（当索引不可用时）"""
        skills = []

        try:
            md_files = list(self.skills_dir.glob("*.md"))
            # 排除索引文件本身
            md_files = [f for f in md_files if f.name != "SKILLS_INDEX.md"]

            for md_file in md_files:
                # 尝试解析文档获取名称和描述
                name, description = self._parse_skill_file(md_file)
                skills.append({
                    "name": name,
                    "file": str(md_file),
                    "description": description
                })

        except Exception as e:
            logger.warning("scan_skills_directory_failed", error=str(e))

        return skills

    def _parse_skill_file(self, file_path: Path) -> tuple[str, str]:
        """解析技能文件，提取名称和描述"""
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.split('\n')

            # 第一行是 # 技能名称
            name = file_path.stem  # 默认使用文件名
            description = "暂无描述"

            for i, line in enumerate(lines):
                line = line.strip()
                if line.startswith("# ") and i < 5:  # 前5行内的标题
                    name = line[2:].strip()
                elif line.startswith("## 概述") or line.startswith("概述："):
                    # 下一行是描述
                    if i + 1 < len(lines):
                        description = lines[i + 1].strip()
                    break

            return name, description

        except Exception as e:
            logger.warning("parse_skill_file_failed", file=str(file_path), error=str(e))
            return file_path.stem, "解析失败"

    def _build_summary(self, count: int, keyword: Optional[str]) -> str:
        """构建摘要信息"""
        if keyword:
            return f"找到 {count} 个与 \"{keyword}\" 相关的技能文档"
        else:
            return f"找到 {count} 个技能文档"

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "list_skills",
            "description": """列出可用的技能文档

技能是MD文档，描述如何使用多个工具完成复杂任务。
此工具帮助发现和浏览可用的技能文档。

使用场景：
- 需要完成复杂任务，不确定从何开始
- 想了解系统支持哪些工作流
- 寻找特定领域的技能（如Excel处理、数据可视化）

注意：
- 找到相关技能后，使用 read_file() 阅读详细文档
- 技能文档位于 backend/docs/skills/ 目录
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": (
                            "过滤关键词（不区分大小写）。示例：\n"
                            "- \"Excel\" - 查找Excel相关技能\n"
                            "- \"可视化\" - 查找可视化相关技能\n"
                            "- 留空 - 列出所有技能"
                        )
                    },
                    "category": {
                        "type": "string",
                        "description": "分类过滤（预留字段，当前未使用）"
                    }
                }
            }
        }

    def is_available(self) -> bool:
        return True


# 创建工具实例
tool = ListSkillsTool()
