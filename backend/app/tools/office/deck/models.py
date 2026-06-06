from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


DeckType = Literal[
    "business_report",
    "implementation_proposal",
    "data_analysis_report",
    "project_plan",
    "technical_solution",
    "government_briefing",
    "product_pitch",
    "research_summary",
]


SlideArchetype = Literal[
    "cover",
    "agenda",
    "section_divider",
    "executive_summary",
    "key_message",
    "three_column_points",
    "metric_dashboard",
    "comparison_matrix",
    "before_after",
    "timeline",
    "roadmap",
    "gantt_plan",
    "process_flow",
    "architecture_overview",
    "data_flow",
    "map_story",
    "chart_story",
    "evidence_table",
    "risk_matrix",
    "budget_breakdown",
    "implementation_plan",
    "responsibility_matrix",
    "closing_actions",
    "appendix",
]


class MetricSpec(BaseModel):
    label: str
    value: Any
    unit: Optional[str] = None
    delta: Optional[str] = None
    tone: Optional[str] = None


class ContentItemSpec(BaseModel):
    title: str
    body: Optional[str] = None
    detail: Optional[str] = None
    label: Optional[str] = None
    value: Optional[Any] = None
    tone: Optional[str] = None
    items: List["ContentItemSpec"] = Field(default_factory=list)


class ContentSpec(BaseModel):
    items: List[ContentItemSpec] = Field(default_factory=list)
    columns: List[ContentItemSpec] = Field(default_factory=list)
    steps: List[ContentItemSpec] = Field(default_factory=list)
    bullets: List[str] = Field(default_factory=list)


class VisualSpec(BaseModel):
    kind: Literal[
        "image",
        "map",
        "chart",
        "table",
        "timeline",
        "roadmap",
        "process",
        "architecture",
        "data_flow",
        "matrix",
    ]
    asset: Optional[str] = None
    caption: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class DeckSlideSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    archetype: SlideArchetype
    title: str
    subtitle: Optional[str] = None
    message: Optional[str] = None
    content: ContentSpec = Field(default_factory=ContentSpec)
    visual: Optional[VisualSpec] = None
    metrics: List[MetricSpec] = Field(default_factory=list)
    chart: Optional[Dict[str, Any]] = None
    table: Optional[Any] = None
    notes: Optional[str] = None


class DeckSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["suyuan.deck.v2"]
    deck_type: DeckType
    title: str
    audience: str = "management"
    tone: str = "professional, evidence-led, concise"
    theme: Optional[Dict[str, Any]] = None
    narrative: List[Dict[str, Any]] = Field(default_factory=list)
    slides: List[DeckSlideSpec]
