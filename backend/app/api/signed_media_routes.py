"""Routes for expiring signed media access."""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.services.signed_media import get_signed_media_service

router = APIRouter()


@router.get("/signed-media/{media_path:path}")
async def get_signed_media(
    media_path: str,
    expires: int = Query(...),
    signature: str = Query(...),
) -> FileResponse:
    try:
        path = get_signed_media_service().resolve(media_path, expires=expires, signature=signature)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Media file not found") from exc
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=403, detail="Invalid or expired media URL") from exc

    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path=str(path),
        media_type=media_type or "application/octet-stream",
        filename=path.name,
    )
