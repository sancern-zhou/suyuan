"""Publish an existing local file through the unified session resource catalog.

This tool has no frontend delivery protocol. It returns canonical ``resources``
declarations; the normal tool-result boundary copies the file into session
storage, updates the catalog, and emits ``resources_changed``.
"""
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from app.services.html_artifact_service import html_artifact_service
from app.services.pdf_converter import pdf_converter
from app.services.report_preview_refresh import (
    create_report_preview_for_source_qmd_path,
    refresh_report_preview_for_qmd_path,
)
from app.tools.artifact_utils import (
    attach_document_resources,
    attach_report_package_resources,
    preview_output_path,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.editable_ppt.delivery_guard import validate_editable_ppt_delivery
from app.tools.resource_declarations import generated_file_products
from app.utils.path_config import BACKEND_ROOT, PROJECT_ROOT

logger = structlog.get_logger()


MARKDOWN_EXTENSIONS = {".md", ".markdown", ".qmd"}
HTML_EXTENSIONS = {".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
PDF_EXTENSIONS = {".pdf"}
WORD_EXTENSIONS = {".doc", ".docx"}
PRESENTATION_EXTENSIONS = {".ppt", ".pptx"}
SPREADSHEET_EXTENSIONS = {".xls", ".xlsx"}
DRAWIO_EXTENSIONS = {".drawio"}
MAX_SESSION_FILE_SIZE = 50 * 1024 * 1024
TOOL_NAME = "publish_session_file"


class PublishSessionFileTool(LLMTool):
    """Register an existing file as a durable, user-visible session resource."""

    def __init__(self):
        super().__init__(
            name=TOOL_NAME,
            description=(
                "将磁盘上已经存在、但尚未作为本次工具产物发布的文件登记到统一会话资源目录，"
                "供用户预览或下载。仅在用户明确要求查看、下载或交付某个已有本地文件时使用；"
                "不要对已经由生成工具自动发布的产物重复调用。"
            ),
            category=ToolCategory.REPORTING,
            version="2.0.0",
            requires_context=False,
        )
        self.allowed_dirs = [
            PROJECT_ROOT.resolve(),
            Path(tempfile.gettempdir()).resolve(),
        ]

    async def execute(
        self,
        file_path: str,
        label: str | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        del kwargs
        resolved_path = self._resolve_path(file_path)
        if not resolved_path:
            return self._failure(f"文件路径无效或超出允许目录范围: {file_path}")
        if not resolved_path.exists():
            return self._failure(f"文件不存在: {file_path}")
        if not resolved_path.is_file():
            return self._failure(f"路径不是文件: {file_path}")

        file_size = resolved_path.stat().st_size
        if file_size > MAX_SESSION_FILE_SIZE:
            return self._failure(
                f"文件超过会话资源发布上限（50 MiB）: {resolved_path.name} ({file_size} bytes)"
            )

        suffix = resolved_path.suffix.lower()
        file_type = self._resolve_file_type(suffix)
        if suffix == ".pptx":
            delivery = validate_editable_ppt_delivery(resolved_path)
            if not delivery.get("allowed", False):
                return self._failure(
                    delivery["message"],
                    code=delivery["code"],
                    project_dir=delivery.get("project_dir"),
                )

        try:
            data: Dict[str, Any] = {
                "file_path": str(resolved_path),
                "file_name": resolved_path.name,
                "file_type": file_type,
                "size": file_size,
            }
            html_artifact_id = (
                html_artifact_service.get_artifact_id_from_index_path(resolved_path)
                if file_type == "html"
                else None
            )

            if html_artifact_id:
                file_type = "html_artifact"
                data["file_type"] = file_type
                attach_document_resources(
                    data,
                    resolved_path,
                    kind="html_artifact",
                    format="html",
                    title=label or html_artifact_id,
                    generator=TOOL_NAME,
                    metadata={"artifact_id": html_artifact_id},
                )
            elif suffix == ".qmd" and self._attach_rendered_report(data, resolved_path):
                file_type = "report"
                data["file_type"] = file_type
            else:
                await self._attach_file_product(data, resolved_path, file_type)

            resources = data.get("resources", [])
            if label:
                primary = next(
                    (item for item in resources if item.get("relation") == "primary"),
                    None,
                )
                if primary is not None:
                    primary["label"] = label.strip()[:512] or resolved_path.name
            preview_available = any(
                "preview" in item.get("capabilities", []) for item in resources
            )
            download_available = any(
                "download" in item.get("capabilities", []) for item in resources
            )
            data["preview_available"] = preview_available
            data["download_available"] = download_available

            logger.info(
                "session_file_published",
                path=str(resolved_path),
                file_type=file_type,
                preview_available=preview_available,
                size=file_size,
            )
            summary = (
                f"已登记到会话资源目录，可预览和下载：{resolved_path.name}"
                if preview_available
                else f"已登记到会话资源目录，可下载：{resolved_path.name}"
            )
            return {
                "status": "success",
                "success": True,
                "data": data,
                "resources": resources,
                "llm_resume": {
                    "file_path": str(resolved_path),
                    "tool_hint": (
                        "The file is available through the unified session resource catalog."
                    ),
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": TOOL_NAME,
                    "file_type": file_type,
                },
                "summary": summary,
            }
        except Exception as exc:
            logger.error("publish_session_file_failed", path=str(resolved_path), error=str(exc))
            return self._failure(f"登记会话资源失败: {str(exc)[:120]}")

    def _attach_rendered_report(self, data: Dict[str, Any], path: Path) -> bool:
        try:
            report_preview = (
                refresh_report_preview_for_source_qmd_path(path)
                or create_report_preview_for_source_qmd_path(path)
            )
        except Exception as exc:
            data["preview_error"] = str(exc)[:200]
            logger.warning(
                "session_report_preview_conversion_failed",
                path=str(path),
                error=data["preview_error"],
            )
            return False
        if not isinstance(report_preview, dict) or not report_preview.get("html_preview"):
            return False
        html_path = preview_output_path(report_preview.get("html_preview"))
        if html_path is None:
            return False
        report_id = str(report_preview.get("report_id") or path.stem)
        package_qmd = html_path.parent / "report.qmd"
        if not package_qmd.is_file():
            return False
        data["report_id"] = report_id
        attach_report_package_resources(
            data,
            package_qmd,
            report_id=report_id,
            html_path=html_path,
            generator=TOOL_NAME,
        )
        data["resources"][0]["label"] = path.name
        return True

    async def _attach_file_product(
        self,
        data: Dict[str, Any],
        path: Path,
        file_type: str,
    ) -> None:
        preview_path = None
        if file_type in {"document", "presentation"}:
            try:
                # Conversion is best effort. Failure must not prevent the user
                # from downloading the original file.
                converted = await pdf_converter.convert_to_pdf(str(path))
                preview_path = preview_output_path(converted)
            except Exception as exc:
                data["preview_error"] = str(exc)[:200]
                logger.warning(
                    "session_file_preview_conversion_failed",
                    path=str(path),
                    error=data["preview_error"],
                )
        resources = generated_file_products(
            [path],
            tool_name=TOOL_NAME,
            preview_paths={str(path): preview_path} if preview_path else None,
        )
        data["resources"] = resources

    def _resolve_path(self, path: str) -> Optional[Path]:
        try:
            candidate = Path(path)
            if not candidate.is_absolute():
                candidate = BACKEND_ROOT / candidate
            resolved = candidate.resolve()
            if any(resolved.is_relative_to(allowed_dir) for allowed_dir in self.allowed_dirs):
                return resolved
            logger.warning(
                "publish_session_file_path_escape",
                requested_path=path,
                allowed_dirs=[str(item) for item in self.allowed_dirs],
            )
            return None
        except Exception as exc:
            logger.warning("publish_session_file_path_resolution_failed", path=path, error=str(exc))
            return None

    def _resolve_file_type(self, suffix: str) -> str:
        if suffix in MARKDOWN_EXTENSIONS:
            return "markdown"
        if suffix in HTML_EXTENSIONS:
            return "html"
        if suffix in IMAGE_EXTENSIONS:
            return "image"
        if suffix in PDF_EXTENSIONS:
            return "pdf"
        if suffix in WORD_EXTENSIONS:
            return "document"
        if suffix in PRESENTATION_EXTENSIONS:
            return "presentation"
        if suffix in SPREADSHEET_EXTENSIONS:
            return "spreadsheet"
        if suffix in DRAWIO_EXTENSIONS:
            return "editable_diagram"
        return "file"

    def _failure(
        self,
        message: str,
        code: str | None = None,
        project_dir: str | None = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": "failed",
            "success": False,
            "error": message,
            "metadata": {
                "schema_version": "v2.0",
                "generator": TOOL_NAME,
            },
            "summary": f"会话资源登记失败：{message}",
        }
        if code:
            result["data"] = {
                "project_dir": project_dir,
                "issues": [{"code": code, "message": message}],
                "next_actions": ["重新 strict 编译、验证并 finalize 后再交付"],
            }
        return result

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": TOOL_NAME,
            "description": (
                "将已有本地文件登记到统一会话资源目录，供用户预览或下载。"
                "仅在用户明确要求查看、下载或交付尚未自动发布的本地文件时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "允许目录内已存在文件的绝对路径，或相对于 backend 目录的路径；"
                            "例如 backend_data_registry/uploads/example.png。"
                        ),
                    },
                    "label": {
                        "type": "string",
                        "description": "可选的用户可见名称；不提供时使用原文件名。",
                    },
                },
                "required": ["file_path"],
            },
        }


tool = PublishSessionFileTool()
