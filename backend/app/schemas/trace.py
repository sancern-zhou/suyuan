from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TraceRequest(BaseModel):
    data_id: Optional[str] = Field(None, description="数据 id（与 Context-Aware 存储交互）")
    al_column: str = Field("铝", description="铝列名，用于归一化")
    taylor_dict: Optional[Dict[str, float]] = Field(None, description="元素列名 -> Taylor 丰度")


class TraceResponse(BaseModel):
    status: str
    success: bool
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    visuals: Optional[List[Dict[str, Any]]] = None









