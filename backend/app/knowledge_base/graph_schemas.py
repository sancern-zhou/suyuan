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


class EvidenceMismatch(ValueError):
    """Raised when an extracted quote is not the declared current-Chunk span."""


class ExtractedEvidence(BaseModel):
    quote: str = Field(min_length=1)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)

    def validate_against(self, chunk_text: str) -> ExtractedEvidence:
        start = self.start_char
        end = self.end_char
        if start is None or end is None:
            first = chunk_text.find(self.quote)
            if first < 0 or chunk_text.find(self.quote, first + 1) >= 0:
                raise EvidenceMismatch(
                    "evidence quote must occur exactly once when offsets are absent"
                )
            self.start_char = first
            self.end_char = first + len(self.quote)
            return self
        if end < start or chunk_text[start:end] != self.quote:
            raise EvidenceMismatch("evidence quote does not match declared offsets")
        return self


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
    evidence: ExtractedEvidence | None = None


class ExtractedRelation(BaseModel):
    source_local_id: str
    target_local_id: str
    relation_type: str
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence_text: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: ExtractedEvidence | None = None


class ChunkGraphExtraction(BaseModel):
    chunk_id: str
    extractor_name: str
    extraction_run_id: str | None = None
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


class GraphQueryRequest(BaseModel):
    query: str = ""
    depth: int = Field(default=2, ge=1, le=2)
    limit: int = Field(default=50, ge=1, le=200)
    review_statuses: set[ReviewStatus] = Field(default_factory=lambda: {"confirmed", "published"})


class GraphSchemaUpdate(BaseModel):
    graph_enabled: bool | None = None
    graph_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    extractor_config: dict[str, Any] | None = None


class GraphBuildCreate(BaseModel):
    mode: Literal["pending", "reset_and_build"] = "pending"
    batch_size: int | None = Field(default=None, ge=1, le=500)


class GraphBuildTaskResponse(BaseModel):
    id: str
    knowledge_base_id: str
    status: str
    mode: str
    created_by: str
    created_at: Any
    started_at: Any = None
    completed_at: Any = None
    total_chunks: int
    processed_chunks: int
    failed_chunks: int
    remaining_chunks: int
    failed_chunk_ids: list[str] = Field(default_factory=list)
    last_error: str | None = None
    cancel_requested: bool
    lease_until: Any = None


class GraphSnapshotResponse(BaseModel):
    knowledge_base_id: str
    snapshot_version: int
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    next_cursor: str | None = None
    entity_total: int
    relation_total: int


class GraphEntityCreate(BaseModel):
    entity_type: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=512)
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    review_status: ReviewStatus = "confirmed"


class GraphEntityUpdate(BaseModel):
    entity_type: str | None = Field(default=None, min_length=1, max_length=80)
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
