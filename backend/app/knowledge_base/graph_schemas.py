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


class GraphQueryRequest(BaseModel):
    query: str = ""
    depth: int = Field(default=2, ge=1, le=2)
    limit: int = Field(default=50, ge=1, le=200)
    review_statuses: set[ReviewStatus] = Field(
        default_factory=lambda: {"confirmed", "published"}
    )


class GraphSchemaUpdate(BaseModel):
    graph_enabled: bool | None = None
    graph_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    extractor_config: dict[str, Any] | None = None


class GraphEntityCreate(BaseModel):
    entity_type: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=512)
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    review_status: ReviewStatus = "confirmed"


class GraphEntityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=512)
    canonical_name: str | None = None
    aliases: list[str] | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None
    review_status: ReviewStatus | None = None


class GraphRelationCreate(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relation_type: str = Field(min_length=1, max_length=120)
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    review_status: ReviewStatus = "confirmed"


class GraphRelationUpdate(BaseModel):
    relation_type: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    attributes: dict[str, Any] | None = None
    review_status: ReviewStatus | None = None


class GraphMergeRequest(BaseModel):
    source_id: str
    target_id: str
