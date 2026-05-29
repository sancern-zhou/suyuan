from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SlideType = Literal[
    "cover",
    "toc",
    "section",
    "executive_summary",
    "metric_dashboard",
    "map_insight",
    "chart_insight",
    "city_ranking",
    "pollution_process",
    "forecast_warning",
    "evidence_table",
    "conclusion_actions",
]


class MetricSpec(BaseModel):
    label: str
    value: Any
    unit: Optional[str] = None
    delta: Optional[str] = None
    tone: Optional[str] = None


class VisualSpec(BaseModel):
    kind: Literal["map", "chart", "image", "icon_group", "timeline", "table"]
    asset: Optional[str] = None
    caption: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class DeckSlideSpec(BaseModel):
    id: str
    type: SlideType
    title: str
    subtitle: Optional[str] = None
    message: Optional[str] = None
    visual: Optional[VisualSpec] = None
    metrics: List[MetricSpec] = Field(default_factory=list)
    insights: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    table: Optional[Any] = None
    chart: Optional[Dict[str, Any]] = None
    items: List[Any] = Field(default_factory=list)
    risk_level: Optional[str] = None
    notes: Optional[str] = None


class DeckSpec(BaseModel):
    version: Literal["suyuan.deck.v1"]
    title: str
    audience: str = "management"
    tone: str = "professional, evidence-led, concise"
    theme: Optional[Dict[str, Any]] = None
    narrative: List[Dict[str, Any]] = Field(default_factory=list)
    slides: List[DeckSlideSpec]
