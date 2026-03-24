"""
Grep 工具 - 基于ripgrep的高速文件内容搜索

依赖：ripgrep (rg命令)
安装：
  - Ubuntu/Debian: apt install ripgrep
  - macOS: brew install ripgrep
  - 其他: https://github.com/BurntSushi/ripgrep
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()


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
        except (FileNotFoundError, subprocess.TimeoutExpired):
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
    文件内容搜索工具（基于ripgrep）

    功能：
    - 正则表达式搜索文件内容
    - 三种输出模式：content / files_with_matches / count
    - 文件类型过滤（type参数）
    - 上下文行显示（context参数）
    - 大小写不敏感搜索
    """

    def __init__(self):
        super().__init__(
            name="grep",
            description="""搜索文件内容（基于ripgrep，高速）

仅搜索 backend/ 目录下的代码文件。
自动跳过 logs/, node_modules/, .git/, __pycache__ 等目录。

示例：
- grep(pattern="query_standard", path="app/agent")              # 搜索agent目录
- grep(pattern="class.*Agent", type="py")                        # 搜索Python文件
- grep(pattern="def execute", output_mode="content")             # 显示匹配行
- grep(pattern="TODO|FIXME", case_insensitive=True)              # 忽略大小写

参数说明：
- pattern: 正则表达式（必填）
- path: 搜索路径，相对于backend/（默认 "."）
- output_mode: content（匹配行）/ files_with_matches（文件列表）/ count（统计）
- type: 文件类型（py/js/ts/json/yaml/md/txt/html/css/sh/sql/xml）
- context: 匹配行前后各显示几行
- case_insensitive: 是否忽略大小写
- head_limit: 最多返回几条结果

注意：
- 需要安装ripgrep: apt install ripgrep 或 brew install ripgrep
- 搜索范围限制在backend/目录内
- 30秒超时自动中断
""",
            category=ToolCategory.QUERY,
            version="2.0.0",
            requires_context=False
        )

        # 获取backend目录路径
        self.backend_dir = Path(__file__).parent.parent.parent.parent  # backend/

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        output_mode: str = "files_with_matches",
        type: Optional[str] = None,
        context: int = 0,
        case_insensitive: bool = False,
        head_limit: int = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行ripgrep搜索

        Returns:
            {
                "success": bool,
                "data": {
                    "results": [...],
                    "output_text": str,
                    "total_matches": int,
                    "files_matched": int,
                    "method": "ripgrep"
                },
                "summary": str
            }
        """
        try:
            # 1. 构建ripgrep命令
            cmd = self._build_rg_command(
                pattern, path, output_mode, type, context, case_insensitive
            )

            logger.info("grep_executing", command=" ".join(cmd), path=path)

            # 2. 执行搜索
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.backend_dir)
            )

            # 3. 解析输出
            return self._parse_output(
                result.stdout,
                output_mode,
                pattern,
                head_limit
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

    def _build_rg_command(
        self,
        pattern: str,
        path: str,
        output_mode: str,
        file_type: Optional[str],
        context: int,
        case_insensitive: bool
    ) -> list:
        """构建ripgrep命令行参数"""
        if not _RIPGREP_PATH:
            raise RuntimeError("ripgrep不可用")

        cmd = [_RIPGREP_PATH, pattern]

        # 输出模式
        if output_mode == "files_with_matches":
            cmd.append("-l")
        elif output_mode == "count":
            cmd.append("-c")
        else:  # content
            cmd.append("-n")  # 显示行号
            if context > 0:
                cmd.extend(["-C", str(context)])

        # 文件类型
        if file_type:
            cmd.extend(["-t", file_type])

        # 忽略大小写
        if case_insensitive:
            cmd.append("-i")

        # 排除目录和文件
        cmd.extend([
            "--glob", "!logs/*",
            "--glob", "!*.log",
            "--glob", "!node_modules/*",
            "--glob", "!.git/*",
            "--glob", "!__pycache__/*",
            "--glob", "!.pytest_cache/*",
            "--glob", "!*.pyc",
        ])

        # 搜索路径（相对于backend/）
        search_path = self.backend_dir / path
        cmd.append(str(search_path))

        return cmd

    def _parse_output(
        self,
        stdout: str,
        output_mode: str,
        pattern: str,
        head_limit: int
    ) -> Dict[str, Any]:
        """解析ripgrep输出为标准格式"""
        lines = [line for line in stdout.strip().splitlines() if line]

        # 应用结果限制
        if head_limit > 0:
            lines = lines[:head_limit]

        if not lines:
            return {
                "success": True,
                "data": {
                    "results": [],
                    "output_text": "(无匹配)",
                    "total_matches": 0,
                    "files_matched": 0,
                    "method": "ripgrep"
                },
                "summary": f"搜索完成：未找到匹配 \"{pattern[:30]}\""
            }

        if output_mode == "files_with_matches":
            # 转换为相对路径
            results = [self._to_rel_path(line) for line in lines]
            return {
                "success": True,
                "data": {
                    "results": results,
                    "output_text": "\n".join(results),
                    "total_matches": len(results),
                    "files_matched": len(results),
                    "method": "ripgrep"
                },
                "summary": f"搜索完成：在 {len(results)} 个文件中找到匹配"
            }

        elif output_mode == "count":
            results = []
            total = 0
            for line in lines:
                if ":" in line:
                    file_path, count = line.rsplit(":", 1)
                    try:
                        count_int = int(count)
                        total += count_int
                        results.append({
                            "file": self._to_rel_path(file_path),
                            "count": count_int
                        })
                    except ValueError:
                        pass
            return {
                "success": True,
                "data": {
                    "results": results,
                    "output_text": "\n".join(lines),
                    "total_matches": total,
                    "files_matched": len(results),
                    "method": "ripgrep"
                },
                "summary": f"统计完成：共 {total} 次匹配，涉及 {len(results)} 个文件"
            }

        else:  # content
            return {
                "success": True,
                "data": {
                    "output_text": "\n".join(lines),
                    "total_matches": len(lines),
                    "method": "ripgrep"
                },
                "summary": f"搜索完成：{len(lines)} 行匹配"
            }

    def _to_rel_path(self, path: str) -> str:
        """转换为相对路径（相对于项目根目录，格式：backend/xxx）"""
        try:
            # 先转换为相对于backend/的路径
            rel_to_backend = Path(path).relative_to(self.backend_dir)
            # 然后添加 backend/ 前缀，这样read_file工具可以正确解析
            return f"backend/{rel_to_backend}"
        except ValueError:
            return path

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "grep",
            "description": """搜索文件内容（基于ripgrep，高速）

在backend/目录下搜索正则表达式匹配的内容。
自动跳过logs、node_modules、.git等目录。

使用场景：
- 查找代码中的类/函数定义
- 搜索配置文件中的参数
- 统计关键词出现次数

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
                        "description": "搜索路径，相对于backend/。示例：\"app/agent\"、\"app/tools\"",
                        "default": "."
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["content", "files_with_matches", "count"],
                        "description": (
                            "输出模式：\n"
                            "- content: 显示匹配的具体行内容\n"
                            "- files_with_matches: 只显示包含匹配的文件路径\n"
                            "- count: 统计每个文件的匹配次数"
                        ),
                        "default": "files_with_matches"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["py", "js", "ts", "json", "yaml", "md", "txt", "html", "css", "sh", "sql", "xml"],
                        "description": "文件类型别名。示例：\"py\" 仅搜索Python文件"
                    },
                    "context": {
                        "type": "integer",
                        "description": "匹配行前后各显示几行",
                        "default": 0
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "是否忽略大小写",
                        "default": False
                    },
                    "head_limit": {
                        "type": "integer",
                        "description": "最多返回几条结果（0 表示不限制）",
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
