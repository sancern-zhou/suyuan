"""Long-lived interactive process sessions for social mode.

This tool is intentionally separate from cli_session:
- cli_session delegates one turn to Claude Code / Codex and exits.
- terminal_session keeps a normal stdin/stdout process alive across social turns.

Pipe mode supports ordinary line-oriented scripts and REPL-like programs, such
as guess-number games. Linux PTY mode gives real terminal behavior for shells,
Claude Code CLIs, and simple TUI programs.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import file_products
from app.utils.path_config import PROJECT_ROOT

logger = structlog.get_logger(__name__)


MAX_BUFFER_CHARS = 200_000
DEFAULT_READ_TIMEOUT = 1.0
DEFAULT_MAX_OUTPUT_CHARS = 6000
MAX_SESSIONS_PER_USER = 3
IDLE_TTL_SECONDS = 1800
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


@dataclass
class ProcessSession:
    id: str
    user_key: str
    session_name: str
    command: str
    args: List[str]
    cwd: str
    process: Any
    backend: str
    started_at: float
    last_activity: float
    output_buffer: str = ""
    read_cursor: int = 0
    stdout_task: Optional[asyncio.Task] = None
    stderr_task: Optional[asyncio.Task] = None
    pty_task: Optional[asyncio.Task] = None
    pty_master_fd: Optional[int] = None
    exit_code: Optional[int] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def running(self) -> bool:
        poll = getattr(self.process, "poll", None)
        if callable(poll):
            return poll() is None
        return self.process.returncode is None


class TerminalSessionManager:
    """In-memory registry for interactive process sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[Tuple[str, str], ProcessSession] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        user_key: str,
        session_name: str,
        command: str,
        args: List[str],
        cwd: Path,
        backend: str,
        columns: int,
        rows: int,
        restart: bool,
        read_timeout: float,
    ) -> Tuple[bool, Optional[ProcessSession], str, str]:
        key = (user_key, session_name)
        async with self._lock:
            await self._cleanup_locked()
            existing = self._sessions.get(key)
            if existing and existing.running and not restart:
                output = await self.read(existing, read_timeout=0, max_output_chars=DEFAULT_MAX_OUTPUT_CHARS)
                return False, existing, "会话已存在且仍在运行；如需重启请设置 restart=true", output
            if existing:
                await self.stop(existing)
                self._sessions.pop(key, None)

            active_for_user = [
                item for item in self._sessions.values()
                if item.user_key == user_key and item.running
            ]
            if len(active_for_user) >= MAX_SESSIONS_PER_USER:
                return False, None, f"当前用户交互进程已达上限 {MAX_SESSIONS_PER_USER}", ""

            env = os.environ.copy()
            env.setdefault("NO_COLOR", "1")
            env.setdefault("TERM", "dumb")
            env.setdefault("PYTHONUNBUFFERED", "1")
            env.setdefault("TOKENIZERS_PARALLELISM", "false")

            try:
                if backend == "pty":
                    process, master_fd = await self._start_pty_process(args, cwd, env, columns, rows)
                else:
                    process = await asyncio.create_subprocess_exec(
                        *args,
                        cwd=str(cwd),
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                    )
                    master_fd = None
            except Exception as exc:
                logger.error("terminal_session_start_failed", command=command, error=str(exc), exc_info=True)
                return False, None, str(exc), ""

            now = time.time()
            session = ProcessSession(
                id=f"term_{uuid.uuid4().hex[:12]}",
                user_key=user_key,
                session_name=session_name,
                command=command,
                args=args,
                cwd=str(cwd),
                process=process,
                backend=backend,
                started_at=now,
                last_activity=now,
                pty_master_fd=master_fd,
            )
            if backend == "pty":
                session.pty_task = asyncio.create_task(self._pty_reader_loop(session))
            else:
                session.stdout_task = asyncio.create_task(self._reader_loop(session, process.stdout, "stdout"))
                session.stderr_task = asyncio.create_task(self._reader_loop(session, process.stderr, "stderr"))
            self._sessions[key] = session

        output = await self.read(session, read_timeout=read_timeout, max_output_chars=DEFAULT_MAX_OUTPUT_CHARS)
        return True, session, "", output

    async def send(
        self,
        session: ProcessSession,
        text: str,
        read_timeout: float,
        max_output_chars: int,
        append_newline: bool,
    ) -> Tuple[bool, str]:
        async with session.lock:
            if not session.running:
                return False, await self.read(session, read_timeout=0, max_output_chars=max_output_chars)
            try:
                payload = text if not append_newline else text.rstrip("\n") + "\n"
                if session.backend == "pty":
                    if session.pty_master_fd is None:
                        return False, "PTY master 不可用"
                    os.write(session.pty_master_fd, payload.encode("utf-8"))
                else:
                    if session.process.stdin is None:
                        return False, "进程 stdin 不可用"
                    session.process.stdin.write(payload.encode("utf-8"))
                    await session.process.stdin.drain()
                session.last_activity = time.time()
            except Exception as exc:
                return False, f"写入 stdin 失败: {exc}"
        return True, await self.read(session, read_timeout=read_timeout, max_output_chars=max_output_chars)

    async def read(self, session: ProcessSession, read_timeout: float, max_output_chars: int) -> str:
        if read_timeout > 0:
            await asyncio.sleep(read_timeout)
        session.exit_code = self._returncode(session)
        new_output = session.output_buffer[session.read_cursor:]
        session.read_cursor = len(session.output_buffer)
        if not new_output:
            new_output = self._tail(session.output_buffer, max_output_chars)
        return self._tail(new_output, max_output_chars)

    async def stop(self, session: ProcessSession) -> str:
        if session.running:
            try:
                session.process.terminate()
                try:
                    await self._wait_process(session.process, timeout=3)
                except asyncio.TimeoutError:
                    session.process.kill()
                    await self._wait_process(session.process, timeout=3)
            except ProcessLookupError:
                pass
            except Exception as exc:
                logger.warning("terminal_session_stop_failed", session_id=session.id, error=str(exc))
        session.exit_code = self._returncode(session)
        if session.pty_master_fd is not None:
            try:
                os.close(session.pty_master_fd)
            except OSError:
                pass
            session.pty_master_fd = None
        for task in (session.stdout_task, session.stderr_task, session.pty_task):
            if task and not task.done():
                task.cancel()
        return self._tail(session.output_buffer, DEFAULT_MAX_OUTPUT_CHARS)

    async def get(self, user_key: str, session_name: str) -> Optional[ProcessSession]:
        async with self._lock:
            await self._cleanup_locked()
            return self._sessions.get((user_key, session_name))

    async def list(self, user_key: str) -> List[ProcessSession]:
        async with self._lock:
            await self._cleanup_locked()
            return [session for session in self._sessions.values() if session.user_key == user_key]

    async def remove(self, user_key: str, session_name: str) -> None:
        key = (user_key, session_name)
        async with self._lock:
            session = self._sessions.pop(key, None)
        if session:
            await self.stop(session)

    async def discard(self, user_key: str, session_name: str) -> None:
        key = (user_key, session_name)
        async with self._lock:
            self._sessions.pop(key, None)

    async def _reader_loop(
        self,
        session: ProcessSession,
        stream: Optional[asyncio.StreamReader],
        stream_name: str,
    ) -> None:
        if stream is None:
            return
        try:
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                if stream_name == "stderr":
                    text = f"[stderr] {text}"
                session.output_buffer += text
                if len(session.output_buffer) > MAX_BUFFER_CHARS:
                    overflow = len(session.output_buffer) - MAX_BUFFER_CHARS
                    session.output_buffer = session.output_buffer[overflow:]
                    session.read_cursor = max(0, session.read_cursor - overflow)
                session.last_activity = time.time()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("terminal_session_reader_failed", session_id=session.id, stream=stream_name, error=str(exc))

    async def _pty_reader_loop(self, session: ProcessSession) -> None:
        fd = session.pty_master_fd
        if fd is None:
            return
        try:
            while True:
                try:
                    chunk = await asyncio.to_thread(os.read, fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                session.output_buffer += text
                if len(session.output_buffer) > MAX_BUFFER_CHARS:
                    overflow = len(session.output_buffer) - MAX_BUFFER_CHARS
                    session.output_buffer = session.output_buffer[overflow:]
                    session.read_cursor = max(0, session.read_cursor - overflow)
                session.last_activity = time.time()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("terminal_session_pty_reader_failed", session_id=session.id, error=str(exc))

    async def _cleanup_locked(self) -> None:
        now = time.time()
        stale_keys = []
        for key, session in self._sessions.items():
            if not session.running:
                session.exit_code = self._returncode(session)
                continue
            if now - session.last_activity > IDLE_TTL_SECONDS:
                stale_keys.append(key)
        for key in stale_keys:
            session = self._sessions.pop(key, None)
            if session:
                await self.stop(session)

    def _tail(self, text: str, max_chars: int) -> str:
        if not text or len(text) <= max_chars:
            return text or ""
        return text[-max_chars:]

    async def _start_pty_process(
        self,
        args: List[str],
        cwd: Path,
        env: Dict[str, str],
        columns: int,
        rows: int,
    ) -> Tuple[Any, int]:
        if os.name == "nt":
            raise RuntimeError("PTY backend 仅支持 Linux/macOS；Windows 请使用 backend=pipe")

        import fcntl
        import pty
        import struct
        import subprocess
        import termios

        master_fd, slave_fd = pty.openpty()
        try:
            size = struct.pack("HHHH", rows, columns, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, size)
            env = env.copy()
            env["TERM"] = "xterm-256color"
            process = subprocess.Popen(
                args,
                cwd=str(cwd),
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                close_fds=True,
                start_new_session=True,
            )
        finally:
            os.close(slave_fd)
        return process, master_fd

    async def _wait_process(self, process: Any, timeout: int) -> None:
        wait = getattr(process, "wait")
        if callable(getattr(process, "poll", None)):
            await asyncio.wait_for(asyncio.to_thread(wait), timeout=timeout)
            return
        await asyncio.wait_for(wait(), timeout=timeout)

    def _returncode(self, session: ProcessSession) -> Optional[int]:
        poll = getattr(session.process, "poll", None)
        if callable(poll):
            return poll()
        return session.process.returncode


_manager = TerminalSessionManager()


class TerminalSessionTool(LLMTool):
    """Manage long-lived line-oriented terminal sessions."""

    VALID_ACTIONS = {"start", "send", "read", "status", "stop", "list"}

    def __init__(self) -> None:
        function_schema = {
            "name": "terminal_session",
            "description": "托管长期运行的交互式命令行进程；不是 Claude/Codex 委托工具，外部编程 Agent 用 cli_session。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "操作类型：start/send/read/status/stop/list。"
                    },
                    "session_name": {
                        "type": "string",
                        "description": "当前社交用户下的会话名，默认default。"
                    },
                    "command": {
                        "type": "string",
                        "description": "start时必填；不支持管道/重定向/shell连接符。"
                    },
                    "input": {"type": "string", "description": "send时写入进程的内容。"},
                    "backend": {
                        "type": "string",
                        "enum": ["pipe", "pty", "auto"],
                        "description": "start后端，默认pipe。"
                    },
                    "cwd": {"type": "string", "description": "工作目录，必须在项目目录内，默认项目根目录。"},
                    "append_newline": {
                        "type": "boolean",
                        "description": "send时是否追加换行，默认true。"
                    },
                    "columns": {
                        "type": "integer",
                        "description": "PTY终端列数，默认120。"
                    },
                    "rows": {
                        "type": "integer",
                        "description": "PTY终端行数，默认30。"
                    },
                    "restart": {
                        "type": "boolean",
                        "description": "start时如同名会话存在是否先停止再重启，默认false。"
                    },
                    "read_timeout": {
                        "type": "number",
                        "description": "等待输出秒数，默认1.0。"
                    },
                    "max_output_chars": {
                        "type": "integer",
                        "description": "本次返回的最大输出字符数，默认6000。"
                    },
                    "output_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "会话命令已创建或修改的成果文件；在 read/send/stop 时声明并登记。"
                    }
                },
                "required": ["action"]
            }
        }
        super().__init__(
            name="terminal_session",
            description="托管长期运行的交互式命令行进程，支持跨社交消息继续 stdin/stdout",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        action: str = "read",
        session_name: str = "default",
        command: Optional[str] = None,
        input: Optional[str] = None,
        backend: str = "pipe",
        cwd: Optional[str] = None,
        append_newline: bool = True,
        columns: int = 120,
        rows: int = 30,
        restart: bool = False,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        output_paths: Optional[List[str]] = None,
        context: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        action = (action or "read").strip().lower()
        session_name = self._safe_name(session_name or "default")
        user_key = self._get_user_key(context)
        read_timeout = self._clamp_float(read_timeout, 0.0, 10.0, DEFAULT_READ_TIMEOUT)
        max_output_chars = self._clamp_int(max_output_chars, 1000, 50000, DEFAULT_MAX_OUTPUT_CHARS)
        backend = self._normalize_backend(backend)
        columns = self._clamp_int(columns, 40, 240, 120)
        rows = self._clamp_int(rows, 10, 80, 30)

        if action not in self.VALID_ACTIONS:
            return self._failed(f"不支持的 action: {action}")

        if action == "list":
            sessions = await _manager.list(user_key)
            data = [self._session_data(session, include_output=False) for session in sessions]
            return self._ok(action, f"共有 {len(data)} 个 terminal 会话", {"sessions": data, "count": len(data)})

        if action == "start":
            if not command or not command.strip():
                return self._failed("action=start 时必须提供 command")
            resolved_cwd = self._resolve_cwd(cwd)
            if resolved_cwd is None:
                return self._failed(f"工作目录无效或超出项目范围: {cwd}")
            validation = self._validate_command(command)
            if not validation["valid"]:
                return self._failed(validation["error"])
            if backend == "pty" and os.name == "nt":
                return self._failed("backend=pty 仅支持 Linux/macOS；当前系统请使用 backend=pipe")
            started, session, error, output = await _manager.start(
                user_key=user_key,
                session_name=session_name,
                command=command,
                args=validation["args"],
                cwd=resolved_cwd,
                backend=backend,
                columns=columns,
                rows=rows,
                restart=bool(restart),
                read_timeout=read_timeout,
            )
            if not started and not session:
                return self._failed(error)
            data = self._session_data(session, include_output=True, output=output, max_output_chars=max_output_chars) if session else {}
            summary = "terminal 会话已启动" if started else error
            return self._with_output_resources(
                self._ok(action, summary, data), output_paths, resolved_cwd
            )

        session = await _manager.get(user_key, session_name)
        if not session:
            return self._failed(f"terminal 会话不存在: {session_name}")

        if action == "send":
            if input is None:
                return self._failed("action=send 时必须提供 input")
            ok, output = await _manager.send(session, input, read_timeout, max_output_chars, bool(append_newline))
            data = self._session_data(session, include_output=True, output=output, max_output_chars=max_output_chars)
            return self._with_output_resources(
                self._ok(action, "已写入输入并读取新输出" if ok else "写入失败", data, success=ok),
                output_paths,
                Path(session.cwd),
            )

        if action == "read":
            output = await _manager.read(session, read_timeout, max_output_chars)
            data = self._session_data(session, include_output=True, output=output, max_output_chars=max_output_chars)
            return self._with_output_resources(
                self._ok(action, "已读取 terminal 会话输出", data),
                output_paths,
                Path(session.cwd),
            )

        if action == "status":
            data = self._session_data(session, include_output=True, output=None, max_output_chars=max_output_chars)
            return self._ok(action, "已获取 terminal 会话状态", data)

        if action == "stop":
            output = await _manager.stop(session)
            await _manager.discard(user_key, session_name)
            data = self._session_data(session, include_output=True, output=output, max_output_chars=max_output_chars)
            return self._with_output_resources(
                self._ok(action, "terminal 会话已停止", data),
                output_paths,
                Path(session.cwd),
            )

        return self._failed(f"未处理的 action: {action}")

    def _validate_command(self, command: str) -> Dict[str, Any]:
        stripped = command.strip()
        if not stripped:
            return {"valid": False, "error": "命令为空"}
        if any(token in stripped for token in [";", "|", "&", ">", "<", "`", "$(", "${", "\n", "\r"]):
            return {"valid": False, "error": "terminal_session 不支持 shell 元字符、管道、重定向或命令连接符"}
        lowered = stripped.lower()
        dangerous = ["sudo", "su ", "rm -rf /", "shutdown", "reboot", "mkfs", "format ", "dd if="]
        for item in dangerous:
            if item in lowered:
                return {"valid": False, "error": f"危险命令被拒绝: {item}"}
        try:
            args = shlex.split(stripped, posix=(os.name != "nt"))
        except ValueError as exc:
            return {"valid": False, "error": f"命令格式错误: {exc}"}
        if not args:
            return {"valid": False, "error": "命令为空"}
        first = args[0]
        if os.name == "nt":
            import shutil
            for candidate in (first, f"{first}.exe", f"{first}.cmd"):
                resolved = shutil.which(candidate)
                if resolved:
                    args[0] = resolved
                    return {"valid": True, "args": args}
        else:
            import shutil
            resolved = shutil.which(first)
            if resolved:
                args[0] = resolved
                return {"valid": True, "args": args}
        if Path(first).is_absolute() and Path(first).exists():
            return {"valid": True, "args": args}
        return {"valid": False, "error": f"命令不存在或不在 PATH 中: {first}"}

    def _with_output_resources(
        self,
        result: Dict[str, Any],
        output_paths: Optional[List[str]],
        cwd: Path,
    ) -> Dict[str, Any]:
        if not result.get("success") or not output_paths:
            return result
        resolved = []
        for value in output_paths:
            path = Path(value).expanduser()
            path = path.resolve() if path.is_absolute() else (cwd / path).resolve()
            if path.is_relative_to(PROJECT_ROOT):
                resolved.append(path)
        result["resources"] = file_products(resolved, tool_name=self.name)
        return result

    def _resolve_cwd(self, cwd: Optional[str]) -> Optional[Path]:
        try:
            base = PROJECT_ROOT.resolve()
            requested = Path(cwd).resolve() if cwd else base
            if requested == base or requested.is_relative_to(base):
                if requested.exists() and requested.is_dir():
                    return requested
            return None
        except Exception:
            return None

    def _session_data(
        self,
        session: Optional[ProcessSession],
        include_output: bool,
        output: Optional[str] = None,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    ) -> Dict[str, Any]:
        if not session:
            return {}
        session.exit_code = self._session_returncode(session)
        data: Dict[str, Any] = {
            "id": session.id,
            "session_name": session.session_name,
            "command": session.command,
            "backend": session.backend,
            "cwd": session.cwd,
            "pid": getattr(session.process, "pid", None),
            "running": session.running,
            "exit_code": session.exit_code,
            "started_at": datetime.fromtimestamp(session.started_at).isoformat(),
            "last_activity": datetime.fromtimestamp(session.last_activity).isoformat(),
            "buffer_chars": len(session.output_buffer),
            "usage_hint": self._usage_hint(session.backend),
        }
        if include_output:
            selected = output if output is not None else session.output_buffer[-max_output_chars:]
            data["output"] = selected[-max_output_chars:] if selected else ""
            data["output_chars"] = len(data["output"])
            if session.backend == "pty":
                plain_output = self._strip_ansi(data["output"])
                data["plain_output"] = plain_output
                data["plain_output_chars"] = len(plain_output)
        return data

    def _get_user_key(self, context: Any = None) -> str:
        try:
            from app.social.message_bus_singleton import (
                get_current_bot_account,
                get_current_chat_id,
                get_current_channel,
            )
            channel = get_current_channel()
            chat_id = get_current_chat_id()
            bot = get_current_bot_account() or "default"
            if channel and chat_id:
                return self._safe_name(f"{channel}:{bot}:{chat_id}")
        except Exception:
            pass
        session_id = getattr(context, "session_id", None) if context else None
        return self._safe_name(session_id or "default")

    def _ok(self, action: str, summary: str, data: Dict[str, Any], success: bool = True) -> Dict[str, Any]:
        return {
            "status": "success" if success else "failed",
            "success": success,
            "metadata": self._metadata(action=action),
            "data": data,
            "summary": summary,
        }

    def _failed(self, error: str) -> Dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": error,
            "metadata": self._metadata(error_type="VALIDATION_FAILED"),
            "data": None,
            "summary": f"terminal_session 失败：{error}",
        }

    def _metadata(self, **extra: Any) -> Dict[str, Any]:
        metadata = {
            "tool_name": "terminal_session",
            "generator": "terminal_session",
            "schema_version": "1.0",
        }
        metadata.update({key: value for key, value in extra.items() if value is not None})
        return metadata

    def _normalize_backend(self, value: str) -> str:
        backend = (value or "pipe").strip().lower()
        if backend == "auto":
            return "pipe" if os.name == "nt" else "pty"
        if backend in {"pipe", "pty"}:
            return backend
        return "pipe"

    def _usage_hint(self, backend: str) -> str:
        if backend == "pty":
            return "PTY 会话：send 默认追加换行；发送 Ctrl+C 用 input='\\u0003', append_newline=false；方向键可发送 ANSI 序列并设 append_newline=false。"
        return "Pipe 会话：适合行式脚本和简单 REPL；每次 send 默认写入一行并读取新输出。"

    def _strip_ansi(self, text: str) -> str:
        return ANSI_ESCAPE_RE.sub("", text or "")

    def _session_returncode(self, session: ProcessSession) -> Optional[int]:
        poll = getattr(session.process, "poll", None)
        if callable(poll):
            return poll()
        return session.process.returncode

    def _safe_name(self, value: str) -> str:
        value = str(value or "default").strip()
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
        return safe[:120] or "default"

    def _clamp_int(self, value: Any, minimum: int, maximum: int, default: int) -> int:
        try:
            parsed = int(value)
        except Exception:
            return default
        return max(minimum, min(maximum, parsed))

    def _clamp_float(self, value: Any, minimum: float, maximum: float, default: float) -> float:
        try:
            parsed = float(value)
        except Exception:
            return default
        return max(minimum, min(maximum, parsed))
