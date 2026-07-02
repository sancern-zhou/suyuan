from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas.query_dashboard import DashboardOverviewResponse
from app.services.data_registry import data_registry
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


@router.get("/guangdong-overview", response_model=DashboardOverviewResponse)
def get_guangdong_overview(
    include: str | None = Query(default=None),
    service: QueryDashboardService = Depends(get_query_dashboard_service),
) -> DashboardOverviewResponse:
    return service.build_guangdong_overview(include=_parse_include(include))


@router.get("/map-data/{data_id:path}")
def get_map_data_features(
    data_id: str,
    lon: str | None = Query(default=None, description="经度字段名；GeoJSON geometry 资产可省略"),
    lat: str | None = Query(default=None, description="纬度字段名；GeoJSON geometry 资产可省略"),
    view: str | None = Query(default=None, description="可选 DataRegistry view 名称"),
    limit: int = Query(default=1000, ge=1, le=5000),
) -> dict:
    try:
        dataset = data_registry.load_dataset(data_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"data_id not found: {data_id}") from exc

    features = dataset_to_geojson_features(
        dataset,
        longitude_field=lon or "longitude",
        latitude_field=lat or "latitude",
        view=view,
        limit=limit,
    )
    return {
        "type": "FeatureCollection",
        "data_id": data_id,
        "features": features,
    }


@router.post("/map-program-receipts")
def record_map_program_receipt(request: MapProgramReceiptRequest) -> dict[str, Any]:
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
def get_map_program_receipt(session_id: str, program_id: str) -> dict[str, Any]:
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
def get_map_program_status(session_id: str, program_id: str) -> dict[str, Any]:
    program = map_program_receipt_store.get_program_status(session_id, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="map program status not found")

    return {
        "success": True,
        "session_id": session_id,
        "program_id": program_id,
        "program": program,
    }
