from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from app.boards.application import BoardApplicationService
from app.db.database import async_session
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import resources_for_files


class AcceptDrawioBoardCandidateTool(LLMTool):
    def __init__(self, name: str = "accept_drawio_board_candidate", *, candidate_accepter=None):
        self.candidate_accepter = candidate_accepter or self._accept_candidate
        super().__init__(
            name=name,
            description=(
                "Board-mode only. Accept the current draw.io candidate. Visual review through "
                "render_drawio_board_candidate is recommended, while the Agent may decide whether "
                "to accept, render, retry, or revise based on the task and available context."
            ),
            category=ToolCategory.VISUALIZATION,
            function_schema={
                "name": name,
                "description": "Accept a draw.io board candidate; prior screenshot review is recommended but optional.",
                "parameters": {
                    "type": "object",
                    "properties": {"candidate_version_id": {"type": "string"}},
                    "required": ["candidate_version_id"],
                },
            },
            version="1.0.0",
        )

    async def execute(self, candidate_version_id: str, **kwargs: Any) -> Dict[str, Any]:
        board_id = str(kwargs.get("_board_id") or "").strip()
        agent_run_id = str(kwargs.get("_agent_run_id") or "").strip()
        expected_revision = int(kwargs.get("_expected_board_revision") or 0)
        if not board_id or not agent_run_id or not candidate_version_id:
            return {
                "status": "error",
                "success": False,
                "data": {"error_code": "board_candidate_context_missing", "retryable": True},
                "metadata": {"tool_name": self.name, "generator": self.name},
                "summary": "候选画板缺少运行上下文，无法接受。",
            }
        payload = await self.candidate_accepter(
            board_id=board_id,
            candidate_version_id=str(candidate_version_id),
            expected_board_revision=expected_revision,
            agent_run_id=agent_run_id,
        )
        data = {
            "artifact_kind": "drawio_board",
            "board_id": payload["board_id"],
            "title": payload["title"],
            "version": payload["version_number"],
            "revision": payload["revision"],
            "current_version_id": payload["version_id"],
            "version_id": payload["version_id"],
            "lifecycle_status": "accepted",
            "xml_ref": payload["xml_ref"],
            "screenshot_ref": payload.get("screenshot_ref"),
            "quality_status": payload["quality_status"],
            "quality_report": payload.get("quality_report") or {},
            "candidate_accepted": True,
            "requires_visual_review": False,
        }
        refs = [payload["xml_ref"]]
        if payload.get("screenshot_ref"):
            refs.append(payload["screenshot_ref"])
        resource_paths = [
            ref.get("local_path")
            for ref in refs
            if isinstance(ref, dict) and ref.get("local_path")
        ]
        return {
            "status": "success",
            "success": True,
            "data": data,
            "metadata": {
                "tool_name": self.name,
                "generator": self.name,
                "artifact_kind": "drawio_board",
                "panel": "board",
                "editable": True,
            },
            "refs": {"artifacts": refs},
            "resources": resources_for_files(resource_paths, tool_name=self.name),
            "summary": f"画板候选版本 v{payload['version_number']} 已正式提交。",
        }

    async def _accept_candidate(self, **payload: Any) -> Dict[str, Any]:
        receipt = await BoardApplicationService(async_session).accept_candidate(**payload)
        return asdict(receipt)
