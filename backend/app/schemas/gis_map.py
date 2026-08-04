from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


LayerType = Literal[
    "point",
    "line",
    "polygon",
    "heatmap",
    "raster_tile",
    "vector_tile",
    "trajectory",
    "wind_arrow",
    "label",
    "mask",
]


class MapLayerLifecycle(BaseModel):
    scope: Literal["turn", "conversation", "user", "system"] = "turn"
    group: str = "current_answer"
    visible: bool = True
    replace_policy: Literal["append", "replace_group", "replace_layer"] = "append"
    pinned: bool = False


class MapLayerSpec(BaseModel):
    id: str
    name: str
    layer_type: LayerType
    data: dict[str, Any]
    geometry: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)
    interactions: dict[str, Any] = Field(default_factory=dict)
    lifecycle: MapLayerLifecycle = Field(default_factory=MapLayerLifecycle)

    @model_validator(mode="after")
    def validate_data_reference(self) -> "MapLayerSpec":
        source_type = self.data.get("type")
        if source_type not in {"file_path", "artifact_id", "inline_geojson"}:
            raise ValueError("data.type must be file_path, artifact_id, or inline_geojson")
        if source_type == "file_path" and not self.data.get("path"):
            raise ValueError("data.path is required for file_path references")
        if source_type == "artifact_id" and not self.data.get("id"):
            raise ValueError("data.id is required for artifact_id references")
        if source_type == "inline_geojson" and "features" not in self.data:
            raise ValueError("data.features is required for inline_geojson references")
        return self


class MapProgramState(BaseModel):
    view: dict[str, Any] = Field(default_factory=dict)
    layers: list[MapLayerSpec] = Field(default_factory=list)
    dashboard_layers: list[dict[str, Any]] = Field(default_factory=list)


class MapProgram(BaseModel):
    type: Literal["map_program"] = "map_program"
    version: str = "0.1"
    renderer: str = "amap-compatible"
    program_id: str
    intent: str
    state: MapProgramState
    lineage: dict[str, Any] = Field(default_factory=dict)


class MapEvent(BaseModel):
    type: Literal["map_event"] = "map_event"
    event_id: str
    event: str
    session_id: str | None = None
    turn_id: str | None = None
    geometry: dict[str, Any] | None = None
    feature: dict[str, Any] | None = None
    active_layers: list[str] = Field(default_factory=list)
    map_view: dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class MapProgramError(BaseModel):
    type: Literal["map_program_error"] = "map_program_error"
    program_id: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    recoverable: bool = True
