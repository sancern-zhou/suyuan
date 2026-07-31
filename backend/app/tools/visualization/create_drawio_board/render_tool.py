from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.boards.application import BoardApplicationService
from app.boards.quality import BoardQualityFailed, BoardRenderFailed, DrawioQualityService
from app.db.database import async_session
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import resources_for_files


def _merge_quality_reports(
    existing: dict[str, Any],
    refreshed: dict[str, Any],
) -> dict[str, Any]:
    report = dict(refreshed)
    report["metrics"] = {
        **(existing.get("metrics") or {}),
        **(refreshed.get("metrics") or {}),
    }
    for key in ("routing_status", "routing_issues"):
        if key in existing:
            report[key] = existing[key]
    routing_warnings = [
        warning
        for warning in existing.get("warnings") or []
        if warning.get("code") == "edge_routing_degraded"
    ]
    refreshed_warnings = list(refreshed.get("warnings") or [])
    report["warnings"] = routing_warnings + [
        warning for warning in refreshed_warnings if warning not in routing_warnings
    ]
    if routing_warnings and report.get("status") == "passed":
        report["status"] = "warning"
    return report


class RenderDrawioBoardCandidateTool(LLMTool):
    def __init__(
        self,
        name: str = "render_drawio_board_candidate",
        *,
        quality_service=None,
        candidate_loader=None,
        render_persister=None,
    ) -> None:
        self.quality_service = quality_service or DrawioQualityService()
        self.candidate_loader = candidate_loader or self._load_candidate
        self.render_persister = render_persister or self._persist_render
        super().__init__(
            name=name,
            description=(
                "Board-mode only. Render a persisted draw.io candidate to a PNG for optional "
                "Agent visual review after create_drawio_board has already returned its preview."
            ),
            category=ToolCategory.VISUALIZATION,
            function_schema={
                "name": name,
                "description": (
                    "Render a persisted draw.io candidate and return its screenshot as a multimodal attachment."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"candidate_version_id": {"type": "string"}},
                    "required": ["candidate_version_id"],
                },
            },
            version="1.0.0",
        )

    async def execute(self, candidate_version_id: str, **kwargs: Any) -> dict[str, Any]:
        candidate_id = str(candidate_version_id or "").strip()
        session_id = str(kwargs.get("_session_id") or "").strip()
        board_id = str(kwargs.get("_board_id") or "").strip()
        agent_run_id = str(kwargs.get("_agent_run_id") or "").strip()
        if not candidate_id or not session_id or not board_id or not agent_run_id:
            return {
                "status": "error",
                "success": False,
                "data": {
                    "error_code": "board_render_context_required",
                    "candidate_version_id": candidate_id or None,
                    "retryable": False,
                },
                "metadata": {"tool_name": self.name, "generator": self.name},
                "summary": "画板截图生成失败：缺少候选版本或运行上下文。",
            }

        source = await self.candidate_loader(
            session_id=session_id,
            board_id=board_id,
            candidate_version_id=candidate_id,
            agent_run_id=agent_run_id,
        )
        existing_screenshot = source.get("screenshot_ref")
        existing_report = source.get("quality_report") or {}
        if existing_screenshot and existing_report.get("render_status") == "completed":
            return self._success_result(source, existing_report, existing_screenshot)

        try:
            rendered = await self.quality_service.inspect(
                source["xml"],
                board_id=source["board_id"],
                candidate_id=source["candidate_version_id"],
            )
        except (BoardQualityFailed, BoardRenderFailed) as exc:
            report = _merge_quality_reports(
                existing_report,
                dict(getattr(exc, "report", None) or {}),
            )
            report.update({"render_status": "failed", "render_error": str(exc)})
            persisted = await self.render_persister(
                session_id=session_id,
                board_id=board_id,
                candidate_version_id=candidate_id,
                agent_run_id=agent_run_id,
                quality_status="failed",
                quality_report=report,
                screenshot_ref=None,
            )
            return {
                "status": "error",
                "success": False,
                "data": {
                    "artifact_kind": "drawio_board",
                    "board_id": board_id,
                    "candidate_version_id": candidate_id,
                    "lifecycle_status": persisted.get("lifecycle_status")
                    or source.get("lifecycle_status"),
                    "quality_status": "failed",
                    "quality_report": report,
                    "render_status": "failed",
                    "error_code": getattr(exc, "code", "board_render_failed"),
                    "retryable": True,
                    "xml_ref": source.get("xml_ref"),
                },
                "metadata": {"tool_name": self.name, "generator": self.name},
                "summary": "画板截图生成失败；候选画板仍可预览，Agent 可自主决定重试、修改或接受。",
            }

        report = {
            **_merge_quality_reports(existing_report, rendered["quality_report"]),
            "render_status": "completed",
        }
        report.pop("render_error", None)
        screenshot_ref = rendered["screenshot_ref"]
        await self.render_persister(
            session_id=session_id,
            board_id=board_id,
            candidate_version_id=candidate_id,
            agent_run_id=agent_run_id,
            quality_status=report["status"],
            quality_report=report,
            screenshot_ref=screenshot_ref,
        )
        return self._success_result(source, report, screenshot_ref)

    def _success_result(
        self,
        source: dict[str, Any],
        report: dict[str, Any],
        screenshot_ref: dict[str, Any],
    ) -> dict[str, Any]:
        title = source.get("title") or "Draw.io Board"
        data = {
            "artifact_kind": "drawio_board",
            "board_id": source["board_id"],
            "candidate_version_id": source["candidate_version_id"],
            "version_id": source["candidate_version_id"],
            "title": title,
            "lifecycle_status": source.get("lifecycle_status") or "candidate",
            "quality_status": report.get("status") or source.get("quality_status") or "pending",
            "quality_report": report,
            "render_status": "completed",
            "screenshot_ref": screenshot_ref,
            "xml_ref": source.get("xml_ref"),
            "requires_visual_review": (source.get("lifecycle_status") or "candidate")
            == "candidate",
        }
        return {
            "status": "success",
            "success": True,
            "type": "multimodal_attachment",
            "data": data,
            "metadata": {
                "tool_name": self.name,
                "generator": self.name,
                "artifact_kind": "drawio_board",
            },
            "refs": {"artifacts": [source.get("xml_ref"), screenshot_ref]},
            "resources": resources_for_files(
                [screenshot_ref.get("local_path")],
                tool_name=self.name,
            ),
            "attachments": [
                {
                    "type": "image",
                    "name": f"{title}-质量核查.png",
                    "mime_type": "image/png",
                    "source": "drawio_quality_review",
                    **screenshot_ref,
                }
            ],
            "summary": "画板截图已生成，请结合截图自主判断是接受当前候选还是继续修改。",
        }

    async def _load_candidate(self, **payload: Any) -> dict[str, Any]:
        receipt = await BoardApplicationService(async_session).load_candidate_for_render(**payload)
        return asdict(receipt)

    async def _persist_render(self, **payload: Any) -> dict[str, Any]:
        receipt = await BoardApplicationService(async_session).complete_candidate_render(**payload)
        return asdict(receipt)
