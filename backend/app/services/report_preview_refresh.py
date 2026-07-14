"""Helpers for refreshing report previews after report.qmd file edits."""
from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from app.auth.share_access import external_api_path

from app.services.quarto_report_renderer import quarto_report_renderer

logger = structlog.get_logger()


def _now_iso() -> str:
    return datetime.now().isoformat()


def _file_fingerprint(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "preview_version": f"{stat.st_mtime_ns}-{stat.st_size}",
    }


def get_report_id_from_qmd_path(path: str | Path) -> Optional[str]:
    """Return report_id when path is reports/{report_id}/report.qmd or source_qmd."""
    try:
        qmd_path = Path(path).expanduser().resolve()
        reports_root = quarto_report_renderer.report_root.resolve()
        relative = qmd_path.relative_to(reports_root)
    except (OSError, ValueError):
        relative = None

    if relative and len(relative.parts) == 2 and relative.parts[1] == "report.qmd":
        return relative.parts[0]

    for meta_path in reports_root.glob("*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
        raw_source_qmd = files.get("source_qmd") or meta.get("source_qmd")
        if not raw_source_qmd:
            continue
        try:
            source_qmd = Path(raw_source_qmd).expanduser().resolve()
        except OSError:
            continue
        if source_qmd == qmd_path:
            return meta_path.parent.name
    return None


def build_html_preview(report_id: str, html_path: Path) -> Dict[str, Any]:
    preview_version = (
        _file_fingerprint(html_path)["preview_version"]
        if html_path.exists()
        else datetime.now().strftime("%Y%m%d%H%M%S%f")
    )
    return {
        "html_id": report_id,
        "html_url": external_api_path(f"/api/reports/{report_id}/html"),
        "file_type": "report",
        "schema_version": "report_package.v1",
        "preview_version": preview_version,
    }


def read_report_meta(report_id: str) -> Dict[str, Any]:
    meta_path = quarto_report_renderer.get_report_dir(report_id) / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("report_meta_read_failed", report_id=report_id, error=str(exc))
        return {}


def write_report_meta(report_id: str, meta: Dict[str, Any]) -> None:
    meta_path = quarto_report_renderer.get_report_dir(report_id) / "meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _source_qmd_report_id(qmd_path: Path) -> str:
    digest = hashlib.sha1(str(qmd_path).encode("utf-8")).hexdigest()[:12]
    return f"source_qmd_{digest}"


def record_report_update(
    report_id: str,
    *,
    source: str = "file_edit",
    html_path: Optional[Path] = None,
    increment_version: bool = True,
) -> Dict[str, Any]:
    """Update ReportPackage metadata after creation, render, or managed edits."""
    report_dir = quarto_report_renderer.get_report_dir(report_id)
    meta = read_report_meta(report_id)
    try:
        qmd_path = quarto_report_renderer.get_qmd_path(report_id)
    except FileNotFoundError:
        qmd_path = report_dir / "report.qmd"
    now = _now_iso()
    previous_version = int(meta.get("version") or 0)
    next_version = previous_version + 1 if increment_version else max(previous_version, 1)
    history = list(meta.get("history") or [])
    event: Dict[str, Any] = {
        "version": next_version,
        "updated_at": now,
        "source": source,
    }
    if qmd_path.exists():
        event["qmd_size"] = qmd_path.stat().st_size
    if html_path and html_path.exists():
        fingerprint = _file_fingerprint(html_path)
        event["preview_version"] = fingerprint["preview_version"]
        event["html_size"] = fingerprint["size"]
        meta["preview_version"] = fingerprint["preview_version"]

    files = dict(meta.get("files") or {})
    files.update(
        {
            "qmd": str(report_dir / "report.qmd"),
            "html": str(report_dir / "report.html"),
            "docx": str(report_dir / "report.docx"),
        }
    )
    if qmd_path != (report_dir / "report.qmd").resolve():
        files["source_qmd"] = str(qmd_path)
    else:
        files.pop("source_qmd", None)

    history.append(event)
    meta.update(
        {
            "report_id": report_id,
            "updated_at": now,
            "version": next_version,
            "files": files,
            "download_urls": {
                "qmd": external_api_path(f"/api/reports/{report_id}/download/qmd"),
                "docx": external_api_path(f"/api/reports/{report_id}/download/docx"),
            },
            "history": history[-20:],
        }
    )
    meta.setdefault("created_at", now)
    meta.setdefault("source", source)
    write_report_meta(report_id, meta)
    return meta


def refresh_report_preview_for_qmd_path(path: str | Path) -> Optional[Dict[str, Any]]:
    """Render HTML preview if path is a standard report package qmd.

    Returns None for non-report paths. Rendering errors are returned as data so
    file editing remains successful while the Agent/frontend can surface the
    preview refresh failure.
    """
    report_id = get_report_id_from_qmd_path(path)
    if not report_id:
        return None

    qmd_path = Path(path).expanduser().resolve()
    try:
        html_path = quarto_report_renderer.render_preview_html(report_id)
        preview = build_html_preview(report_id, html_path)
        meta = record_report_update(report_id, source="file_edit", html_path=html_path)
        logger.info(
            "report_qmd_preview_refreshed",
            report_id=report_id,
            qmd_path=str(qmd_path),
            html_path=str(html_path),
            preview_version=preview.get("preview_version"),
            version=meta.get("version"),
        )
        return {
            "report_id": report_id,
            "file_path": str(qmd_path),
            "file_type": "report",
            "html_preview": preview,
            "version": meta.get("version"),
            "report_preview_refresh": {
                "success": True,
                "report_id": report_id,
                "html_path": str(html_path),
                "preview_version": preview.get("preview_version"),
                "version": meta.get("version"),
            },
        }
    except Exception as exc:
        logger.warning(
            "report_qmd_preview_refresh_failed",
            report_id=report_id,
            qmd_path=str(qmd_path),
            error=str(exc),
        )
        data: Dict[str, Any] = {
            "report_id": report_id,
            "file_path": str(qmd_path),
            "file_type": "report",
            "report_preview_refresh": {
                "success": False,
                "report_id": report_id,
                "error": str(exc),
            },
            "render_error": str(exc),
        }
        try:
            data["markdown_preview"] = {
                "content": qmd_path.read_text(encoding="utf-8", errors="replace"),
                "file_type": "report",
                "schema_version": "report_package.v1",
            }
        except Exception:
            pass
        return data


def create_report_preview_for_source_qmd_path(path: str | Path) -> Dict[str, Any]:
    """Create/update a transient report preview package for an arbitrary source qmd."""
    qmd_path = Path(path).expanduser().resolve()
    report_id = _source_qmd_report_id(qmd_path)
    report_dir = quarto_report_renderer.get_report_dir(report_id)
    now = _now_iso()
    existing_meta = read_report_meta(report_id)
    meta = {
        **existing_meta,
        "report_id": report_id,
        "title": qmd_path.stem,
        "created_at": existing_meta.get("created_at") or now,
        "updated_at": now,
        "source": "present_artifact_source_qmd",
        "files": {
            "qmd": str(report_dir / "report.qmd"),
            "source_qmd": str(qmd_path),
            "html": str(report_dir / "report.html"),
            "docx": str(report_dir / "report.docx"),
        },
        "download_urls": {
            "qmd": external_api_path(f"/api/reports/{report_id}/download/qmd"),
            "docx": external_api_path(f"/api/reports/{report_id}/download/docx"),
        },
    }
    write_report_meta(report_id, meta)

    try:
        html_path = quarto_report_renderer.render_preview_html(report_id)
        preview = build_html_preview(report_id, html_path)
        meta = record_report_update(
            report_id,
            source="present_artifact_source_qmd_render",
            html_path=html_path,
        )
        logger.info(
            "source_qmd_preview_created",
            report_id=report_id,
            qmd_path=str(qmd_path),
            html_path=str(html_path),
            preview_version=preview.get("preview_version"),
        )
        return {
            "report_id": report_id,
            "file_path": str(qmd_path),
            "file_name": qmd_path.name,
            "file_type": "report",
            "html_preview": preview,
            "version": meta.get("version"),
            "report_preview_refresh": {
                "success": True,
                "report_id": report_id,
                "html_path": str(html_path),
                "preview_version": preview.get("preview_version"),
                "version": meta.get("version"),
            },
        }
    except Exception as exc:
        logger.warning(
            "source_qmd_preview_create_failed",
            report_id=report_id,
            qmd_path=str(qmd_path),
            error=str(exc),
        )
        return {
            "report_id": report_id,
            "file_path": str(qmd_path),
            "file_name": qmd_path.name,
            "file_type": "report",
            "render_error": str(exc),
            "report_preview_refresh": {
                "success": False,
                "report_id": report_id,
                "error": str(exc),
            },
        }
