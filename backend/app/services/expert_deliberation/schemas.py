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


class ParsedInputFilesResult(BaseModel):
    consultation_tables: List[TableInput] = Field(default_factory=list)
    monthly_report_text: str = ""
    stage5_report_text: str = ""
    warnings: List[str] = Field(default_factory=list)


class DeliberationOptions(BaseModel):
    max_facts_per_expert: int = 12
    enable_supplement_planning: bool = True
    enable_llm_fact_extraction: bool = True
    enable_llm_experts: bool = True
    enable_tool_supplement: bool = True
    max_discussion_rounds: int = 5


class DeliberationRequest(BaseModel):
    topic: str = Field("月度空气质量专家会商", description="会商主题")
    region: str = Field("广东省", description="区域")
    time_range: TimeRange = Field(default_factory=TimeRange)
    pollutants: List[str] = Field(default_factory=list)
    consultation_tables: List[TableInput] = Field(default_factory=list)
    monthly_report_text: str = ""
    stage5_report_text: str = ""
    data_ids: List[str] = Field(default_factory=list)
    discussion_prompt: str = ""
    target_experts: List[str] = Field(default_factory=list)
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
    params: Dict[str, Any] = Field(default_factory=dict)
    executed: bool = False
    status: str = "planned"


class ExpertCard(BaseModel):
    expert_id: str
    display_name: str
    prompt_file: str
    deliberation_mode: str = "deliberation_reviewer"
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


class DiscussionTurn(BaseModel):
    turn_id: str
    round_index: int
    expert_id: str
    display_name: str
    turn_type: str = "initial_opinion"
    position: str
    used_fact_ids: List[str] = Field(default_factory=list)
    new_fact_ids: List[str] = Field(default_factory=list)
    claims: List[ClaimRecord] = Field(default_factory=list)
    questions_to_others: List[Dict[str, str]] = Field(default_factory=list)
    tool_call_plan: List[ToolCallPlan] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)


class ConsensusConclusion(BaseModel):
    claim: str
    consensus_level: str
    supporting_experts: List[str] = Field(default_factory=list)
    evidence_fact_ids: List[str] = Field(default_factory=list)
    confidence: float = 0.6
    report_sentence: str


class EvidenceMatrixRow(BaseModel):
    conclusion_id: str
    claim: str
    status: str = "candidate"
    supporting_experts: List[str] = Field(default_factory=list)
    opposing_experts: List[str] = Field(default_factory=list)
    evidence_fact_ids: List[str] = Field(default_factory=list)
    contradicting_fact_ids: List[str] = Field(default_factory=list)
    missing_facts: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    confidence: float = 0.6
    writability: str = "降级写"


class TimelineEvent(BaseModel):
    event_id: str
    stage: str
    title: str
    description: str
    round_index: Optional[int] = None
    expert_id: Optional[str] = None
    fact_ids: List[str] = Field(default_factory=list)
    turn_id: Optional[str] = None


class DeliberationResult(BaseModel):
    topic: str
    region: str
    time_range: TimeRange
    pollutants: List[str]
    facts: List[FactRecord]
    experts: List[ExpertCard]
    analyses: List[ExpertAnalysis]
    discussion_turns: List[DiscussionTurn] = Field(default_factory=list)
    evidence_matrix: List[EvidenceMatrixRow] = Field(default_factory=list)
    timeline_events: List[TimelineEvent] = Field(default_factory=list)
    conclusions: List[ConsensusConclusion]
    dissents: List[Dict[str, Any]]
    forbidden_claims: List[Dict[str, str]]
    report_markdown: str
    output_files: Dict[str, str] = Field(default_factory=dict)
