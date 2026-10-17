"""Request contracts for the current Agent-based template report endpoints."""
from typing import Any

from pydantic import BaseModel, Field


class TemplateReportRequest(BaseModel):
    """Generate a report using supplied template content."""

    template_content: str = Field(..., description="历史报告内容")
    target_time_range: dict[str, str] = Field(..., description="目标时间范围")
    options: dict[str, Any] | None = Field(None, description="生成选项")


class QuickGenerateRequest(BaseModel):
    """Generate a report using a saved template."""

    time_range: dict[str, str] = Field(..., description="目标时间范围")
    options: dict[str, Any] | None = Field(None, description="生成选项")
