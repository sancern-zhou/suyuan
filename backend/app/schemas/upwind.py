"""Schemas shared by upwind enterprise analysis clients and tools."""

from datetime import datetime

from pydantic import BaseModel


class WindData(BaseModel):
    """Single wind observation used by the upwind analysis API."""

    time: datetime | str
    wd_deg: float
    ws_ms: float
