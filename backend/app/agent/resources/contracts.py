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


class DocumentPreviewType(str, Enum):
    NONE = "none"
    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "markdown"
    IMAGE = "image"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"


SPREADSHEET_FORMATS = {"xls", "xlsx", "xlsm", "csv", "ods"}
MARKDOWN_FORMATS = {"md", "markdown", "qmd"}
HTML_FORMATS = {"html", "htm"}
IMAGE_FORMATS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "svg"}
PRESENTATION_FORMATS = {"ppt", "pptx"}


def infer_document_preview_type(format_name: str, preview: dict[str, Any]) -> DocumentPreviewType:
    normalized_format = str(format_name or "").strip().lower()
    if normalized_format == "drawio":
        return DocumentPreviewType.NONE
    declared_type = str(preview.get("type") or "").strip().lower()
    if declared_type in {item.value for item in DocumentPreviewType}:
        return DocumentPreviewType(declared_type)
    if not preview:
        return DocumentPreviewType.NONE
    if preview.get("pdf_url") or preview.get("pdf_id") or preview.get("pdf_path"):
        return DocumentPreviewType.PDF
    if normalized_format in SPREADSHEET_FORMATS or preview.get("spreadsheet_preview"):
        return DocumentPreviewType.SPREADSHEET
    if normalized_format in IMAGE_FORMATS:
        return DocumentPreviewType.IMAGE
    if preview.get("html_url") or preview.get("html_id") or normalized_format in HTML_FORMATS:
        return DocumentPreviewType.HTML
    if preview.get("content") or normalized_format in MARKDOWN_FORMATS:
        return DocumentPreviewType.MARKDOWN
    if normalized_format in PRESENTATION_FORMATS and (
        preview.get("pages") or preview.get("montage_path")
    ):
        return DocumentPreviewType.PRESENTATION
    return DocumentPreviewType.NONE


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
    preview_type: DocumentPreviewType | None = None
    preview: dict[str, Any] = Field(default_factory=dict)
    download: dict[str, Any] = Field(default_factory=dict)
    editable: bool = False

    @model_validator(mode="after")
    def normalize_preview_type(self) -> "DocumentPresentation":
        if self.format.strip().lower() == "drawio":
            self.preview_type = DocumentPreviewType.NONE
        elif self.preview_type is None:
            self.preview_type = infer_document_preview_type(self.format, self.preview)
        return self


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
    tool_name: str = Field(default="", max_length=255)

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
