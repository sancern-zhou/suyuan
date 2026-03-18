"""
Trajectory-related schema definitions.

用于描述轨迹+源清单深度溯源的统一数据结构，便于在数据注册与
后续可视化时获得类型提示。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TrajectorySourceAnalysisResult(BaseModel):
    status: str
    success: bool
    mode: str
    analysis_period: Dict[str, Any]
    target_location: Dict[str, Any]
    pollutant: str
    top_contributors: List[Dict[str, Any]]
    trajectory_summary: Dict[str, Any]
    emission_summary: Dict[str, Any]
    visuals: List[Dict[str, Any]]
    recommendations: List[Any]
    metadata: Dict[str, Any]
    summary: str
    data: Optional[Dict[str, Any]] = None
    data_id: Optional[str] = None
    registry_schema: Optional[str] = None

