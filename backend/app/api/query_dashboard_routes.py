from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas.query_dashboard import DashboardOverviewResponse
import json

from app.agent.context.data_files import get_data_root, resolve_data_path
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations.repository import ConversationCatalogRepository
from app.services.map_program_receipts import map_program_receipt_store
from app.services.query_dashboard_map_data import dataset_to_geojson_features
from app.services.query_dashboard_service import QueryDashboardService

router = APIRouter(prefix="/query-dashboard", tags=["query-dashboard"])


class MapProgramReceiptRequest(BaseModel):
    session_id: str = Field(min_length=1)
    receipt: dict[str, Any]


def get_query_dashboard_service() -> QueryDashboardService:
    return QueryDashboardService()


def _parse_include(include: str | None) -> list[str] | None:
    if not include:
        return None
    return [item.strip() for item in include.split(",") if item.strip()]


async def _require_session_access(
    session_id: str, user: CurrentUser
) -> None:
    """Fail-closed ownership check for session-scoped data."""
    if user.is_admin:
        return
    record = await ConversationCatalogRepository().get(session_id)
    if record is None or record.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="session not found")


async def _require_data_file_access(path, user: CurrentUser) -> None:
    """Restrict registry session directories to their owners."""
    if user.is_admin:
        return
    try:
        relative = path.relative_to(get_data_root())
    except ValueError:
        raise HTTPException(status_code=404, detail="data file unavailable") from None
    parts = relative.parts
    if len(parts) >= 2 and parts[0] == "sessions":
        session_dir = parts[1]
        if session_dir.startswith("agent_session_"):
            await _require_session_access(session_dir.removeprefix("agent_session_"), user)


@router.get("/guangdong-overview", response_model=DashboardOverviewResponse)
def get_guangdong_overview(
    include: str | None = Query(default=None),
    service: QueryDashboardService = Depends(get_query_dashboard_service),
) -> DashboardOverviewResponse:
    return service.build_guangdong_overview(include=_parse_include(include))


@router.get("/map-data")
async def get_map_data_features(
    file_path: str = Query(description="会话数据文件绝对路径"),
    lon: str | None = Query(default=None, description="经度字段名；GeoJSON geometry 资产可省略"),
    lat: str | None = Query(default=None, description="纬度字段名；GeoJSON geometry 资产可省略"),
    view: str | None = Query(default=None, description="可选 DataRegistry view 名称"),
    limit: int = Query(default=1000, ge=1, le=5000),
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    try:
        path = resolve_data_path(file_path)
    except (ValueError, PermissionError, FileNotFoundError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=404, detail=f"data file unavailable: {file_path}") from exc
    await _require_data_file_access(path, user)
    try:
        with path.open("r", encoding="utf-8") as stream:
            dataset = json.load(stream)
    except (ValueError, PermissionError, FileNotFoundError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=404, detail=f"data file unavailable: {file_path}") from exc

    features = dataset_to_geojson_features(
        dataset,
        longitude_field=lon or "longitude",
        latitude_field=lat or "latitude",
        view=view,
        limit=limit,
    )
    return {
        "type": "FeatureCollection",
        "file_path": file_path,
        "features": features,
    }


@router.post("/map-program-receipts")
async def record_map_program_receipt(
    request: MapProgramReceiptRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    await _require_session_access(request.session_id, user)
    try:
        receipt = map_program_receipt_store.record(request.session_id, request.receipt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "success": True,
        "session_id": request.session_id,
        "program_id": receipt.get("program_id"),
        "receipt": receipt,
    }


@router.get("/map-program-receipts/{session_id}/{program_id}")
async def get_map_program_receipt(
    session_id: str,
    program_id: str,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    await _require_session_access(session_id, user)
    receipt = map_program_receipt_store.get(session_id, program_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="map program receipt not found")

    return {
        "success": True,
        "session_id": session_id,
        "program_id": program_id,
        "receipt": receipt,
    }


@router.get("/map-program-status/{session_id}/{program_id}")
async def get_map_program_status(
    session_id: str,
    program_id: str,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    await _require_session_access(session_id, user)
    program = map_program_receipt_store.get_program_status(session_id, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="map program status not found")

    return {
        "success": True,
        "session_id": session_id,
        "program_id": program_id,
        "program": program,
    }
