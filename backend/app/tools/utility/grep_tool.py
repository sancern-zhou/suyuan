"""
Grep 工具 - 基于ripgrep的高速文件内容搜索（完整版）

参照 Claude Code 官方实现，支持完整功能特性。

依赖：ripgrep (rg命令)
安装：
  - Ubuntu/Debian: apt install ripgrep
  - macOS: brew install ripgrep
  - 其他: https://github.com/BurntSushi/ripgrep

特性：
- 三种输出模式：content / files_with_matches / count
- 精细上下文控制：-B, -A, -C, context
- Glob 模式支持：*.{ts,tsx}, **/*.test.js
- 文件类型过滤：type 参数
- 分页功能：head_limit + offset
- 多行模式：multiline 参数
- 结果排序：按修改时间排序（files_with_matches 模式）
- 大小写不敏感搜索
- 默认结果限制：DEFAULT_HEAD_LIMIT = 250
"""
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()

# 版本控制系统目录（自动排除）
VCS_DIRECTORIES_TO_EXCLUDE = [
    '.git',
    '.svn',
    '.hg',
    '.bzr',
    '.jj',
    '.sl',
]

# 默认结果限制（0 = 无限制）
DEFAULT_HEAD_LIMIT = 250


def _find_ripgrep() -> Optional[str]:
    """查找ripgrep可执行文件"""
    import platform

    # 1. 尝试系统PATH中的rg
    for cmd in ["rg", "ripgrep"]:
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, OSError) as exc:
            logger.warning("ripgrep_probe_failed", command=cmd, error=str(exc))
            continue

    # 2. 尝试Claude Code内置的ripgrep
    machine = platform.machine().lower()
    if machine == "x86_64":
        machine = "x64"
    elif machine == "aarch64":
        machine = "arm64"

    system = platform.system().lower()
    if system == "linux":
        system = "linux"
    elif system == "darwin":
        system = "darwin"

    # Claude Code vendor路径
    vendor_paths = [
        f"/usr/local/node-v20.18.0-linux-x64/lib/node_modules/@anthropic-ai/claude-code/vendor/ripgrep/{machine}-{system}/rg",
        f"/usr/local/node-v20.18.0-linux-x64/lib/node_modules/@anthropic-ai/claude-code/vendor/ripgrep/{machine}-linux/rg",
    ]

    for path in vendor_paths:
        if Path(path).exists():
            return path

    return None


# ripgrep路径（模块加载时检测）
_RIPGREP_PATH = _find_ripgrep()


class GrepTool(LLMTool):
    """
    文件内容搜索工具（基于ripgrep，完整版）

    功能：
    - 正则表达式搜索文件内容
    - 三种输出模式：content / files_with_matches / count
    - 精细上下文控制：-B, -A, -C, context
    - Glob 模式支持：*.{ts,tsx}, **/*.test.js
    - 文件类型过滤：type 参数
    - 分页功能：head_limit + offset
    - 多行模式：multiline 参数
    - 结果排序：按修改时间排序（files_with_matches 模式）
    - 大小写不敏感搜索
    """

    def __init__(self):
        super().__init__(
            name="grep",
            description="""搜索文件内容（基于ripgrep，高速完整版）

搜索 backend/ 目录下的代码文件。
自动跳过 logs/, node_modules/, .git/, __pycache__ 等目录。

示例：
- grep(pattern="query_standard", path="app/agent")                          # 搜索agent目录
- grep(pattern="class.*Agent", type="py")                                    # 搜索Python文件
- grep(pattern="def execute", output_mode="content")                         # 显示匹配行
- grep(pattern="TODO|FIXME", case_insensitive=True)                          # 忽略大小写
- grep(pattern="import", glob="*.{py,ts}")                                   # Glob模式匹配
- grep(pattern="async def", context_lines_before=2, context_lines_after=2)  # 精细上下文控制
- grep(pattern="class.*:", multiline=True)                                   # 多行模式
- grep(pattern="test", head_limit=10, offset=20)                            # 分页查询

参数说明：
- pattern: 正则表达式（必填）
- path: 搜索路径，相对于backend/（默认 "."）
- glob: Glob模式过滤文件（如 "*.{py,ts}", "**/*.test.js"）
- type: 文件类型（py/js/ts/json/yaml/md/txt/html/css/sh/sql/xml）
- output_mode: content（匹配行）/ files_with_matches（文件列表）/ count（统计）
- context_lines: 匹配行前后各显示几行（与 -C 相同）
- context_lines_before: 匹配行前显示几行（与 -B 相同）
- context_lines_after: 匹配行后显示几行（与 -A 相同）
- show_line_numbers: 是否显示行号（默认 True，仅 content 模式）
- case_insensitive: 是否忽略大小写
- multiline: 是否启用多行模式（. 匹配换行符）
- head_limit: 最多返回几条结果（默认 250，0 表示不限制）
- offset: 跳过前几条结果（用于分页，默认 0）

注意：
- 需要安装ripgrep: apt install ripgrep 或 brew install ripgrep
- 搜索范围限制在backend/目录内
- 30秒超时自动中断
- files_with_matches 模式按修改时间排序
""",
            category=ToolCategory.QUERY,
            version="3.0.0",
            requires_context=False
        )

        # 获取backend目录路径
        self.backend_dir = Path(__file__).parent.parent.parent.parent  # backend/

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        glob: Optional[str] = None,
        type: Optional[str] = None,
        output_mode: str = "files_with_matches",
        context_lines: Optional[int] = None,
        context_lines_before: Optional[int] = None,
        context_lines_after: Optional[int] = None,
        show_line_numbers: bool = True,
        case_insensitive: bool = False,
        multiline: bool = False,
        head_limit: int = DEFAULT_HEAD_LIMIT,
        offset: int = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行ripgrep搜索

        Returns:
            {
                "success": bool,
                "data": {
                    "mode": str,
                    "numFiles": int,
                    "filenames": List[str],
                    "content": Optional[str],
                    "numLines": Optional[int],
                    "numMatches": Optional[int],
                    "appliedLimit": Optional[int],
                    "appliedOffset": Optional[int],
                },
                "summary": str
            }
        """
        try:
            # 1. 验证路径
            search_path = self._resolve_path(path)
            if not search_path or not search_path.exists():
                return {
                    "success": False,
                    "error": f"搜索路径不存在: {path}",
                    "summary": "搜索失败：路径不存在"
                }

            # 2. 构建ripgrep命令
            cmd = self._build_rg_command(
                pattern=pattern,
                search_path=search_path,
                glob=glob,
                file_type=type,
                output_mode=output_mode,
                context=context_lines,
                context_before=context_lines_before,
                context_after=context_lines_after,
                show_line_numbers=show_line_numbers,
                case_insensitive=case_insensitive,
                multiline=multiline,
            )

            logger.info(
                "grep_executing",
                command=" ".join(cmd),
                path=path,
                output_mode=output_mode
            )

            # 3. 执行搜索
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.backend_dir)
            )

            # 4. 解析输出
            return self._parse_output(
                stdout=result.stdout,
                output_mode=output_mode,
                pattern=pattern,
                head_limit=head_limit,
                offset=offset,
            )

        except subprocess.TimeoutExpired:
            logger.error("grep_timeout", pattern=pattern, path=path)
            return {
                "success": False,
                "error": "搜索超时（30秒）",
                "summary": "搜索失败：超时"
            }
        except FileNotFoundError:
            logger.error("grep_not_found")
            return {
                "success": False,
                "error": "ripgrep未安装，请运行: apt install ripgrep 或 brew install ripgrep",
                "summary": "搜索失败：缺少ripgrep"
            }
        except Exception as e:
            logger.error("grep_failed", pattern=pattern, path=path, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "summary": f"搜索失败：{str(e)[:80]}"
            }

    def _resolve_path(self, path: str) -> Optional[Path]:
        """解析搜索路径"""
        try:
            # 相对于 backend/ 目录
            search_path = self.backend_dir / path
            return search_path.resolve()
        except Exception:
            return None

    def _build_rg_command(
        self,
        pattern: str,
        search_path: Path,
        glob: Optional[str],
        file_type: Optional[str],
        output_mode: str,
        context: Optional[int],
        context_before: Optional[int],
        context_after: Optional[int],
        show_line_numbers: bool,
        case_insensitive: bool,
        multiline: bool,
    ) -> List[str]:
        """
        构建ripgrep命令行参数

        注意：参数名保持为 context/context_before/context_after（内部使用），
        对外暴露的参数名已改为 context_lines/context_lines_before/context_lines_after
        """
        """构建ripgrep命令行参数"""
        if not _RIPGREP_PATH:
            raise RuntimeError("ripgrep不可用")

        cmd = [_RIPGREP_PATH]

        # 不读取 .gitignore/.rgignore 等忽略文件（强制搜索所有文件）
        cmd.append("--no-ignore")

        # 添加隐藏文件搜索
        cmd.append("--hidden")

        # 排除VCS目录
        for vcs_dir in VCS_DIRECTORIES_TO_EXCLUDE:
            cmd.extend(["--glob", f"!{vcs_dir}"])

        # 限制行长度（防止base64/压缩内容干扰）
        cmd.extend(["--max-columns", "500"])

        # 多行模式
        if multiline:
            cmd.extend(["-U", "--multiline-dotall"])

        # 忽略大小写
        if case_insensitive:
            cmd.append("-i")

        # 输出模式
        if output_mode == "files_with_matches":
            cmd.append("-l")
        elif output_mode == "count":
            cmd.append("-c")
        elif output_mode == "content":
            # 显示行号
            if show_line_numbers:
                cmd.append("-n")

            # 上下文控制（-C/context 优先于 context_before/context_after）
            if context is not None:
                cmd.extend(["-C", str(context)])
            elif context_before is not None or context_after is not None:
                if context_before is not None:
                    cmd.extend(["-B", str(context_before)])
                if context_after is not None:
                    cmd.extend(["-A", str(context_after)])

        # 文件类型过滤
        if file_type:
            cmd.extend(["--type", file_type])

        # Glob 模式
        if glob:
            glob_patterns = self._parse_glob_patterns(glob)
            for glob_pattern in glob_patterns:
                cmd.extend(["--glob", glob_pattern])

        # 排除常见干扰目录和文件
        cmd.extend([
            "--glob", "!logs/*",
            "--glob", "!*.log",
            "--glob", "!node_modules/*",
            "--glob", "!__pycache__/*",
            "--glob", "!.pytest_cache/*",
            "--glob", "!*.pyc",
            "--glob", "!*.pyo",
            "--glob", "!*.min.js",
            "--glob", "!*.min.css",
            "--glob", "!dist/*",
            "--glob", "!build/*",
            "--glob", "!.venv/*",
            "--glob", "!venv/*",
            "--glob", "!env/*",
            "--glob", "!*.egg-info/*",
            "--glob", "!**/*.egg-info/*",
        ])

        # 添加模式（如果以 - 开头，使用 -e 标志）
        if pattern.startswith("-"):
            cmd.extend(["-e", pattern])
        else:
            cmd.append(pattern)

        # 添加搜索路径
        cmd.append(str(search_path))

        return cmd

    def _parse_glob_patterns(self, glob: str) -> List[str]:
        """
        解析 glob 模式字符串

        支持格式：
        - "*.py" -> ["*.py"]
        - "*.{py,ts}" -> ["*.py", "*.ts"]
        - "*.test.js **/*.spec.ts" -> ["*.test.js", "**/*.spec.ts"]
        """
        patterns = []

        # 按空格分割（但保留大括号）
        raw_patterns = glob.split()

        for raw_pattern in raw_patterns:
            # 如果包含大括号，展开大括号内的选项
            if "{" in raw_pattern and "}" in raw_pattern:
                # 提取大括号前缀、内容、后缀
                match = re.match(r"^(.*?)\{([^}]+)\}(.*?)$", raw_pattern)
                if match:
                    prefix, options, suffix = match.groups()
                    # 分割选项（逗号分隔）
                    for option in options.split(","):
                        patterns.append(f"{prefix}{option}{suffix}")
                else:
                    patterns.append(raw_pattern)
            else:
                # 按逗号分割（处理 "*.py,*.ts" 格式）
                for part in raw_pattern.split(","):
                    if part.strip():
                        patterns.append(part.strip())

        return patterns

    def _apply_head_limit(
        self,
        items: List[Any],
        limit: int,
        offset: int = 0
    ) -> Tuple[List[Any], Optional[int]]:
        """
        应用结果限制和偏移

        Returns:
            (处理后的列表, 实际应用的限制值)
            - 如果 limit=0 或 items 长度未超过限制，返回 (items, None)
            - 如果发生截断，返回 (截断后的列表, limit)
        """
        # 显式传 0 = 无限制
        if limit == 0:
            return items[offset:], None

        # 使用默认限制或指定限制
        effective_limit = limit
        sliced = items[offset:offset + effective_limit]

        # 只有实际发生截断时才报告 appliedLimit
        was_truncated = len(items) - offset > effective_limit
        applied_limit = effective_limit if was_truncated else None

        return sliced, applied_limit

    def _format_limit_info(
        self,
        applied_limit: Optional[int],
        applied_offset: Optional[int]
    ) -> str:
        """格式化分页信息"""
        parts = []
        if applied_limit is not None:
            parts.append(f"limit: {applied_limit}")
        if applied_offset and applied_offset > 0:
            parts.append(f"offset: {applied_offset}")
        return ", ".join(parts)

    def _sort_files_by_mtime(self, filepaths: List[str]) -> List[str]:
        """
        按修改时间排序文件路径（最新的在前）

        使用 Promise.allSettled 策略：单个文件 stat 失败不影响其他文件
        """
        def get_mtime(filepath: str) -> float:
            try:
                return Path(filepath).stat().st_mtime
            except Exception:
                return 0.0

        # 添加时间戳并排序
        with_time = [(f, get_mtime(f)) for f in filepaths]
        with_time.sort(key=lambda x: x[1], reverse=True)
        return [f for f, _ in with_time]

    def _parse_output(
        self,
        stdout: str,
        output_mode: str,
        pattern: str,
        head_limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        """解析ripgrep输出为标准格式"""
        lines = [line for line in stdout.strip().splitlines() if line]

        if not lines:
            return {
                "success": True,
                "data": {
                    "mode": output_mode,
                    "numFiles": 0,
                    "filenames": [],
                    "content": None,
                    "numLines": None,
                    "numMatches": None,
                    "appliedLimit": None,
                    "appliedOffset": None,
                },
                "summary": f"搜索完成：未找到匹配 \"{pattern[:30]}\""
            }

        if output_mode == "files_with_matches":
            # 按修改时间排序
            sorted_lines = self._sort_files_by_mtime(lines)

            # 应用分页
            final_matches, applied_limit = self._apply_head_limit(
                sorted_lines, head_limit, offset
            )

            # 转换为相对路径
            relative_matches = [self._to_rel_path(f) for f in final_matches]

            applied_offset = offset if offset > 0 else None

            return {
                "success": True,
                "data": {
                    "mode": "files_with_matches",
                    "numFiles": len(relative_matches),
                    "filenames": relative_matches,
                    "content": None,
                    "numLines": None,
                    "numMatches": None,
                    "appliedLimit": applied_limit,
                    "appliedOffset": applied_offset,
                },
                "summary": self._format_summary(
                    "files_with_matches",
                    num_files=len(relative_matches),
                    applied_limit=applied_limit,
                    applied_offset=applied_offset
                )
            }

        elif output_mode == "count":
            # 应用分页
            limited_lines, applied_limit = self._apply_head_limit(
                lines, head_limit, offset
            )

            # 解析统计结果
            results = []
            total_matches = 0
            for line in limited_lines:
                if ":" in line:
                    file_path, count_str = line.rsplit(":", 1)
                    try:
                        count = int(count_str)
                        total_matches += count
                        results.append({
                            "file": self._to_rel_path(file_path),
                            "count": count
                        })
                    except ValueError:
                        pass

            applied_offset = offset if offset > 0 else None

            return {
                "success": True,
                "data": {
                    "mode": "count",
                    "numFiles": len(results),
                    "filenames": [r["file"] for r in results],
                    "content": "\n".join(limited_lines),
                    "numLines": None,
                    "numMatches": total_matches,
                    "appliedLimit": applied_limit,
                    "appliedOffset": applied_offset,
                },
                "summary": self._format_summary(
                    "count",
                    num_files=len(results),
                    num_matches=total_matches,
                    applied_limit=applied_limit,
                    applied_offset=applied_offset
                )
            }

        else:  # content mode
            # 应用分页
            limited_lines, applied_limit = self._apply_head_limit(
                lines, head_limit, offset
            )

            # 转换为相对路径（节省 token）
            final_lines = [self._to_rel_path_in_content(line) for line in limited_lines]

            applied_offset = offset if offset > 0 else None

            return {
                "success": True,
                "data": {
                    "mode": "content",
                    "numFiles": 0,
                    "filenames": [],
                    "content": "\n".join(final_lines),
                    "numLines": len(final_lines),
                    "numMatches": None,
                    "appliedLimit": applied_limit,
                    "appliedOffset": applied_offset,
                },
                "summary": self._format_summary(
                    "content",
                    num_lines=len(final_lines),
                    applied_limit=applied_limit,
                    applied_offset=applied_offset
                )
            }

    def _format_summary(
        self,
        mode: str,
        num_files: int = 0,
        num_matches: int = 0,
        num_lines: int = 0,
        applied_limit: Optional[int] = None,
        applied_offset: Optional[int] = None
    ) -> str:
        """格式化结果摘要"""
        limit_info = self._format_limit_info(applied_limit, applied_offset)

        if mode == "files_with_matches":
            if num_files == 0:
                return "未找到匹配文件"
            base = f"找到 {num_files} 个文件"
            return f"{base}{f' ({limit_info})' if limit_info else ''}"

        elif mode == "count":
            if num_files == 0:
                return "未找到匹配"
            occurrences = "occurrence" if num_matches == 1 else "occurrences"
            files = "file" if num_files == 1 else "files"
            base = f"找到 {num_matches} 个 {occurrences}，涉及 {num_files} 个 {files}"
            return f"{base}{f' ({limit_info})' if limit_info else ''}"

        else:  # content
            if num_lines == 0:
                return "未找到匹配行"
            base = f"找到 {num_lines} 行匹配"
            return f"{base}{f' ({limit_info})' if limit_info else ''}"

    def _to_rel_path(self, path: str) -> str:
        """转换为相对路径（相对于项目根目录，格式：backend/xxx）"""
        try:
            # 先转换为相对于backend/的路径
            rel_to_backend = Path(path).relative_to(self.backend_dir)
            # 然后添加 backend/ 前缀
            return f"backend/{rel_to_backend}"
        except ValueError:
            return path

    def _to_rel_path_in_content(self, line: str) -> str:
        """
        在 content 模式下转换行中的路径

        输入格式：/absolute/path:line_num:content 或 /absolute/path:content
        输出格式：backend/rel/path:line_num:content
        """
        colon_index = line.find(":")
        if colon_index > 0:
            file_path = line[:colon_index]
            rest = line[colon_index:]
            return self._to_rel_path(file_path) + rest
        return line

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "grep",
            "description": """搜索文件内容（基于ripgrep，高速完整版）

