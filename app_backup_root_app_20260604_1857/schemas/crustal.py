from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CrustalRequest(BaseModel):
    data_id: Optional[str] = Field(None, description="数据 id（与 Context-Aware 存储交互）")
    reconstruction_type: str = Field("full", description="full/daily/hourly")
    oxide_coeff_dict: Optional[Dict[str, float]] = Field(None, description="元素列名 -> 氧化物系数")


class CrustalResponse(BaseModel):
    status: str
    success: bool
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    visuals: Optional[List[Dict[str, Any]]] = None









