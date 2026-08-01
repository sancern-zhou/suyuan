"""
present_artifact 工具

Agent 用这个工具把已经生成的文件推送到前端右侧面板。
工具不生成文件，只把文件路径转换成现有前端可消费的 preview 字段。
"""
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote

import structlog

from app.services.pdf_converter import pdf_converter
from app.services.html_artifact_service import html_artifact_service
from app.services.report_preview_refresh import (
    create_report_preview_for_source_qmd_path,
    refresh_report_preview_for_qmd_path,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.artifact_utils import attach_document_artifact
from app.tools.office.editable_ppt.delivery_guard import validate_editable_ppt_delivery

logger = structlog.get_logger()


MARKDOWN_EXTENSIONS = {".md", ".markdown", ".qmd"}
HTML_EXTENSIONS = {".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
PDF_EXTENSIONS = {".pdf"}
WORD_EXTENSIONS = {".doc", ".docx"}
PRESENTATION_EXTENSIONS = {".ppt", ".pptx"}
SPREADSHEET_EXTENSIONS = {".xls", ".xlsx"}
DRAWIO_EXTENSIONS = {".drawio"}
MAX_ARTIFACT_SIZE = 50 * 1024 * 1024


class PresentArtifactTool(LLMTool):
    """把已存在的文件呈现给用户。"""

    def __init__(self):
        super().__init__(
            name="present_artifact",
            description=(
                "将已生成的文件推送到前端右侧预览面板，并允许用户下载原文件。"
                "仅接收已存在的文件路径，不负责生成文件。支持 PDF、Word、PPT、Excel、"
                "Markdown/QMD、HTML、图片和 Draw.io 图表。"
            ),
            category=ToolCategory.VISUALIZATION,
            version="1.0.0",
            requires_context=False,
        )
        self.allowed_dirs = [Path("/home/xckj/suyuan").resolve(), Path("/tmp").resolve()]

    async def execute(
        self,
        file_path: str,
        artifact_type: str = "auto",
        **kwargs,
    ) -> Dict[str, Any]:
        resolved_path = self._resolve_path(file_path)
        if not resolved_path:
            return self._failure(f"文件路径无效或超出允许目录范围: {file_path}")

        if not resolved_path.exists():
            return self._failure(f"文件不存在: {file_path}")

        if not resolved_path.is_file():
            return self._failure(f"路径不是文件: {file_path}")

        file_size = resolved_path.stat().st_size
        if file_size > MAX_ARTIFACT_SIZE:
            return self._failure(
                f"文件过大，无法推送预览: {resolved_path.name} ({file_size} bytes)"
            )

        suffix = resolved_path.suffix.lower()
        resolved_type = self._resolve_artifact_type(suffix, artifact_type)
        if resolved_type == "unsupported":
            return self._failure(f"不支持预览的文件类型: {suffix or '无扩展名'}")
        if suffix == ".pptx":
            delivery = validate_editable_ppt_delivery(resolved_path)
            if not delivery.get("allowed", False):
                return self._failure(
                    delivery["message"],
                    code=delivery["code"],
                    project_dir=delivery.get("project_dir"),
                )

        try:
            artifact: Optional[Dict[str, Any]] = None
            data: Dict[str, Any] = {
                "file_path": str(resolved_path),
                "file_name": resolved_path.name,
                "file_type": resolved_type,
                "size": file_size,
            }

            html_artifact_id = None
            if resolved_type == "html":
                html_artifact_id = html_artifact_service.get_artifact_id_from_index_path(resolved_path)

            if html_artifact_id:
                html_preview = html_artifact_service.build_html_preview(html_artifact_id)
                resolved_type = "html_artifact"
                data["file_type"] = "html_artifact"
                data["html_preview"] = html_preview
                data["download_url"] = f"/api/html-artifacts/{html_artifact_id}/download/html"
                data["share_endpoint"] = f"/api/html-artifacts/{html_artifact_id}/share"
            elif suffix == ".qmd":
                report_preview = (
                    refresh_report_preview_for_qmd_path(resolved_path)
                    or create_report_preview_for_source_qmd_path(resolved_path)
                )
                if report_preview:
                    if not report_preview.get("html_preview"):
                        error = report_preview.get("render_error") or report_preview.get("report_preview_refresh", {}).get("error")
                        return self._failure(f"QMD报告HTML预览生成失败: {error or resolved_path.name}")
                    resolved_type = "report"
                    data.update(report_preview)
                    data["file_type"] = "report"
            if resolved_type in {"report", "html_artifact"}:
                pass
            elif resolved_type == "markdown":
                data["markdown_preview"] = {
                    "content": resolved_path.read_text(encoding="utf-8", errors="replace"),
                    "file_type": resolved_type,
                }
            elif resolved_type in {"html", "image"}:
                data["html_preview"] = {
                    "html_path": str(resolved_path),
                    "html_id": self._stable_artifact_id(resolved_path),
                    "preview_version": str(int(resolved_path.stat().st_mtime)),
                    "file_type": resolved_type,
                }
            elif resolved_type == "pdf":
                data["pdf_preview"] = {
                    "pdf_path": str(resolved_path),
                    "size": file_size,
                }
            elif resolved_type == "spreadsheet":
                data["spreadsheet_preview"] = {
                    "file_type": suffix.lstrip(".") or "xlsx",
                    "editable": True,
                    "size": file_size,
                }
            elif resolved_type in {"document", "presentation"}:
                data["pdf_preview"] = await pdf_converter.convert_to_pdf(str(resolved_path))
                if resolved_type == "presentation" and suffix == ".pptx":
                    ppt_preview = await self._render_ppt_preview(resolved_path)
                    if ppt_preview:
                        data["ppt_preview"] = ppt_preview
            elif resolved_type == "editable_diagram" and suffix in DRAWIO_EXTENSIONS:
                artifact = {
                    "type": "document",
                    "kind": "editable_diagram",
                    "format": "drawio",
                    "file_path": str(resolved_path),
                    "file_name": resolved_path.name,
                    "preview_panel": False,
                }
            else:
                return self._failure(f"不支持预览的文件类型: {suffix or '无扩展名'}")

            artifact_format = suffix.lstrip(".") or resolved_type
            if artifact is None:
                artifact = {
                    "type": "document",
                    "kind": resolved_type,
                    "format": artifact_format,
                    "file_path": str(resolved_path),
                    "file_name": resolved_path.name,
                    "title": html_artifact_id or resolved_path.stem,
                }
            else:
                artifact.setdefault("type", "document")
                artifact.setdefault("kind", resolved_type)
                artifact.setdefault("format", artifact_format)
                artifact.setdefault("file_path", str(resolved_path))
                artifact.setdefault("file_name", resolved_path.name)
                artifact.setdefault("title", html_artifact_id or resolved_path.stem)
            preview = (
                data.get("html_preview")
                or data.get("spreadsheet_preview")
                or data.get("pdf_preview")
                or data.get("ppt_preview")
                or data.get("markdown_preview")
            )
            if isinstance(preview, dict):
                artifact["preview"] = preview
            preview_key = next(
                (
                    key
                    for key in (
                        "html_preview",
                        "spreadsheet_preview",
                        "pdf_preview",
                        "ppt_preview",
                        "markdown_preview",
                    )
                    if isinstance(data.get(key), dict)
                ),
                None,
            )
            resource_kind = (
                resolved_type
                if resolved_type in {"report", "html_artifact"}
                else "office"
            )
            logical_key = html_artifact_id or artifact.get("artifact_id") or resolved_path.stem
            attach_document_artifact(
                data,
                resolved_path,
                kind=resource_kind,
                format=artifact_format,
                title=artifact.get("title") or resolved_path.name,
                preview_key=preview_key,
                generator="present_artifact",
                metadata={
                    "artifact_id": str(logical_key)
                    if resource_kind == "html_artifact"
                    else None,
                    "report_id": str(logical_key)
                    if resource_kind == "report"
                    else None,
                },
            )

            logger.info(
                "artifact_presented",
                path=str(resolved_path),
                artifact_type=resolved_type,
                size=file_size,
            )
            summary = (
                f"已作为可下载产物提供: {resolved_path.name}"
                if artifact and artifact.get("preview_panel") is False
                else f"已推送到右侧预览面板: {resolved_path.name}"
            )
            resources = data.get("resources", [])
            return {
                "status": "success",
                "success": True,
                "data": data,
                **({"artifact": artifact, "artifacts": [artifact]} if artifact else {}),
                "resources": resources,
                "llm_resume": {
                    "file_path": str(resolved_path),
                    "tool_hint": f"Use present_artifact(file_path='{resolved_path}') to preview this artifact.",
                },
                "metadata": {
                    "schema_version": "v1.0",
                    "generator": "present_artifact",
                    "file_type": resolved_type,
                },
                "summary": summary,
            }
        except UnicodeDecodeError:
            return self._failure(f"无法按文本读取文件: {resolved_path.name}")
        except Exception as exc:
            logger.error("present_artifact_failed", path=str(resolved_path), error=str(exc))
            return self._failure(f"推送预览失败: {str(exc)[:120]}")

    def _resolve_path(self, path: str) -> Optional[Path]:
        try:
            candidate = Path(path)
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            resolved = candidate.resolve()
            if any(resolved.is_relative_to(allowed_dir) for allowed_dir in self.allowed_dirs):
                return resolved
            logger.warning(
                "present_artifact_path_escape",
                requested_path=path,
                allowed_dirs=[str(path) for path in self.allowed_dirs],
            )
            return None
        except Exception as exc:
            logger.warning("present_artifact_path_resolution_failed", path=path, error=str(exc))
            return None

    def _resolve_artifact_type(self, suffix: str, artifact_type: str) -> str:
        normalized = (artifact_type or "auto").strip().lower()
        if normalized != "auto":
            aliases = {
                "doc": "document",
                "docx": "document",
                "word": "document",
                "ppt": "presentation",
                "pptx": "presentation",
                "powerpoint": "presentation",
                "xls": "spreadsheet",
                "xlsx": "spreadsheet",
                "excel": "spreadsheet",
                "md": "markdown",
                "qmd": "markdown",
                "drawio": "editable_diagram",
            }
            return aliases.get(normalized, normalized)

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
        return "unsupported"

    def _stable_artifact_id(self, path: Path) -> str:
        return quote(str(path), safe="")

    async def _render_ppt_preview(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            validator_cls = globals().get("ValidatePptxTool")
            if validator_cls is None:
                from app.tools.office.validate_pptx_tool import ValidatePptxTool as validator_cls

            validation = await validator_cls().execute(str(path), render_overflow_check=False)
            data = validation.get("data") if isinstance(validation, dict) else None
            if not isinstance(data, dict):
                return None
            return {
                "pptx_path": data.get("pptx_path"),
                "pages": data.get("pages", []),
                "montage_path": data.get("montage_path"),
                "report_path": data.get("report_path"),
            }
        except Exception as exc:
            logger.warning("present_artifact_ppt_preview_failed", path=str(path), error=str(exc))
            return None

    def _failure(self, message: str, code: str | None = None, project_dir: str | None = None) -> Dict[str, Any]:
        result = {
            "status": "failed",
            "success": False,
            "error": message,
            "metadata": {
                "schema_version": "v1.0",
                "generator": "present_artifact",
            },
            "summary": f"不支持预览: {message}" if "不支持预览" not in message else message,
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
            "name": "present_artifact",
            "description": (
                "把已存在的文件推送到前端右侧预览面板。"
                "用于让用户查看并下载 Agent 已生成的文件、图片或报告产物。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "已存在文件的绝对路径或相对路径。",
                    },
                    "artifact_type": {
                        "type": "string",
                        "enum": [
                            "auto",
                            "document",
                            "spreadsheet",
                            "presentation",
                            "pdf",
                            "markdown",
                            "html",
                            "image",
                            "editable_diagram",
                        ],
                        "default": "auto",
                        "description": "产物类型提示。默认 auto 根据扩展名判断。",
                    },
                },
                "required": ["file_path"],
            },
        }


tool = PresentArtifactTool()
