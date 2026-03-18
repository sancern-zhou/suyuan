"""
报告生成相关数据模型
"""
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum

class ReportType(str, Enum):
    """报告类型"""
    RESEARCH_REPORT = "research_report"  # 研究报告
    ANALYSIS_REPORT = "analysis_report"  # 分析报告
    MONTHLY_REPORT = "monthly_report"    # 月度报告
    WEEKLY_REPORT = "weekly_report"      # 周报

class EventType(str, Enum):
    """报告生成事件类型"""
    PLAN_CREATED = "plan_created"
    SECTION_STARTED = "section_started"
    TOOL_COMPLETED = "tool_completed"
    SECTION_COMPLETED = "section_completed"
    EXPERT_RESULT = "expert_result"
    REPORT_COMPLETED = "report_completed"
    PHASE_STARTED = "phase_started"
    STRUCTURE_PARSED = "structure_parsed"
    DATA_FETCHED = "data_fetched"
    DATA_ORGANIZED = "data_organized"

class ReportSection(BaseModel):
    """报告章节"""
    id: str = Field(..., description="章节ID")
    title: str = Field(..., description="章节标题")
    required: bool = Field(True, description="是否必需")
    order: int = Field(..., description="章节顺序")
    tools: Optional[List[str]] = Field(None, description="需要的工具列表")
    requires_expert: bool = Field(False, description="是否需要专家")
    expert_type: Optional[str] = Field(None, description="专家类型")
    use_knowledge_base: bool = Field(False, description="是否使用知识库")
    use_data_tools: bool = Field(False, description="是否使用数据工具")
    use_visualization: bool = Field(False, description="是否使用可视化")

class ReportPlan(BaseModel):
    """报告生成计划"""
    topic: str = Field(..., description="报告主题")
    report_type: ReportType = Field(..., description="报告类型")
    requirements: Optional[str] = Field(None, description="额外要求")
    sections: List[ReportSection] = Field(..., description="章节列表")
    knowledge_base_ids: Optional[List[str]] = Field(None, description="知识库ID列表")
    estimated_duration: Optional[int] = Field(None, description="预估耗时（秒）")

class ReportEvent(BaseModel):
    """报告生成事件"""
    type: EventType = Field(..., description="事件类型")
    data: Dict[str, Any] = Field(..., description="事件数据")
    timestamp: float = Field(default_factory=lambda: __import__('time').time())

class ReportGenerationRequest(BaseModel):
    """报告生成请求"""
    topic: str = Field(..., description="研究主题")
    report_type: ReportType = Field(ReportType.RESEARCH_REPORT, description="报告类型")
    requirements: Optional[str] = Field(None, description="额外要求")
    knowledge_base_ids: Optional[List[str]] = Field(None, description="知识库ID列表")

class TemplateReportRequest(BaseModel):
    """模板报告生成请求"""
    template_content: str = Field(..., description="历史报告内容")
    target_time_range: Dict[str, str] = Field(..., description="目标时间范围")
    options: Optional[Dict[str, Any]] = Field(None, description="生成选项")

class CreateTemplateRequest(BaseModel):
    """创建模板请求"""
    name: str = Field(..., description="模板名称")
    source_report: str = Field(..., description="源报告内容")
    description: Optional[str] = Field(None, description="模板描述")

class QuickGenerateRequest(BaseModel):
    """快速生成请求"""
    time_range: Dict[str, str] = Field(..., description="目标时间范围")
    options: Optional[Dict[str, Any]] = Field(None, description="生成选项")

class ReportStructure(BaseModel):
    """报告结构"""
    time_range: Dict[str, Any] = Field(..., description="时间范围")
    sections: List[Dict[str, Any]] = Field(..., description="章节列表")
    tables: List[Dict[str, Any]] = Field(default_factory=list, description="表格列表")
    rankings: List[Dict[str, Any]] = Field(default_factory=list, description="排名列表")
    analysis_sections: List[Dict[str, Any]] = Field(default_factory=list, description="分析章节")

class ReportTemplate(BaseModel):
    """报告模板"""
    id: str = Field(..., description="模板ID")
    name: str = Field(..., description="模板名称")
    content: str = Field(..., description="模板内容")
    placeholders: List[Dict[str, Any]] = Field(..., description="占位符列表")
    data_sources: List[Dict[str, Any]] = Field(..., description="数据源列表")
    created_by: str = Field(..., description="创建者")
    version: int = Field(1, description="版本号")
    created_at: float = Field(default_factory=lambda: __import__('time').time())

class ToolCall(BaseModel):
    """工具调用"""
    name: str = Field(..., description="工具名称")
    params: Dict[str, Any] = Field(..., description="工具参数")
    schema: Optional[str] = Field(None, description="数据schema")

class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool = Field(..., description="是否成功")
    data: Optional[Dict[str, Any]] = Field(None, description="返回数据")
    error: Optional[str] = Field(None, description="错误信息")
    data_id: Optional[str] = Field(None, description="数据ID（Context-Aware V2）")
    execution_time: Optional[float] = Field(None, description="执行时间")

class SectionContent(BaseModel):
    """章节内容"""
    section_id: str = Field(..., description="章节ID")
    title: str = Field(..., description="章节标题")
    content: str = Field(..., description="Markdown内容")
    charts: Optional[List[Dict[str, Any]]] = Field(None, description="图表列表")
    data_references: Optional[List[str]] = Field(None, description="数据引用ID列表")

class ReportOutput(BaseModel):
    """报告输出（符合UDF v2.0格式）"""
    status: str = Field("success", description="状态")
    success: bool = Field(True, description="是否成功")
    data: Optional[Dict[str, Any]] = Field(None, description="数据（报告不使用）")
    visuals: List[Dict[str, Any]] = Field(..., description="可视化列表")
    metadata: Dict[str, Any] = Field(..., description="元数据")
    summary: str = Field(..., description="摘要信息")

class ReportOptions(BaseModel):
    """报告生成选项"""
    include_analysis: bool = Field(True, description="包含分析")
    include_charts: bool = Field(True, description="包含图表")
    include_knowledge_base: bool = Field(True, description="包含知识库引用")
    output_format: str = Field("markdown", description="输出格式")
