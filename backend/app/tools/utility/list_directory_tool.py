"""
ListDirectory 工具 - 列出目录内容

功能：
- 列出目录中的文件和子目录
- 显示文件大小、修改时间
- 支持递归列出子目录
- 文件类型过滤
- 工作目录安全限制

使用场景：
- 查看目录结构
- 检查文件是否存在
- 获取文件元信息
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()

# 默认忽略的目录
# 注意：backend_data_registry 移除此列表，因为用户需要访问上传的文件
IGNORED_DIRS = {
    "__pycache__", ".git", ".svn", "node_modules", ".venv", "venv",
    "env", ".env", "dist", "build", ".pytest_cache", ".mypy_cache",
    ".idea", ".vscode", ".DS_Store",
}


class ListDirectoryTool(LLMTool):
    """
    列出目录内容工具

    功能：
    - 列出目录中的文件和子目录
    - 显示文件大小、修改时间、类型
    - 支持递归列出
    - 文件类型过滤
    """

    def __init__(self):
        super().__init__(
            name="list_directory",
            description="""列出目录内容

功能：
- 列出指定目录中的文件和子目录
- 显示文件大小、修改时间、类型（文件/目录）
- 支持递归列出所有子目录
- 支持文件类型过滤

使用场景：
- 查看目录结构
- 检查文件是否存在
- 获取文件元信息（大小、修改时间）
- 浏览项目目录

示例：
- list_directory(path="backend/app")                    # 列出目录内容
- list_directory(path="backend/app", recursive=True)    # 递归列出所有子目录
- list_directory(path="backend", show_hidden=False)     # 不显示隐藏文件
- list_directory(path="data", sort_by="size")           # 按文件大小排序

参数说明：
- path: 目录路径（必填）
- recursive: 是否递归列出子目录（默认 False）
- show_hidden: 是否显示隐藏文件（默认 False）
- sort_by: 排序方式（name/size/time，默认 name）
- limit: 最多返回几个条目（默认 1000）

