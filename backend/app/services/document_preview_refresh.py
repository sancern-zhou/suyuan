"""Refresh frontend document previews after managed artifact file edits."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from app.services.html_artifact_service import html_artifact_service
from app.services.report_preview_refresh import refresh_report_preview_for_qmd_path

logger = structlog.get_logger()


def refresh_html_artifact_preview_for_index_path(path: str | Path) -> Optional[Dict[str, Any]]:
    """Return fresh html_preview if path is a managed HTML artifact index."""
    artifact_id = html_artifact_service.get_artifact_id_from_index_path(path)
    if not artifact_id:
        return None

    index_path = Path(path).expanduser().resolve()
    try:
        meta = html_artifact_service.record_update(artifact_id, source="file_edit")
        preview = html_artifact_service.build_html_preview(artifact_id)
        logger.info(
            "html_artifact_preview_refreshed",
            artifact_id=artifact_id,
            index_path=str(index_path),
            preview_version=preview.get("preview_version"),
            version=meta.get("version"),
        )
        return {
            "artifact_id": artifact_id,
            "file_path": str(index_path),
            "file_type": "html_artifact",
            "html_preview": preview,
            "version": meta.get("version"),
            "html_artifact_preview_refresh": {
                "success": True,
                "artifact_id": artifact_id,
                "preview_version": preview.get("preview_version"),
                "version": meta.get("version"),
            },
        }
    except Exception as exc:
        logger.warning(
            "html_artifact_preview_refresh_failed",
            artifact_id=artifact_id,
            index_path=str(index_path),
            error=str(exc),
        )
        return {
            "artifact_id": artifact_id,
            "file_path": str(index_path),
            "file_type": "html_artifact",
            "html_artifact_preview_refresh": {
                "success": False,
                "artifact_id": artifact_id,
                "error": str(exc),
            },
            "render_error": str(exc),
        }


def refresh_preview_for_managed_document_path(path: str | Path) -> Optional[Dict[str, Any]]:
    """Refresh preview metadata for managed report/html artifact files."""
    return (
        refresh_report_preview_for_qmd_path(path)
        or refresh_html_artifact_preview_for_index_path(path)
    )
