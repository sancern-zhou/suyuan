"""HTML presentation artifact preview, download, and share routes."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from app.services.html_artifact_service import html_artifact_service
from app.auth.share_access import (
    SHARE_GRANT_COOKIE,
    external_api_path,
    get_share_access_service,
)
from config.settings import settings


router = APIRouter(prefix="/api/html-artifacts", tags=["html-artifacts"])


@router.get("/{artifact_id}/html")
async def get_html_artifact(artifact_id: str):
    try:
        index_path = html_artifact_service.get_index_path(artifact_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        path=str(index_path),
        media_type="text/html",
        filename="index.html",
        headers={"Content-Disposition": "inline; filename=index.html"},
    )


@router.get("/{artifact_id}/assets/{asset_path:path}")
async def get_html_artifact_asset(artifact_id: str, asset_path: str):
    try:
        artifact_dir = html_artifact_service.get_artifact_dir(artifact_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assets_dir = (artifact_dir / "assets").resolve()
    file_path = (assets_dir / asset_path).resolve()
    try:
        file_path.relative_to(assets_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return FileResponse(path=str(file_path), media_type=media_type, filename=file_path.name)


@router.get("/{artifact_id}/download/html")
async def download_html_artifact(artifact_id: str):
    try:
        index_path = html_artifact_service.get_index_path(artifact_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path=str(index_path), media_type="text/html", filename="index.html")


@router.post("/{artifact_id}/share")
async def share_html_artifact(artifact_id: str):
    try:
        result = html_artifact_service.create_share(artifact_id)
        for key in ("share_url", "html_url"):
            if result.get(key):
                result[key] = external_api_path(result[key])
        return {"success": True, **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/share/{token}")
async def get_shared_html_artifact(token: str):
    index_path = html_artifact_service.find_by_share_token(token)
    if not index_path:
        raise HTTPException(status_code=404, detail="Share token not found")
    artifact_id = Path(index_path).parent.name
    html = Path(index_path).read_text(encoding="utf-8", errors="replace")
    resource_base = external_api_path(f"/api/html-artifacts/{artifact_id}/")
    base = f'<base href="{resource_base}">'
    if "<head>" in html:
        html = html.replace("<head>", f"<head>{base}", 1)
    else:
        html = f"{base}\n{html}"
    response = HTMLResponse(content=html)
    response.set_cookie(
        SHARE_GRANT_COOKIE,
        get_share_access_service().issue("html-artifact", artifact_id),
        max_age=settings.auth_share_grant_ttl_seconds,
        httponly=True,
        secure=settings.environment.strip().lower() == "production",
        samesite="lax",
        path=resource_base,
    )
    return response