注意：
- 工作目录限制：D:/溯源/ 及其子目录
- 自动跳过 __pycache__、node_modules、.git 等目录
- 递归模式可能较慢，建议使用 limit 限制
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        # 使用项目根目录（后端目录的父目录，动态适配实际部署路径）
        # 当前工作目录是 backend 目录，parent 是项目根目录
        self.working_dir = Path.cwd().parent  # 动态获取：D:\溯源\ 或 /opt/app/ 等

    async def execute(
        self,
        path: str,
        recursive: bool = False,
        show_hidden: bool = False,
        sort_by: str = "name",
        limit: int = 1000,
        **kwargs
    ) -> Dict[str, Any]:
        """
        列出目录内容

        Args:
            path: 目录路径
            recursive: 是否递归列出子目录（默认 False）
            show_hidden: 是否显示隐藏文件（默认 False）
            sort_by: 排序方式（name/size/time，默认 name）
            limit: 最多返回几个条目（默认 1000）

        Returns:
            {
                "success": bool,
                "data": {
                    "entries": [
                        {
                            "name": str,
                            "path": str,
                            "type": "file"|"directory",
                            "size": int,           # 字节（仅文件）
                            "modified": str,       # ISO格式时间
                        }
                    ],
                    "count": int,
                    "total": int,
                    "truncated": bool
                },
                "summary": str
            }
        """
        try:
            # 1. 路径解析
            resolved_path = self._resolve_path(path)
            if not resolved_path:
                return {
                    "success": False,
                    "error": f"路径无效或超出工作目录范围: {path}",
                    "summary": f"列出失败：路径不合法"
                }

            if not resolved_path.exists():
                return {
                    "success": False,
                    "error": f"路径不存在: {path}",
                    "summary": f"列出失败：路径不存在"
                }

            if not resolved_path.is_dir():
                return {
                    "success": False,
                    "error": f"路径不是目录: {path}",
                    "summary": f"列出失败：路径不是目录"
                }

            # 2. 收集条目
            entries = self._collect_entries(
                resolved_path,
                recursive,
                show_hidden
            )

            # 3. 排序
            entries = self._sort_entries(entries, sort_by)

            # 4. 应用 limit
            total_count = len(entries)
            truncated = total_count > limit
            if truncated:
                entries = entries[:limit]

            logger.info(
                "list_directory_success",
                path=str(resolved_path),
                count=len(entries),
                total=total_count,
                recursive=recursive
            )

            # ⭐ 新增：路径引导信息（帮助 LLM 理解路径规则）
            path_guide = self._build_path_guide(path, resolved_path)

            return {
                "success": True,
                "data": {
                    "entries": entries,
                    "count": len(entries),
                    "total": total_count,
                    "truncated": truncated,
                    "path": str(resolved_path),
                    "_path_guide": path_guide  # 路径使用指南
                },
                "summary": self._build_summary(
                    len(entries), total_count, str(resolved_path), truncated
                )
            }

        except Exception as e:
            logger.error("list_directory_failed", path=path, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "summary": f"列出失败：{str(e)[:80]}"
            }

    def _collect_entries(
        self,
        root: Path,
        recursive: bool,
        show_hidden: bool
    ) -> List[Dict[str, Any]]:
        """收集目录条目"""
        entries = []

        if recursive:
            # 递归模式
            for item in root.rglob("*"):
                if self._should_include(item, show_hidden):
                    entry = self._create_entry(item, root)
                    if entry:
                        entries.append(entry)
        else:
            # 非递归模式
            for item in root.iterdir():
                if self._should_include(item, show_hidden):
                    entry = self._create_entry(item, root)
                    if entry:
                        entries.append(entry)

        return entries

    def _should_include(self, path: Path, show_hidden: bool) -> bool:
        """判断是否应包含此路径"""
        # 跳过忽略目录
        if any(part in IGNORED_DIRS for part in path.parts):
            return False

        # 隐藏文件过滤
        if not show_hidden and path.name.startswith('.'):
            return False

        return True

    def _create_entry(self, path: Path, root: Path) -> Optional[Dict[str, Any]]:
        """
        创建条目信息

        修改说明：
        - 返回的路径字段改为相对于工作目录的相对路径（更清晰）
        - 添加 access_path 字段，建议 LLM 下次使用的路径
        """
        try:
            stat = path.stat()

            # ⭐ 修改：计算相对于工作目录的路径（而不是相对于 root）
            try:
                rel_to_working = str(path.relative_to(self.working_dir)).replace("\\", "/")
            except ValueError:
                # 如果不在工作目录下，降级使用相对于 root 的路径
                try:
                    rel_to_working = str(path.relative_to(root)).replace("\\", "/")
                except ValueError:
                    rel_to_working = str(path).replace("\\", "/")

            entry = {
                "name": path.name,
                "type": "directory" if path.is_dir() else "file",
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                # ⭐ 新增：明确的路径字段
                "path": rel_to_working,  # 相对于工作目录的路径（用于后续访问）
            }

            # 文件大小（仅文件）
            if path.is_file():
                entry["size"] = stat.st_size

            return entry

        except Exception as e:
            logger.warning("entry_creation_failed", path=str(path), error=str(e))
            return None

    def _sort_entries(
        self,
        entries: List[Dict[str, Any]],
        sort_by: str
    ) -> List[Dict[str, Any]]:
        """排序条目"""
        if sort_by == "size":
            # 按大小排序（目录视为0）
            entries.sort(key=lambda e: e.get("size", 0), reverse=True)
        elif sort_by == "time":
            # 按修改时间排序（最新优先）
            entries.sort(key=lambda e: e["modified"], reverse=True)
        else:  # name
            # 按名称排序（目录在前）
            entries.sort(key=lambda e: (e["type"] != "directory", e["name"].lower()))

        return entries

    def _build_summary(
        self,
        count: int,
        total: int,
        path: str,
        truncated: bool
    ) -> str:
        """构建摘要信息"""
        path_preview = path[-50:] if len(path) > 50 else path

        if count == 0:
            return f"目录为空：{path_preview}"

        if truncated:
            return f"列出完成：{path_preview} 包含 {total} 个条目（显示前 {count} 个）"
        else:
            return f"列出完成：{path_preview} 包含 {count} 个条目"

    def _build_path_guide(self, input_path: str, resolved_path: Path) -> dict:
        """
        构建路径使用指南（帮助 LLM 理解路径规则）

        设计原则：
        - 自描述：通过返回值告诉 LLM 路径应该如何使用
        - 纠正常见错误：检测路径重复并提供修正建议
        - 提供清晰示例：给出具体的路径使用示例
        """
        import os

        # 检测路径重复问题
        resolved_str = str(resolved_path)
        working_str = str(self.working_dir)

        # 检测是否包含工作目录的重复
        has_duplication = False
        duplication_parts = []
        try:
            rel_to_working = resolved_path.relative_to(self.working_dir)
            # 检查相对路径的第一部分是否是工作目录名
            if len(rel_to_working.parts) > 0 and rel_to_working.parts[0] == self.working_dir.name:
                has_duplication = True
                duplication_parts = list(rel_to_working.parts)
        except ValueError:
            pass

        # 生成正确的相对路径（去除重复）
        if has_duplication and len(duplication_parts) > 1:
            correct_relative = os.path.join(*duplication_parts[1:])  # 去掉第一个重复部分
            warning = f"检测到路径重复：'{input_path}' 包含工作目录名 '{self.working_dir.name}'"
            suggestion = f"正确路径应为：'{correct_relative}' 或绝对路径"
        else:
            try:
                correct_relative = str(resolved_path.relative_to(self.working_dir)).replace("\\", "/")
                warning = None
                suggestion = None
            except ValueError:
                correct_relative = input_path
                warning = "路径超出工作目录范围"
                suggestion = "请使用工作目录内的路径"

        # 构建引导信息
        guide = {
            "working_directory": working_str.replace("\\", "/"),
            "path_rule": "所有路径都是相对于工作目录的相对路径",
            "your_input": input_path,
            "resolved_to": resolved_str.replace("\\", "/"),
        }

        # 如果有警告，添加警告信息
        if warning:
            # 简化绝对路径格式
            abs_path_display = resolved_str.replace("\\", "/")
            guide["warning"] = warning
            guide["suggestion"] = suggestion
            guide["correct_usage"] = [
                f"[OK] 相对路径：'{correct_relative}'",
                f"[OK] 绝对路径：'{abs_path_display}'",
                f"[ERROR] 错误：'{input_path}'（包含工作目录名）"
            ]
        else:
            # 路径正确，提供正常使用示例
            guide["status"] = "path_correct"
            guide["examples"] = [
                f"访问子目录：path='{correct_relative}/子目录名'",
                f"访问文件：path='{correct_relative}/文件名.txt'",
                f"返回上级：path='..'"
            ]

        return guide

    def _resolve_path(self, path: str) -> Optional[Path]:
        """解析路径，确保在工作目录范围内"""
        try:
            p = Path(path)
            if not p.is_absolute():
                p = self.working_dir / p
            p = p.resolve()

            if not p.is_relative_to(self.working_dir):
                logger.warning("list_directory_path_escape", requested=path, allowed=str(self.working_dir))
                return None
            return p
        except Exception as e:
            logger.error("list_directory_path_resolve_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "list_directory",
            "description": """列出目录内容

列出指定目录中的文件和子目录，显示文件大小、修改时间等信息。

使用场景：
- 查看目录结构
- 检查文件是否存在
- 获取文件元信息

注意：
- 自动跳过 __pycache__、node_modules、.git 等
- 工作目录限制：D:/溯源/ 及其子目录
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径。示例：\"backend/app\"、\"D:/溯源/backend\""
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归列出所有子目录（默认 False）",
                        "default": False
                    },
                    "show_hidden": {
                        "type": "boolean",
                        "description": "是否显示隐藏文件（以 . 开头的文件，默认 False）",
                        "default": False
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["name", "size", "time"],
                        "description": "排序方式：name（名称）/ size（大小）/ time（修改时间），默认 name",
                        "default": "name"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回几个条目（默认 1000）",
                        "default": 1000
                    }
                },
                "required": ["path"]
            }
        }

    def is_available(self) -> bool:
        return True


# 创建工具实例
tool = ListDirectoryTool()
