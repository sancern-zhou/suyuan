"""
Glob 工具 - 文件名模式搜索

使用 glob 模式快速查找文件：
- 支持通配符（*, **, ?, []）
- 递归搜索子目录
- 按修改时间排序
- 文件类型过滤
- 工作目录安全限制

使用场景：
- 查找特定扩展名的文件（*.py, *.json）
- 递归搜索目录（**/*.ts）
- 查找匹配模式的文件（test_*.py）
"""
import fnmatch
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()

# 默认忽略的目录
# 注意：backend_data_registry 移除此列表，因为用户需要访问上传的文件和定时任务配置
IGNORED_DIRS = {
    "__pycache__", ".git", ".svn", "node_modules", ".venv", "venv",
    "env", ".env", "dist", "build", ".pytest_cache", ".mypy_cache",
    ".idea", ".vscode", ".DS_Store",
}


class GlobTool(LLMTool):
    """
    文件名模式搜索工具（Glob）

    功能：
    - 使用 glob 模式查找文件
    - 支持递归搜索（**）
    - 按修改时间排序
    - 文件/目录过滤
    """

    def __init__(self):
        super().__init__(
            name="search_files",
            description="""搜索文件名（glob 模式匹配）

功能：
- 使用 glob 模式快速查找文件
- 支持通配符：* (任意字符) / ** (递归目录) / ? (单个字符) / [] (字符集)
- 按修改时间排序（最新优先）
- 自动跳过常见忽略目录（__pycache__, node_modules, .git 等）

使用场景：
- 查找特定扩展名的文件
- 递归搜索目录树
- 查找匹配命名模式的文件

示例：
- search_files(pattern="*.py", path="backend/app")              # 查找所有 Python 文件
- search_files(pattern="**/*.json", path="backend")             # 递归查找所有 JSON 文件
- search_files(pattern="test_*.py", path="backend/tests")       # 查找测试文件
- search_files(pattern="*config*", path="backend")              # 查找包含 config 的文件
- search_files(pattern="*.{py,js,ts}", path="src")              # 查找多种扩展名（需展开）

参数说明：
- pattern: glob 模式（必填）
  * "*" 匹配任意字符（不含路径分隔符）
  * "**" 递归匹配所有子目录
  * "?" 匹配单个字符
  * "[abc]" 匹配字符集中的任意字符
- path: 搜索路径（默认当前工作目录）
- files_only: 是否只返回文件（默认 True，排除目录）
- limit: 最多返回几个结果（默认 100）
- sort_by_time: 是否按修改时间排序（默认 True，最新优先）

注意：
- 工作目录限制：D:/溯源/ 及其子目录
- 自动跳过 __pycache__、node_modules、.git 等目录
- 大型目录树搜索可能较慢，建议使用 limit 限制结果数量
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        # 使用backend目录作为工作目录
        # 因为 backend_data_registry 等数据目录都在 backend 目录下
        self.working_dir = Path.cwd()  # 当前目录：/home/xckj/suyuan/backend
        # 允许访问的额外目录（项目根目录、临时目录）
        self.allowed_dirs = [self.working_dir, self.working_dir.parent, Path("/tmp")]

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        files_only: bool = True,
        limit: int = 100,
        sort_by_time: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        搜索文件名（glob 模式）

        Args:
            pattern: glob 模式（如 "*.py", "**/*.json"）
            path: 搜索路径（默认当前工作目录）
            files_only: 是否只返回文件（默认 True）
            limit: 最多返回几个结果（默认 100）
            sort_by_time: 是否按修改时间排序（默认 True）

        Returns:
            {
                "success": bool,
                "data": {
                    "files": [str],        # 文件路径列表
                    "count": int,          # 匹配文件数
                    "pattern": str,
                    "search_path": str,
                    "truncated": bool      # 是否因 limit 截断
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
                    "summary": f"搜索失败：路径不合法"
                }

            if not resolved_path.exists():
                return {
                    "success": False,
                    "error": f"路径不存在: {path}",
                    "summary": f"搜索失败：路径不存在"
                }

            # 2. 执行 glob 搜索
            matches = self._glob_search(resolved_path, pattern, files_only)

            # 3. 按修改时间排序
            if sort_by_time and matches:
                try:
                    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                except Exception as e:
                    logger.warning("glob_sort_failed", error=str(e))

            # 4. 应用 limit
            total_count = len(matches)
            truncated = total_count > limit
            if truncated:
                matches = matches[:limit]

            # 5. 转换为相对路径（便于显示）
            file_paths = []
            for match in matches:
                try:
                    rel_path = str(match.relative_to(resolved_path))
                except ValueError:
                    rel_path = str(match)
                file_paths.append(rel_path)

            logger.info(
                "glob_search_success",
                pattern=pattern,
                path=str(resolved_path),
                count=len(file_paths),
                total=total_count
            )

            return {
                "success": True,
                "data": {
                    "files": file_paths,
                    "count": len(file_paths),
                    "total_matches": total_count,
                    "pattern": pattern,
                    "search_path": str(resolved_path),
                    "truncated": truncated
                },
                "summary": self._build_summary(
                    len(file_paths), total_count, pattern, truncated
                )
            }

        except Exception as e:
            logger.error("glob_search_failed", pattern=pattern, path=path, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "summary": f"搜索失败：{str(e)[:80]}"
            }

    def _glob_search(
        self,
        root: Path,
        pattern: str,
        files_only: bool
    ) -> List[Path]:
        """执行 glob 搜索"""
        matches = []

        # 判断是否为递归模式
        is_recursive = "**" in pattern

        if is_recursive:
            # 递归搜索
            for item in root.rglob(pattern.replace("**/", "")):
                if self._should_include(item, files_only):
                    matches.append(item)
        else:
            # 非递归搜索
            for item in root.glob(pattern):
                if self._should_include(item, files_only):
                    matches.append(item)

        return matches

    def _should_include(self, path: Path, files_only: bool) -> bool:
        """判断是否应包含此路径"""
        # 跳过忽略目录
        if any(part in IGNORED_DIRS for part in path.parts):
            return False

        # 文件/目录过滤
        if files_only and not path.is_file():
            return False

        return True

    def _build_summary(
        self,
        count: int,
        total: int,
        pattern: str,
        truncated: bool
    ) -> str:
        """构建摘要信息"""
        pat_preview = pattern[:40] + ("..." if len(pattern) > 40 else "")

        if count == 0:
            return f"搜索完成：未找到匹配 \"{pat_preview}\" 的文件"

        if truncated:
            return f"搜索完成：找到 {total} 个匹配 \"{pat_preview}\" 的文件（显示前 {count} 个）"
        else:
            return f"搜索完成：找到 {count} 个匹配 \"{pat_preview}\" 的文件"

    def _resolve_path(self, path: str) -> Optional[Path]:
        """解析路径，确保在允许的目录范围内"""
        try:
            p = Path(path)
            if not p.is_absolute():
                p = self.working_dir / p
            p = p.resolve()

            # 检查是否在允许的目录范围内
            is_allowed = any(p.is_relative_to(allowed_dir) for allowed_dir in self.allowed_dirs)

            if not is_allowed:
                logger.warning("glob_path_escape", requested=path, allowed_dirs=[str(d) for d in self.allowed_dirs])
                return None
            return p
        except Exception as e:
            logger.error("glob_path_resolve_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "search_files",
            "description": """搜索文件名（glob 模式匹配）

使用 glob 模式快速查找文件。
支持通配符：* / ** / ? / []

使用场景：
- 查找特定扩展名的文件
- 递归搜索目录树
- 查找匹配命名模式的文件

注意：
- 自动跳过 __pycache__、node_modules、.git 等
- 工作目录限制：D:/溯源/ 及其子目录
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": (
                            "glob 模式。示例：\n"
                            "- \"*.py\" 查找所有 Python 文件\n"
                            "- \"**/*.json\" 递归查找所有 JSON 文件\n"
                            "- \"test_*.py\" 查找测试文件\n"
                            "- \"*config*\" 查找包含 config 的文件"
                        )
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径（文件或目录）。示例：\"backend/app\"、\"D:/溯源/backend\"",
                        "default": "."
                    },
                    "files_only": {
                        "type": "boolean",
                        "description": "是否只返回文件（排除目录）。默认 True",
                        "default": True
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回几个结果（默认 100）",
                        "default": 100
                    },
                    "sort_by_time": {
                        "type": "boolean",
                        "description": "是否按修改时间排序（最新优先）。默认 True",
                        "default": True
                    }
                },
                "required": ["pattern"]
            }
        }

    def is_available(self) -> bool:
        return True


# 创建工具实例
tool = GlobTool()
