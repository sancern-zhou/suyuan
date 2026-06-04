"""Persistent Claude Code / Codex CLI sessions for social mode.

This tool intentionally uses each CLI's non-interactive resume protocol instead
of keeping an interactive TTY alive. Social channels are message based, so a
turn-based process model is easier to isolate, time out, log, and recover after
backend restarts.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.path_config import PROJECT_ROOT, get_social_dir

logger = structlog.get_logger(__name__)


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

DEFAULT_ANSWER_CHARS = 12000
DEFAULT_RAW_OUTPUT_CHARS = 4000
MAX_STDOUT_BYTES = 50 * 1024 * 1024  # 50 MB hard cap per CLI invocation
MAX_STDERR_BYTES = 10 * 1024 * 1024  # 10 MB hard cap for stderr


class CliSessionTool(LLMTool):
    """Run multi-turn Claude Code or Codex sessions from social mode."""

    VALID_PROVIDERS = {"claude", "codex"}
    VALID_ACTIONS = {"start", "send", "status", "list", "reset", "task_status", "task_list", "task_cancel"}

    def __init__(self) -> None:
        function_schema = {
            "name": "cli_session",
            "description": "运行可恢复 Claude Code/Codex CLI 会话；start/send 默认后台返回 task_id。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "操作类型：start/send/status/list/reset/task_status/task_list/task_cancel。"
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["claude", "codex"],
                        "description": "外部CLI，默认claude。"
                    },
                    "session_name": {
                        "type": "string",
                        "description": "会话名，默认default。"
                    },
                    "prompt": {
                        "type": "string",
                        "description": "start/send必填。"
                    },
                    "cwd": {"type": "string", "description": "项目内工作目录。"},
                    "timeout": {
                        "type": "integer",
                        "description": "执行秒数，默认600（范围30-3600）。"
                    },
                    "model": {"type": "string", "description": "透传模型名。"},
                    "permission_mode": {
                        "type": "string",
                        "description": "Claude Code权限：default/acceptEdits/bypassPermissions/dontAsk/plan。"
                    },
                    "sandbox": {
                        "type": "string",
                        "description": "Codex沙箱：read-only/workspace-write/danger-full-access。"
                    },
                    "approval_policy": {
                        "type": "string",
                        "description": "Codex审批：untrusted/on-failure/on-request/never。"
                    },
                    "max_output_chars": {
                        "type": "integer",
                        "description": "answer字符上限，默认12000（范围1000-100000）。"
                    },
                    "include_raw_output": {
                        "type": "boolean",
                        "description": "返回stdout/stderr摘要，默认false。"
                    },
                    "background": {
                        "type": "boolean",
                        "description": "start/send后台执行，默认true。"
                    },
                    "task_id": {"type": "string", "description": "后台任务ID。"}
                },
                "required": ["action"]
            }
        }
        super().__init__(
            name="cli_session",
            description="通过 Claude Code / Codex CLI 进行可恢复的多轮对话和编程",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False,
        )
        self.base_dir = get_social_dir() / "cli_sessions"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def execute(
        self,
        action: str = "send",
        provider: str = "claude",
        session_name: str = "default",
        prompt: Optional[str] = None,
        cwd: Optional[str] = None,
        timeout: int = 600,
        model: Optional[str] = None,
        permission_mode: str = "acceptEdits",
        sandbox: str = "workspace-write",
        approval_policy: str = "never",
        max_output_chars: int = DEFAULT_ANSWER_CHARS,
        include_raw_output: bool = False,
        background: bool = True,
        task_id: Optional[str] = None,
        context: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        action = (action or "send").strip()
        provider = (provider or "claude").strip().lower()
        session_name = self._safe_name(session_name or "default")
        timeout = self._clamp_int(timeout, 30, 3600, 600)
        max_output_chars = self._clamp_int(max_output_chars, 1000, 100000, DEFAULT_ANSWER_CHARS)

        if action not in self.VALID_ACTIONS:
            return self._failed(f"不支持的 action: {action}")

        user_key = self._get_user_key(context)

        if action in {"task_status", "task_cancel"}:
            if not task_id:
                return self._failed(f"action={action} 时必须提供 task_id")
            manager = self._get_cli_task_manager()
            if not manager:
                return self._failed("CliTaskManager未初始化")
            if action == "task_status":
                task = await manager.get_task(task_id)
                if not task:
                    return self._failed(f"CLI后台任务不存在: {task_id}")
                if task.get("social_user_id") and task.get("social_user_id") != user_key:
                    return self._failed(f"CLI后台任务不存在: {task_id}")
                return {
                    "status": "success",
                    "success": True,
                    "metadata": self._metadata(action=action, task_id=task_id),
                    "data": task,
                    "summary": f"CLI后台任务 {task_id} 当前状态: {task.get('status')}",
                }
            task = await manager.get_task(task_id)
            if task and task.get("social_user_id") and task.get("social_user_id") != user_key:
                return self._failed(f"CLI后台任务不存在: {task_id}")
            result = await manager.cancel_task(task_id)
            if not result.get("success"):
                return self._failed(result.get("error", "取消后台CLI任务失败"))
            return {
                "status": "success",
                "success": True,
                "metadata": self._metadata(action=action, task_id=task_id),
                "data": result,
                "summary": f"已取消CLI后台任务: {task_id}",
            }

        if action == "task_list":
            manager = self._get_cli_task_manager()
            if not manager:
                return self._failed("CliTaskManager未初始化")
            tasks = await manager.list_tasks(social_user_id=user_key)
            return {
                "status": "success",
                "success": True,
                "metadata": self._metadata(action=action),
                "data": {"tasks": tasks, "count": len(tasks)},
                "summary": f"共有 {len(tasks)} 个CLI后台任务",
            }

        if action == "list":
            return self._list_sessions(user_key)

        state_path = self._state_path(user_key, session_name)
        state = self._load_state(state_path)

        if action == "status":
            if not state:
                return self._failed(f"CLI会话不存在: {session_name}")
            return {
                "status": "success",
                "success": True,
                "metadata": self._metadata(action=action),
                "data": self._public_state(state),
                "summary": self._status_summary(state),
            }

        if action == "reset":
            if state_path.exists():
                state_path.unlink()
            return {
                "status": "success",
                "success": True,
                "metadata": self._metadata(action=action),
                "summary": f"已重置 CLI 会话: {session_name}",
                "data": {
                    "session_name": session_name,
                    "reset": True,
                },
            }

        if provider not in self.VALID_PROVIDERS:
            return self._failed(f"不支持的 provider: {provider}")

        if not prompt or not prompt.strip():
            return self._failed("action=start/send 时必须提供 prompt")

        resolved_cwd = self._resolve_cwd(cwd or state.get("cwd") if state else cwd)
        if resolved_cwd is None:
            return self._failed(f"工作目录无效或超出项目范围: {cwd}")

        binary = self._resolve_binary(provider)
        if not binary:
            return self._failed(
                f"未找到 {provider} CLI。请确认后端服务环境 PATH 中可执行 `{provider}`。"
            )

        if not state or action == "start" or state.get("provider") != provider:
            state = self._new_state(
                user_key=user_key,
                session_name=session_name,
                provider=provider,
                cwd=str(resolved_cwd),
            )
        else:
            state["cwd"] = str(resolved_cwd)

        if provider == "claude":
            args, stdin_text, output_file = self._build_claude_command(
                binary=binary,
                state=state,
                prompt=prompt,
                model=model,
                permission_mode=permission_mode,
            )
        else:
            args, stdin_text, output_file = self._build_codex_command(
                binary=binary,
                state=state,
                prompt=prompt,
                model=model,
                sandbox=sandbox,
                approval_policy=approval_policy,
            )

        if background:
            return await self._start_background_task(
                user_key=user_key,
                provider=provider,
                session_name=session_name,
                prompt=prompt,
                cwd=resolved_cwd,
                args=args,
                stdin_text=stdin_text,
                timeout=timeout,
                state_path=state_path,
                state=state,
                output_file=output_file,
            )

        started_at = datetime.now().isoformat()
        result = await self._run_cli(args, stdin_text, resolved_cwd, timeout)
        finished_at = datetime.now().isoformat()

        parsed_text, vendor_session_id = self._parse_cli_output(
            provider=provider,
            stdout=result["stdout"],
            stderr=result["stderr"],
            output_file=output_file,
        )
        if vendor_session_id:
            state["vendor_session_id"] = vendor_session_id

        turn = {
            "started_at": started_at,
            "finished_at": finished_at,
            "prompt": prompt,
            "exit_code": result["exit_code"],
            "success": result["exit_code"] == 0,
            "stdout_tail": self._tail(result["stdout"], 12000),
            "stderr_tail": self._tail(result["stderr"], 6000),
            "answer": self._tail(parsed_text, 30000),
        }
        state.setdefault("turns", []).append(turn)
        state["updated_at"] = finished_at
        state["last_exit_code"] = result["exit_code"]
        state["last_success"] = result["exit_code"] == 0
        state["last_error"] = result["stderr"] if result["exit_code"] != 0 else ""
        self._save_state(state_path, state)

        answer = parsed_text.strip() or result["stdout"].strip() or result["stderr"].strip()
        truncated_answer, answer_truncated = self._truncate_middle(answer, max_output_chars)
        success = result["exit_code"] == 0
        raw_limit = min(max_output_chars, DEFAULT_RAW_OUTPUT_CHARS)

        data: Dict[str, Any] = {
            "provider": provider,
            "session_name": session_name,
            "vendor_session_id": state.get("vendor_session_id"),
            "cwd": str(resolved_cwd),
            "exit_code": result["exit_code"],
            "answer": truncated_answer,
            "answer_chars": len(answer),
            "answer_truncated": answer_truncated,
            "turn_count": len(state.get("turns", [])),
        }

        if include_raw_output or not success:
            stdout_excerpt, stdout_truncated = self._truncate_middle(result["stdout"], raw_limit)
            stderr_excerpt, stderr_truncated = self._truncate_middle(result["stderr"], raw_limit)
            data.update({
                "stdout_excerpt": stdout_excerpt,
                "stderr_excerpt": stderr_excerpt,
                "stdout_chars": len(result["stdout"]),
                "stderr_chars": len(result["stderr"]),
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            })

        return {
            "status": "success" if success else "failed",
            "success": success,
            "metadata": self._metadata(
                action=action,
                provider=provider,
                session_name=session_name,
                vendor_session_id=state.get("vendor_session_id"),
                exit_code=result["exit_code"],
                cwd=str(resolved_cwd),
                command=self._redact_command(args),
                answer_chars=len(answer),
                answer_truncated=answer_truncated,
                include_raw_output=include_raw_output,
            ),
            "data": data,
            "summary": self._build_summary(
                provider=provider,
                session_name=session_name,
                success=success,
                answer=truncated_answer,
                stderr=result["stderr"],
                answer_chars=len(answer),
                answer_truncated=answer_truncated,
            ),
        }

    async def _start_background_task(
        self,
        *,
        user_key: str,
        provider: str,
        session_name: str,
        prompt: str,
        cwd: Path,
        args: List[str],
        stdin_text: str,
        timeout: int,
        state_path: Path,
        state: Dict[str, Any],
        output_file: Optional[Path],
    ) -> Dict[str, Any]:
        manager = self._get_cli_task_manager()
        if not manager:
            return self._failed("CliTaskManager未初始化")

        origin_info = self._get_origin_info()
        label = f"{provider} CLI: {session_name}"
        started_at = datetime.now().isoformat()

        def parser(stdout: str, stderr: str) -> Tuple[str, Optional[str]]:
            return self._parse_cli_output(provider, stdout, stderr, output_file)

        def completion_callback(payload: Dict[str, Any]) -> None:
            result = {
                "exit_code": payload.get("exit_code", -1),
                "stdout": payload.get("stdout", ""),
                "stderr": payload.get("stderr", ""),
            }
            self._record_turn(
                state_path=state_path,
                state=state,
                prompt=prompt,
                started_at=started_at,
                finished_at=payload.get("finished_at") or datetime.now().isoformat(),
                result=result,
                parsed_text=payload.get("parsed_text", ""),
                vendor_session_id=payload.get("vendor_session_id"),
            )

        result = await manager.start_task(
            social_user_id=user_key,
            origin_info=origin_info,
            provider=provider,
            session_name=session_name,
            cwd=str(cwd),
            args=args,
            stdin_text=stdin_text,
            timeout=timeout,
            label=label,
            parser=parser,
            completion_callback=completion_callback,
        )
        if not result.get("success"):
            return self._failed(result.get("error", "创建CLI后台任务失败"))

        return {
            "status": "success",
            "success": True,
            "metadata": self._metadata(
                action="background",
                provider=provider,
                session_name=session_name,
                task_id=result.get("task_id"),
                cwd=str(cwd),
                command=self._redact_command(args),
            ),
            "data": {
                "task_id": result.get("task_id"),
                "provider": provider,
                "session_name": session_name,
                "cwd": str(cwd),
                "background": True,
            },
            "summary": (
                f"已创建CLI后台任务 `{result.get('task_id')}`，当前对话不会阻塞。"
                "可用 action=task_status 查询，action=task_cancel 取消。"
            ),
        }

    def _build_claude_command(
        self,
        binary: str,
        state: Dict[str, Any],
        prompt: str,
        model: Optional[str],
        permission_mode: str,
    ) -> Tuple[List[str], str, Optional[Path]]:
        args = [
            binary,
            "--print",
            "--output-format",
            "json",
            "--session-id",
            state["vendor_session_id"],
            "--permission-mode",
            permission_mode if permission_mode in {"default", "acceptEdits", "bypassPermissions", "dontAsk", "plan"} else "acceptEdits",
        ]
        if model:
            args.extend(["--model", model])
        args.append(prompt)
        return args, "", None

    def _build_codex_command(
        self,
        binary: str,
        state: Dict[str, Any],
        prompt: str,
        model: Optional[str],
        sandbox: str,
        approval_policy: str,
    ) -> Tuple[List[str], str, Optional[Path]]:
        fd, output_path = tempfile.mkstemp(prefix="codex_last_", suffix=".txt")
        os.close(fd)
        output_file = Path(output_path)

        args = [
            binary,
            "exec",
            "--json",
            "--output-last-message",
            str(output_file),
            "--cd",
            state["cwd"],
        ]

        # 在SELinux环境下，bubblewrap无法正常工作，需要绕过沙箱
        # 检测SELinux状态，如果启用则使用dangerously-bypass模式
        try:
            import subprocess
            selinux_result = subprocess.run(["getenforce"], capture_output=True, text=True, timeout=2)
            if selinux_result.stdout.strip() in ["Enforcing", "Permissive"]:
                # SELinux启用时，绕过沙箱以避免bubblewrap权限问题
                args.append("--dangerously-bypass-approvals-and-sandbox")
            else:
                # 正常情况下使用沙箱
                args.extend(["--sandbox", sandbox if sandbox in {"read-only", "workspace-write", "danger-full-access"} else "workspace-write"])
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
            # 无法检测SELinux状态，使用沙箱
            args.extend(["--sandbox", sandbox if sandbox in {"read-only", "workspace-write", "danger-full-access"} else "workspace-write"])

        # Add approval policy via config override (仅在不绕过沙箱时有效)
        if approval_policy in {"untrusted", "on-failure", "on-request", "never"}:
            args.extend(["-c", f'approval_policy="{approval_policy}"'])
        if model:
            args.extend(["--model", model])

        existing_session = state.get("vendor_session_id")
        if existing_session:
            args.extend(["resume", existing_session, "-"])
        else:
            args.append("-")
        return args, prompt, output_file

    def _record_turn(
        self,
        *,
        state_path: Path,
        state: Dict[str, Any],
        prompt: str,
        started_at: str,
        finished_at: str,
        result: Dict[str, Any],
        parsed_text: str,
        vendor_session_id: Optional[str],
    ) -> None:
        if vendor_session_id:
            state["vendor_session_id"] = vendor_session_id
        turn = {
            "started_at": started_at,
            "finished_at": finished_at,
            "prompt": prompt,
            "exit_code": result["exit_code"],
            "success": result["exit_code"] == 0,
            "stdout_tail": self._tail(result["stdout"], 12000),
            "stderr_tail": self._tail(result["stderr"], 6000),
            "answer": self._tail(parsed_text, 30000),
            "background": True,
        }
        state.setdefault("turns", []).append(turn)
        state["updated_at"] = finished_at
        state["last_exit_code"] = result["exit_code"]
        state["last_success"] = result["exit_code"] == 0
        state["last_error"] = result["stderr"] if result["exit_code"] != 0 else ""
        self._save_state(state_path, state)

    async def _run_cli(
        self,
        args: List[str],
        stdin_text: str,
        cwd: Path,
        timeout: int,
    ) -> Dict[str, Any]:
        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")
        env.setdefault("TERM", "dumb")
        env.setdefault("TOKENIZERS_PARALLELISM", "false")

        logger.info("cli_session_running", command=self._redact_command(args), cwd=str(cwd), timeout=timeout)
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(cwd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                process.communicate(stdin_text.encode("utf-8")),
                timeout=timeout,
            )
            # Hard cap: truncate raw stdout/stderr to prevent disk bombs
            if len(stdout_b) > MAX_STDOUT_BYTES:
                logger.warning(
                    "cli_session_stdout_truncated",
                    original_bytes=len(stdout_b),
                    max_bytes=MAX_STDOUT_BYTES,
                )
                stdout_b = stdout_b[:MAX_STDOUT_BYTES]
            if len(stderr_b) > MAX_STDERR_BYTES:
                logger.warning(
                    "cli_session_stderr_truncated",
                    original_bytes=len(stderr_b),
                    max_bytes=MAX_STDERR_BYTES,
                )
                stderr_b = stderr_b[:MAX_STDERR_BYTES]
            return {
                "exit_code": process.returncode if process.returncode is not None else -1,
                "stdout": stdout_b.decode("utf-8", errors="replace"),
                "stderr": stderr_b.decode("utf-8", errors="replace"),
            }
        except asyncio.TimeoutError:
            try:
                process.kill()  # type: ignore[name-defined]
            except Exception:
                pass
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"CLI command timed out after {timeout}s",
            }
        except Exception as exc:
            logger.error("cli_session_run_failed", error=str(exc), exc_info=True)
            return {"exit_code": -1, "stdout": "", "stderr": str(exc)}

    def _get_cli_task_manager(self):
        try:
            from app.social.cli_task_singleton import get_cli_task_manager

            manager = get_cli_task_manager()
            if manager:
                return manager
        except Exception:
            pass

        try:
            from app.social.cli_task_manager import CliTaskManager
            from app.social.cli_task_store import CliTaskStore
            from app.social.message_bus_singleton import get_message_bus

            manager = CliTaskManager(task_store=CliTaskStore(), message_bus=get_message_bus())
            from app.social.cli_task_singleton import set_cli_task_manager

            set_cli_task_manager(manager)
            return manager
        except Exception as exc:
            logger.error("cli_task_manager_init_failed", error=str(exc), exc_info=True)
            return None

    def _get_origin_info(self) -> Dict[str, str]:
        try:
            from app.social.message_bus_singleton import get_current_chat_id, get_current_channel

            channel = get_current_channel() or "unknown"
            chat_id = get_current_chat_id() or "unknown"
            return {"channel": channel, "chat_id": chat_id, "sender_id": chat_id}
        except Exception:
            return {"channel": "unknown", "chat_id": "unknown", "sender_id": "unknown"}

    def _parse_cli_output(
        self,
        provider: str,
        stdout: str,
        stderr: str,
        output_file: Optional[Path],
    ) -> Tuple[str, Optional[str]]:
        if provider == "claude":
            return self._parse_claude_output(stdout, stderr)
        return self._parse_codex_output(stdout, stderr, output_file)

    def _parse_claude_output(self, stdout: str, stderr: str) -> Tuple[str, Optional[str]]:
        text = stdout.strip()
        session_id = None
        try:
            payload = json.loads(text)
            session_id = payload.get("session_id") or payload.get("sessionId")
            for key in ("result", "content", "message", "response", "text"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value, session_id
            return json.dumps(payload, ensure_ascii=False, indent=2), session_id
        except Exception:
            pass
        match = UUID_RE.search(stdout) or UUID_RE.search(stderr)
        if match:
            session_id = match.group(0)
        return stdout, session_id

    def _parse_codex_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Optional[Path],
    ) -> Tuple[str, Optional[str]]:
        session_id = None
        text_parts: List[str] = []

        if output_file and output_file.exists():
            try:
                final_text = output_file.read_text(encoding="utf-8", errors="replace")
                if final_text.strip():
                    text_parts.append(final_text)
            finally:
                try:
                    output_file.unlink()
                except OSError:
                    pass

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            event_text = json.dumps(event, ensure_ascii=False)
            match = UUID_RE.search(event_text)
            if match and not session_id:
                session_id = match.group(0)
            for key in ("message", "text", "content", "output", "delta"):
                value = event.get(key)
                if isinstance(value, str) and value.strip() and value not in text_parts:
                    text_parts.append(value)

        if not session_id:
            match = UUID_RE.search(stdout) or UUID_RE.search(stderr)
            if match:
                session_id = match.group(0)

        return ("\n".join(text_parts).strip() or stdout), session_id

    def _new_state(self, user_key: str, session_name: str, provider: str, cwd: str) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        vendor_session_id = str(uuid.uuid4()) if provider == "claude" else None
        return {
            "user_key": user_key,
            "session_name": session_name,
            "provider": provider,
            "vendor_session_id": vendor_session_id,
            "cwd": cwd,
            "created_at": now,
            "updated_at": now,
            "turns": [],
        }

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

    def _state_path(self, user_key: str, session_name: str) -> Path:
        user_dir = self.base_dir / self._safe_name(user_key)
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / f"{self._safe_name(session_name)}.json"

    def _load_state(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("cli_session_state_load_failed", path=str(path), error=str(exc))
            return {}

    def _save_state(self, path: Path, state: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _list_sessions(self, user_key: str) -> Dict[str, Any]:
        user_dir = self.base_dir / self._safe_name(user_key)
        sessions = []
        if user_dir.exists():
            for path in sorted(user_dir.glob("*.json")):
                state = self._load_state(path)
                if state:
                    sessions.append(self._public_state(state))
        return {
            "status": "success",
            "success": True,
            "metadata": self._metadata(action="list"),
            "data": {"sessions": sessions, "count": len(sessions)},
            "summary": f"共有 {len(sessions)} 个 CLI 会话",
        }

    def _public_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "session_name": state.get("session_name"),
            "provider": state.get("provider"),
            "vendor_session_id": state.get("vendor_session_id"),
            "cwd": state.get("cwd"),
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at"),
            "turn_count": len(state.get("turns", [])),
            "last_success": state.get("last_success"),
            "last_exit_code": state.get("last_exit_code"),
        }

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

    def _resolve_binary(self, provider: str) -> Optional[str]:
        if os.name == "nt":
            # Node-based CLIs often install extensionless shims plus .cmd files.
            # subprocess on Windows is most reliable with the .cmd shim.
            for candidate in (f"{provider}.cmd", f"{provider}.exe", provider):
                resolved = shutil.which(candidate)
                if resolved:
                    return resolved
        return shutil.which(provider)

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

    def _tail(self, text: str, max_chars: int) -> str:
        if not text or len(text) <= max_chars:
            return text or ""
        return text[-max_chars:]

    def _truncate_middle(self, text: str, max_chars: int) -> Tuple[str, bool]:
        """Keep head and tail when output is too large, following Hermes' terminal pattern."""
        if not text:
            return "", False
        if len(text) <= max_chars:
            return text, False
        head_chars = max(1, int(max_chars * 0.4))
        tail_chars = max(1, max_chars - head_chars)
        omitted = len(text) - head_chars - tail_chars
        notice = f"\n\n... [truncated {omitted} chars] ...\n\n"
        return text[:head_chars] + notice + text[-tail_chars:], True

    def _redact_command(self, args: List[str]) -> List[str]:
        redacted = []
        for arg in args:
            text = str(arg)
            if len(text) > 160:
                redacted.append(text[:80] + "...<truncated>..." + text[-40:])
            else:
                redacted.append(text)
        return redacted

    def _status_summary(self, state: Dict[str, Any]) -> str:
        return (
            f"CLI会话 {state.get('session_name')} "
            f"({state.get('provider')})，轮次 {len(state.get('turns', []))}，"
            f"最近状态: {'成功' if state.get('last_success') else '未知/失败'}"
        )

    def _build_summary(
        self,
        provider: str,
        session_name: str,
        success: bool,
        answer: str,
        stderr: str,
        answer_chars: int = 0,
        answer_truncated: bool = False,
    ) -> str:
        if success:
            suffix = "，answer 已截断" if answer_truncated else ""
            return (
                f"{provider} CLI 会话 `{session_name}` 本轮完成"
                f"（answer_chars={answer_chars}{suffix}）。"
                "完整会话状态已持久化，可继续使用同一 session_name 发送后续任务。"
            )
        detail = stderr.strip() or answer or "未知错误"
        detail_excerpt, _ = self._truncate_middle(detail, DEFAULT_RAW_OUTPUT_CHARS)
        return f"{provider} CLI 会话 `{session_name}` 本轮失败：\n{detail_excerpt}"

    def _failed(self, error: str) -> Dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": error,
            "metadata": self._metadata(error_type="VALIDATION_FAILED"),
            "data": None,
            "summary": f"CLI会话失败：{error}",
        }

    def _metadata(self, **extra: Any) -> Dict[str, Any]:
        metadata = {
            "tool_name": "cli_session",
            "generator": "cli_session",
            "schema_version": "1.0",
        }
        metadata.update({key: value for key, value in extra.items() if value is not None})
        return metadata
