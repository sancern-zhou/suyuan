"""
Chart Configuration Schema

图表配置的Pydantic模型定义，用于规范化图表工具的数据存储和访问。
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ChartConfig(BaseModel):
    """图表配置模型

    统一管理所有图表生成工具的输出，确保数据质量和一致性。
    """
    chart_id: str = Field(..., description="图表唯一标识符")
    chart_type: str = Field(..., description="图表类型：pie, bar, line, timeseries, scatter, etc.")
    title: str = Field(..., description="图表标题")
    payload: Dict[str, Any] = Field(..., description="ECharts配置payload")
    method: str = Field(..., description="生成方法：template or llm_generated")
    template_used: Optional[str] = Field(default=None, description="使用的模板ID（如果是模板生成）")
    scenario: Optional[str] = Field(default=None, description="场景标识：vocs_analysis, pm_analysis, custom等")

    # 数据信息
    data_record_count: int = Field(default=0, description="原始数据记录数")
    data_schema: Optional[str] = Field(default=None, description="原始数据schema类型")

    # 上下文信息
    pollutant: Optional[str] = Field(default=None, description="污染物类型")
    station_name: Optional[str] = Field(default=None, description="站点名称")
    venue_name: Optional[str] = Field(default=None, description="场地名称")

    # 生成信息
    generated_at: Optional[str] = Field(default=None, description="生成时间戳")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外元数据")

    class Config:
        json_encoders = {
            # 确保datetime等类型能正确序列化
        }
        schema_extra = {
            "example": {
                "chart_id": "chart_abc123def456",
                "chart_type": "pie",
                "title": "VOCs组分浓度分布",
                "payload": {
                    "id": "vocs_pie_chart",
                    "type": "pie",
                    "title": "VOCs组分浓度分布",
                    "mode": "dynamic",
                    "payload": [
                        {"name": "乙烯", "value": 45.2},
                        {"name": "丙烯", "value": 32.8}
                    ]
                },
                "method": "template",
                "template_used": "vocs_analysis",
                "scenario": "vocs_analysis",
                "data_record_count": 48,
                "data_schema": "vocs",
                "pollutant": "VOCs",
                "station_name": "深圳南山站",
                "generated_at": "2025-11-06T10:30:00"
            }
        }