在 backend/ 目录下搜索正则表达式匹配的内容。
自动跳过 logs、node_modules、.git 等目录。

使用场景：
- 查找代码中的类/函数定义
- 搜索配置文件中的参数
- 统计关键词出现次数
- 多文件模式搜索

特性：
- 三种输出模式：content（匹配行）、files_with_matches（文件列表）、count（统计）
- Glob 模式：支持 "*.{py,ts}", "**/*.test.js" 等复杂模式
- 分页查询：head_limit + offset
- 精细上下文：context_before/context_after 或 context
- 多行模式：multiline 让 . 匹配换行符
- 结果排序：files_with_matches 按修改时间排序
- 默认限制：head_limit 默认 250（0 表示无限制）

注意：
- 需要安装ripgrep: apt install ripgrep
- 搜索范围限制在backend/目录
- 30秒超时自动中断
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "正则表达式模式。示例：\"class.*Agent\"、\"def execute\"、\"TODO|FIXME\""
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径，相对于 backend/。示例：\"app/agent\"、\"app/tools\"",
                        "default": "."
                    },
                    "glob": {
                        "type": "string",
                        "description": "Glob 模式过滤文件。支持复杂模式：\n- \"*.py\" - 所有 Python 文件\n- \"*.{py,ts}\" - Python 和 TypeScript 文件\n- \"**/*.test.js\" - 所有测试文件\n- \"*.py **/*.md\" - 多个模式（空格分隔）"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["py", "js", "ts", "json", "yaml", "md", "txt", "html", "css", "sh", "sql", "xml"],
                        "description": "文件类型别名（ripgrep 内置类型）。示例：\"py\" 仅搜索 Python 文件"
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["content", "files_with_matches", "count"],
                        "description": "输出模式：\n- content: 显示匹配的具体行内容\n- files_with_matches: 只显示包含匹配的文件路径（按修改时间排序）\n- count: 统计每个文件的匹配次数",
                        "default": "files_with_matches"
                    },
                    "context": {
                        "type": "integer",
                        "description": "匹配行前后各显示几行（等同于同时设置 context_before 和 context_after）",
                        "default": None
                    },
                    "context_before": {
                        "type": "integer",
                        "description": "匹配行前显示几行（-B 参数）",
                        "default": None
                    },
                    "context_after": {
                        "type": "integer",
                        "description": "匹配行后显示几行（-A 参数）",
                        "default": None
                    },
                    "show_line_numbers": {
                        "type": "boolean",
                        "description": "是否显示行号（仅 content 模式有效，默认 True）",
                        "default": True
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "是否忽略大小写（-i 参数）",
                        "default": False
                    },
                    "multiline": {
                        "type": "boolean",
                        "description": "是否启用多行模式，让 . 可以匹配换行符（-U --multiline-dotall）",
                        "default": False
                    },
                    "head_limit": {
                        "type": "integer",
                        "description": "最多返回几条结果（默认 250，0 表示不限制）",
                        "default": 250
                    },
                    "offset": {
                        "type": "integer",
                        "description": "跳过前几条结果（用于分页，默认 0）",
                        "default": 0
                    }
                },
                "required": ["pattern"]
            }
        }

    def is_available(self) -> bool:
        """检查ripgrep是否可用"""
        return _RIPGREP_PATH is not None


# 创建工具实例
tool = GrepTool()
