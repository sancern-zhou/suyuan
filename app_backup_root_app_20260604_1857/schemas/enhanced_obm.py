"""
Enhanced OBM Analysis Result Schema

增强OBM分析结果的Pydantic模型定义，包含EKMA/PO3/RIR三大引擎的结果格式。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ============================================
# EKMA Engine Schema
# ============================================

class EKMASensitivityData(BaseModel):
    """EKMA敏感性等值线数据"""
    koh_voc: List[float] = Field(default_factory=list, description="VOC控制效率数组")
    koh_nox: List[float] = Field(default_factory=list, description="NOx控制效率数组")
    po3: List[float] = Field(default_factory=list, description="O3生成效率数组")
    voc_factor: List[float] = Field(default_factory=list, description="VOC减排因子数组")
    nox_factor: List[float] = Field(default_factory=list, description="NOx减排因子数组")
    sensitivity_type: str = Field(..., description="敏感性类型: VOCs-limited/NOx-limited/transitional")
    control_recommendation: str = Field(..., description="控制建议")
    base_o3: float = Field(..., description="基准O3浓度(ppb)")
    data_points: int = Field(..., description="网格计算点数")


class EKMAResult(BaseModel):
    """EKMA分析结果"""
    status: str = Field(default="success")
    success: bool = Field(default=True)
    data: Optional[EKMASensitivityData] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(default="")


# ============================================
# PO3 Engine Schema
# ============================================

class PO3TimePoint(BaseModel):
    """PO3时序单点数据"""
    time: str = Field(..., description="时间戳")
    PO3_ppb_per_h: float = Field(..., description="臭氧生成速率(ppb/h)")
    dOx_ppb_per_h: float = Field(..., description="O3变化率(ppb/h)")
    TransO3_ppb_per_h: float = Field(..., description="传输项(ppb/h)")
    O3_ppb: float = Field(..., description="O3浓度(ppb)")
    NOx_ppb: float = Field(default=0.0, description="NOx浓度(ppb)")
    VOCs_reactivity: float = Field(default=0.0, description="VOCs总反应性")


class PO3DailyPeak(BaseModel):
    """PO3日峰值信息"""
    time: str = Field(..., description="峰值时间")
    po3_rate: float = Field(..., description="峰值PO3速率(ppb/h)")
    o3_concentration: float = Field(..., description="对应O3浓度(ppb)")


class PO3PhotochemicalPeriod(BaseModel):
    """光化学活跃期"""
    start: str = Field(..., description="开始时间(HH:MM)")
    end: str = Field(..., description="结束时间(HH:MM)")
    peak_hours: int = Field(..., description="活跃小时数")


class PO3Statistics(BaseModel):
    """PO3统计信息"""
    mean_po3: float = Field(..., description="平均PO3速率")
    max_po3: float = Field(..., description="最大PO3速率")
    min_po3: float = Field(..., description="最小PO3速率")
    std_po3: float = Field(..., description="PO3标准差")
    total_ozone_production: float = Field(..., description="总臭氧生成量")
    data_points: int = Field(..., description="数据点数")


class PO3Data(BaseModel):
    """PO3分析数据"""
    timeseries: List[PO3TimePoint] = Field(default_factory=list, description="时序数据")
    daily_peak: Optional[PO3DailyPeak] = Field(None, description="日峰值信息")
    photochemical_period: Optional[PO3PhotochemicalPeriod] = Field(None, description="光化学活跃期")
    statistics: Optional[PO3Statistics] = Field(None, description="统计信息")


class PO3Result(BaseModel):
    """PO3分析结果"""
    status: str = Field(default="success")
    success: bool = Field(default=True)
    data: Optional[PO3Data] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(default="")


# ============================================
# RIR Engine Schema
# ============================================

class RIRKeySpecies(BaseModel):
    """RIR关键控制物种"""
    species: str = Field(..., description="物种名称")
    rir: float = Field(..., description="RIR值")
    category: str = Field(..., description="VOC类别")
    concentration: float = Field(..., description="平均浓度(ppb)")
    mir: float = Field(..., description="MIR系数")
    control_priority: int = Field(..., description="控制优先级")


class RIRSummaryStats(BaseModel):
    """RIR汇总统计"""
    positive_rir_count: int = Field(..., description="正效应物种数")
    negative_rir_count: int = Field(..., description="负效应物种数")
    max_rir: float = Field(..., description="最大RIR值")
    min_rir: float = Field(..., description="最小RIR值")
    mean_rir: float = Field(default=0.0, description="平均RIR值")
    std_rir: float = Field(default=0.0, description="RIR标准差")


class RIRData(BaseModel):
    """RIR分析数据"""
    rir_by_species: Dict[str, float] = Field(default_factory=dict, description="各物种RIR值")
    rir_by_category: Dict[str, float] = Field(default_factory=dict, description="各类别RIR值")
    key_control_species: List[RIRKeySpecies] = Field(default_factory=list, description="关键控制物种")
    summary_stats: Optional[RIRSummaryStats] = Field(None, description="汇总统计")


class RIRResult(BaseModel):
    """RIR分析结果"""
    status: str = Field(default="success")
    success: bool = Field(default=True)
    data: Optional[RIRData] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(default="")


# ============================================
# Enhanced OBM Unified Result
# ============================================

class EnhancedOBMAnalysisResults(BaseModel):
    """增强OBM分析结果集合"""
    ekma: Optional[EKMASensitivityData] = Field(None, description="EKMA敏感性分析结果")
    po3: Optional[PO3Data] = Field(None, description="PO3时序分析结果")
    rir: Optional[RIRData] = Field(None, description="RIR反应性分析结果")


class EnhancedOBMResult(BaseModel):
    """
    增强OBM分析完整结果模型
    
    集成EKMA/PO3/RIR三大引擎的统一结果格式，
    兼容UDF v2.0标准和Context-Aware V2架构。
    """
    station_name: str = Field(..., description="站点名称")
    analysis_mode: str = Field(..., description="分析模式: ekma/po3/rir/all")
    results: EnhancedOBMAnalysisResults = Field(..., description="分析结果集合")
    timestamp: str = Field(..., description="分析时间戳")
    
    # 元数据
    schema_version: str = Field(default="v2.0", description="Schema版本")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外元数据")

    class Config:
        schema_extra = {
            "example": {
                "station_name": "广州从化天湖",
                "analysis_mode": "all",
                "results": {
                    "ekma": {
                        "sensitivity_type": "VOCs-limited",
                        "control_recommendation": "优先控制VOCs排放",
                        "base_o3": 85.5,
                        "data_points": 2204
                    },
                    "po3": {
                        "daily_peak": {
                            "time": "2025-08-01 14:00:00",
                            "po3_rate": 11.43,
                            "o3_concentration": 120.5
                        },
                        "photochemical_period": {
                            "start": "10:00",
                            "end": "16:00",
                            "peak_hours": 6
                        }
                    },
                    "rir": {
                        "key_control_species": [
                            {"species": "乙烯", "rir": 0.0348, "category": "烯烃", "control_priority": 1},
                            {"species": "丙烯", "rir": 0.0285, "category": "烯烃", "control_priority": 2}
                        ]
                    }
                },
                "timestamp": "2025-12-02 18:30:00"
            }
        }
