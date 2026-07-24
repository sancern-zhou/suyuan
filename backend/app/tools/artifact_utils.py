"""Helpers for tool-returned deliverable artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

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
    result_data["resources"] = [{
        "kind": "file",
        "logical_key": logical_key,
        "role": "report" if kind == "report" else "output",
        "label": title or Path(file_path).name,
        "locator": {"path": str(Path(file_path).resolve())},
        "presentation_type": "document",
        "presentation": {
            "format": artifact.get("format") or "document",
            "preview": preview or {},
            "editable": bool(artifact.get("preview_panel", False)),
        },
        "metadata": {
            "generator": generator,
            "artifact_kind": kind,
            "mime_type": artifact.get("mime_type"),
        },
    }]
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
