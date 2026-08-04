from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DashboardStatus = Literal["idle", "loading", "success", "partial", "error", "stale"]


class DashboardSource(BaseModel):
    source_id: str
    tool_name: str
    file_path: str | None = None
    file_paths: list[str] = Field(default_factory=list)
    query_params: dict[str, Any] = Field(default_factory=dict)
    record_count: int | None = None
    updated_at: str | None = None
    generated_at: str | None = None
    sample_records: list[dict[str, Any]] = Field(default_factory=list)


class DashboardModule(BaseModel):
    status: DashboardStatus
    summary: dict[str, Any] = Field(default_factory=dict)
    cities: list[dict[str, Any]] = Field(default_factory=list)
    stations: list[dict[str, Any]] = Field(default_factory=list)
    rankings: list[dict[str, Any]] = Field(default_factory=list)
    city_metrics: list[dict[str, Any]] = Field(default_factory=list)
    heat_points: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[DashboardSource] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class DashboardOverviewResponse(BaseModel):
    success: bool = True
    generated_at: str
    region: str = "广东省"
    modules: dict[str, DashboardModule] = Field(default_factory=dict)
    sources: list[DashboardSource] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
