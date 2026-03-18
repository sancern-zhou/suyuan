"""
Unified PMF Analysis Result Schema

PMF分析结果的统一存储格式，用于与图表生成工具无缝对接。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class UnifiedPMFSource(BaseModel):
    """PMF污染源贡献"""
    source_name: str = Field(..., description="污染源名称")
    contribution_pct: float = Field(..., ge=0.0, le=100.0, description="贡献百分比")
    concentration: float = Field(0.0, ge=0.0, description="平均浓度 (μg/m³)")
    confidence: Optional[str] = Field(None, description="置信度等级")


class UnifiedPMFTimePoint(BaseModel):
    """PMF时序数据点"""
    time: str = Field(..., description="时间戳 (YYYY-MM-DD HH:MM:SS)")
    source_values: Dict[str, float] = Field(..., description="各污染源贡献值")


class UnifiedPMFData(BaseModel):
    """PMF分析结果统一模型

    标准化PMF源解析结果的存储格式，确保与图表生成工具兼容。
    """
    # 站点信息
    station_code: str = Field("", description="站点代码")
    station_name: str = Field(..., description="站点名称")

    # 污染物信息
    pollutant: str = Field(..., description="污染物类型 (PM2.5/PM10/VOCs)")
    schema_version: str = Field("unified_pmf.v1", description="Schema版本")

    # 核心结果
    sources: List[UnifiedPMFSource] = Field(
        default_factory=list,
        description="污染源贡献列表"
    )

    # 时序数据
    timeseries: List[UnifiedPMFTimePoint] = Field(
        default_factory=list,
        description="源贡献时序变化"
    )

    # 性能指标
    performance: Dict[str, float] = Field(
        default_factory=dict,
        description="模型性能指标 (R2, Q, etc.)"
    )

    # 质量报告
    quality_report: Optional[Dict[str, Any]] = Field(
        default=None,
        description="数据质量报告"
    )

    # 元数据
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="额外元数据"
    )

    class Config:
        json_encoders = {
            # 确保能正确序列化
        }
        schema_extra = {
            "example": {
                "station_code": "1011b",
                "station_name": "深圳南山超级站",
                "pollutant": "PM2.5",
                "schema_version": "unified_pmf.v1",
                "sources": [
                    {
                        "source_name": "机动车尾气",
                        "contribution_pct": 35.2,
                        "concentration": 12.5,
                        "confidence": "High"
                    },
                    {
                        "source_name": "工业排放",
                        "contribution_pct": 28.7,
                        "concentration": 10.2,
                        "confidence": "High"
                    }
                ],
                "timeseries": [
                    {
                        "time": "2025-08-01 00:00:00",
                        "source_values": {
                            "机动车尾气": 15.2,
                            "工业排放": 12.1
                        }
                    }
                ],
                "performance": {
                    "R2": 0.85,
                    "Q": 2.3
                }
            }
        }
