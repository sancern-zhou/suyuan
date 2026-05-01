"""Schemas for fact-driven expert deliberation."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    display: Optional[str] = None


class TableInput(BaseModel):
    name: str = Field(..., description="表格名称")
    source_type: str = Field("consultation_table", description="来源类型")
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="表格行")


class DeliberationOptions(BaseModel):
    max_facts_per_expert: int = 12
    enable_supplement_planning: bool = True


class DeliberationRequest(BaseModel):
    topic: str = Field("月度空气质量专家会商", description="会商主题")
    region: str = Field("广东省", description="区域")
    time_range: TimeRange = Field(default_factory=TimeRange)
    pollutants: List[str] = Field(default_factory=list)
    consultation_tables: List[TableInput] = Field(default_factory=list)
    monthly_report_text: str = ""
    stage5_report_text: str = ""
    data_ids: List[str] = Field(default_factory=list)
    options: DeliberationOptions = Field(default_factory=DeliberationOptions)


class FactQuality(BaseModel):
    completeness: str = "medium"
    temporal_coverage: str = "unknown"
    confidence: float = 0.65


class FactRecord(BaseModel):
    fact_id: str
    source_type: str
    source_ref: Dict[str, Any] = Field(default_factory=dict)
    time_range: TimeRange = Field(default_factory=TimeRange)
    region: str = ""
    city: Optional[str] = None
    pollutant: Optional[str] = None
    fact_type: str = "report_finding"
    statement: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    method: str = ""
    quality: FactQuality = Field(default_factory=FactQuality)
    tags: List[str] = Field(default_factory=list)


class ToolCallPlan(BaseModel):
    tool_name: str
    purpose: str
    expected_fact_type: str = "supplement"


class ExpertCard(BaseModel):
    expert_id: str
    display_name: str
    prompt_file: str
    tags_any: List[str] = Field(default_factory=list)
    tool_whitelist: List[str] = Field(default_factory=list)


class ClaimRecord(BaseModel):
    claim_id: str
    expert_id: str
    claim: str
    claim_type: str = "causal_interpretation"
    supporting_facts: List[str] = Field(default_factory=list)
    contradicting_facts: List[str] = Field(default_factory=list)
    missing_facts: List[str] = Field(default_factory=list)
    confidence: float = 0.6
    status: str = "candidate"


class ExpertAnalysis(BaseModel):
    expert_id: str
    display_name: str
    used_fact_ids: List[str] = Field(default_factory=list)
    new_fact_ids: List[str] = Field(default_factory=list)
    tool_call_plan: List[ToolCallPlan] = Field(default_factory=list)
    position: str
    key_findings: List[ClaimRecord] = Field(default_factory=list)
    questions_to_others: List[Dict[str, str]] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)


class ConsensusConclusion(BaseModel):
    claim: str
    consensus_level: str
    supporting_experts: List[str] = Field(default_factory=list)
    evidence_fact_ids: List[str] = Field(default_factory=list)
    confidence: float = 0.6
    report_sentence: str


class DeliberationResult(BaseModel):
    topic: str
    region: str
    time_range: TimeRange
    pollutants: List[str]
    facts: List[FactRecord]
    experts: List[ExpertCard]
    analyses: List[ExpertAnalysis]
    conclusions: List[ConsensusConclusion]
    dissents: List[Dict[str, Any]]
    forbidden_claims: List[Dict[str, str]]
    report_markdown: str
    output_files: Dict[str, str] = Field(default_factory=dict)

