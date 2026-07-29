from __future__ import annotations

import asyncio
import json
import os
import signal
from pathlib import Path
from typing import Any


class CompilerClientError(RuntimeError):
    def __init__(self, code: str, message: str, *, stderr: str = ""):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.stderr = stderr


class EditablePptCompilerClient:
    def __init__(
        self,
        node_binary: str = "node",
        cli_path: str | Path | None = None,
        timeout_seconds: float = 120,
    ):
        self.node_binary = node_binary
        self.cli_path = Path(cli_path) if cli_path else (
            Path(__file__).resolve().parent.parent / "editable_ppt_runtime" / "src" / "cli.mjs"
        )
        self.timeout_seconds = timeout_seconds

    async def health(self) -> dict[str, Any]:
        return await self._request({"command": "health"})

    async def inspect(self, project_dir: str | Path) -> dict[str, Any]:
        return await self._request({"command": "inspect", "projectDir": str(Path(project_dir).resolve())})

    async def preview(
        self, project_dir: str | Path, output_dir: str | Path | None = None,
        *, dirty_slides: list[str] | None = None, pages: list[int] | None = None,
        cache_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        project = Path(project_dir).resolve()
        return await self._request(self._build_request(
            "preview", project, output_dir or project / "build" / "preview",
            dirty_slides=dirty_slides, pages=pages, cache_dir=cache_dir,
        ))

    async def compile(
        self, project_dir: str | Path, output_dir: str | Path | None = None,
        *, dirty_slides: list[str] | None = None, cache_dir: str | Path | None = None,
        editable: str = "strict", file_name: str = "presentation.pptx",
    ) -> dict[str, Any]:
        project = Path(project_dir).resolve()
        request = self._build_request(
            "compile", project, output_dir or project / "build" / "pptx",
            dirty_slides=dirty_slides, cache_dir=cache_dir,
        )
        request.update({"editable": editable, "fileName": file_name})
        return await self._request(request)

    @staticmethod
    def _build_request(command, project, output, **options):
        request = {
            "command": command, "projectDir": str(project),
            "outputDir": str(Path(output).resolve()),
        }
        mapping = {"dirty_slides": "dirtySlides", "cache_dir": "cacheDir", "pages": "pages"}
        for key, value in options.items():
            if value is not None:
                request[mapping[key]] = str(Path(value).resolve()) if key == "cache_dir" else value
        return request

    async def _request(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.cli_path.is_file():
            raise CompilerClientError("COMPILER_RUNTIME_MISSING", f"CLI not found: {self.cli_path}")
        try:
            process = await asyncio.create_subprocess_exec(
                self.node_binary, str(self.cli_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=os.name == "posix",
            )
        except FileNotFoundError as exc:
            raise CompilerClientError("NODE_RUNTIME_MISSING", self.node_binary) from exc
        payload = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(payload), timeout=self.timeout_seconds
            )
        except TimeoutError as exc:
            await self._terminate(process)
            raise CompilerClientError("COMPILER_TIMEOUT", f"exceeded {self.timeout_seconds}s") from exc
        except asyncio.CancelledError:
            await self._terminate(process)
            raise
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            raise CompilerClientError(
                "COMPILER_PROCESS_FAILED", f"exit code {process.returncode}", stderr=stderr_text
            )
        lines = [line for line in stdout.decode("utf-8", errors="replace").splitlines() if line.strip()]
        if len(lines) != 1:
            raise CompilerClientError(
                "COMPILER_PROTOCOL_ERROR", f"expected one JSON object, received {len(lines)} lines",
                stderr=stderr_text,
            )
        try:
            response = json.loads(lines[0])
        except json.JSONDecodeError as exc:
            raise CompilerClientError("COMPILER_PROTOCOL_ERROR", str(exc), stderr=stderr_text) from exc
        if not isinstance(response, dict):
            raise CompilerClientError("COMPILER_PROTOCOL_ERROR", "response must be an object")
        return response

    @staticmethod
    async def _terminate(process):
        try:
            if os.name == "posix" and getattr(process, "pid", None):
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        finally:
            await process.wait()
