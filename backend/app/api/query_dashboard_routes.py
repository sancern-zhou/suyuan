from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.query_dashboard import DashboardOverviewResponse
from app.services.query_dashboard_service import QueryDashboardService

router = APIRouter(prefix="/query-dashboard", tags=["query-dashboard"])


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
