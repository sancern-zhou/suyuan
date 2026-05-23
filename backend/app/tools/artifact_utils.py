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
    """Attach artifact and artifacts fields while preserving legacy preview keys."""
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
    result_data["artifacts"] = [artifact]
    return result_data
