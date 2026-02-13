from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReconstructionRequest(BaseModel):
    data_id: Optional[str] = Field(None, description="数据 id（与 Context-Aware 存储交互）")
    components: Optional[List[str]] = Field(None, description="指定要用于重构的组件列名")
    reconstruction_type: str = Field("full", description="full/daily/hourly")
    oc_to_om: float = Field(1.4, description="OC 转 OM 的系数")
    negative_handling: str = Field("clip", description="负值处理策略：clip/rescale/preserve")


class ReconstructionResponse(BaseModel):
    status: str
    success: bool
    data: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    visuals: Optional[List[Dict[str, Any]]] = None









