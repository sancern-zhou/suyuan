from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CarbonRequest(BaseModel):
    data_id: Optional[str] = Field(None, description="数据 id（与 Context-Aware 存储交互）")
    carbon_type: str = Field("pm25", description="pm25/vocs")
    poc_method: str = Field("ec_normalization", description="POC 计算方法")


class CarbonResponse(BaseModel):
    status: str
    success: bool
    data: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    visuals: Optional[List[Dict[str, Any]]] = None









