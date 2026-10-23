"""Structured result record produced by one scheduled-task execution."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskResult(BaseModel):
    """Business conclusion and artifact references for a finished execution."""

    execution_id: str = Field(..., description="执行ID")
    task_id: str = Field(..., description="任务ID")
    task_name: str = Field(default="", description="任务名称")
    session_id: Optional[str] = None
    status: str = Field(default="", description="执行状态")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    city: Optional[str] = Field(default=None, description="城市")
    station_id: Optional[str] = Field(default=None, description="站点ID")
    station_name: Optional[str] = Field(default=None, description="站点名称")
    pollutant: Optional[str] = Field(default=None, description="污染物")
    conclusion: Optional[str] = Field(default=None, description="LLM 最终结论")
    conclusion_source: Optional[str] = None
    findings: List[str] = Field(default_factory=list)
    image_paths: List[str] = Field(default_factory=list, description="图片产物路径")
    document_paths: List[str] = Field(default_factory=list, description="报告文档路径")
    evidence_package_paths: List[str] = Field(default_factory=list, description="证据包路径")
    report_refs: List[Dict[str, Any]] = Field(default_factory=list)
    broadcast_message: Optional[str] = Field(default=None, description="广播推送正文")
    broadcast_image_paths: List[str] = Field(
        default_factory=list, description="广播推送图片路径"
    )
    trigger_type: str = Field(default="scheduled")
    event_id: Optional[str] = None
    event_type: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
