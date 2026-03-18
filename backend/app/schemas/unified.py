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
                        "generator": "chart_data_converter",
                        "original_data_ids": ["pmf_result:v2:abc123"],
                        "scenario": "pmf_analysis",
                        "layout_hint": "main"
                    }
                }
            },
            "meta": {
                "source_data_ids": ["pmf_result:v2:abc123"],
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
    data_id: str = Field(..., description="数据唯一标识符")
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
    source_data_ids: Optional[List[str]] = Field(default=None, description="源数据ID列表（支持多源）")
    scenario: Optional[str] = Field(default=None, description="场景标识：vocs_analysis | pmf_analysis等")
    generator: Optional[str] = Field(default=None, description="生成工具：smart_chart_generator | calculate_pmf等")
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

    # 向后兼容字段
    legacy_fields: Optional[Dict[str, Any]] = Field(default=None, description="旧格式兼容字段")

    # v2.0 新增：可视化块（用于多图表场景）
    visuals: Optional[List[VisualBlock]] = Field(default=None, description="可视化块列表（v2.0新增）")

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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.dict()

    def to_pmf_format(self) -> Dict[str, Any]:
        """
        转换为PMF工具期望的格式（向后兼容）

        PMF工具期望格式：
        {
            "source_contributions": {"机动车排放": 6.22, "石油化工": 71.96},
            "timeseries": [{"time": "2025-08-09 00:00:00", "机动车排放": 1.23}],
            "performance": {"R2": 0.85}
        }
        """
        # 提取源解析结果
        source_contributions = {}
        timeseries = []

        if self.data:
            for record in self.data:
                # 假设测量值中包含源贡献信息
                for key, value in record.measurements.items():
                    if key in ["机动车排放", "石油化工", "燃料挥发", "生物质燃烧", "溶剂使用", "工业排放"]:
                        if key not in source_contributions:
                            source_contributions[key] = 0.0
                        source_contributions[key] += value

        # 转换为时序格式
        for record in self.data:
            ts_entry = {
                "time": record.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                **record.measurements
            }
            timeseries.append(ts_entry)

        return {
            "source_contributions": source_contributions,
            "timeseries": timeseries,
            "performance": {"R2": self.metadata.quality_score or 0.0},
            "success": self.success
        }

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
                "id": f"default_chart_{self.metadata.data_id}",
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

    @classmethod
    def from_legacy_format(
        cls,
        status: DataStatus,
        data: Any,
        metadata: Dict[str, Any],
        summary: str = ""
    ) -> "UnifiedData":
        """
        从旧格式转换为统一格式（v2.0增强版）

        Args:
            status: 执行状态
            data: 旧格式数据
            metadata: 元数据
            summary: 摘要

        Returns:
            UnifiedData实例
        """
        # 转换数据为UnifiedDataRecord列表
        records = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # 提取时间戳
                    timestamp_str = item.get("time", item.get("timestamp", ""))
                    if isinstance(timestamp_str, str):
                        try:
                            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            timestamp = datetime.now()
                    else:
                        timestamp = timestamp_str

                    # v2.0: 保留原始字段用于调试
                    original_fields = {
                        k: v for k, v in item.items()
                        if k not in ["time", "timestamp", "station_name", "lat", "lon", "location"]
                    }

                    # 提取测量值（v2.0：保留原始字段名）
                    measurements = {
                        k: v for k, v in item.items()
                        if k not in ["time", "timestamp", "station_name", "lat", "lon", "location"]
                    }

                    # 提取地理信息
                    station_name = item.get("station_name", metadata.get("station_name"))
                    lat = item.get("lat", metadata.get("lat"))
                    lon = item.get("lon", metadata.get("lon"))

                    if isinstance(lat, str) or isinstance(lon, str):
                        # 尝试从location中提取
                        location = item.get("location", {})
                        if isinstance(location, dict):
                            lat = lat or location.get("lat")
                            lon = lon or location.get("lon")

                    record = UnifiedDataRecord(
                        timestamp=timestamp,
                        station_name=station_name,
                        lat=lat,
                        lon=lon,
                        measurements=measurements,
                        original_fields=original_fields
                    )
                    records.append(record)

        # v2.0: 构建元数据
        data_metadata = DataMetadata(
            data_id=metadata.get("data_id", f"custom:v2:{id(records)}"),
            data_type=DataType(metadata.get("data_type", "custom")),
            schema_version="v2.0",  # v2.0版本
            record_count=len(records),
            station_name=metadata.get("station_name"),
            lat=metadata.get("lat"),
            lon=metadata.get("lon"),
            quality_score=metadata.get("quality_score"),
            source=metadata.get("source"),
            # v2.0新增字段
            source_data_ids=metadata.get("source_data_ids"),
            scenario=metadata.get("scenario"),
            generator=metadata.get("generator")
        )

        return UnifiedData(
            status=status,
            success=status != DataStatus.FAILED,
            data=records,
            metadata=data_metadata,
            summary=summary,
            legacy_fields=data,  # 保留旧格式用于向后兼容
            data_flow={
                "source_format": "legacy",
                "target_format": "UDF_v2.0",
                "transformation": "from_legacy_format"
            }
        )


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
        data_id=f"{data_type.value}:v2:{id(records)}",
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
    source_data_ids: List[str],
    scenario: str,
    generator: str,
    **kwargs
) -> UnifiedData:
    """创建可视化统一数据实例 (v2.0新增)"""

    metadata = DataMetadata(
        data_id=f"chart_config:v2:{id(visuals)}",
        data_type=DataType.CHART_CONFIG,
        schema_version="v2.0",
        record_count=len(visuals),
        source_data_ids=source_data_ids,
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
# 示例用法 (v2.0)
# ============================================================================

"""
示例1: VOCs数据 (v2.0)
```python
from app.schemas.unified import create_unified_data, DataType, UnifiedDataRecord
from datetime import datetime

records = [
    UnifiedDataRecord(
        timestamp=datetime(2025, 8, 9, 0, 0),
        station_name="深圳南山站",
        measurements={"乙烯": 12.5, "丙烯": 8.3, "苯": 5.2},
        original_fields={"乙烯": 12.5, "丙烯": 8.3, "苯": 5.2}  # v2.0新增
    )
]

vocs_data = create_unified_data(
    data_type=DataType.VOCs,
    records=records,
    station_name="深圳南山站",
    city="深圳市",
    source="component_monitor",
    scenario="vocs_analysis",
    generator="get_component_data"
)
```
"""

"""
示例2: PMF分析结果 (v2.0)
```python
from app.schemas.unified import UnifiedData, DataType, DataStatus, VisualBlock
from datetime import datetime

pmf_chart = VisualBlock(
    id="pmf_pie_001",
    type="chart",
    schema="chart_config",
    payload={
        "id": "pmf_pie_chart",
        "type": "pie",
        "title": "污染源贡献率",
        "data": {"type": "pie", "data": [{"name": "石油化工", "value": 71.96}]},
        "meta": {
            "schema_version": "3.1",
            "generator": "chart_data_converter",
            "original_data_ids": ["pmf_result:v2:abc123"],
            "scenario": "pmf_analysis"
        }
    },
    meta={
        "source_data_ids": ["pmf_result:v2:abc123"],
        "layout_hint": "main"
    }
)

pmf_result = UnifiedData(
    status=DataStatus.SUCCESS,
    success=True,
    data=[
        UnifiedDataRecord(
            timestamp=datetime.now(),
            measurements={"石油化工": 71.96, "燃料挥发": 14.80, "机动车排放": 6.22}
        )
    ],
    metadata=DataMetadata(
        data_id="pmf_result:v2:abc123",
        data_type=DataType.PMF_RESULT,
        station_name="深圳南山站",
        quality_score=0.85,
        schema_version="v2.0",  # v2.0版本
        scenario="pmf_analysis",
        generator="calculate_pmf"
    ),
    summary="✅ PMF源解析完成，识别出6个污染源 (UDF v2.0)"
)
```
"""

"""
示例3: 工具调用转换 (v2.0)
```python
# 旧格式 -> UDF v2.0
legacy_data = {
    "success": True,
    "data": [
        {"time": "2025-08-09 00:00:00", "乙烯": 12.5, "丙烯": 8.3}
    ],
    "station_name": "深圳南山站"
}

unified = UnifiedData.from_legacy_format(
    status=DataStatus.SUCCESS,
    data=legacy_data["data"],
    metadata={
        "data_type": "vocs",
        "station_name": legacy_data["station_name"],
        "scenario": "vocs_analysis",
        "generator": "get_component_data"
    },
    summary="成功获取数据 (UDF v2.0)"
)
```
"""


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

    # 数据ID (保存后注入)
    data_id: Optional[str] = Field(default=None, description="数据唯一标识符")

    # 源数据ID
    source_data_ids: Optional[List[str]] = Field(default_factory=list, description="源数据ID列表")

    class Config:
        """允许保留扩展字段"""
        extra = "allow"
