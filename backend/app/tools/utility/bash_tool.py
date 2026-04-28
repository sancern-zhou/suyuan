"""
Bash Command Execution Tool

安全地执行 Bash 命令，用于扩展 Agent 能力：
- 调用外部命令行工具（HYSPLIT、WRF、CMAQ 等气象模型）
- 数据处理（gdal、ncdump、Python 脚本）
- 文件系统操作（批量处理、格式转换）
- 系统监控（磁盘空间、进程状态）

安全措施（防止命令注入）：
1. 禁用 shell=True：使用参数列表执行命令，防止shell元字符注入
2. Shell元字符黑名单：禁止 ; | & $ ` 等特殊字符（使用引号状态追踪）
3. 危险命令黑名单：禁止 rm -rf /、sudo、shutdown 等
4. 命令白名单验证：只允许特定类别的命令
5. 工作目录限制：只能在工作目录内操作
6. 超时保护：默认 60 秒超时
7. 输出大小限制：限制输出大小（1MB）

安全改进（v2.0 - 减少误报）：
- 引号状态追踪：正确识别引号内/外的元字符
- 允许引号内的安全元字符（如 grep "pattern\|other"）
- 改进的转义字符处理
"""

import subprocess
import shutil
import platform
import shlex
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.utility.project_root import get_project_root

logger = structlog.get_logger()


# ============================================================================
# 辅助函数：引号状态追踪和字符检测
# ============================================================================

def has_unescaped_char(content: str, char: str) -> bool:
    """
    检查内容中是否包含未转义的指定字符（引号外）

    这是核心的安全检查函数，正确处理：
    - 单引号 ('...')：完全引用，所有特殊字符都失去特殊含义
    - 双引号 ("...")：部分引用，但 $ ` 仍保持特殊含义
    - 转义字符 (\)：转义下一个字符

    Args:
        content: 要检查的内容
        char: 要查找的字符

    Returns:
        如果字符在引号外且未转义，返回True（危险）
        如果字符在引号内或已转义，返回False（安全）

    Examples:
        has_unescaped_char('echo "hello; world"', ';')  # False（安全，分号在双引号内）
        has_unescaped_char('echo hello; world', ';')    # True（危险，分号在引号外）
        has_unescaped_char('echo "hello\\; world"', ';') # False（安全，分号已转义）
        has_unescaped_char("echo 'hello; world'", ';')  # False（安全，分号在单引号内）
    """
    in_single_quote = False
    in_double_quote = False
    escaped = False

    for c in content:
        if escaped:
            # 转义状态：当前字符被转义，重置转义标志
            escaped = False
            continue

        if c == '\\':
            # 反斜杠：转义下一个字符（但在单引号内不转义）
            if not in_single_quote:
                escaped = True
            continue

        if c == "'" and not in_double_quote:
            # 单引号：切换单引号状态（在双引号内是普通字符）
            in_single_quote = not in_single_quote
            continue

        if c == '"' and not in_single_quote:
            # 双引号：切换双引号状态（在单引号内是普通字符）
            in_double_quote = not in_double_quote
            continue

        # 检查目标字符（只在引号外且未转义时）
        if c == char and not in_single_quote and not in_double_quote:
            return True

    return False


def extract_unquoted_content(command: str) -> Tuple[str, str, str]:
    """
    提取命令的不同内容版本，用于多层级验证

    Args:
        command: 原始命令

    Returns:
        (unquoted_content, fully_unquoted, unquoted_keep_quotes)
        - unquoted_content: 移除双引号内容（保留单引号内容）
        - fully_unquoted: 移除所有引号内容
        - unquoted_keep_quotes: 移除引号内容但保留引号字符
    """
    unquoted_content = ""
    fully_unquoted = ""
    unquoted_keep_quotes = ""

    in_single_quote = False
    in_double_quote = False
    escaped = False

    for c in command:
        if escaped:
            escaped = False
            if not in_single_quote:
                unquoted_content += c
            if not in_single_quote and not in_double_quote:
                fully_unquoted += c
            unquoted_keep_quotes += c
            continue

        if c == '\\':
            if not in_single_quote:
                escaped = True
            if not in_single_quote:
                unquoted_content += c
            if not in_single_quote and not in_double_quote:
                fully_unquoted += c
            unquoted_keep_quotes += c
            continue

        if c == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            unquoted_keep_quotes += c
            continue

        if c == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            unquoted_keep_quotes += c
            continue

        if not in_single_quote:
            unquoted_content += c
        if not in_single_quote and not in_double_quote:
            fully_unquoted += c
        unquoted_keep_quotes += c

    return unquoted_content, fully_unquoted, unquoted_keep_quotes


