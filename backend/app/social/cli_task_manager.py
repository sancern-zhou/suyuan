"""Background execution manager for cli_session tasks."""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import structlog

from app.social.cli_task_store import CliTaskStore
from app.social.events import OutboundMessage

logger = structlog.get_logger(__name__)

Parser = Callable[[str, str], Tuple[str, Optional[str]]]
CompletionCallback = Callable[[Dict[str, Any]], Any]

MAX_OUTPUT_CHARS = 200_000
TAIL_CHARS = 12_000


class CliTaskManager:
    """Run CLI commands in the background and persist task status."""

    MAX_CONCURRENT_PER_USER = 5

    def __init__(self, task_store: CliTaskStore, message_bus=None) -> None:
        self.task_store = task_store
        self.message_bus = message_bus
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}

    async def start(self) -> None:
        stale_count = await self.task_store.mark_stale_running_tasks()
        if stale_count:
            logger.info("cli_task_stale_tasks_marked", count=stale_count)

    async def shutdown(self) -> None:
        for task_id in list(self._running_tasks):
            await self.cancel_task(task_id)
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)

    async def start_task(
        self,
        *,
        social_user_id: str,
        origin_info: Dict[str, str],
        provider: str,
        session_name: str,
        cwd: str,
        args: list[str],
        stdin_text: str,
        timeout: int,
        label: str | None = None,
        parser: Parser | None = None,
        completion_callback: CompletionCallback | None = None,
    ) -> Dict[str, Any]:
        running = await self.task_store.list_tasks(social_user_id=social_user_id, status="running")
        pending = await self.task_store.list_tasks(social_user_id=social_user_id, status="pending")
        if len(running) + len(pending) >= self.MAX_CONCURRENT_PER_USER:
            return {
                "status": "failed",
                "success": False,
                "error": f"后台CLI任务数量已达上限（{self.MAX_CONCURRENT_PER_USER}个）",
            }

        task_id = await self.task_store.create_task(
            social_user_id=social_user_id,
            provider=provider,
            session_name=session_name,
            cwd=cwd,
            command=self._redact_command(args),
            label=label,
            origin_channel=origin_info.get("channel", "unknown"),
            origin_chat_id=origin_info.get("chat_id", "unknown"),
            origin_sender_id=origin_info.get("sender_id", "unknown"),
            timeout=timeout,
        )
        task = asyncio.create_task(
            self._run_task(
                task_id=task_id,
                origin_info=origin_info,
                cwd=cwd,
                args=args,
                stdin_text=stdin_text,
                timeout=timeout,
                parser=parser,
                completion_callback=completion_callback,
            )
        )
        self._running_tasks[task_id] = task
        task.add_done_callback(lambda _task: self._running_tasks.pop(task_id, None))
        return {
            "status": "success",
            "success": True,
            "task_id": task_id,
            "label": label or f"{provider} CLI 后台任务",
        }

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = await self.task_store.get_task(task_id)
        process = self._processes.get(task_id)
        if task and process:
            task["pid"] = process.pid
        return task

    async def list_tasks(self, social_user_id: str | None = None) -> list[Dict[str, Any]]:
        return await self.task_store.list_tasks(social_user_id=social_user_id)

    async def cancel_task(self, task_id: str) -> Dict[str, Any]:
        task = await self.task_store.get_task(task_id)
        if not task:
            return {"status": "failed", "success": False, "error": f"CLI后台任务不存在: {task_id}"}

        process = self._processes.get(task_id)
        if process and process.returncode is None:
            try:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            except ProcessLookupError:
                pass

        running_task = self._running_tasks.get(task_id)
        if running_task and not running_task.done():
            running_task.cancel()

        await self.task_store.update_task(
            task_id,
            status="cancelled",
            progress=0.0,
            error="任务已取消",
        )
        return {"status": "success", "success": True, "task_id": task_id}

    async def _run_task(
        self,
        *,
        task_id: str,
        origin_info: Dict[str, str],
        cwd: str,
        args: list[str],
        stdin_text: str,
        timeout: int,
        parser: Parser | None,
        completion_callback: CompletionCallback | None,
    ) -> None:
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        process: asyncio.subprocess.Process | None = None
        try:
            env = self._build_env()
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(Path(cwd)),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._processes[task_id] = process
            await self.task_store.update_task(
                task_id,
                status="running",
                progress=0.05,
                pid=process.pid,
            )

            stdout_reader = asyncio.create_task(self._read_stream(task_id, process.stdout, stdout_parts, "stdout_tail"))
            stderr_reader = asyncio.create_task(self._read_stream(task_id, process.stderr, stderr_parts, "stderr_tail"))

            if process.stdin:
                if stdin_text:
                    process.stdin.write(stdin_text.encode("utf-8"))
                    await process.stdin.drain()
                process.stdin.close()

            await asyncio.wait_for(process.wait(), timeout=timeout)
            await asyncio.gather(stdout_reader, stderr_reader, return_exceptions=True)

            stdout = "".join(stdout_parts)
            stderr = "".join(stderr_parts)
            parsed_text, vendor_session_id = parser(stdout, stderr) if parser else (stdout.strip(), None)
            result_payload = {
                "task_id": task_id,
                "exit_code": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "parsed_text": parsed_text,
                "vendor_session_id": vendor_session_id,
                "finished_at": datetime.now().isoformat(),
            }
            if completion_callback:
                callback_result = completion_callback(result_payload)
                if inspect.isawaitable(callback_result):
                    await callback_result

            success = process.returncode == 0
            await self.task_store.update_task(
                task_id,
                status="completed" if success else "failed",
                progress=1.0,
                exit_code=process.returncode,
                result=parsed_text.strip() or stdout.strip(),
                error=None if success else (stderr.strip() or f"CLI exited with {process.returncode}"),
                stdout_tail=self._tail(stdout),
                stderr_tail=self._tail(stderr),
            )
            if success:
                await self._send_completion_notification(task_id, origin_info, parsed_text.strip() or stdout.strip())
            else:
                await self._send_failure_notification(task_id, origin_info, stderr.strip() or "CLI任务失败")

        except asyncio.CancelledError:
            await self.task_store.update_task(task_id, status="cancelled", error="任务已取消")
            raise
        except asyncio.TimeoutError:
            if process and process.returncode is None:
                process.kill()
                await process.wait()
            await self.task_store.update_task(
                task_id,
                status="failed",
                error=f"CLI后台任务超时（{timeout}秒）",
                stdout_tail=self._tail("".join(stdout_parts)),
                stderr_tail=self._tail("".join(stderr_parts)),
            )
            await self._send_failure_notification(task_id, origin_info, f"CLI后台任务超时（{timeout}秒）")
        except Exception as exc:
            await self.task_store.update_task(task_id, status="failed", error=str(exc))
            await self._send_failure_notification(task_id, origin_info, str(exc))
            logger.error("cli_task_failed", task_id=task_id, error=str(exc), exc_info=True)
        finally:
            self._processes.pop(task_id, None)

    async def _read_stream(
        self,
        task_id: str,
        stream: Optional[asyncio.StreamReader],
        target: list[str],
        field: str,
    ) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            target.append(text)
            self._trim_parts(target)
            await self.task_store.update_task(task_id, **{field: self._tail("".join(target)), "progress": 0.5})

    async def _send_completion_notification(self, task_id: str, origin_info: Dict[str, str], result: str) -> None:
        if not self.message_bus:
            return
        task = await self.task_store.get_task(task_id)
        label = task.get("label", "CLI后台任务") if task else "CLI后台任务"
        content = f"""【后台CLI任务完成】

任务: {label}
结果:
{self._tail(result, 800)}

任务ID: {task_id}"""
        await self.message_bus.publish_outbound(self._outbound(origin_info, content))

    async def _send_failure_notification(self, task_id: str, origin_info: Dict[str, str], error: str) -> None:
        if not self.message_bus:
            return
        task = await self.task_store.get_task(task_id)
        label = task.get("label", "CLI后台任务") if task else "CLI后台任务"
        content = f"""【后台CLI任务失败】

任务: {label}
原因: {self._tail(error, 800)}

任务ID: {task_id}"""
        await self.message_bus.publish_outbound(self._outbound(origin_info, content))

    def _outbound(self, origin_info: Dict[str, str], content: str) -> OutboundMessage:
        return OutboundMessage(
            channel=origin_info.get("channel", "unknown"),
            chat_id=origin_info.get("chat_id", "unknown"),
            content=content,
            reply_to=origin_info.get("sender_id"),
        )

    def _build_env(self) -> dict[str, str]:
        import os

        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")
        env.setdefault("TERM", "dumb")
        env.setdefault("TOKENIZERS_PARALLELISM", "false")
        return env

    def _trim_parts(self, parts: list[str]) -> None:
        while len("".join(parts)) > MAX_OUTPUT_CHARS and parts:
            parts.pop(0)

    def _tail(self, text: str, max_chars: int = TAIL_CHARS) -> str:
        return text[-max_chars:] if text and len(text) > max_chars else (text or "")

    def _redact_command(self, args: list[str]) -> list[str]:
        return [arg if len(str(arg)) <= 160 else str(arg)[:80] + "...<truncated>" for arg in args]
