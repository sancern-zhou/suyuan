"""Long-lived interactive process sessions for social mode.

This tool is intentionally separate from cli_session:
- cli_session delegates one turn to Claude Code / Codex and exits.
- terminal_session keeps a normal stdin/stdout process alive across social turns.

The first implementation uses pipes rather than a PTY. It supports ordinary
line-oriented scripts and REPL-like programs, such as guess-number games. Full
TUI programs and interactive Claude Code shells require a PTY backend later.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import signal
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.path_config import PROJECT_ROOT

logger = structlog.get_logger(__name__)


MAX_BUFFER_CHARS = 200_000
DEFAULT_READ_TIMEOUT = 1.0
DEFAULT_MAX_OUTPUT_CHARS = 6000
MAX_SESSIONS_PER_USER = 3
IDLE_TTL_SECONDS = 1800


@dataclass
class ProcessSession:
    id: str
    user_key: str
    session_name: str
    command: str
    args: List[str]
    cwd: str
    process: asyncio.subprocess.Process
    started_at: float
    last_activity: float
    output_buffer: str = ""
    read_cursor: int = 0
    stdout_task: Optional[asyncio.Task] = None
    stderr_task: Optional[asyncio.Task] = None
    exit_code: Optional[int] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def running(self) -> bool:
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
                process = await asyncio.create_subprocess_exec(
                    *args,
                    cwd=str(cwd),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
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
                started_at=now,
                last_activity=now,
            )
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
    ) -> Tuple[bool, str]:
        async with session.lock:
            if not session.running:
                return False, await self.read(session, read_timeout=0, max_output_chars=max_output_chars)
            if session.process.stdin is None:
                return False, "进程 stdin 不可用"
            try:
                session.process.stdin.write((text.rstrip("\n") + "\n").encode("utf-8"))
                await session.process.stdin.drain()
                session.last_activity = time.time()
            except Exception as exc:
                return False, f"写入 stdin 失败: {exc}"
        return True, await self.read(session, read_timeout=read_timeout, max_output_chars=max_output_chars)

    async def read(self, session: ProcessSession, read_timeout: float, max_output_chars: int) -> str:
        if read_timeout > 0:
            await asyncio.sleep(read_timeout)
        session.exit_code = session.process.returncode
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
                    await asyncio.wait_for(session.process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    session.process.kill()
                    await session.process.wait()
            except ProcessLookupError:
                pass
            except Exception as exc:
                logger.warning("terminal_session_stop_failed", session_id=session.id, error=str(exc))
        session.exit_code = session.process.returncode
        for task in (session.stdout_task, session.stderr_task):
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

    async def _cleanup_locked(self) -> None:
        now = time.time()
        stale_keys = []
        for key, session in self._sessions.items():
            if not session.running:
                session.exit_code = session.process.returncode
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


_manager = TerminalSessionManager()


class TerminalSessionTool(LLMTool):
    """Manage long-lived line-oriented terminal sessions."""

    VALID_ACTIONS = {"start", "send", "read", "status", "stop", "list"}

    def __init__(self) -> None:
        function_schema = {
            "name": "terminal_session",
            "description": (
                "托管长期运行的交互式命令行进程，适合猜数字游戏、简单REPL、等待stdin的脚本。"
                "不是Claude/Codex委托工具；如需外部编程Agent请用cli_session。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["start", "send", "read", "status", "stop", "list"],
                        "description": "操作：start启动进程，send写入一行输入，read读取输出，status查看状态，stop终止，list列出。"
                    },
                    "session_name": {
                        "type": "string",
                        "description": "当前社交用户下的会话名，默认 default。"
                    },
                    "command": {
                        "type": "string",
                        "description": "start 时必填，要启动的命令。使用普通命令和参数，不支持管道/重定向/shell连接符。"
                    },
                    "input": {
                        "type": "string",
                        "description": "send 时写入 stdin 的一行内容。"
                    },
                    "cwd": {
                        "type": "string",
                        "description": "工作目录，必须在项目目录内。默认项目根目录。"
                    },
                    "restart": {
                        "type": "boolean",
                        "description": "start 时如同名会话存在，是否先停止再重启。",
                        "default": False
                    },
                    "read_timeout": {
                        "type": "number",
                        "description": "写入或启动后等待输出的秒数，默认 1.0，范围 0-10。",
                        "default": DEFAULT_READ_TIMEOUT
                    },
                    "max_output_chars": {
                        "type": "integer",
                        "description": "本次返回的最大输出字符数，默认 6000。",
                        "default": DEFAULT_MAX_OUTPUT_CHARS
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
        cwd: Optional[str] = None,
        restart: bool = False,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        context: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        action = (action or "read").strip().lower()
        session_name = self._safe_name(session_name or "default")
        user_key = self._get_user_key(context)
        read_timeout = self._clamp_float(read_timeout, 0.0, 10.0, DEFAULT_READ_TIMEOUT)
        max_output_chars = self._clamp_int(max_output_chars, 1000, 50000, DEFAULT_MAX_OUTPUT_CHARS)

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
            started, session, error, output = await _manager.start(
                user_key=user_key,
                session_name=session_name,
                command=command,
                args=validation["args"],
                cwd=resolved_cwd,
                restart=bool(restart),
                read_timeout=read_timeout,
            )
            if not started and not session:
                return self._failed(error)
            data = self._session_data(session, include_output=True, output=output, max_output_chars=max_output_chars) if session else {}
            summary = "terminal 会话已启动" if started else error
            return self._ok(action, summary, data)

        session = await _manager.get(user_key, session_name)
        if not session:
            return self._failed(f"terminal 会话不存在: {session_name}")

        if action == "send":
            if input is None:
                return self._failed("action=send 时必须提供 input")
            ok, output = await _manager.send(session, input, read_timeout, max_output_chars)
            data = self._session_data(session, include_output=True, output=output, max_output_chars=max_output_chars)
            return self._ok(action, "已写入输入并读取新输出" if ok else "写入失败", data, success=ok)

        if action == "read":
            output = await _manager.read(session, read_timeout, max_output_chars)
            data = self._session_data(session, include_output=True, output=output, max_output_chars=max_output_chars)
            return self._ok(action, "已读取 terminal 会话输出", data)

        if action == "status":
            data = self._session_data(session, include_output=True, output=None, max_output_chars=max_output_chars)
            return self._ok(action, "已获取 terminal 会话状态", data)

        if action == "stop":
            output = await _manager.stop(session)
            await _manager.discard(user_key, session_name)
            data = self._session_data(session, include_output=True, output=output, max_output_chars=max_output_chars)
            return self._ok(action, "terminal 会话已停止", data)

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
        session.exit_code = session.process.returncode
        data: Dict[str, Any] = {
            "id": session.id,
            "session_name": session.session_name,
            "command": session.command,
            "cwd": session.cwd,
            "pid": getattr(session.process, "pid", None),
            "running": session.running,
            "exit_code": session.exit_code,
            "started_at": datetime.fromtimestamp(session.started_at).isoformat(),
            "last_activity": datetime.fromtimestamp(session.last_activity).isoformat(),
            "buffer_chars": len(session.output_buffer),
        }
        if include_output:
            selected = output if output is not None else session.output_buffer[-max_output_chars:]
            data["output"] = selected[-max_output_chars:] if selected else ""
            data["output_chars"] = len(data["output"])
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
