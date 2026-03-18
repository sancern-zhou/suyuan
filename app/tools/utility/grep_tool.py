"""
Grep 工具 - 正则搜索文件内容

纯 Python 实现（无需外部依赖），功能对标 ripgrep：
- 支持正则表达式搜索
- 三种输出模式：内容行 / 文件路径 / 匹配数量
- 文件类型过滤（glob 模式 / 类型别名）
- 上下文行显示（-A / -B / -C）
- 大小写不敏感 / 多行匹配
- 工作目录安全限制
"""
import re
import fnmatch
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()

# 文件类型别名映射（类似 rg --type）
FILE_TYPE_MAP = {
    "py":   ["*.py"],
    "js":   ["*.js", "*.mjs", "*.cjs"],
    "ts":   ["*.ts", "*.tsx"],
    "json": ["*.json"],
    "yaml": ["*.yaml", "*.yml"],
    "md":   ["*.md", "*.markdown"],
    "txt":  ["*.txt"],
    "html": ["*.html", "*.htm"],
    "css":  ["*.css", "*.scss", "*.less"],
    "sh":   ["*.sh", "*.bash"],
    "sql":  ["*.sql"],
    "xml":  ["*.xml"],
    "toml": ["*.toml"],
    "ini":  ["*.ini", "*.cfg"],
    "env":  ["*.env", ".env*"],
    "log":  ["*.log"],
    "csv":  ["*.csv"],
}

# 二进制文件扩展名（跳过）
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".pyc", ".pyd",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".ttf", ".woff", ".woff2", ".eot",
    ".db", ".sqlite", ".pkl", ".npy", ".npz",
}

# 默认忽略的目录
IGNORED_DIRS = {
    "__pycache__", ".git", ".svn", "node_modules", ".venv", "venv",
    "env", ".env", "dist", "build", ".pytest_cache", ".mypy_cache",
    "backend_data_registry", ".idea", ".vscode",
}


