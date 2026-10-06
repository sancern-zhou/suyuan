"""Bash execution tool with real shell semantics and bounded resources."""

from __future__ import annotations

import asyncio
import os
import platform
import signal
import shutil
import subprocess
import tempfile
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import file_products
from app.utils import path_config

logger = structlog.get_logger()
resolve_agent_path = path_config.resolve_agent_path


class BashTool(LLMTool):
    """Execute a real shell command without a command-name allowlist.

    Shell syntax is validated by Bash itself.  Bubblewrap isolates host paths
    while this tool bounds runtime, inline output and process lifetime.
    """

    DEFAULT_TIMEOUT = 120
    MAX_TIMEOUT = 600
    MAX_OUTPUT_BYTES = 30_000
    MAX_CAPTURE_BYTES = 5_000_000
    TERMINATION_GRACE_SECONDS = 1.0

    def __init__(self) -> None:
        super().__init__(
            name="bash",
            description="执行 Bash 命令并返回结构化结果",
            category=ToolCategory.QUERY,
            version="2.0.0",
            requires_context=False,
        )
        self.working_dir = path_config.PROJECT_ROOT
        self.default_timeout = self.DEFAULT_TIMEOUT
        self.max_output_size = self.MAX_OUTPUT_BYTES
        self.command_history: List[Dict[str, Any]] = []
        self.max_history = 1000

    async def execute(
        self,
        context: Any = None,
        command: str | None = None,
        timeout: Optional[int] = None,
        working_dir: Optional[str] = None,
        output_paths: Optional[List[str]] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        if not command or not command.strip():
            return self._failure("Missing required parameter: command", "spawn_error", "MISSING_PARAMETER")

        command = command.strip()
        validation = self._validate_command(command)
        if not validation["valid"]:
            self._log_command(command, validation["error"])
            return self._failure(validation["error"], "spawn_error", "COMMAND_NOT_PARSABLE", command=command)

        work_dir = self._resolve_working_dir(working_dir)
        if work_dir is None:
            self._log_command(command, "Invalid working directory")
            return self._failure(
                f"工作目录无效或超出项目范围: {working_dir or self.working_dir}",
                "spawn_error",
                "INVALID_WORKING_DIR",
                command=command,
            )

        timeout_value = self._resolve_timeout(timeout)
        process: asyncio.subprocess.Process | None = None
        capture_tasks: list[asyncio.Task] = []
        output_dir = self._output_directory(context)
        output_files: list[Path] = []
        retained_files: set[Path] = set()
        started = datetime.now().isoformat()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info("bash_command_executing", command=command, working_dir=str(work_dir), timeout=timeout_value)
            process = await asyncio.create_subprocess_exec(
                *self._execution_command(command, work_dir, context),
                cwd=str(work_dir),
                stdin=subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=(os.name != "nt"),
                env=self._build_environment(),
            )
            async def capture(stream: asyncio.StreamReader, label: str) -> tuple[str, bool, Path]:
                with tempfile.NamedTemporaryFile(
                    mode="wb", prefix=f"bash-{label}-", suffix=".log",
                    dir=output_dir, delete=False,
                ) as handle:
                    path = Path(handle.name)
                    output_files.append(path)
                    preview = bytearray()
                    total = 0
                    exceeded = False
                    while chunk := await stream.read(64 * 1024):
                        allowed = max(0, self.MAX_CAPTURE_BYTES - total)
                        if allowed:
                            handle.write(chunk[:allowed])
                            preview.extend(chunk[: max(0, self.MAX_OUTPUT_BYTES + 1 - len(preview))])
                            total += min(len(chunk), allowed)
                        if len(chunk) > allowed:
                            exceeded = True
                            if process.returncode is None:
                                self._signal_process_tree(process, signal.SIGKILL)
                return preview.decode("utf-8", errors="replace"), exceeded, path

            stdout_task = asyncio.create_task(capture(process.stdout, "stdout"))
            stderr_task = asyncio.create_task(capture(process.stderr, "stderr"))
            capture_tasks = [stdout_task, stderr_task]
            deadline = asyncio.get_running_loop().time() + timeout_value
            try:
                await asyncio.wait_for(process.wait(), timeout=max(0, deadline - asyncio.get_running_loop().time()))
                captured = await asyncio.wait_for(
                    asyncio.shield(asyncio.gather(*capture_tasks)),
                    timeout=max(0, deadline - asyncio.get_running_loop().time()),
                )
            except asyncio.TimeoutError:
                await self._terminate_process_tree(process)
                try:
                    await asyncio.wait_for(asyncio.gather(*capture_tasks), timeout=2)
                except asyncio.TimeoutError:
                    for task in capture_tasks:
                        task.cancel()
                captured = await asyncio.gather(*capture_tasks, return_exceptions=True)
                stdout, _, stdout_path = captured[0] if isinstance(captured[0], tuple) else ("", False, None)
                stderr, _, stderr_path = captured[1] if isinstance(captured[1], tuple) else ("", False, None)
                if stdout_path is not None:
                    retained_files.add(stdout_path)
                if stderr_path is not None:
                    retained_files.add(stderr_path)
                self._log_command(command, "timeout")
                return self._failure(
                    f"Command timed out after {timeout_value}s", "timed_out", "TIMEOUT",
                    command=command, timeout=timeout_value,
                    stdout=self._limit_output(stdout)[0], stderr=self._limit_output(stderr)[0],
                    stdout_path=path_config.format_agent_path(stdout_path) if stdout_path else None,
                    stderr_path=path_config.format_agent_path(stderr_path) if stderr_path else None,
                )
            (stdout, stdout_exceeded, stdout_path), (stderr, stderr_exceeded, stderr_path) = captured
            if stdout_exceeded or stderr_exceeded:
                retained_files.update((stdout_path, stderr_path))
                self._log_command(command, "output_limit")
                return self._failure(
                    f"Command output exceeded {self.MAX_CAPTURE_BYTES} bytes per stream",
                    "output_limit", "OUTPUT_LIMIT", command=command,
                    stdout=self._limit_output(stdout)[0], stderr=self._limit_output(stderr)[0],
                    stdout_path=path_config.format_agent_path(stdout_path),
                    stderr_path=path_config.format_agent_path(stderr_path),
                )
            returncode = process.returncode
            result = self._success_result(
                command, work_dir, stdout or "", stderr or "", returncode,
                timeout_value, started, output_paths,
            )
            for label, path in (("stdout", stdout_path), ("stderr", stderr_path)):
                if result["metadata"][f"{label}_truncated"]:
                    result["metadata"][f"{label}_path"] = path_config.format_agent_path(path)
                    retained_files.add(path)
            self._log_command(command, "success" if returncode == 0 else "failed", returncode)
            return result
        except asyncio.CancelledError:
            if process is not None:
                await self._terminate_process_tree(process)
            raise
        except Exception as exc:
            self._log_command(command, str(exc))
            logger.error("bash_command_failed", command=command, error=str(exc), exc_info=True)
            return self._failure(str(exc), "spawn_error", type(exc).__name__, command=command)
        finally:
            if process is not None and any(not task.done() for task in capture_tasks):
                await self._terminate_process_tree(process)
                for task in capture_tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*capture_tasks, return_exceptions=True)
            elif process is not None and process.returncode is None:
                await self._terminate_process_tree(process)
            for path in output_files:
                if path not in retained_files:
                    path.unlink(missing_ok=True)

    def _output_directory(self, context: Any) -> Path:
        try:
            session_dir = resolve_agent_path(context.data_manager.memory.session.data_dir)
            if session_dir.is_relative_to(path_config.get_data_registry()):
                return session_dir / "bash_outputs"
        except (AttributeError, TypeError, ValueError):
            pass
        return Path(tempfile.gettempdir()) / "suyuan-bash-output"

    def _validate_command(self, command: str) -> Dict[str, Any]:
        """Parse shell syntax without rejecting valid shell features."""
        if "\x00" in command:
            return {"valid": False, "error": "命令包含 NUL 字符"}
        if platform.system() == "Windows":
            return {"valid": True}
        try:
            check = subprocess.run(
                ["bash", "-n", "-c", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"valid": False, "error": f"Shell 语法检查失败: {exc}"}
        if check.returncode != 0:
            return {"valid": False, "error": f"Shell 语法错误: {(check.stderr or '命令语法无效').strip()}"}
        return {"valid": True}

    def _shell_command(self, command: str) -> List[str]:
        if os.name == "nt":
            return ["cmd.exe", "/d", "/s", "/c", command]
        return ["bash", "-c", command]

    def _execution_command(self, command: str, work_dir: Path, context: Any = None) -> List[str]:
        shell = self._shell_command(command)
        if os.name == "nt":
            return shell

        bwrap = shutil.which("bwrap")
        if not bwrap:
            raise RuntimeError("Bash 沙箱不可用：未找到 bubblewrap")

        python_env = Path(sys.prefix).resolve()
        command = [
            bwrap,
            "--die-with-parent",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--cap-drop", "ALL",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/etc", "/etc",
            "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib64", "/lib64",
            "--dir", "/home",
            "--dir", "/home/xckj",
            "--dir", "/home/software",
            "--ro-bind-try", "/home/software/nimiconda3", "/home/software/nimiconda3",
            "--dir", "/root",
            "--dir", "/root/miniconda3",
            "--dir", "/root/miniconda3/envs",
            "--ro-bind-try", str(python_env), str(python_env),
            "--bind", str(self.working_dir), str(self.working_dir),
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--setenv", "HOME", "/tmp",
            "--chdir", str(work_dir),
        ]
        # Keep git metadata visible when this workspace is a linked worktree.
        git_file = self.working_dir / ".git"
        if git_file.is_file():
            first_line = git_file.read_text(encoding="utf-8").strip()
            if first_line.startswith("gitdir: "):
                git_dir = resolve_agent_path(git_file.parent / first_line[8:])
                if git_dir.is_dir() and not git_dir.is_relative_to(self.working_dir):
                    common_dir = git_dir.parents[1] if git_dir.parent.name == "worktrees" else git_dir
                    command.extend(["--ro-bind", str(common_dir), str(common_dir)])
            command.extend(["--ro-bind", str(git_file), str(git_file)])
        for protected in (
            self.working_dir / "backend/app",
            self.working_dir / "backend/config",
            self.working_dir / "backend/alembic",
            self.working_dir / "deploy",
            self.working_dir / ".github",
            self.working_dir / "scripts",
        ):
            if protected.is_dir():
                command.extend(["--ro-bind", str(protected), str(protected)])
        for secret in self.working_dir.glob("backend/.env*"):
            if secret.is_file() and not secret.is_symlink():
                command.extend(["--ro-bind", "/dev/null", str(secret)])
        registry = path_config.get_data_registry()
        project_registry = self.working_dir / "backend/backend_data_registry"
        if project_registry.is_dir():
            command.extend(["--tmpfs", str(project_registry)])
        if registry != project_registry and registry.is_relative_to(self.working_dir):
            command.extend(["--tmpfs", str(registry)])

        session_dir = None
        if context is not None:
            try:
                candidate = resolve_agent_path(context.data_manager.memory.session.data_dir)
                if candidate.is_dir() and candidate.is_relative_to(registry):
                    session_dir = candidate
            except (AttributeError, TypeError, ValueError):
                pass
        if session_dir is not None:
            self._append_mount_parents(command, session_dir.parent)
            command.extend(["--bind", str(session_dir), str(session_dir)])
        if context is not None:
            authorized = [
                *(getattr(context, "available_file_paths", []) or []),
                *(getattr(context, "authorized_input_paths", []) or []),
            ]
            for raw_path in dict.fromkeys(authorized):
                try:
                    path = resolve_agent_path(raw_path)
                except (TypeError, ValueError, OSError):
                    continue
                if not path.is_file() or path_config.is_agent_sensitive_path(path):
                    continue
                if session_dir is not None and path.is_relative_to(session_dir):
                    continue
                # Project files are already visible; only data-registry or external
                # inputs need explicit mounts.
                if path.is_relative_to(self.working_dir) and not path.is_relative_to(registry):
                    continue
                self._append_mount_parents(command, path.parent)
                command.extend(["--ro-bind", str(path), str(path)])
        return [*command, *shell]

    def _append_mount_parents(self, command: List[str], parent: Path) -> None:
        missing = []
        current = parent
        while current != current.parent and not (
            current == self.working_dir or current.is_relative_to(self.working_dir)
        ):
            missing.append(current)
            current = current.parent
        for directory in reversed(missing):
            command.extend(["--dir", str(directory)])
        if parent.is_relative_to(self.working_dir):
            root = path_config.get_data_registry()
            for directory in reversed([parent, *parent.parents]):
                if directory == root or directory.is_relative_to(root):
                    command.extend(["--dir", str(directory)])

    @staticmethod
    def _build_environment() -> Dict[str, str]:
        return {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "HOME": "/tmp",
            "TERM": "dumb",
            "NO_COLOR": "1",
            "PYTHONUNBUFFERED": "1",
        }

    def _resolve_timeout(self, timeout: Optional[int]) -> int:
        value = self.default_timeout if timeout is None else int(timeout)
        return max(1, min(value, self.MAX_TIMEOUT))

    def _resolve_working_dir(self, requested_dir: Optional[str]) -> Optional[Path]:
        try:
            requested = resolve_agent_path(requested_dir or self.working_dir)
            if not requested.is_relative_to(self.working_dir) or not requested.is_dir():
                return None
            return requested
        except (OSError, ValueError):
            return None

    @classmethod
    def _limit_output(cls, value: str) -> tuple[str, bool]:
        encoded = value.encode("utf-8", errors="replace")
        if len(encoded) <= cls.MAX_OUTPUT_BYTES:
            return value, False
        clipped = encoded[: cls.MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore")
        return clipped + "\n... (output truncated)", True

    def _success_result(
        self,
        command: str,
        work_dir: Path,
        stdout: str,
        stderr: str,
        returncode: int,
        timeout: int,
        started: str,
        output_paths: Optional[List[str]],
    ) -> Dict[str, Any]:
        stdout, stdout_truncated = self._limit_output(stdout)
        stderr, stderr_truncated = self._limit_output(stderr)
        result: Dict[str, Any] = {
            "status": "success" if returncode == 0 else "failed",
            "success": returncode == 0,
            "data": {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": returncode,
                "command": command,
                "working_directory": str(work_dir),
            },
            "metadata": {
                "tool_name": "bash",
                "timeout": timeout,
                "stdout_length": len(stdout),
                "stderr_length": len(stderr),
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "started_at": started,
                "execution_status": "completed" if returncode == 0 else "failed",
            },
        }
        if returncode == 0 and output_paths:
            resolved_outputs = []
            for output_path in output_paths:
                try:
                    candidate = resolve_agent_path(output_path)
                    if candidate.is_relative_to(self.working_dir):
                        resolved_outputs.append(candidate)
                except (OSError, ValueError):
                    continue
            if resolved_outputs:
                result["resources"] = file_products(resolved_outputs, tool_name=self.name)
        return result

    @staticmethod
    def _failure(error: str, status: str, error_type: str, **data: Any) -> Dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": error,
            "data": data or None,
            "metadata": {"tool_name": "bash", "error_type": error_type, "execution_status": status},
            "summary": error,
        }

    @staticmethod
    def _signal_process_tree(process: asyncio.subprocess.Process, sig: signal.Signals) -> None:
        if os.name != "nt":
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            return
        if process.returncode is None:
            process.kill()

    @classmethod
    async def _terminate_process_tree(cls, process: asyncio.subprocess.Process) -> None:
        cls._signal_process_tree(process, signal.SIGTERM)
        if process.returncode is not None:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=cls.TERMINATION_GRACE_SECONDS)
        except asyncio.TimeoutError:
            cls._signal_process_tree(process, signal.SIGKILL)
            await process.wait()

    def _log_command(self, command: str, result: str, exit_code: Optional[int] = None) -> None:
        self.command_history.append({
            "command": command,
            "timestamp": datetime.now().isoformat(),
            "result": result,
            "exit_code": exit_code,
        })
        if len(self.command_history) > self.max_history:
            del self.command_history[: -self.max_history]

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": "bash",
            "description": (
                "执行 Bash/Shell 命令并返回结构化结果。支持管道、重定向、条件执行、"
                "脚本片段和常见 CLI；命令在项目目录内运行，默认超时120秒，最大600秒，"
                "超过30KB的输出在结果中预览并提供完整输出文件路径；单路输出达到5MB时终止。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 Shell 命令"},
                    "timeout": {"type": "integer", "description": "超时时间（秒），默认120，最大600"},
                    "working_dir": {"type": "string", "description": "项目目录内的工作目录，可选"},
                    "output_paths": {
                        "type": "array", "items": {"type": "string"},
                        "description": "命令产生的项目内文件路径",
                    },
                },
                "required": ["command"],
            },
        }
