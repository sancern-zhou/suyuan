"""Report library catalog and protected report-package delivery."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.services.report_catalog import list_report_packages
from app.utils.path_config import get_reports_dir

router = APIRouter(prefix="/api/reports", tags=["report-library"])


def _report_root() -> Path:
    return get_reports_dir().expanduser().resolve()


def _read_meta(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _format_file(report_id: str, fmt: str, path: Path) -> dict:
    return {
        "format": fmt,
        "name": path.name,
        "available": path.is_file(),
        "url": f"/api/reports/{report_id}/files/{fmt}",
    }


def _report_dto(meta: dict, report_dir: Path) -> dict:
    report_id = str(meta.get("report_id") or report_dir.name)
    files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
    formats = []
    for fmt in ("html", "docx", "qmd", "pdf"):
        raw = files.get(fmt)
        path = Path(str(raw)).expanduser() if raw else report_dir / f"report.{fmt}"
        if path.is_file() or fmt in files:
            formats.append(_format_file(report_id, fmt, path))
    created = meta.get("created_at") or meta.get("updated_at")
    return {
        "report_id": report_id,
        "name": str(meta.get("title") or report_id),
        "report_type": str(meta.get("report_type") or meta.get("source") or "其他"),
        "created_at": created,
        "updated_at": meta.get("updated_at") or created,
        "validation": meta.get("validation") or {},
        "files": formats,
    }


@router.get("")
async def list_reports(
    report_type: str | None = None,
    format: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    user: CurrentUser = Depends(require_current_user),
):
    """List published report packages for the active deployment."""
    del user
    start = datetime.fromisoformat(start_time) if start_time else None
    end = datetime.fromisoformat(end_time) if end_time else None
    indexed = await list_report_packages(report_type=report_type, format_name=format, start_time=start_time, end_time=end_time)
    reports = []
    for entry in indexed:
        files = entry.files if isinstance(entry.files, dict) else {}
        reports.append({
            "report_id": entry.report_id,
            "name": entry.title,
            "report_type": entry.report_type,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
            "status": entry.status,
            "version": entry.version,
            "files": [_format_file(entry.report_id, fmt, Path(str(path))) for fmt, path in files.items() if fmt in {"html", "docx", "qmd", "pdf"}],
        })
    return {"reports": reports, "total": len(reports)}


@router.get("/{report_id}/files/{format}")
async def get_report_file(
    report_id: str,
    format: str,
    user: CurrentUser = Depends(require_current_user),
):
    """Serve a report rendition after verifying it belongs to a published package."""
    del user
    if format not in {"html", "docx", "qmd", "pdf"} or any(part in report_id for part in ("/", "\\", "..")):
        raise HTTPException(status_code=404, detail="report_file_not_found")
    report_dir = (_report_root() / report_id).resolve()
    if _report_root() not in report_dir.parents:
        raise HTTPException(status_code=404, detail="report_file_not_found")
    meta = _read_meta(report_dir / "meta.json")
    if not meta:
        raise HTTPException(status_code=404, detail="report_not_found")
    files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
    candidate = Path(str(files.get(format))).expanduser().resolve() if files.get(format) else (report_dir / f"report.{format}").resolve()
    if report_dir not in candidate.parents or not candidate.is_file():
        raise HTTPException(status_code=404, detail="report_file_not_found")
    media = {"html": "text/html", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "qmd": "text/markdown", "pdf": "application/pdf"}[format]
    return FileResponse(candidate, media_type=media, filename=candidate.name)
