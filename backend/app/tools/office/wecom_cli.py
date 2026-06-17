"""Thin wrapper around the official WeCom CLI."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from typing import Any, Dict

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


DEFAULT_TIMEOUT_SECONDS = 120
MAX_OUTPUT_CHARS = 20000


class WeComCliTool(LLMTool):
    """Execute official ``wecom-cli`` commands for WeCom workspace operations."""

    def __init__(self) -> None:
        super().__init__(
            name="wecom_cli",
            description=(
                "调用官方 wecom-cli 执行企业微信能力。适用于文档、智能表格、"
                "消息、日程、会议、待办、通讯录等 CLI 已支持的操作。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        module: str,
        command: str,
        payload: Dict[str, Any] | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        cli_path = shutil.which("wecom-cli")
        if not cli_path:
            return {
                "success": False,
                "data": {"error": "wecom-cli not found"},
                "summary": "未找到 wecom-cli，请先安装 @wecom/cli 并运行 wecom-cli init",
            }

        clean_module = (module or "").strip()
        clean_command = (command or "").strip()
        if not clean_module or not clean_command:
            return {
                "success": False,
                "data": {"error": "module and command are required"},
                "summary": "module 和 command 不能为空",
            }

        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        timeout = max(1, min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), 600))
        args = (cli_path, clean_module, clean_command, payload_json)

        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "data": {"error": f"wecom-cli timed out after {timeout}s"},
                    "summary": f"wecom-cli 执行超时（{timeout}s）",
                }

            stdout = (await process.stdout.read()).decode("utf-8", errors="replace") if process.stdout else ""
            stderr = (await process.stderr.read()).decode("utf-8", errors="replace") if process.stderr else ""
            parsed = self._parse_stdout(stdout)
            success = process.returncode == 0
            return {
                "success": success,
                "data": parsed,
                "stdout": stdout[-MAX_OUTPUT_CHARS:],
                "stderr": stderr[-MAX_OUTPUT_CHARS:],
                "summary": (
                    f"wecom-cli {clean_module} {clean_command} 执行成功"
                    if success
                    else f"wecom-cli {clean_module} {clean_command} 执行失败，退出码 {process.returncode}"
                ),
            }
        except Exception as exc:
            logger.error("wecom_cli_execution_failed", error=str(exc), exc_info=True)
            return {
                "success": False,
                "data": {"error": str(exc)},
                "summary": f"wecom-cli 调用失败: {str(exc)[:120]}",
            }

    @staticmethod
    def _parse_stdout(stdout: str) -> Any:
        text = (stdout or "").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text[-MAX_OUTPUT_CHARS:]}

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": "wecom_cli",
            "description": (
                "调用官方 wecom-cli。调用前需已执行 wecom-cli init 完成授权。"
                "参数会以 `wecom-cli <module> <command> <payload-json>` 形式执行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {
                        "type": "string",
                        "description": "CLI 模块名，例如 doc、sheet、contact、message，具体以 wecom-cli 帮助为准",
                    },
                    "command": {
                        "type": "string",
                        "description": "模块下的命令名，例如 create、get、update、list_records",
                    },
                    "payload": {
                        "type": "object",
                        "description": "传给 wecom-cli 的 JSON 参数对象",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "执行超时时间，默认 120 秒，最大 600 秒",
                    },
                },
                "required": ["module", "command"],
            },
        }


tool = WeComCliTool()
