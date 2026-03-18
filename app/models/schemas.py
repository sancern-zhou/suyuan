"""
Pydantic models for request/response validation.
"""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ==================== Request Models ====================

class AnalyzeRequest(BaseModel):
    """Analysis request from frontend."""
    query: str = Field(..., description="Natural language query")
    station_id: Optional[str] = Field(None, description="Station ID (optional)")
    pollutant: Optional[str] = Field(None, description="Pollutant type")
    time_range: Optional[Dict[str, str]] = Field(None, description="Time range")


class ConfigRequest(BaseModel):
    """Configuration request (currently no parameters needed)."""
    pass


# ==================== Response Models ====================

class VisualMeta(BaseModel):
    """Metadata for visualizations."""
    unit: Optional[str] = None
    thresholds: Optional[List[Dict[str, Any]]] = None
    legend_order: Optional[List[str]] = Field(None, alias="legendOrder")
    palette: Optional[List[str]] = None
    notes: Optional[str] = None


class VisualStatic(BaseModel):
    """Static image visualization."""
    id: str
    type: str = "image"
    title: str
    mode: Literal["static"] = "static"
    url: str
    meta: Optional[VisualMeta] = None


class VisualDynamic(BaseModel):
    """Dynamic visualization with payload."""
    id: str
    type: Literal["map", "timeseries", "bar", "pie", "scatter"]
    title: str
    mode: Literal["dynamic"] = "dynamic"
    payload: Dict[str, Any]
    meta: Optional[VisualMeta] = None


class Anchor(BaseModel):
    """Evidence anchor linking text to visuals."""
    ref: str = Field(..., description="Visual ID reference")
    label: str = Field(..., description="Display label")


class ModuleResult(BaseModel):
    """Analysis module result."""
    analysis_type: str = Field(..., description="Type of analysis")
    content: str = Field(..., description="Markdown content")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score")
    visuals: Optional[List[Any]] = Field(None, description="List of visualizations")
    anchors: Optional[List[Anchor]] = Field(None, description="Evidence anchors")


class QueryInfo(BaseModel):
    """Extracted query information."""
    location: Optional[str] = None
    city: Optional[str] = None
    pollutant: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    scale: Optional[Literal["station", "city"]] = "station"


class VisualizationCapability(BaseModel):
    """Visualization capability flags."""
    supports_dynamic_map: bool = True
    supports_echarts: bool = True
    supports_small_multiples: bool = False
    supports_animation: bool = False


class UpwindEnterpriseData(BaseModel):
    """Upwind enterprise analysis data."""
    public_url: Optional[str] = Field(None, description="AMap static map URL")
    public_urls: Optional[List[str]] = Field(None, description="Multiple map URLs if paginated")
    filtered: Optional[List[Dict[str, Any]]] = Field(None, description="Filtered enterprise list")
    meta: Optional[Dict[str, Any]] = Field(None, description="Metadata (legend, station info, etc)")


class AnalysisResponseData(BaseModel):
    """Analysis response data structure (without KPI)."""
    query_info: Optional[QueryInfo] = None
    visualization_capability: Optional[VisualizationCapability] = None
    upwind_enterprises: Optional[UpwindEnterpriseData] = None
    weather_analysis: Optional[ModuleResult] = None
    regional_analysis: Optional[ModuleResult] = None
    voc_analysis: Optional[ModuleResult] = None
    particulate_analysis: Optional[ModuleResult] = None
    comprehensive_analysis: Optional[ModuleResult] = None


class AnalyzeResponse(BaseModel):
    """Analysis API response."""
    success: bool
    data: Optional[AnalysisResponseData] = None
    message: Optional[str] = None


class ConfigResponse(BaseModel):
    """Configuration API response."""
    amap_public_key: Optional[str] = Field(None, alias="amapPublicKey")
    features: Optional[Dict[str, bool]] = None


# ==================== Internal Data Models ====================

class ExtractedParams(BaseModel):
    """Parameters extracted from user query."""
    location: Optional[str] = None  # Station name
    city: Optional[str] = None  # City name (without 市)
    pollutant: Optional[str] = None  # SO2, CO, O3, PM2.5, PM10, NOX
    start_time: Optional[str] = None  # YYYY-MM-DD HH:MM:SS
    end_time: Optional[str] = None  # YYYY-MM-DD HH:MM:SS
    scale: Literal["station", "city"] = "station"
    venue_name: Optional[str] = None  # 体育场馆名称（广东省全运会专用）


class StationInfo(BaseModel):
    """Station information."""
    station_name: str
    station_code: Optional[str] = None
    city: str
    district: str
    longitude: float
    latitude: float
    address: Optional[str] = None


class WindData(BaseModel):
    """Wind data for a specific time point."""
    time: str  # ISO format: YYYY-MM-DDTHH:MM:SSZ
    wd_deg: float  # Wind direction in degrees
    ws_ms: float  # Wind speed in m/s


class EnterpriseInfo(BaseModel):
    """Enterprise information."""
    name: str
    industry: Optional[str] = None
    longitude: float
    latitude: float
    distance: Optional[float] = None
    emissions: Optional[Dict[str, float]] = None  # Pollutant: value


class MonitoringData(BaseModel):
    """Monitoring data point."""
    time_point: str
    value: float
    pollutant: str
    station: str


class ComponentData(BaseModel):
    """VOCs or particulate component data."""
    time_point: str
    component: str
    concentration: float
    ofp: Optional[float] = None  # For VOCs only


# ==================== Conversational Session Models ====================

class ChatMessage(BaseModel):
    """A single chat message in the conversation."""
    role: Literal["user", "ai"]
    content: str
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    """Request for conversational chat endpoint."""
    message: str = Field(..., description="User's message")
    session_id: Optional[str] = Field(None, description="Session ID for continuing conversation")
    stream: Optional[bool] = Field(True, description="Enable streaming response")


class IntentClassificationResult(BaseModel):
    """Result of combined parameter extraction and intent classification."""
    intent: Literal["NEW_ANALYSIS", "FOLLOW_UP_QUESTION", "CLARIFICATION_RESPONSE", "GENERAL_CHAT"]
    extracted_params: Dict[str, Any]
    missing_params: List[str]
    clarification_prompt: Optional[str] = None
    can_proceed: bool


class ChatResponse(BaseModel):
    """Response for conversational chat endpoint."""
    session_id: str
    message: str  # AI's response message
    intent: Optional[str] = None
    extracted_params: Optional[Dict[str, Any]] = None
    missing_params: Optional[List[str]] = None
    analysis_result: Optional[AnalysisResponseData] = None
    can_proceed: bool = False
