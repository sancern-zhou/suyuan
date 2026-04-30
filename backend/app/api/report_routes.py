"""
Quarto report preview, asset, download, and share routes.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.quarto_report_renderer import ReportRenderError, quarto_report_renderer


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/{report_id}/render/html")
async def render_report_html(report_id: str):
    try:
        html_path = quarto_report_renderer.render_preview_html(report_id)
        return {
            "success": True,
            "report_id": report_id,
            "file_path": str(quarto_report_renderer.get_report_dir(report_id) / "report.qmd"),
            "html_preview": {
                "html_id": report_id,
                "html_url": f"/api/reports/{report_id}/html",
                "file_type": "report",
            },
            "path": str(html_path),
            "metadata": {"generator": "quarto_report"},
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ReportRenderError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{report_id}/render/docx")
async def render_report_docx(report_id: str):
    try:
        docx_path = quarto_report_renderer.render_docx(report_id)
        return {
            "success": True,
            "report_id": report_id,
            "download_url": f"/api/reports/{report_id}/download/docx",
            "path": str(docx_path),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ReportRenderError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{report_id}/render/pptx")
async def render_report_pptx(report_id: str):
    try:
        pptx_path = quarto_report_renderer.render_pptx(report_id)
        return {
            "success": True,
            "report_id": report_id,
            "download_url": f"/api/reports/{report_id}/download/pptx",
            "path": str(pptx_path),
        }
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


@router.get("/{report_id}/download/{format_name}")
async def download_report(report_id: str, format_name: str):
    formats = {
        "html": ("report.html", "text/html"),
        "docx": (
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        "pptx": (
            "report.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
    }
    if format_name not in formats:
        raise HTTPException(status_code=400, detail="Unsupported report format")
    filename, media_type = formats[format_name]
    try:
        report_dir = quarto_report_renderer.get_report_dir(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    file_path = report_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"{filename} not found")
    return FileResponse(path=str(file_path), media_type=media_type, filename=filename)


@router.post("/{report_id}/share/html")
async def create_share_html(report_id: str):
    try:
        return {"success": True, **quarto_report_renderer.render_share_html(report_id)}
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
    return FileResponse(
        path=str(html_path),
        media_type="text/html",
        filename=Path(html_path).name,
        headers={"Content-Disposition": "inline; filename=report.html"},
    )
