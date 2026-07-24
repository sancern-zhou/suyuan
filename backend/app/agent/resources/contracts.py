"""Canonical resource declarations exchanged between tools and the session store."""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import ResourceKind, ResourceRole, ResourceStatus


class PresentationType(str, Enum):
    DOCUMENT = "document"
    VISUALIZATION = "visualization"


class ResourceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_id: str | None = None
    path: str | None = None
    artifact_id: str | None = None
    visual_id: str | None = None
    url: str | None = None

    @model_validator(mode="after")
    def validate_primary_locator(self) -> "ResourceLocator":
        values = [self.data_id, self.path, self.artifact_id, self.visual_id, self.url]
        if sum(bool(value) for value in values) != 1:
            raise ValueError("locator requires exactly one primary identifier")
        if self.path:
            self.path = str(Path(self.path).expanduser().resolve())
        return self

    def canonical_identity(self) -> str:
        payload = self.model_dump(exclude_none=True)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class DocumentPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str = Field(min_length=1, max_length=32)
    preview: dict[str, Any] = Field(default_factory=dict)
    download: dict[str, Any] = Field(default_factory=dict)
    editable: bool = False


class VisualizationPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    renderer: str = Field(min_length=1, max_length=64)
    spec: dict[str, Any] = Field(default_factory=dict)


class ResourceDeclaration(BaseModel):
    """One explicit, bounded resource declaration from a successful tool result."""

    model_config = ConfigDict(extra="forbid")

    kind: ResourceKind
    logical_key: str | None = Field(default=None, max_length=255)
    role: ResourceRole = ResourceRole.OUTPUT
    label: str = Field(min_length=1, max_length=512)
    locator: ResourceLocator
    presentation_type: PresentationType | None = None
    presentation: DocumentPresentation | VisualizationPresentation | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: ResourceStatus = ResourceStatus.ACTIVE

    @model_validator(mode="after")
    def validate_presentation(self) -> "ResourceDeclaration":
        if self.presentation_type is not None and not self.logical_key:
            raise ValueError("logical_key is required for presented resources")
        if self.presentation_type is PresentationType.DOCUMENT:
            if not isinstance(self.presentation, DocumentPresentation):
                raise ValueError("document presentation is required")
        elif self.presentation_type is PresentationType.VISUALIZATION:
            if not isinstance(self.presentation, VisualizationPresentation):
                raise ValueError("visualization presentation is required")
        elif self.presentation is not None:
            raise ValueError("presentation_type is required when presentation is set")
        encoded = json.dumps(self.metadata, ensure_ascii=False, default=str)
        if len(encoded.encode("utf-8")) > 8192:
            raise ValueError("resource metadata exceeds 8192 bytes")
        return self

    def resource_key(self) -> str:
        if self.logical_key:
            return self.logical_key
        identity = f"{self.kind.value}:{self.locator.canonical_identity()}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
