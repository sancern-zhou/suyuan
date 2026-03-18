from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, List

from pydantic import BaseModel, Field


class PMFSourceContribution(BaseModel):
    source_name: str
    contribution_pct: float = Field(..., ge=0.0)
    concentration: float = Field(..., ge=0.0)
    confidence: Optional[str] = None


class PMFTimeSeriesPoint(BaseModel):
    time: datetime
    source_values: Dict[str, float]


class PMFResult(BaseModel):
    pollutant: str
    station_name: str
    station_code: Optional[str] = None
    schema_version: str = "pmf.v1"
    sources: List[PMFSourceContribution]
    timeseries: List[PMFTimeSeriesPoint]
    performance: Dict[str, float]
    quality_report: Optional[Dict[str, str]] = None
    metadata: Optional[Dict[str, str]] = None
