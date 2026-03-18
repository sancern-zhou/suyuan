"""
OBM/OFP Analysis Result Schema

OBM/OFP分析结果的Pydantic模型定义，用于规范数据存储和访问。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VOCCategoryOFP(BaseModel):
    """VOC类别OFP汇总"""
    category: str = Field(..., description="VOC类别")
    total_ofp: float = Field(..., description="总OFP值")
    species_count: int = Field(..., description="该类别物种数量")
    contribution_pct: float = Field(..., description="贡献百分比")


class VOCCarbonOFP(BaseModel):
    """基于碳原子数的OFP汇总"""
    carbon_count: int = Field(..., description="碳原子数")
    total_ofp: float = Field(..., description="总OFP值")
    species_count: int = Field(..., description="物种数量")


class OBMOFPSensitivity(BaseModel):
    """O3生成敏感性诊断"""
    sensitivity_type: str = Field(..., description="敏感性类型：VOCs-limited, NOx-limited, Transitional")
    vocs_control_effectiveness: float = Field(..., description="VOCs控制效果")
    nox_control_effectiveness: float = Field(..., description="NOx控制效果")
    recommendation: str = Field(..., description="控制建议")


class OBMOFPSample(BaseModel):
    """OBM/OFP单样本结果"""
    time: str = Field(..., description="时间戳")
    vocs_ofp: float = Field(..., description="VOCs总OFP")
    ozone_formation_potential: float = Field(..., description="臭氧生成潜势")
    sensitivity_type: str = Field(..., description="敏感性类型")


class OBMOFPResult(BaseModel):
    """OBM/OFP分析完整结果模型

    统一存储格式，与PMFResult保持一致
    """
    station_name: str = Field(..., description="站点名称")
    schema_version: str = "obm_ofp.v1"

    # VOC物种OFP列表
    species_ofp: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="各VOC物种的OFP值和属性"
    )

    # 时序数据（可选）
    timeseries: List[OBMOFPSample] = Field(
        default_factory=list,
        description="时间序列OFP分析结果"
    )

    # 汇总数据
    category_summary: List[VOCCategoryOFP] = Field(
        default_factory=list,
        description="按类别的OFP汇总"
    )
    carbon_summary: List[VOCCarbonOFP] = Field(
        default_factory=list,
        description="按碳原子数的OFP汇总"
    )

    # 敏感性分析
    sensitivity: OBMOFPSensitivity = Field(
        ...,
        description="O3生成敏感性诊断结果"
    )

    # 总体统计
    total_ofp: float = Field(..., description="总OFP值")
    primary_vocs: List[str] = Field(
        default_factory=list,
        description="主要控制VOCs物种列表"
    )

    # 元数据
    quality_report: Optional[Dict[str, str]] = Field(
        default=None,
        description="质量报告"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="额外元数据"
    )

    class Config:
        json_encoders = {
            # 确保datetime等类型能正确序列化
        }
        schema_extra = {
            "example": {
                "station_name": "深圳南山站",
                "schema_version": "obm_ofp.v1",
                "species_ofp": [
                    {"species": "乙烯", "concentration": 10.5, "ofp": 15.2, "category": "烯烃"},
                    {"species": "丙烯", "concentration": 8.3, "ofp": 12.1, "category": "烯烃"}
                ],
                "category_summary": [
                    {"category": "烯烃", "total_ofp": 45.6, "species_count": 8, "contribution_pct": 35.2},
                    {"category": "芳香烃", "total_ofp": 32.1, "species_count": 6, "contribution_pct": 24.8}
                ],
                "sensitivity": {
                    "sensitivity_type": "VOCs-limited",
                    "vocs_control_effectiveness": 85.3,
                    "nox_control_effectiveness": 15.7,
                    "recommendation": "优先控制VOCs排放"
                },
                "total_ofp": 129.5,
                "primary_vocs": ["乙烯", "丙烯", "甲苯"]
            }
        }
