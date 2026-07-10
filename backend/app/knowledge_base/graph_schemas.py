"""Stable domain contracts for knowledge-base graph extraction and review."""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, Field

ReviewStatus: TypeAlias = Literal[
    "candidate",
    "confirmed",
    "rejected",
    "merged",
    "published",
    "archived",
]
GraphRecordKind: TypeAlias = Literal["entity", "relation"]

TRUSTED_REVIEW_STATUSES = frozenset({"confirmed", "published"})


class ExtractedEntity(BaseModel):
    local_id: str
    entity_type: str
    name: str
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence_text: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ExtractedRelation(BaseModel):
    source_local_id: str
    target_local_id: str
    relation_type: str
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence_text: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ChunkGraphExtraction(BaseModel):
    chunk_id: str
    extractor_name: str
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
