from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


ReviewStatus = Literal["candidate", "confirmed", "rejected", "needs_review", "merged", "published"]


class SourceFile(BaseModel):
    file_id: str
    map_id: str
    filename: str
    content_type: str
    storage_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def path(self) -> Path:
        return Path(self.storage_path)


class DocumentChunk(BaseModel):
    chunk_id: str
    map_id: str
    source_file_id: str
    chunk_index: int
    text: str
    location: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CognitiveSchema(BaseModel):
    allowed_entity_types: list[str]
    allowed_relation_types: list[str]
    allowed_relation_triplets: list[tuple[str, str, str]] = Field(default_factory=list)
    required_evidence: bool = True
    build_requirement: str = ""
    domain_aliases: dict[str, list[str]] = Field(default_factory=dict)
    normalization_rules: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def default_air_quality_schema(cls) -> "CognitiveSchema":
        return cls(
            allowed_entity_types=[
                "Station",
                "Pollutant",
                "Metric",
                "TimeWindow",
                "Region",
                "DataSource",
                "AnalysisMethod",
                "EmissionSource",
                "ProcessMechanism",
                "ControlMeasure",
                "StandardRule",
                "Finding",
                "Hypothesis",
                "Dataset",
                "Tool",
                "AgentRole",
                "Device",
                "Analyzer",
                "Alarm",
                "WorkOrder",
                "FaultSymptom",
                "MaintenanceAction",
                "DataMetric",
                "RootCause",
                "QualityRule",
                "CheckItem",
            ],
            allowed_relation_types=[
                "located_in",
                "measures",
                "has_alias",
                "belongs_to_category",
                "affects",
                "indicates",
                "supports",
                "contradicts",
                "requires_data",
                "derived_from",
                "regulated_by",
                "applies_to",
                "produces",
                "consumes",
                "uses_method",
                "has_limitation",
                "handled_by_agent",
                "station_has_device",
                "device_measures",
                "alarm_indicates",
                "fault_affects_metric",
                "work_order_about",
                "maintenance_handles",
                "metric_anomaly_supports",
                "root_cause_causes",
                "data_source_validates",
                "check_requires",
                "fault_related_to_pollutant",
            ],
            allowed_relation_triplets=[
                ("ProcessMechanism", "affects", "Pollutant"),
                ("EmissionSource", "supports", "Hypothesis"),
                ("Station", "measures", "Pollutant"),
                ("Region", "located_in", "Region"),
                ("Station", "station_has_device", "Device"),
                ("Device", "device_measures", "Pollutant"),
                ("Analyzer", "device_measures", "Pollutant"),
                ("Alarm", "alarm_indicates", "FaultSymptom"),
                ("FaultSymptom", "fault_affects_metric", "DataMetric"),
                ("WorkOrder", "work_order_about", "FaultSymptom"),
                ("MaintenanceAction", "maintenance_handles", "RootCause"),
                ("DataMetric", "metric_anomaly_supports", "RootCause"),
                ("RootCause", "root_cause_causes", "FaultSymptom"),
                ("DataSource", "data_source_validates", "RootCause"),
                ("CheckItem", "check_requires", "DataSource"),
            ],
            domain_aliases={
                "臭氧": ["O3", "O₃"],
                "PM2.5": ["PM25", "细颗粒物"],
                "深圳市": ["深圳"],
                "零点漂移": ["零漂", "zero drift"],
                "跨度漂移": ["跨漂", "span drift"],
                "采样泵": ["抽气泵", "sample pump"],
            },
        )


class Evidence(BaseModel):
    evidence_id: str
    map_id: str
    source_file_id: str
    chunk_id: str
    location: str
    text_span: str
    normalized_summary: str
    quote: str | None = None
    support_type: str = "unknown"
    evidence_quality: str = "unknown"
    supported_entity_ids: list[str] = Field(default_factory=list)
    supported_relation_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.7

    @property
    def ref(self) -> str:
        return f"map_evidence:{self.evidence_id}"


class CandidateEntity(BaseModel):
    entity_id: str
    map_id: str
    entity_type: str
    name: str
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.7
    review_status: ReviewStatus = "candidate"
    created_by: Literal["system", "user", "agent"] = "system"


class CandidateRelation(BaseModel):
    relation_id: str
    map_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.7
    review_status: ReviewStatus = "candidate"
    created_by: Literal["system", "user", "agent"] = "system"


class ExtractionDiagnostic(BaseModel):
    provider_name: str
    provider_version: str = "0.1"
    status: Literal["success", "partial", "failed"] = "success"
    messages: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    map_id: str
    candidate_entities: list[CandidateEntity] = Field(default_factory=list)
    candidate_relations: list[CandidateRelation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    diagnostics: ExtractionDiagnostic


class CognitiveMapQuery(BaseModel):
    task: str
    agent_mode: str
    agent_role: str | None = None
    map_ids: list[str] = Field(default_factory=list)
    data_ids: list[str] = Field(default_factory=list)
    entity_hints: list[str] = Field(default_factory=list)


class CognitiveMapView(BaseModel):
    view_id: str
    map_id: str
    task: str
    agent_mode: str
    agent_role: str | None = None
    entities: list[CandidateEntity] = Field(default_factory=list)
    relations: list[CandidateRelation] = Field(default_factory=list)
    evidence_summaries: list[Evidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    prompt_summary: str
