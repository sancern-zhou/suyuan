"""Canonical declarations for durable, grouped session resources."""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator



class ResourceKind(str, Enum):
    DATA = "data"
    FILE = "file"
    ARTIFACT = "artifact"
    URL = "url"
    VISUAL = "visual"


class ResourceRole(str, Enum):
    PRIMARY = "primary"
    SOURCE = "source"
    REPORT = "report"
    OUTPUT = "output"
    ATTACHMENT = "attachment"


class ResourceStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    MISSING = "missing"
    INVALID = "invalid"


class ResourceRelation(str, Enum):
    PRIMARY = "primary"
    PREVIEW = "preview"
    RENDITION = "rendition"
    SOURCE = "source"
    ATTACHMENT = "attachment"


class ResourceRenderer(str, Enum):
    FILE = "file"
    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "markdown"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    IMAGE = "image"
    CHART = "chart"
    BOARD = "board"


class ResourceCapability(str, Enum):
    PREVIEW = "preview"
    DOWNLOAD = "download"
    EDIT = "edit"
    RENDER = "render"
    SHARE = "share"


class ResourceLocator(BaseModel):
    """Server-only locator with exactly one primary identity."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    artifact_id: str | None = None
    visual_id: str | None = None
    url: str | None = None

    @model_validator(mode="after")
    def validate_primary_locator(self) -> "ResourceLocator":
        values = [self.path, self.artifact_id, self.visual_id, self.url]
        if sum(bool(value) for value in values) != 1:
            raise ValueError("locator requires exactly one primary identifier")
        if self.path:
            self.path = str(Path(self.path).expanduser().resolve())
        return self


class ResourceDeclaration(BaseModel):
    """One explicit member of a resource group published by a successful tool."""

    model_config = ConfigDict(extra="forbid")

    kind: ResourceKind
    group_key: str = Field(min_length=1, max_length=255)
    resource_key: str = Field(min_length=1, max_length=255)
    parent_key: str | None = Field(default=None, max_length=255)
    relation: ResourceRelation = ResourceRelation.PRIMARY
    role: ResourceRole = ResourceRole.OUTPUT
    label: str = Field(min_length=1, max_length=512)
    locator: ResourceLocator
    format: str = Field(min_length=1, max_length=64)
    media_type: str = Field(min_length=1, max_length=255)
    renderer: ResourceRenderer = ResourceRenderer.FILE
    capabilities: set[ResourceCapability] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: ResourceStatus = ResourceStatus.ACTIVE
    tool_name: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def validate_relation_and_metadata(self) -> "ResourceDeclaration":
        if self.relation is ResourceRelation.PRIMARY and self.parent_key:
            raise ValueError("primary resource cannot have parent_key")
        if self.relation is not ResourceRelation.PRIMARY and not self.parent_key:
            raise ValueError("non-primary resource requires parent_key")
        encoded = json.dumps(self.metadata, ensure_ascii=False, default=str)
        if len(encoded.encode("utf-8")) > 8192:
            raise ValueError("resource metadata exceeds 8192 bytes")
        return self

    def catalog_key(self) -> tuple[str, str, str]:
        return self.role.value, self.group_key, self.resource_key
