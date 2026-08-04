"""
Unified Data Format (UDF) v2.0
统一数据格式规范

解决工具间数据格式不兼容、无法互操作的问题
提供完整的字段标准化和多图表支持

版本历史：
- v1.0: 初始版本，统一数据记录格式
- v1.1: 增强多源数据支持、可视化块、扩展元数据
- v2.0: 全面字段标准化、智能数据流、统一字段映射
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from enum import Enum
from pydantic import BaseModel, Field, validator, root_validator, field_validator

# ============================================================================
# 核心枚举类型
# ============================================================================

class DataType(str, Enum):
    """统一数据类型枚举"""
    # 原始数据
    AIR_QUALITY = "air_quality"  # 空气质量数据
    WEATHER = "weather"  # 气象数据
    VOCs = "vocs"  # VOCs组分数据
    PARTICULATE = "particulate"  # 颗粒物组分数据
    ENTERPRISE = "enterprise"  # 企业数据
    FIRE_HOTSPOT = "fire_hotspot"  # 卫星火点数据

    # 分析结果
    PMF_RESULT = "pmf_result"  # PMF源解析结果
    OBM_RESULT = "obm_result"  # OBM/OFP分析结果
    WIND_ANALYSIS = "wind_analysis"  # 风场分析结果
    COMPONENT_ANALYSIS = "component_analysis"  # 组分分析结果

    # 可视化
    CHART_CONFIG = "chart_config"  # 图表配置

    # 自定义
    CUSTOM = "custom"


class ToolCategory(str, Enum):
    """工具类别"""
    QUERY = "query"  # 数据查询
    ANALYSIS = "analysis"  # 数据分析
    VISUALIZATION = "visualization"  # 可视化


class DataStatus(str, Enum):
    """数据状态"""
    SUCCESS = "success"  # 成功
    FAILED = "failed"  # 失败
    PARTIAL = "partial"  # 部分成功
    EMPTY = "empty"  # 无数据


# ============================================================================
# UDF v2.0 新增：可视化块
# ============================================================================

class VisualBlock(BaseModel):
    """可视化块 (UDF v2.0)

    用于支持多图表场景、故事线等复杂可视化需求
    """
    id: str = Field(..., description="可视化块唯一标识符")
    type: str = Field(..., description="可视化类型：chart | map | table | story")
    schema: str = Field(..., description="数据schema：chart_config | map_config | table_config | storyboard")
    payload: Dict[str, Any] = Field(..., description="实际内容（遵循对应schema）")
    meta: Optional[Dict[str, Any]] = Field(default=None, description="元数据")

    class Config:
        schema_extra = {
            "example": {
                "id": "chart_pmf_pie_001",
                "type": "chart",
                "schema": "chart_config",
                "payload": {
                    "id": "pmf_pie_chart",
                    "type": "pie",
                    "title": "污染源贡献率",
                    "data": {"type": "pie", "data": [{"name": "机动车", "value": 35.5}]},
                    "meta": {
                        "schema_version": "3.1",
                        "generator": "execute_echarts_python",
                        "original_file_paths": ["/srv/suyuan/sessions/example/data/pmf_result.json"],
                        "scenario": "pmf_analysis",
                        "layout_hint": "main"
                    }
                }
            },
            "meta": {
                "source_file_paths": ["/srv/suyuan/sessions/example/data/pmf_result.json"],
                "template": "pmf_analysis",
                "layout_hint": "main"
            }
        }


# ============================================================================
# UDF v2.0 新增：标准化字段定义
# ============================================================================

class StandardField(BaseModel):
    """标准化字段定义 (UDF v2.0)

    用于记录字段标准化映射关系
    """
    field_name: str = Field(..., description="标准字段名")
    original_names: List[str] = Field(..., description="原始字段名列表")
    data_type: str = Field(..., description="数据类型：float | int | str | bool")
    unit: Optional[str] = Field(default=None, description="单位")
    description: Optional[str] = Field(default=None, description="字段描述")


# ============================================================================
# 统一数据模型
# ============================================================================

class DataMetadata(BaseModel):
    """数据元信息 (UDF v2.0 扩展)"""
    file_path: Optional[str] = Field(default=None, description="会话数据文件的绝对路径")
    data_type: DataType = Field(..., description="数据类型")
    schema_version: str = Field(default="v2.0", description="数据格式版本")
    record_count: int = Field(default=0, description="数据记录数")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")

    # 空间信息
    station_name: Optional[str] = Field(default=None, description="站点名称")
    station_code: Optional[str] = Field(default=None, description="站点代码")
    city: Optional[str] = Field(default=None, description="城市名称")
    lat: Optional[float] = Field(default=None, description="纬度")
    lon: Optional[float] = Field(default=None, description="经度")

    # 时间信息
    time_range: Optional[Dict[str, str]] = Field(default=None, description="时间范围")
    granularity: Optional[str] = Field(default=None, description="时间粒度")

    # 数据质量
    quality_score: Optional[float] = Field(default=None, description="数据质量评分 0-1")
    missing_rate: Optional[float] = Field(default=None, description="缺失率 0-1")

    # 上下文信息
    source: Optional[str] = Field(default=None, description="数据来源")
    tool_version: Optional[str] = Field(default=None, description="工具版本")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="查询参数")

    # v2.0 新增字段 - 用于统一数据流
    source_schema: Optional[str] = Field(default=None, description="源数据schema类型")
    source_file_paths: Optional[List[str]] = Field(default=None, description="源数据文件路径列表（支持多源）")
    scenario: Optional[str] = Field(default=None, description="场景标识：vocs_analysis | pmf_analysis等")
    generator: Optional[str] = Field(default=None, description="生成工具：execute_echarts_python | create_report_chart | calculate_pmf 等")
    dimensions: Optional[List[str]] = Field(default=None, description="数据维度列表：['station', 'time', 'pollutant']")
    metrics: Optional[List[str]] = Field(default=None, description="数据指标列表：['PM2.5', 'O3', 'NO2']")
    quality_report: Optional[Dict[str, Any]] = Field(default=None, description="数据质量详细报告")
    extensions: Optional[Dict[str, Any]] = Field(default=None, description="扩展字段（用于特殊场景）")

    # v2.0 新增：字段标准化信息
    standardized_fields: Optional[List[StandardField]] = Field(default=None, description="标准化字段定义")
    field_mapping_info: Optional[Dict[str, Any]] = Field(default=None, description="字段映射信息")


class UnifiedDataRecord(BaseModel):
    """统一数据记录 (UDF v2.0 扩展)"""
    # 时间戳（可选，用于支持非时序数据如站点信息）
    # 支持格式：
    # 1. datetime 对象
    # 2. ISO格式字符串： "2025-01-01T00:00:00"
    # 3. 时间范围字符串： "2025-01-01~ 2025-01-31" (解析为起始时间)
    timestamp: Optional[datetime] = None

    # 地理信息
    station_name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

    # 测量值（v2.0：统一使用标准字段名）
    # 标准字段包括：PM2_5, PM10, O3, NO2, SO2, CO, AQI, temperature, humidity, windSpeed等
    # 支持嵌套字典：aqi_indices, air_quality_status, meteorological_data
    measurements: Dict[str, Union[float, int, str, bool, Dict[str, Any], None]] = Field(default_factory=dict, description="测量值（v2.0使用标准字段名，支持嵌套字典）")

    # 额外信息
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="额外元信息")

    # v2.0 新增：支持多维数据
    dimensions: Optional[Dict[str, Any]] = Field(default=None, description="维度信息：{station_name, city, height_layer}")

    # v2.0 新增：原始字段映射（用于调试和向后兼容）
    original_fields: Optional[Dict[str, Any]] = Field(default=None, description="原始字段映射（v2.0新增）")

    @field_validator('timestamp', mode='before')
    @classmethod
    def parse_timestamp_with_range(cls, v):
        """
        解析时间戳字段，支持时间范围格式

        支持的格式：
        1. datetime 对象：直接返回
        2. ISO格式： "2025-01-01T00:00:00"
        3. 时间范围： "2025-01-01~ 2025-01-31" → 解析为起始时间 2025-01-01 00:00:00
        4. 日期格式： "2025-01-01"
        5. 月度格式： "2025-01" → 解析为 2025-01-01 00:00:00
        6. None 或空字符串：返回 None
        """
        if v is None or v == "":
            return None

        # 如果已经是datetime对象，直接返回
        if isinstance(v, datetime):
            return v

        # 如果是字符串，尝试多种格式
        if isinstance(v, str):
            # 格式0：月度格式 "2025-01" 或 "2026-01"
            if len(v) == 7 and v.count('-') == 1:
                try:
                    return datetime.strptime(v, "%Y-%m")
                except ValueError:
                    pass

            # 格式1：时间范围 "2025-01-01~ 2025-01-31" 或 "2025-01-01~2025-01-31"
            if '~' in v:
                try:
                    # 提取起始时间（~之前的部分）
                    start_part = v.split('~')[0].strip()
                    return datetime.strptime(start_part, "%Y-%m-%d")
                except (ValueError, IndexError):
                    # 如果解析失败，尝试其他格式
                    pass

            # 格式2：ISO格式 "2025-01-01T00:00:00"
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                pass

            # 格式3：日期格式 "2025-01-01"
            try:
                return datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                pass

            # 格式4：常见时间格式 "2025-01-01 00:00:00"
            try:
                return datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        # 如果所有格式都失败，返回None（不抛出错误，允许数据加载）
        # 这种情况下，原始字符串会保存在original_fields中
        return None

    @root_validator(pre=True)
    def populate_measurements_from_flat_fields(cls, values):
        """
        自动填充measurements字段（向后兼容扁平格式）

        如果传入的字典包含扁平的污染物字段（如PM2_5、O3等），
        自动将它们聚合到measurements字段中，避免数据丢失。

        这个validator在DataStandardizer的_convert_to_udf_v2_format之前运行，
        提供双重保障。
        """
        # 定义应该放入measurements的污染物字段
        POLLUTANT_FIELDS = {
            'PM2_5', 'PM10', 'O3', 'NO2', 'SO2', 'CO', 'NO', 'NOx',
            'AQI', 'IAQI', 'PM2_5_IAQI', 'PM10_IAQI', 'O3_IAQI',
            'SO2_IAQI', 'NO2_IAQI', 'CO_IAQI',
            'temperature', 'humidity', 'wind_speed', 'wind_direction',
            'pressure', 'dew_point'
        }

        # 如果measurements已经存在且非空，说明数据已经是v2.0格式，直接返回
        measurements = values.get('measurements', {})
        if measurements:
            return values

        # 检测是否有扁平的污染物字段
        flat_pollutants = {}
        for field in POLLUTANT_FIELDS:
            if field in values and values[field] is not None:
                flat_pollutants[field] = values[field]

        # 如果找到扁平的污染物字段，聚合到measurements
        if flat_pollutants:
            # 创建measurements字典
            values['measurements'] = flat_pollutants

            # 从values中移除这些字段（避免重复）
            for field in flat_pollutants.keys():
                values.pop(field, None)

        return values

    class Config:
        """允许保留扩展字段，避免加载后丢失 PM/O3 等顶层键。"""
        extra = "allow"


class UnifiedData(BaseModel):
    """
    统一数据格式 (UDF v2.0)

    所有工具的输出都应该遵循此格式

    版本变更：
    - v1.0: 基础数据格式
    - v1.1: 新增visuals字段支持多图表场景
    - v2.0: 全面字段标准化、智能数据流、统一字段映射
    """

    # 状态信息
    status: DataStatus = Field(..., description="执行状态")
    success: bool = Field(..., description="是否成功")
    error: Optional[str] = Field(default=None, description="错误信息")

    # 核心数据
    data: Optional[List[UnifiedDataRecord]] = Field(default_factory=list, description="数据记录（v2.0改为可选）")
    metadata: DataMetadata = Field(..., description="元数据")

    # 统计信息
    summary: str = Field(default="", description="结果摘要")

    # 数据验证报告
    validation_report: Optional[Dict[str, Any]] = Field(default=None, description="验证报告")

    # v2.0 新增：可视化块（用于多图表场景）
    visuals: List[VisualBlock] = Field(default_factory=list, description="可视化块列表（v2.0新增）")

    # v2.0 新增：数据流信息
    data_flow: Optional[Dict[str, Any]] = Field(default=None, description="数据流信息：{source_tool, target_tool, transformation}")

    @validator('success')
    def validate_success_status(cls, v, values):
        """确保success和status字段一致"""
        if v and values.get('status') == DataStatus.FAILED:
            raise ValueError("Success=True 但 status=FAILED 矛盾")
        if not v and values.get('status') == DataStatus.SUCCESS:
            raise ValueError("Success=False 但 status=SUCCESS 矛盾")
        return v

    @validator('visuals', pre=True, always=True)
    def normalize_visuals(cls, v):
        """工具不生成可视化时统一输出空列表，避免消费端对 None 做 len/遍历。"""
        return [] if v is None else v

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.dict()

    def to_chart_format(self) -> Dict[str, Any]:
        """
        转换为图表格式（v2.0）

        如果有visuals，直接返回visuals
        如果有data，转换为默认图表格式
        """
        if self.visuals:
            return {
                "visuals": [v.dict() for v in self.visuals],
                "metadata": self.metadata.dict()
            }

        if self.data:
            # 默认转换为时序图
            return {
                "id": "default_chart",
                "type": "timeseries",
                "title": f"{self.metadata.station_name}数据时序",
                "data": {
                    "type": "timeseries",
                    "data": {
                        "x": [r.timestamp.strftime("%Y-%m-%d %H:%M") for r in self.data if r.timestamp],
                        "series": [{
                            "name": "measurement",
                            "data": [list(r.measurements.values())[0] if r.measurements else 0 for r in self.data]
                        }]
                    }
                },
                "meta": self.metadata.dict()
            }

        return {"error": "无数据可转换"}

# ============================================================================
# 便利构造函数
# ============================================================================

def create_unified_data(
    data_type: DataType,
    records: List[UnifiedDataRecord],
    station_name: Optional[str] = None,
    city: Optional[str] = None,
    source: Optional[str] = None,
    scenario: Optional[str] = None,
    generator: Optional[str] = None,
    **kwargs
) -> UnifiedData:
    """创建统一数据实例的便利函数 (v2.0增强版)"""

    # v2.0: 构建元数据
    metadata = DataMetadata(
        data_type=data_type,
        schema_version="v2.0",
        record_count=len(records),
        station_name=station_name,
        city=city,
        source=source,
        scenario=scenario,
        generator=generator,
        **kwargs
    )

    return UnifiedData(
        status=DataStatus.SUCCESS,
        success=True,
        data=records,
        metadata=metadata,
        summary=f"✅ 成功创建 {data_type.value} 数据，记录数: {len(records)} (UDF v2.0)",
        data_flow={
            "source_format": "create_unified_data",
            "target_format": "UDF_v2.0",
            "transformation": "direct_creation"
        }
    )


def create_visual_unified_data(
    visuals: List[VisualBlock],
    source_file_paths: List[str],
    scenario: str,
    generator: str,
    **kwargs
) -> UnifiedData:
    """创建可视化统一数据实例 (v2.0新增)"""

    metadata = DataMetadata(
        data_type=DataType.CHART_CONFIG,
        schema_version="v2.0",
        record_count=len(visuals),
        source_file_paths=source_file_paths,
        scenario=scenario,
        generator=generator,
        **kwargs
    )

    return UnifiedData(
        status=DataStatus.SUCCESS,
        success=True,
        data=None,  # 可视化数据不使用data字段
        metadata=metadata,
        summary=f"✅ 成功创建可视化数据，图表数: {len(visuals)} (UDF v2.0)",
        visuals=visuals,
        data_flow={
            "source_format": "chart_data",
            "target_format": "UDF_v2.0",
            "transformation": "visual_creation",
            "chart_count": len(visuals)
        }
    )


# ============================================================================
# 颗粒物分析结果模型 (2025-12-29 新增)
# 用于保存 calculate_soluble, calculate_carbon, calculate_crustal 等分析结果
# ============================================================================

class ParticulateAnalysisResult(BaseModel):
    """颗粒物分析结果 (UDF v2.0)

    用于保存水溶性离子、碳组分、地壳元素等分析结果
    支持保存完整的 visuals 用于前端渲染
    """
    # 状态信息
    status: str = Field(default="success", description="执行状态")
    success: bool = Field(default=True, description="是否成功")

    # 分析数据 - 支持字典格式（包含series、records等子字段）
    data: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = Field(default_factory=dict, description="分析数据记录")

    # 元数据
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")

    # 可视化数据 - 用于前端渲染
    visuals: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="可视化配置列表")

    # 摘要信息
    summary: Optional[str] = Field(default="", description="结果摘要")

    file_path: Optional[str] = Field(default=None, description="保存后的会话数据文件路径")

    source_file_paths: Optional[List[str]] = Field(default_factory=list, description="源数据文件路径列表")

    class Config:
        """允许保留扩展字段"""
        extra = "allow"
