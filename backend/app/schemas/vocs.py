from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field

from .common import Unit


class VOCsSample(BaseModel):
    """Standardized VOCs hourly record."""

    station_code: str = Field(..., alias="stationCode")
    station_name: str = Field(..., alias="stationName")
    timestamp: datetime = Field(..., alias="time")
    unit: Unit = Field(default=Unit.PPB, description="Concentration unit.")
    species: Dict[str, float] = Field(
        ..., description="VOCs species concentration map (Chinese name -> value)."
    )
    qc_flag: Optional[str] = Field(default=None, description="Quality control flag.")
    metadata: Optional[Dict[str, str]] = Field(
        default=None, description="Additional metadata such as instrument, remark."
    )

    class Config:
        populate_by_name = True


class UnifiedVOCsData(BaseModel):
    """Unified VOCs data format for global converter output.

    数据已在DataStandardizer.standardize()中完成标准化（物种聚合到species_data）。
    """
    station_code: str = Field(..., description="Station code (e.g., ZX001)")
    station_name: str = Field(..., description="Station name (e.g., 肇庆莲花山)")
    timestamp: str = Field(
        ...,
        description="Timestamp in YYYY-MM-DD HH:MM:SS format"
    )
    unit: str = Field(
        default="ppb",
        description="Concentration unit (e.g., ppb, ppm, ug/m3)"
    )
    species_data: Dict[str, float] = Field(
        ...,
        description="VOCs species concentration map (Chinese name -> value)"
    )
    qc_flag: Optional[str] = Field(
        default=None,
        description="Quality control flag"
    )
    metadata: Optional[Dict[str, str]] = Field(
        default=None,
        description="Additional metadata such as instrument, remark"
    )

    class Config:
        populate_by_name = True
        use_enum_values = True
