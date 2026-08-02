"""Helpers for tool-returned deliverable artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.tools.resource_declarations import (
    derivative_file,
    directory_artifact,
    primary_file,
)


def preview_output_path(*descriptors: Any) -> Path | None:
    """Resolve a renderer output descriptor to an existing local file."""
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            continue
        for key in ("pdf_path", "html_path", "markdown_path", "svg_path", "file_path", "local_path"):
            value = descriptor.get(key)
            if not isinstance(value, str) or not value:
                continue
            candidate = Path(value).expanduser().resolve()
            if candidate.is_file():
                return candidate
    return None

def attach_document_resources(
    result_data: Dict[str, Any],
    file_path: str | Path,
    *,
    kind: str = "office",
    format: Optional[str] = None,
    title: Optional[str] = None,
    preview_path: str | Path | None = None,
    generator: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attach a primary file and optional preview directly as resources."""
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
    capabilities = (
        ("preview", "download", "render")
        if kind == "report" and fmt == "qmd"
        else ("preview", "download", "edit")
        if fmt in {"docx", "xlsx", "pptx"}
        else ("preview", "download")
    )
    primary = primary_file(
        path,
        group_key=group_key,
        tool_name=generator or "document",
        role=role,
        renderer=renderer_by_format.get(fmt, "file"),
        capabilities=capabilities,
        label=title or path.name,
        metadata={"artifact_kind": kind},
    )
    primary["resource_key"] = fmt
    resources = [primary]

    resolved_preview = None
    if preview_path:
        candidate = Path(preview_path).expanduser().resolve()
        if candidate.is_file() and candidate != path:
            resolved_preview = candidate
    if kind == "html_artifact" and fmt == "html":
        resolved_preview = path
    elif resolved_preview is None and kind == "report" and fmt == "qmd":
        rendered_html = path.with_name("report.html")
        if rendered_html.is_file():
            resolved_preview = rendered_html
    if resolved_preview is not None:
        preview_fmt = resolved_preview.suffix.lower().lstrip(".") or "file"
        if (
            (kind == "report" and fmt == "qmd" and preview_fmt == "html")
            or (kind == "html_artifact" and preview_fmt == "html")
        ):
            derivative = directory_artifact(
                resolved_preview.parent,
                entrypoint=resolved_preview.name,
                group_key=group_key,
                tool_name=generator or "document",
                role=role,
                renderer="html",
                capabilities=("preview",),
                label=resolved_preview.name,
            )
            derivative.update(
                resource_key="html",
                parent_key=primary["resource_key"],
                relation="preview",
            )
        else:
            derivative = derivative_file(
                resolved_preview,
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
    path = Path(file_path)
    resume = {
        "artifact_path": str(path),
        "artifact_format": path.suffix.lstrip(".") or None,
        "tool_hint": tool_hint or f"Use present_artifact(file_path='{path}') to preview this artifact.",
    }
    if extra_resume:
        resume.update({key: value for key, value in extra_resume.items() if value is not None})
    return {
        "resources": result_data.get("resources", []),
        "llm_resume": resume,
    }
