"""
Quarto report preview, asset, download, and share routes.
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
import yaml

from app.services.quarto_report_renderer import ReportRenderError, quarto_report_renderer
from app.services.report_preview_refresh import build_html_preview, record_report_update
from app.agent.resources.actions import attach_rendered_file
from app.agent.resources.resource_service import SessionResourceService
from app.auth.share_access import (
    SHARE_GRANT_COOKIE,
    external_api_path,
    get_share_access_service,
)
from config.settings import settings


router = APIRouter(prefix="/api/reports", tags=["reports"])

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(errors="ignore")


def _sanitize_download_stem(value: str, fallback: str) -> str:
    stem = INVALID_FILENAME_CHARS.sub("_", value or "").strip().strip(".")
    stem = re.sub(r"\s+", " ", stem)
    return stem[:120] or fallback


def _extract_qmd_title(qmd_path: Path) -> str | None:
    if not qmd_path.exists():
        return None

    content = _read_text(qmd_path)
    normalized_content = content.lstrip("\ufeff\r\n\t ")
    body = normalized_content

    if normalized_content.startswith("---"):
        end_index = normalized_content.find("\n---", 3)
        if end_index >= 0:
            front_matter = normalized_content[3:end_index]
            body = normalized_content[end_index + 4 :]
            try:
                metadata = yaml.safe_load(front_matter) or {}
            except yaml.YAMLError:
                metadata = {}
            if isinstance(metadata, dict):
                title = metadata.get("title")
                if isinstance(title, str) and title.strip():
                    return title.strip()

    for line in body.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()

    return None


def _report_download_filename(qmd_path: Path, stored_filename: str, report_id: str) -> str:
    extension = Path(stored_filename).suffix
    if stored_filename == "report.qmd":
        title = _extract_qmd_title(qmd_path)
    elif stored_filename == "report.docx":
        title = _extract_qmd_title(qmd_path)
    else:
        title = None

    stem = _sanitize_download_stem(title or report_id, Path(stored_filename).stem)
    return f"{stem}{extension}"


def _content_disposition(disposition: str, filename: str) -> str:
    safe_name = Path(filename).name or "download"
    ascii_fallback = "".join(
        ch if 32 <= ord(ch) < 127 and ch not in {'"', "\\", ";"} else "_"
        for ch in safe_name
    ).strip(" .")
    if not ascii_fallback:
        ascii_fallback = f"download{Path(safe_name).suffix}"
    elif ascii_fallback.startswith("."):
        ascii_fallback = f"download{ascii_fallback}"
    encoded_name = quote(safe_name.encode("utf-8"))
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_name}"


def _refresh_report_html_if_stale(report_id: str, html_path: Path) -> Path:
    qmd_path = quarto_report_renderer.get_qmd_path(report_id)
    html_missing = not html_path.exists()
    html_stale = (
        not html_missing
        and qmd_path.exists()
        and qmd_path.stat().st_mtime_ns > html_path.stat().st_mtime_ns
    )
    if not html_missing and not html_stale:
        return html_path

    refreshed_html_path = quarto_report_renderer.render_preview_html(report_id)
    record_report_update(report_id, source="api_html_auto_refresh", html_path=refreshed_html_path)
    return refreshed_html_path


@router.post("/{report_id}/render/html")
async def render_report_html(
    report_id: str, session_id: str, parent_resource_id: str
):
    try:
        html_path = quarto_report_renderer.render_preview_html(report_id)
        record_report_update(report_id, source="api_render_html", html_path=html_path)
        return await attach_rendered_file(
            SessionResourceService.database(),
            session_id=session_id,
            run_id=f"render-report-html:{report_id}",
            group_key=f"report:{report_id}",
            parent_resource_id=parent_resource_id,
            path=html_path,
            relation="preview",
            renderer="html",
            tool_name="render_report_html",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ReportRenderError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{report_id}/render/docx")
async def render_report_docx(
    report_id: str, session_id: str, parent_resource_id: str
):
    try:
        docx_path = quarto_report_renderer.render_docx(report_id)
        return await attach_rendered_file(
            SessionResourceService.database(),
            session_id=session_id,
            run_id=f"render-report-docx:{report_id}",
            group_key=f"report:{report_id}",
            parent_resource_id=parent_resource_id,
            path=docx_path,
            relation="rendition",
            renderer="file",
            tool_name="render_report_docx",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ReportRenderError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{report_id}/html")
async def get_report_html(report_id: str):
    try:
        report_dir = quarto_report_renderer.get_report_dir(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    html_path = report_dir / "report.html"
    try:
        html_path = _refresh_report_html_if_stale(report_id, html_path)
    except FileNotFoundError as exc:
        if not html_path.exists():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ReportRenderError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="report.html not found")
    return FileResponse(
        path=str(html_path),
        media_type="text/html",
        filename="report.html",
        headers={"Content-Disposition": "inline; filename=report.html"},
    )


@router.get("/{report_id}/assets/{asset_path:path}")
async def get_report_asset(report_id: str, asset_path: str):
    try:
        report_dir = quarto_report_renderer.get_report_dir(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assets_dir = (report_dir / "assets").resolve()
    file_path = (assets_dir / asset_path).resolve()
    try:
        file_path.relative_to(assets_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return FileResponse(path=str(file_path), media_type=media_type)


@router.get("/{report_id}/report_files/{file_path:path}")
async def get_report_generated_file(report_id: str, file_path: str):
    """Serve Quarto-generated files (CSS/JS libs) from report_files/ directory."""
    try:
        report_dir = quarto_report_renderer.get_report_dir(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    report_files_dir = (report_dir / "report_files").resolve()
    target_path = (report_files_dir / file_path).resolve()
    try:
        target_path.relative_to(report_files_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = mimetypes.guess_type(str(target_path))[0] or "application/octet-stream"
    return FileResponse(path=str(target_path), media_type=media_type)


@router.get("/{report_id}/download/{format_name}")
async def download_report(report_id: str, format_name: str):
    formats = {
        "qmd": ("report.qmd", "text/markdown"),
        "docx": (
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    }
    if format_name not in formats:
        raise HTTPException(status_code=400, detail="Unsupported report format")
    stored_filename, media_type = formats[format_name]
    try:
        report_dir = quarto_report_renderer.get_report_dir(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        qmd_path = quarto_report_renderer.get_qmd_path(report_id)
    except FileNotFoundError as exc:
        if format_name == "qmd":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        qmd_path = report_dir / "report.qmd"
    file_path = qmd_path if format_name == "qmd" else report_dir / stored_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"{stored_filename} not found")
    download_filename = _report_download_filename(qmd_path, stored_filename, report_id)
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=download_filename,
        headers={"Content-Disposition": _content_disposition("attachment", download_filename)},
    )


@router.post("/{report_id}/share/html")
async def create_share_html(report_id: str):
    try:
        result = quarto_report_renderer.render_share_html(report_id)
        for key in ("share_url", "html_url"):
            if result.get(key):
                result[key] = external_api_path(result[key])
        return {"success": True, **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ReportRenderError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{report_id}/share/html")
async def get_report_share_html(report_id: str):
    try:
        report_dir = quarto_report_renderer.get_report_dir(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    html_path = report_dir / "report_standalone.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="report_standalone.html not found")
    return FileResponse(
        path=str(html_path),
        media_type="text/html",
        filename="report_standalone.html",
        headers={"Content-Disposition": "inline; filename=report_standalone.html"},
    )


@router.get("/share/{token}")
async def get_shared_report(token: str):
    html_path = quarto_report_renderer.find_shared_html(token)
    if not html_path:
        raise HTTPException(status_code=404, detail="Share token not found")
    report_id = Path(html_path).parent.name
    resource_base = external_api_path(f"/api/reports/{report_id}/")
    html = Path(html_path).read_text(encoding="utf-8", errors="replace")
    html = re.sub(
        r'<base\s+href="[^"]*"\s*/?>',
        f'<base href="{resource_base}">',
        html,
        count=1,
    )
    if "<base " not in html:
        html = html.replace("<head>", f'<head><base href="{resource_base}">', 1)
    response = HTMLResponse(content=html)
    response.set_cookie(
        SHARE_GRANT_COOKIE,
        get_share_access_service().issue("report", report_id),
        max_age=settings.auth_share_grant_ttl_seconds,
        httponly=True,
        secure=settings.environment.strip().lower() == "production",
        samesite="lax",
        path=resource_base,
    )
    return response