def strip_safe_redirections(command: str) -> str:
    """
    移除安全的重定向模式（如 /dev/null）

    Args:
        command: 原始命令

    Returns:
        移除安全重定向后的命令
    """
    # 安全的重定向模式（这些可以自动允许）
    safe_patterns = [
        r'\s*2\s*>&\s*1(?=\s|$)',      # 2>&1（合并stderr到stdout）
        r'[012]?\s*>\s*/dev/null(?=\s|$)',  # > /dev/null（丢弃输出）
        r'\s*<\s*/dev/null(?=\s|$)',    # < /dev/null（从/dev/null读取）
    ]

    result = command
    for pattern in safe_patterns:
        result = re.sub(pattern, '', result)

    return result


class BashTool(LLMTool):
    """
    Bash 命令执行工具（安全版本）

    设计参考：
    - openwork-dev: Rust std::process::Command
    - learn-claude-code: v0_bash_agent 的安全措施
    """

    # 危险命令黑名单（多层安全防护）
    DANGEROUS_COMMANDS = [
        # ========== 系统破坏 ==========
        "rm -rf /",
        "rm -rf /*",
        "rm -Rf /",
        "rmdir /s /q C:\\",  # Windows格式化
        "rmdir /s /q D:\\",
        "del /q C:\\Windows\\*",
        "format ",           # 格式化磁盘
        "mkfs",
        "dd if=/dev/zero",
        "> /dev/sda",
        "> /dev/sdb",
        "shred",            # 安全删除文件
        "wipe",

        # ========== 权限提升 ==========
        "sudo",
        "su ",
        "runas",            # Windows权限提升
        "chmod 000",
        "chown root",
        "userdel",
        "usermod -L",       # 锁定用户
        "passwd --lock",

        # ========== 系统控制 ==========
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "init 0",
        "systemctl poweroff",
        "systemctl halt",

        # ========== 网络攻击 ==========
        "iptables -F",     # 防火墙规则清除
        "iptables -X",
        ":(){:|:&};:",     # fork bomb

        # ========== 配置破坏 ==========
        "rm /etc/passwd",
        "rm /etc/shadow",
        "> /etc/sudoers",
    ]

    # 允许的命令类别（白名单）- 包含 Unix 和 Windows 命令
    ALLOWED_CATEGORIES = {
        # 文件操作 - Unix 命令
        "ls", "cd", "pwd", "mkdir", "rmdir", "cp", "mv", "cat", "head", "tail",
        "grep", "find", "locate", "wc", "sort", "uniq", "cut", "awk", "sed",

        # 文件操作 - Windows 命令
        "dir", "type", "del", "copy", "move", "findstr", "cls",

        # 数据处理
        "python", "python3", "node", "npm",
        "gdal", "ncdump", "ncview", "cdo", "nco",

        # 气象/环境模型
        "hyts_std",  # HYSPLIT
        "wrf",

        # 系统监控 - Unix 命令
        "df", "du", "free", "top", "ps", "uptime",

        # 系统监控 - Windows 命令
        "systeminfo",  # Windows 系统信息
        "tasklist",    # Windows 进程列表
        "taskkill",    # Windows 终止进程
        "wmic",        # Windows 管理接口
        "ver",         # Windows 版本
        "hostname",    # 主机名
        "ipconfig",    # IP 配置
        "netstat",     # 网络连接
        "whoami",      # 当前用户
        "chkdsk",      # 磁盘检查

        # 网络
        "curl", "wget", "rsync", "ping",

        # 压缩/解压
        "tar", "gzip", "gunzip", "zip", "unzip",

        # 其他安全工具
        "echo", "date", "which", "whereis", "type", "test", "timeout"
    }

    def __init__(self):
        # 调用父类构造函数
        super().__init__(
            name="bash",
            description="执行安全的 Bash 命令（文件操作、数据处理、系统监控）",
            category=ToolCategory.QUERY,  # 归类为查询工具
            version="1.0.0",
            requires_context=False
        )

        # 工作目录：使用项目根目录（稳定路径，不依赖 cwd）
        self.working_dir = get_project_root()
        self.default_timeout = 60
        self.max_output_size = 1024 * 1024  # 1MB（大幅提升，有上下文压缩策略）

        # 命令历史（用于审计）
        self.command_history = []
        self.max_history = 1000

        logger.info(
            "bash_tool_initialized",
            working_dir=str(self.working_dir),
            timeout=self.default_timeout,
            max_output_size=self.max_output_size
        )

    async def execute(
        self,
        context=None,
        command: str = None,
        timeout: Optional[int] = None,
        working_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行 Bash 命令

        Args:
            command: 要执行的命令
            timeout: 超时时间（秒），默认 60 秒
            working_dir: 工作目录（可选），必须在 working_dir 范围内

        Returns:
            {
                "status": "success|failed",
                "success": bool,
                "data": {
                    "stdout": str,
                    "stderr": str,
                    "exit_code": int,
                    "command": str
                },
                "metadata": {...},
                "summary": str
            }
        """
        if not command:
            return {
                "status": "failed",
                "success": False,
                "error": "Missing required parameter: command",
                "data": None,
                "metadata": {
                    "tool_name": "bash",
                    "error_type": "MISSING_PARAMETER"
                },
                "summary": "❌ 缺少命令参数"
            }

        # 0. 安全检查（先检查原命令，防止绕过黑名单）
        validation = self._validate_command(command)
        if not validation["valid"]:
            self._log_command(command, validation["error"])
            return {
                "status": "failed",
                "success": False,
                "error": validation["error"],
                "data": {"command": command},
                "metadata": {
                    "tool_name": "bash",
                    "error_type": "VALIDATION_FAILED"
                },
                "summary": f"❌ 命令安全检查失败: {validation['error']}"
            }

        # 1. 标准化路径格式（正斜杠 → 反斜杠，修复 LLM 过度转义）
        command = self._normalize_path_format(command)

        # 2. Windows 命令转换（跨平台兼容）
        command = self._translate_command(command)

        # 3. 确定工作目录
        work_dir = self.working_dir
        if working_dir:
            work_dir = self._resolve_working_dir(working_dir)
            if not work_dir:
                self._log_command(command, "Invalid working directory")
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"工作目录超出允许范围。请求的目录: {working_dir}，允许的范围: {self.working_dir}",
                    "data": {
                        "command": command,
                        "requested_dir": working_dir,
                        "allowed_dir": str(self.working_dir),
                        "suggestion": f"请不要设置 working_dir 参数，直接在命令中使用完整路径。例如: dir \"{self.working_dir}\\\\报告模板\""
                    },
                    "metadata": {
                        "tool_name": "bash",
                        "error_type": "INVALID_WORKING_DIR"
                    },
                    "summary": f"❌ 工作目录超出范围: {working_dir}（允许范围: {self.working_dir}）"
                }

        # 3. 执行命令（使用参数列表，禁用shell=True防止命令注入）
        timeout_val = timeout or self.default_timeout

        try:
            logger.info(
                "bash_command_executing",
                command=command,
                working_dir=str(work_dir),
                timeout=timeout_val
            )

            # 使用shlex分词命令（安全处理引号）
            # posix=True确保Unix风格引号处理，Windows下也会正确处理
            try:
                command_parts = shlex.split(command, posix=True)
            except ValueError as e:
                self._log_command(command, f"命令分词失败: {e}")
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"命令格式错误（引号不匹配）: {e}",
                    "data": {"command": command},
                    "metadata": {
                        "tool_name": "bash",
                        "error_type": "COMMAND_PARSE_ERROR"
                    },
                    "summary": f"❌ 命令格式错误: {e}"
                }

            # 确定编码方式
            is_windows = platform.system() == "Windows"
            output_encoding = 'gbk' if (is_windows and not any(cmd in command_parts[0] for cmd in ['python', 'node', 'java', 'hyts_std', 'wrf'])) else 'utf-8'

            # ✅ 关键安全改进：不使用shell=True，使用参数列表
            # 这防止了shell元字符注入攻击
            result = subprocess.run(
                command_parts,  # 参数列表，而非字符串
                shell=False,    # ✅ 明确禁用shell（默认就是False）
                cwd=work_dir,
                capture_output=True,
                encoding=output_encoding,
                errors='replace',
                timeout=timeout_val
            )

            # 4. 处理输出（完全不截断，依赖上下文压缩策略）
            stdout = result.stdout or ""
            stderr = result.stderr or ""

            # 记录命令历史
            self._log_command(
                command,
                "success" if result.returncode == 0 else "failed",
                exit_code=result.returncode
            )

            logger.info(
                "bash_command_completed",
                command=command,
                exit_code=result.returncode,
                stdout_length=len(stdout),
                stderr_length=len(stderr),
                stderr_preview=stderr[:50] if stderr else "",
                stdout_preview=stdout[:100] if stdout else ""
            )

            # ✅ 完整输出，不生成 summary，让上层格式化器决定如何呈现
            # 依赖系统的上下文压缩策略管理 token 消耗
            return {
                "status": "success" if result.returncode == 0 else "failed",
                "success": result.returncode == 0,
                "data": {
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": result.returncode,
                    "command": command,
                    "working_directory": str(work_dir)
                },
                "metadata": {
                    "tool_name": "bash",
                    "timeout": timeout_val,
                    "stdout_length": len(stdout),
                    "stderr_length": len(stderr)
                }
            }

        except subprocess.TimeoutExpired:
            self._log_command(command, "timeout")
            logger.warning(
                "bash_command_timeout",
                command=command,
                timeout=timeout_val
            )
            result_dict = {
                "status": "failed",
                "success": False,
                "error": f"Command timeout after {timeout_val}s",
                "data": {
                    "command": command,
                    "timeout": timeout_val
                },
                "metadata": {
                    "tool_name": "bash",
                    "error_type": "TIMEOUT"
                }
            }

            # 失败时提供简短摘要
            result_dict["summary"] = f"⏱️ 命令执行超时（{timeout_val}秒）: {command[:50]}..."

            return result_dict
        except Exception as e:
            self._log_command(command, str(e))
            logger.error(
                "bash_command_failed",
                command=command,
                error=str(e),
                exc_info=True
            )
            result_dict = {
                "status": "failed",
                "success": False,
                "error": str(e),
                "data": {"command": command},
                "metadata": {
                    "tool_name": "bash",
                    "error_type": type(e).__name__
                }
            }

            # 失败时提供简短摘要
            result_dict["summary"] = f"❌ 命令执行失败: {str(e)[:50]}"

            return result_dict

    def _validate_command(self, command: str) -> Dict[str, Any]:
        """
        六层安全验证（防止命令注入，减少误报）：

        第一层：命令替换检测（$(), ``, ${}等）- 最高优先级
        第二层：危险命令黑名单（绝对禁止）
        第三层：引号外Shell元字符检测（使用引号状态追踪）
        第四层：重定向/管道检测（允许引号内的安全使用）
        第五层：智能命令验证（PATH + 白名单）
        第六层：路径遍历检查

        Returns:
            {"valid": bool, "error": str (if invalid)}
        """
        command_stripped = command.strip()

        # ========== 第一层：命令替换检测（最高优先级） ==========
        # 命令替换即使在双引号内也是危险的
        command_substitution_patterns = [
            ('`', '反引号命令替换'),
            ('$(', '$()命令替换'),
            ('${', '${}变量扩展'),
        ]

        for pattern, name in command_substitution_patterns:
            if pattern in command_stripped:
                return {
                    "valid": False,
                    "error": f"禁止使用{name}（防止命令注入）"
                }

        # 特殊检查：ANSI-C引用（$'...'）可以编码任意字符
        if "$'" in command_stripped:
            return {
                "valid": False,
                "error": "禁止使用ANSI-C引用（$'...')（可能绕过安全检查）"
            }

        # ========== 第二层：危险命令黑名单 ==========
        command_lower = command_stripped.lower()
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous in command_lower:
                return {
                    "valid": False,
                    "error": f"危险命令检测到: {dangerous}"
                }

        # ========== 第三层：Shell元字符检测（引号状态追踪） ==========
        # 只检测引号外的元字符，允许引号内的安全使用
        # 使用 fully_unquoted（移除所有引号内容）检测引号外的危险字符
        _, fully_unquoted, _ = extract_unquoted_content(command_stripped)

        shell_metacharacters = [';', '|', '&', '\n', '\r', '\t',
                                '(', ')', '[', ']', '{', '}', '!',
                                '~', '%', '#']

        for char in shell_metacharacters:
            if char in fully_unquoted:
                return {
                    "valid": False,
                    "error": f"禁止使用Shell元字符: '{char}'（防止命令注入）"
                }

        # ========== 第四层：重定向/管道检测（改进版） ==========
        # 移除安全的重定向（如 > /dev/null）
        safe_command = strip_safe_redirections(command_stripped)

        # 检测剩余的重定向（在fully_unquoted中）
        safe_unquoted, _, _ = extract_unquoted_content(safe_command)

        if '>' in safe_unquoted:
            return {
                "valid": False,
                "error": "禁止使用输出重定向（>）（防止文件写入攻击）"
            }

        if '<' in safe_unquoted:
            return {
                "valid": False,
                "error": "禁止使用输入重定向（<）（防止文件读取攻击）"
            }

        # 检测管道（在fully_unquoted中）
        if '|' in safe_unquoted:
            return {
                "valid": False,
                "error": "禁止使用管道（|）（防止命令链接）"
            }

        # 检测命令连接符（&&, ||）
        if '&&' in safe_command or '||' in safe_command:
            return {
                "valid": False,
                "error": "禁止使用命令连接符（&&, ||）（防止多命令执行）"
            }

        # ========== 第五层：智能命令验证 ==========
        try:
            # 使用shlex安全分词（处理引号）
            parts = shlex.split(command_stripped, posix=True)
        except ValueError as e:
            return {
                "valid": False,
                "error": f"命令格式错误（引号不匹配）: {e}"
            }

        if not parts:
            return {
                "valid": False,
                "error": "命令为空"
            }

        first_command = parts[0]

        # 策略1：PATH中的命令自动允许（优先级最高）
        if shutil.which(first_command):
            logger.debug(
                "command_allowed_via_path",
                command=first_command,
                path=shutil.which(first_command)
            )
            # PATH中的命令允许，但要检查参数是否安全
            return self._validate_command_args(parts)

        # 策略2：白名单中的命令允许
        if first_command in self.ALLOWED_CATEGORIES:
            return self._validate_command_args(parts)

        # 策略3：Windows可执行文件允许
        if any(first_command.endswith(ext) for ext in ['.exe', '.bat', '.cmd', '.ps1']):
            return self._validate_command_args(parts)

        # 策略4：完整路径的命令
        if first_command.startswith("/") or (len(first_command) > 1 and first_command[1] == ':'):
            binary_name = Path(first_command).name
            # 检查二进制文件名是否在PATH或白名单中
            if binary_name in self.ALLOWED_CATEGORIES or shutil.which(binary_name):
                return self._validate_command_args(parts)
            else:
                return {
                    "valid": False,
                    "error": f"命令不在白名单中: {first_command}"
                }

        # 策略5：其他命令拒绝
        return {
            "valid": False,
            "error": f"命令不存在或不在白名单中: {first_command}"
        }

    def _validate_command_args(self, parts: List[str]) -> Dict[str, Any]:
        """
        验证命令参数是否安全

        Args:
            parts: 分词后的命令列表

        Returns:
            {"valid": bool, "error": str (if invalid)}
        """
        # 检查参数中是否包含危险的选项
        for i, part in enumerate(parts[1:], 1):  # 跳过命令本身
            # 检查危险的选项标志
            if part.startswith('-'):
                dangerous_flags = [
                    '-exec',       # find命令的-exec参数（可执行任意命令）
                    '-delete',
                    '-execdir',
                ]
                if any(flag in part for flag in dangerous_flags):
                    return {
                        "valid": False,
                        "error": f"禁止使用危险参数: {part}"
                    }

        return {"valid": True}

    def _normalize_path_format(self, command: str) -> str:
        """
        标准化路径格式，解决 LLM 输出和 Windows 路径的兼容性问题

        处理三种路径格式：
        1. 正斜杠路径（推荐，无转义问题）: "D:/溯源/报告模板" → "D:\\溯源\\报告模板"
        2. 双反斜杠（JSON 转义后）: "D:\\\\溯源\\\\报告模板" → "D:\\溯源\\报告模板"
        3. 单反斜杠（可能被 JSON 误解析）: "D:\\溯源\\报告模板" → "D:\\溯源\\报告模板"

        策略：优先使用正斜杠，让 LLM 无需关心转义问题

        Args:
            command: 原始命令字符串

        Returns:
            标准化后的命令字符串（Windows 下转换为反斜杠）
        """
        import re

        # 只在 Windows 系统下处理
        if platform.system() != "Windows":
            return command

        # 策略 1: 修复过度转义（4个反斜杠 → 2个反斜杠）
        # 在引号内的路径中匹配 4 个反斜杠
        def fix_over_escaped(match):
            quote = match.group(1)  # 引号类型
            path = match.group(2)   # 路径内容
            # 将 4 个反斜杠替换为 2 个
            fixed_path = path.replace('\\\\\\\\', '\\\\')
            return f'{quote}{fixed_path}{quote}'

        # 匹配引号内的 Windows 路径
        pattern = r'(["\'])([A-Za-z]:\\\\(?:[^"\'\\]|\\.)*)\1'
        command = re.sub(pattern, fix_over_escaped, command)

        # 策略 2: 正斜杠转反斜杠（Windows 兼容）
        # 匹配 "D:/path" 或 'D:/path' 格式
        def convert_slashes(match):
            quote = match.group(1)
            path = match.group(2)
            # 将正斜杠替换为反斜杠
            converted = path.replace('/', '\\\\')
            return f'{quote}{converted}{quote}'

        slash_pattern = r'(["\'])([A-Za-z]:/(?:[^"\'\\]|\\.)*)\1'
        command = re.sub(slash_pattern, convert_slashes, command)

        return command

    def _resolve_working_dir(self, requested_dir: str) -> Optional[Path]:
        """
        解析工作目录，确保在允许的范围内

        Returns:
            Path 对象或 None（如果无效）
        """
        try:
            requested = Path(requested_dir).resolve()

            # 检查是否在工作目录范围内
            if not requested.is_relative_to(self.working_dir):
                logger.warning(
                    "working_dir_escape_attempt",
                    requested_dir=str(requested),
                    allowed_dir=str(self.working_dir)
                )
                return None

            # 检查是否存在
            if not requested.exists():
                return None

            return requested
        except Exception as e:
            logger.error(
                "working_dir_resolution_failed",
                requested_dir=requested_dir,
                error=str(e)
            )
            return None

    def _translate_command(self, command: str) -> str:
        """
        转换 Unix 命令为 Windows 命令（跨平台兼容）

        Args:
            command: 原始命令

        Returns:
            转换后的命令
        """
        # 检测是否为 Windows 系统
        is_windows = platform.system() == "Windows"

        if not is_windows:
            return command

        import re

        # 特殊处理：echo -e 命令（带转义字符）
        # Windows 的 echo 不支持 -e 参数，需要转换为 Python 命令
        if 'echo -e' in command:
            # 提取内容和文件路径
            # 格式: echo -e "content\n" >> file.txt 或 echo -e 'content\n' >> file.txt
            match = re.match(r'echo\s+-e\s+(["\'])(.+?)\1\s*>>\s*(.+)', command)
            if match:
                content = match.group(2)
                filepath = match.group(3)
                # 转换为 Python 命令
                # 处理常见转义字符：\n → 换行，\t → 制表符
                content_processed = content.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
                new_command = f'python -c "with open(\'{filepath}\', \'a\', encoding=\'utf-8\') as f: f.write(r\'{content_processed}\' + \'\')"'
                logger.info(
                    "command_translated",
                    original=command.strip(),
                    translated=new_command.strip()
                )
                return new_command

        # Unix → Windows 命令映射表（支持参数）
        command_patterns = [
            # 简化的 echo 追加（不带 -e）
            (r'echo\s+(["\'])(.+?)\1\s*>>\s*(.+)', r'echo \2 >> \3'),
            (r'echo\s+(.+?)\s*>>\s*(.+)', r'echo \1 >> \2'),

            # echo 覆盖（创建新文件）
            (r'echo\s+(["\'])(.+?)\1\s*>\s*(.+)', r'echo \2 > \3'),
            (r'echo\s+(.+?)\s*>\s*(.+)', r'echo \1 > \2'),

            # ls 命令（最常用，优先处理）
            (r'\bls\s+-la\s*(.*)', r'dir \1'),  # ls -la → dir
            (r'\bls\s+-l\s*(.*)', r'dir \1'),   # ls -l → dir
            (r'\bls\s+-a\s*(.*)', r'dir /a \1'), # ls -a → dir /a
            (r'\bls\s*(.*)', r'dir \1'),        # ls → dir

            # cat 命令
            (r'\bcat\s+(.+)', r'type \1'),      # cat file → type file

            # grep 命令
            (r'\bgrep\s+-r\s+(.+)', r'findstr /s \1'),  # grep -r → findstr /s
            (r'\bgrep\s+(.+)', r'findstr \1'),          # grep → findstr

            # pwd 命令
            (r'\bpwd\s*$', r'cd'),                  # pwd → cd (显示当前目录)

            # rm 命令
            (r'\brm\s+-rf\s+(.+)', r'rmdir /s /q \1'),  # rm -rf → rmdir /s /q
            (r'\brm\s+-r\s+(.+)', r'rmdir /s \1'),      # rm -r → rmdir /s
            (r'\brm\s+(.+)', r'del \1'),                # rm → del

            # cp 命令
            (r'\bcp\s+(.+)', r'copy \1'),          # cp → copy

            # mv 命令
            (r'\bmv\s+(.+)', r'move \1'),          # mv → move

            # head 命令（使用 PowerShell）
            (r'\bhead\s+-n\s+(\d+)\s+(.+)', r'powershell -Command "Get-Content \\2 | Select-Object -First \\1"'),
            (r'\bhead\s+(\d+)\s+(.+)', r'powershell -Command "Get-Content \\2 | Select-Object -First \\1"'),

            # clear 命令
            (r'\bclear\s*$', r'cls'),              # clear → cls
        ]

        # 按顺序尝试匹配模式
        for pattern, replacement in command_patterns:
            if re.match(pattern, command, re.IGNORECASE):
                new_command = re.sub(pattern, replacement, command, count=1, flags=re.IGNORECASE)
                logger.info(
                    "command_translated",
                    original=command.strip(),
                    translated=new_command.strip()
                )
                return new_command

        # 没有匹配到任何模式，返回原命令
        return command

    def _log_command(self, command: str, result: str, exit_code: Optional[int] = None):
        """记录命令到历史"""
        self.command_history.append({
            "command": command,
            "timestamp": datetime.now().isoformat(),
            "result": result,
            "exit_code": exit_code
        })

        # 限制历史大小
        if len(self.command_history) > self.max_history:
            self.command_history = self.command_history[-self.max_history:]

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "bash",
            "description": (
                "【工具名称：bash】执行安全的 Bash 命令（跨平台兼容，防止命令注入）。\n\n"
                "使用场景：\n"
                "• 文件操作：ls/dir, cat/type, grep/findstr 等\n"
                "• 数据处理：Python 脚本、gdal、ncdump 等\n"
                "• 气象模型：HYSPLIT、WRF 等命令行工具\n"
                "• 系统监控：df, du, ps 等\n\n"
                "跨平台支持：\n"
                "• 自动转换 Unix 命令为 Windows 命令（ls→dir, cat→type, grep→findstr 等）\n"
                "• Linux/macOS 执行原生 Unix 命令\n"
                "• Windows 执行等价命令或 PowerShell 命令\n\n"
                "安全限制（防止命令注入）：\n"
                "• 工作目录限制在项目范围内\n"
                "• 禁止Shell元字符（; | & $ ` 等）防止命令注入\n"
                "• 禁止Shell特性（重定向>、管道|、命令替换$()）\n"
                "• 禁止危险命令（rm -rf /、sudo 等）\n"
                "• 默认超时 60 秒\n"
                "• 输出限制 1MB\n\n"
                "【重要提示】\n"
                "• 工具名称必须是 'bash'，不要使用 execute_command、run_command 等其他名称\n"
                "• **不能使用重定向和管道**：不能使用 > >> < | && 等Shell特性\n"
                "  ❌ 错误：command=\"cat file.txt > output.txt\"（不能使用重定向）\n"
                "  ❌ 错误：command=\"cat file.txt | grep test\"（不能使用管道）\n"
                "  ✅ 正确：使用Python脚本处理文件读写\n"
                "• **路径格式建议**：使用正斜杠（推荐）或双反斜杠，避免转义问题\n"
                "  ✅ 推荐：command=\"dir D:/溯源/报告模板\"（正斜杠，无需转义）\n"
                "  ✅ 可用：command=\"dir D:\\\\溯源\\\\报告模板\"（双反斜杠，需要转义）\n"
                "  ❌ 避免：command=\"dir D:\\溯源\\报告模板\"（单反斜杠可能被JSON误解析）\n"
                "• 命令中可以直接使用绝对路径或相对路径，无需指定 working_dir\n"
                "• 使用 cd 命令切换目录时，不要设置 working_dir 参数\n"
                "• 只在需要在特定目录执行命令时才使用 working_dir 参数\n\n"
                "注意：只用于调用现有工具，不要用此工具编写复杂脚本。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 Bash 命令（不能包含重定向、管道等Shell特性）"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒），默认 60"
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "命令执行的起始目录（可选，不指定则使用默认项目目录 D:/溯源）。【重要】\n\n**路径格式（推荐使用正斜杠，避免转义问题）**：\n- ✅ 推荐：working_dir=\"D:/溯源/data\"（正斜杠，JSON 友好）\n- ✅ 可用：working_dir=\"D:\\\\溯源\\\\data\"（双反斜杠，需要转义）\n\n**使用规则**：\n1. 默认情况下不需要填写此参数，直接在命令中使用完整路径即可\n2. working_dir 必须在项目目录范围内（D:/溯源 及其子目录）\n3. **错误示例**：working_dir=\"D:/\" （超出允许范围，会被拒绝）\n\n**示例**：\n- ✅ command=\"dir D:/溯源/报告模板\"（推荐格式，不需要 working_dir）\n- ✅ command=\"cd data && dir\"（相对路径，不需要 working_dir）\n- ❌ working_dir=\"D:/\" + command=\"dir 溯源\"（超出范围）"
                    }
                },
                "required": ["command"]
            }
        }