class GrepTool(LLMTool):
    """
    文件内容搜索工具

    功能：
    - 正则表达式搜索文件内容
    - 三种输出模式：content / files_with_matches / count
    - 文件过滤：glob 模式或类型别名
    - 上下文行：-A（后）/ -B（前）/ -C（前后）
    - 输出限制：head_limit / offset
    """

    def __init__(self):
        super().__init__(
            name="grep",
            description="""搜索文件内容（正则表达式，类似 ripgrep）

功能：
- 在文件或目录中搜索匹配正则表达式的内容
- 三种输出模式：content（匹配行）/ files_with_matches（文件路径）/ count（匹配数）
- 支持文件过滤（glob 模式或文件类型）
- 支持显示匹配行的上下文（前后几行）

示例：
- grep(pattern="class.*Agent", path="backend/app/agent")          # 搜索类定义
- grep(pattern="def execute", path="backend/app/tools", type="py") # 仅搜索 Python 文件
- grep(pattern="ERROR", path="backend/app", output_mode="count")   # 统计错误出现次数
- grep(pattern="import.*asyncio", glob="*.py", context=2)          # 带上下文行
- grep(pattern="PORT", path="backend/app/config.py", output_mode="content") # 搜索单个文件

参数说明：
- pattern: 正则表达式（必填）
- path: 搜索路径，文件或目录（默认当前工作目录）
- output_mode: content（匹配行）/ files_with_matches（文件列表）/ count（统计）
- glob: 文件名过滤（如 "*.py", "**/*.ts"）
- type: 文件类型别名（py/js/ts/json/yaml/md/txt/html/css/sh/sql/xml/toml/ini）
- context: 匹配行前后各显示几行（等同于 -C）
- A: 匹配行后显示几行（等同于 -A）
- B: 匹配行前显示几行（等同于 -B）
- case_insensitive: 是否忽略大小写（默认 False）
- multiline: 是否多行匹配（默认 False）
- head_limit: 最多返回几条结果（默认 0 不限制）
- show_line_numbers: 是否显示行号（默认 True）

限制：
- 工作目录：D:/溯源/ 及其子目录
- 自动跳过二进制文件
- 自动跳过 __pycache__、node_modules、.git 等目录
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        self.working_dir = Path.cwd().parent  # D:\溯源\ 或 /opt/app/ 等

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        output_mode: str = "files_with_matches",
        glob: Optional[str] = None,
        type: Optional[str] = None,
        context: int = 0,
        A: int = 0,
        B: int = 0,
        case_insensitive: bool = False,
        multiline: bool = False,
        head_limit: int = 0,
        show_line_numbers: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        搜索文件内容

        Returns:
            {
                "success": bool,
                "data": {
                    "results": [...],      # 搜索结果
                    "total_matches": int,  # 总匹配数
                    "files_searched": int, # 搜索文件数
                    "files_matched": int,  # 匹配文件数
                    "output_mode": str,
                    "pattern": str
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

            # 2. 编译正则表达式
            regex_flags = 0
            if case_insensitive:
                regex_flags |= re.IGNORECASE
            if multiline:
                regex_flags |= re.MULTILINE | re.DOTALL

            try:
                compiled_pattern = re.compile(pattern, regex_flags)
            except re.error as e:
                return {
                    "success": False,
                    "error": f"正则表达式无效: {str(e)}",
                    "summary": f"搜索失败：正则语法错误"
                }

            # 3. 确定上下文行数
            lines_before = max(B, context)
            lines_after = max(A, context)

            # 4. 收集要搜索的文件
            target_files = self._collect_files(resolved_path, glob, type)

            # 5. 执行搜索
            results = []
            total_matches = 0
            files_matched = 0

            for file_path in target_files:
                file_results, match_count = self._search_file(
                    file_path,
                    compiled_pattern,
                    output_mode,
                    lines_before,
                    lines_after,
                    show_line_numbers,
                    resolved_path  # 用于计算相对路径
                )

                if match_count > 0:
                    files_matched += 1
                    total_matches += match_count
                    results.extend(file_results)

                    # 应用 head_limit（对 content 模式逐条限制）
                    if head_limit > 0 and output_mode == "content" and len(results) >= head_limit:
                        results = results[:head_limit]
                        break

            # 6. 对 files_with_matches 和 count 模式应用 head_limit
            if head_limit > 0 and output_mode != "content":
                results = results[:head_limit]

            # 7. 格式化输出
            output_text = self._format_output(results, output_mode)

            return {
                "success": True,
                "data": {
                    "results": results,
                    "output_text": output_text,
                    "total_matches": total_matches,
                    "files_searched": len(target_files),
                    "files_matched": files_matched,
                    "output_mode": output_mode,
                    "pattern": pattern,
                    "path": str(resolved_path)
                },
                "summary": self._build_summary(
                    output_mode, total_matches, files_matched,
                    len(target_files), pattern
                )
            }

        except Exception as e:
            logger.error("grep_failed", pattern=pattern, path=path, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "summary": f"搜索失败：{str(e)[:80]}"
            }

    def _collect_files(
        self,
        root: Path,
        glob_pattern: Optional[str],
        file_type: Optional[str]
    ) -> List[Path]:
        """收集要搜索的文件列表"""
        # 如果是单个文件，直接返回
        if root.is_file():
            return [root] if not self._is_binary(root) else []

        # 确定文件过滤模式
        type_patterns: List[str] = []
        if file_type and file_type in FILE_TYPE_MAP:
            type_patterns = FILE_TYPE_MAP[file_type]
        elif glob_pattern:
            # 将 glob 拆分为文件名模式（忽略路径部分用于简单匹配）
            type_patterns = [glob_pattern]

        files = []
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue

            # 跳过忽略目录
            if any(part in IGNORED_DIRS for part in file_path.parts):
                continue

            # 跳过二进制文件
            if self._is_binary(file_path):
                continue

            # 文件类型过滤
            if type_patterns:
                matched = False
                for tp in type_patterns:
                    # 支持 **/ 前缀的 glob
                    name_pattern = tp.lstrip("**/")
                    if fnmatch.fnmatch(file_path.name, name_pattern):
                        matched = True
                        break
                    # 也尝试完整路径匹配
                    if fnmatch.fnmatch(str(file_path), tp):
                        matched = True
                        break
                if not matched:
                    continue

            files.append(file_path)

        return sorted(files)

    def _search_file(
        self,
        file_path: Path,
        pattern: re.Pattern,
        output_mode: str,
        lines_before: int,
        lines_after: int,
        show_line_numbers: bool,
        root: Path
    ) -> Tuple[List[Any], int]:
        """在单个文件中搜索，返回 (结果列表, 匹配数)"""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return [], 0

        # 计算相对路径（用于显示）
        try:
            rel_path = str(file_path.relative_to(root)) if root.is_dir() else file_path.name
        except ValueError:
            rel_path = str(file_path)

        lines = content.splitlines()
        match_count = 0
        results = []

        if output_mode == "count":
            # 仅统计模式：计算总匹配行数
            for line in lines:
                if pattern.search(line):
                    match_count += 1
            if match_count > 0:
                results.append({
                    "file": rel_path,
                    "count": match_count
                })
            return results, match_count

        elif output_mode == "files_with_matches":
            # 文件路径模式：只要有一个匹配就收录文件
            for line in lines:
                if pattern.search(line):
                    match_count += 1
                    break
            if match_count > 0:
                results.append(rel_path)
            return results, match_count

        else:  # content 模式
            # 找到所有匹配行的索引
            matched_line_indices = set()
            for i, line in enumerate(lines):
                if pattern.search(line):
                    matched_line_indices.add(i)
                    match_count += 1

            if not matched_line_indices:
                return [], 0

            # 计算需要显示的行范围（含上下文）
            display_ranges: List[Tuple[int, int, bool]] = []  # (start, end, is_match)
            covered = set()

            for idx in sorted(matched_line_indices):
                start = max(0, idx - lines_before)
                end = min(len(lines) - 1, idx + lines_after)
                for i in range(start, end + 1):
                    if i not in covered:
                        covered.add(i)
                        display_ranges.append((
                            i + 1,           # 行号（1-based）
                            lines[i],        # 行内容
                            i in matched_line_indices  # 是否为匹配行
                        ))

            # 格式化每个匹配块
            current_block_lines = []
            prev_lineno = None

            for lineno, line_content, is_match in display_ranges:
                # 不连续时插入分隔符
                if prev_lineno is not None and lineno > prev_lineno + 1:
                    if current_block_lines:
                        results.append({
                            "file": rel_path,
                            "lines": current_block_lines
                        })
                        current_block_lines = []

                entry: Dict[str, Any] = {"lineno": lineno, "text": line_content}
                if is_match:
                    entry["match"] = True
                current_block_lines.append(entry)
                prev_lineno = lineno

            if current_block_lines:
                results.append({
                    "file": rel_path,
                    "lines": current_block_lines
                })

            return results, match_count

    def _format_output(self, results: List[Any], output_mode: str) -> str:
        """将结构化结果转换为可读文本"""
        if not results:
            return "(无匹配)"

        lines = []
        if output_mode == "files_with_matches":
            lines = [str(r) for r in results]

        elif output_mode == "count":
            for r in results:
                lines.append(f"{r['file']}: {r['count']}")

        else:  # content
            for block in results:
                file_name = block["file"]
                for entry in block["lines"]:
                    lineno = entry["lineno"]
                    text = entry["text"]
                    is_match = entry.get("match", False)
                    prefix = f"{file_name}:{lineno}:" if is_match else f"{file_name}:{lineno}-"
                    lines.append(f"{prefix}{text}")
                lines.append("--")

            # 移除末尾分隔符
            if lines and lines[-1] == "--":
                lines.pop()

        return "\n".join(lines)

    def _build_summary(
        self,
        output_mode: str,
        total_matches: int,
        files_matched: int,
        files_searched: int,
        pattern: str
    ) -> str:
        pat_preview = pattern[:30] + ("..." if len(pattern) > 30 else "")
        if total_matches == 0:
            return f"搜索完成：未找到匹配 \"{pat_preview}\"（共搜索 {files_searched} 个文件）"

        if output_mode == "files_with_matches":
            return (f"搜索完成：在 {files_matched}/{files_searched} 个文件中找到"
                    f" \"{pat_preview}\" 的匹配")
        elif output_mode == "count":
            return (f"统计完成：\"{pat_preview}\" 共出现 {total_matches} 次，"
                    f"涉及 {files_matched} 个文件")
        else:
            return (f"搜索完成：找到 {total_matches} 处匹配 \"{pat_preview}\"，"
                    f"涉及 {files_matched}/{files_searched} 个文件")

    def _is_binary(self, file_path: Path) -> bool:
        """判断是否为二进制文件"""
        return file_path.suffix.lower() in BINARY_EXTENSIONS

    def _resolve_path(self, path: str) -> Optional[Path]:
        """解析路径，确保在工作目录范围内"""
        try:
            p = Path(path)
            if not p.is_absolute():
                p = self.working_dir / p
            p = p.resolve()

            if not p.is_relative_to(self.working_dir):
                logger.warning("grep_path_escape", requested=path, allowed=str(self.working_dir))
                return None
            return p
        except Exception as e:
            logger.error("grep_path_resolve_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "grep",
            "description": """搜索文件内容（正则表达式，类似 ripgrep）

在文件或目录中搜索正则表达式匹配的内容。
支持三种输出模式、文件类型过滤、上下文行显示。

使用场景：
- 查找代码中的类/函数定义
- 搜索配置文件中的参数
- 统计关键词出现次数
- 定位错误日志

注意：
- 自动跳过二进制文件、__pycache__、node_modules 等
- 工作目录限制：D:/溯源/ 及其子目录
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "正则表达式模式。示例：\"class.*Agent\"、\"def execute\"、\"PORT\\s*=\\s*\\d+\""
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径（文件或目录）。示例：\"backend/app/agent\"、\"backend/app/config.py\"",
                        "default": "."
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["content", "files_with_matches", "count"],
                        "description": (
                            "输出模式：\n"
                            "- content: 显示匹配的具体行内容（默认建议）\n"
                            "- files_with_matches: 只显示包含匹配的文件路径（快速定位）\n"
                            "- count: 统计每个文件的匹配次数"
                        ),
                        "default": "files_with_matches"
                    },
                    "glob": {
                        "type": "string",
                        "description": "文件名过滤 glob 模式。示例：\"*.py\"、\"*.{ts,tsx}\"、\"**/*.json\""
                    },
                    "type": {
                        "type": "string",
                        "enum": list(FILE_TYPE_MAP.keys()),
                        "description": "文件类型别名（比 glob 更简洁）。示例：\"py\" 等同于 glob=\"*.py\""
                    },
                    "context": {
                        "type": "integer",
                        "description": "匹配行前后各显示几行（等同于 rg -C）",
                        "default": 0
                    },
                    "A": {
                        "type": "integer",
                        "description": "匹配行后显示几行（等同于 rg -A）",
                        "default": 0
                    },
                    "B": {
                        "type": "integer",
                        "description": "匹配行前显示几行（等同于 rg -B）",
                        "default": 0
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "是否忽略大小写（等同于 rg -i）",
                        "default": False
                    },
                    "multiline": {
                        "type": "boolean",
                        "description": "是否多行匹配，让 . 能匹配换行符（等同于 rg -U --multiline-dotall）",
                        "default": False
                    },
                    "head_limit": {
                        "type": "integer",
                        "description": "最多返回几条结果（0 表示不限制）",
                        "default": 0
                    },
                    "show_line_numbers": {
                        "type": "boolean",
                        "description": "是否在 content 模式下显示行号",
                        "default": True
                    }
                },
                "required": ["pattern"]
            }
        }

    def is_available(self) -> bool:
        return True


# 创建工具实例
tool = GrepTool()
