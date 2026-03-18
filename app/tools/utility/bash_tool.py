"""
Bash Command Execution Tool

安全地执行 Bash 命令，用于扩展 Agent 能力：
- 调用外部命令行工具（HYSPLIT、WRF、CMAQ 等气象模型）
- 数据处理（gdal、ncdump、Python 脚本）
- 文件系统操作（批量处理、格式转换）
- 系统监控（磁盘空间、进程状态）

安全措施：
1. 工作目录限制：只能在工作目录内操作
2. 危险命令黑名单：禁止 rm -rf /、sudo、shutdown 等
3. 超时保护：默认 60 秒超时
4. 输出截断：限制输出大小（50KB）
5. 白名单模式：只允许特定命令类别
"""

import subprocess
import shutil
import platform
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


class BashTool(LLMTool):
    """
    Bash 命令执行工具（安全版本）

    设计参考：
    - openwork-dev: Rust std::process::Command
    - learn-claude-code: v0_bash_agent 的安全措施
    """

    # 危险命令黑名单
    DANGEROUS_COMMANDS = [
        "rm -rf /",
        "rm -rf /*",
        "rm -Rf /",
        "sudo",
        "su ",
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "mkfs",
        "dd if=/dev/zero",
        "> /dev/sda",
        "chmod 000",
        "chown root",
        "iptables -F",
        ":(){:|:&};:",  # fork bomb
    ]

    # 允许的命令类别（白名单）- 包含 Unix 和 Windows 命令
    ALLOWED_CATEGORIES = {
        # 文件操作 - Unix 命令
        "ls", "cd", "pwd", "mkdir", "rmdir", "cp", "mv", "cat", "head", "tail",
        "grep", "find", "locate", "wc", "sort", "uniq", "cut", "awk", "sed",

        # 文件操作 - Windows 命令
        "dir", "type", "del", "copy", "move", "findstr", "cls",

        # 数据处理
        "python", "python3",
        "gdal", "ncdump", "ncview", "cdo", "nco",

        # 气象/环境模型
        "hyts_std",  # HYSPLIT
        "wrf",

        # 系统监控
        "df", "du", "free", "top", "ps", "uptime",

        # 网络
        "curl", "wget", "rsync",

        # 压缩/解压
        "tar", "gzip", "gunzip", "zip", "unzip",

        # 其他安全工具
        "echo", "date", "which", "whereis", "type", "test"
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

        # 工作目录：默认为项目根目录
        self.working_dir = Path.cwd().parent  # D:\溯源\ 或 /opt/app/ 等
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

        # 3. 执行命令
        timeout_val = timeout or self.default_timeout

        try:
            logger.info(
                "bash_command_executing",
                command=command,
                working_dir=str(work_dir),
                timeout=timeout_val
            )

            # Windows 下使用 GBK 编码读取本地命令输出，其他情况使用 UTF-8
            is_windows = platform.system() == "Windows"
            output_encoding = 'gbk' if (is_windows and not any(cmd in command for cmd in ['python', 'node', 'java', 'hyts_std', 'wrf'])) else 'utf-8'

            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                encoding=output_encoding,  # Windows: GBK for local commands, UTF-8 for scripts
                errors='replace',           # 替换无法解码的字符
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
        安全检查命令

        Returns:
            {"valid": bool, "error": str (if invalid)}
        """
        command_lower = command.lower().strip()

        # 1. 检查黑名单
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous in command_lower:
                return {
                    "valid": False,
                    "error": f"Dangerous command detected: {dangerous}"
                }

        # 2. 检查命令白名单（提取第一个命令）
        parts = command.split()
        if parts:
            first_command = parts[0]

            # 检查是否是完整路径
            if first_command.startswith("/"):
                binary_name = Path(first_command).name
                if binary_name not in self.ALLOWED_CATEGORIES:
                    return {
                        "valid": False,
                        "error": f"Command not in whitelist: {first_command}"
                    }
            elif first_command not in self.ALLOWED_CATEGORIES:
                # Windows 平台允许 .exe, .bat, .cmd 等扩展名
                if not any(first_command.endswith(ext) for ext in ['.exe', '.bat', '.cmd', '.ps1']):
                    # 检查命令是否存在于 PATH 中
                    if not shutil.which(first_command):
                        return {
                            "valid": False,
                            "error": f"Command not found in whitelist or PATH: {first_command}"
                        }

        # 3. 检查路径遍历攻击
        if "../" in command and "rm " in command:
            return {
                "valid": False,
                "error": "Path traversal with rm command detected"
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
                "【工具名称：bash】执行安全的 Bash 命令（跨平台兼容）。\n\n"
                "使用场景：\n"
                "• 文件操作：ls/dir, cat/type, grep/findstr 等\n"
                "• 数据处理：Python 脚本、gdal、ncdump 等\n"
                "• 气象模型：HYSPLIT、WRF 等命令行工具\n"
                "• 系统监控：df, du, ps 等\n\n"
                "跨平台支持：\n"
                "• 自动转换 Unix 命令为 Windows 命令（ls→dir, cat→type, grep→findstr 等）\n"
                "• Linux/macOS 执行原生 Unix 命令\n"
                "• Windows 执行等价命令或 PowerShell 命令\n\n"
                "安全限制：\n"
                "• 工作目录限制在项目范围内\n"
                "• 禁止危险命令（rm -rf /、sudo 等）\n"
                "• 默认超时 60 秒\n"
                "• 输出限制 50KB\n\n"
                "【重要提示】\n"
                "• 工具名称必须是 'bash'，不要使用 execute_command、run_command 等其他名称\n"
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
                        "description": "要执行的 Bash 命令"
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
