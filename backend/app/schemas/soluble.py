from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SolubleRequest(BaseModel):
    data_id: Optional[str] = Field(None, description="数据 id（与 Context-Aware 存储交互）")
    analysis_type: str = Field("full", description="full/ternary/sor_nor/balance")


class SolubleResponse(BaseModel):
    status: str
    success: bool
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    visuals: Optional[List[Dict[str, Any]]] = None









