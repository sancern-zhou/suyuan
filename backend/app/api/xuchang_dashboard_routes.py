"""Project-owned read-only API for the Xuchang big-screen dashboard.

The snapshot is materialized by ``xuchang_screen_snapshot_fetcher`` (worker
process) into the shared data registry; this endpoint only reads the file, so
all uvicorn workers serve byte-identical screens without touching Cube or
SQL Server per request.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.fetchers.xuchang_screen_snapshot import SNAPSHOT_DIR, SNAPSHOT_FILE
from app.utils.path_config import get_data_registry

router = APIRouter(prefix="/api/xuchang-dashboard", tags=["xuchang-dashboard"])

_MEDIA_TYPE = "application/json"


def _snapshot_path() -> Path:
    return get_data_registry() / SNAPSHOT_DIR / SNAPSHOT_FILE


@router.get("/screen-snapshot")
async def get_screen_snapshot(
    request: Request,
    user: CurrentUser = Depends(require_current_user),
) -> Response:
    path = _snapshot_path()
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return Response(
            content='{"detail": "大屏快照尚未生成，请等待快照任务首次运行"}',
            status_code=503,
            media_type=_MEDIA_TYPE,
        )
    etag = '"' + hashlib.sha256(payload).hexdigest()[:32] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(
        content=payload,
        media_type=_MEDIA_TYPE,
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )
