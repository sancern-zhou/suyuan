"""Helpers for tool-returned deliverable artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.tools.resource_declarations import (
    derivative_file,
    directory_artifact,
    primary_file,
)

OFFICE_MIME_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def build_document_artifact(
    file_path: str | Path,
    *,
    kind: str = "office",
    format: Optional[str] = None,
    title: Optional[str] = None,
    preview: Optional[Dict[str, Any]] = None,
    generator: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the normalized document artifact contract for the right panel."""
    path = Path(file_path)
    fmt = (format or path.suffix.lstrip(".") or "document").lower()
    artifact: Dict[str, Any] = {
        "type": "document",
        "kind": kind,
        "format": fmt,
        "file_path": str(path),
        "file_name": path.name,
        "preview_panel": True,
    }
    mime_type = OFFICE_MIME_TYPES.get(fmt)
    if mime_type:
        artifact["mime_type"] = mime_type
    if title:
        artifact["title"] = title
    if preview:
        artifact["preview"] = preview
    if generator:
        artifact["generator"] = generator
    if metadata:
        artifact["metadata"] = metadata
    return artifact


def attach_document_artifact(
    result_data: Dict[str, Any],
    file_path: str | Path,
    *,
    kind: str = "office",
    format: Optional[str] = None,
    title: Optional[str] = None,
    preview_key: Optional[str] = None,
    generator: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attach one explicit document resource and the render payload."""
    preview = result_data.get(preview_key) if preview_key else None
    artifact = build_document_artifact(
        file_path,
        kind=kind,
        format=format,
        title=title,
        preview=preview,
        generator=generator,
        metadata=metadata,
    )
    result_data["artifact"] = artifact
    logical_key = str(
        metadata.get("report_id") if isinstance(metadata, dict) and metadata.get("report_id")
        else metadata.get("artifact_id") if isinstance(metadata, dict) and metadata.get("artifact_id")
        else title or Path(file_path).stem
    )
    path = Path(file_path).expanduser().resolve()
    if kind == "report":
        group_key = f"report:{logical_key}"
    elif kind == "html_artifact":
        group_key = f"html-artifact:{logical_key}"
    elif (format or path.suffix.lstrip(".")).lower() == "pptx":
        group_key = f"presentation:{logical_key}"
    else:
        group_key = f"office:{logical_key}"
    fmt = (format or path.suffix.lstrip(".") or "document").lower()
    renderer_by_format = {
        "pdf": "pdf",
        "html": "html",
        "qmd": "markdown",
        "md": "markdown",
        "xlsx": "spreadsheet",
        "xls": "spreadsheet",
        "pptx": "presentation",
        "ppt": "presentation",
        "png": "image",
        "jpg": "image",
        "jpeg": "image",
        "svg": "image",
    }
    role = "report" if kind == "report" else "output"
    if kind == "html_artifact":
        primary = directory_artifact(
            path.parent,
            entrypoint=path.name,
            group_key=group_key,
            tool_name=generator or "html_artifact",
            role=role,
            label=title or logical_key,
        )
    else:
        primary = primary_file(
            path,
            group_key=group_key,
            tool_name=generator or "document",
            role=role,
            renderer=renderer_by_format.get(fmt, "file"),
            capabilities=("preview", "download", "edit")
            if fmt in {"docx", "xlsx", "pptx"}
            else ("preview", "download"),
            label=title or path.name,
            metadata={"artifact_kind": kind},
        )
    primary["resource_key"] = fmt
    resources = [primary]

    preview_path = None
    if isinstance(preview, dict):
        for key in (
            "pdf_path",
            "html_path",
            "markdown_path",
            "svg_path",
            "file_path",
            "local_path",
        ):
            value = preview.get(key)
            if isinstance(value, str) and value:
                candidate = Path(value).expanduser().resolve()
                if candidate.is_file() and candidate != path:
                    preview_path = candidate
                    break
    if preview_path is None and kind == "report" and fmt == "qmd":
        rendered_html = path.with_name("report.html")
        if rendered_html.is_file():
            preview_path = rendered_html
    if preview_path is not None:
        preview_fmt = preview_path.suffix.lower().lstrip(".") or "file"
        derivative = derivative_file(
            preview_path,
            group_key=group_key,
            parent_key=primary["resource_key"],
            tool_name=generator or "document",
            relation="preview",
            role=role,
            renderer=renderer_by_format.get(preview_fmt, "file"),
        )
        derivative["resource_key"] = preview_fmt
        resources.append(derivative)
    result_data["resources"] = resources
    return result_data


def build_artifact_resume_context(
    result_data: Dict[str, Any],
    file_path: str | Path,
    *,
    extra_resume: Optional[Dict[str, Any]] = None,
    tool_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Return top-level Agent resume fields for an explicit artifact result."""
    artifact = result_data.get("artifact") if isinstance(result_data.get("artifact"), dict) else {}
    resume = {
        "artifact_path": str(Path(file_path)),
        "artifact_format": artifact.get("format") or Path(file_path).suffix.lstrip(".") or None,
        "tool_hint": tool_hint or f"Use present_artifact(file_path='{Path(file_path)}') to preview this artifact.",
    }
    if extra_resume:
        resume.update({key: value for key, value in extra_resume.items() if value is not None})
    return {
        "resources": result_data.get("resources", []),
        "llm_resume": resume,
    }
