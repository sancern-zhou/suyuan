"""
统一的可视化数据规范 v3.1 - 前后端数据契约

定义Chart数据的所有标准格式，确保前后端数据一致性。
该文件是权威规范，所有图表生成必须遵循此Schema。

版本历史：
- v3.0: 初始版本，支持基础图表（pie/bar/line/timeseries）
- v3.1: 扩展支持气象图表、3D图表、地图，增强元数据
"""

from __future__ import annotations

from typing import Union, List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field, validator


# ============================================
# 图表类型枚举 v3.1
# ============================================

ChartType = Literal[
    # 基础图表
    "pie",           # 饼图
    "bar",           # 柱状图
    "line",          # 折线图
    "timeseries",    # 时序图（多系列）

    # 气象图表
    "wind_rose",     # 风向玫瑰图
    "profile",       # 边界层廓线图

    # 3D图表（暂不优化，但保留类型定义）
    "scatter3d",     # 3D散点图
    "surface3d",     # 3D曲面图
    "line3d",        # 3D线图
    "bar3d",         # 3D柱状图
    "volume3d",      # 3D体素图

    # 高级图表
    "heatmap",       # 热力图（待实现）
    "radar",         # 雷达图
    "map",           # 地图（高德地图）

    # 未来扩展
    "story"          # 故事线（待讨论）
]


class ChartMeta(BaseModel):
    """图表元数据 v3.1"""
    # v3.0 字段
    unit: Optional[str] = Field(default=None, description="数据单位")
    station_name: Optional[str] = Field(default=None, description="站点名称")
    venue_name: Optional[str] = Field(default=None, description="场地名称")
    pollutant: Optional[str] = Field(default=None, description="污染物类型")
    data_source: Optional[str] = Field(default=None, description="数据来源")
    time_range: Optional[str] = Field(default=None, description="时间范围")
    record_count: Optional[int] = Field(default=None, description="数据记录数")

    # v3.1 新增字段
    schema_version: str = Field(default="3.1", description="Schema版本号")
    original_data_ids: Optional[List[str]] = Field(default=None, description="原始数据ID列表（支持多源数据）")
    generator: Optional[str] = Field(default=None, description="生成器标识：template:xxx | llm | smart_chart_generator")
    scenario: Optional[str] = Field(default=None, description="场景标识：vocs_analysis | pmf_analysis | custom等")
    layout_hint: Optional[str] = Field(default=None, description="布局提示：wide | tall | map-full | side | main")
    interaction_group: Optional[str] = Field(default=None, description="交互组ID（用于多图联动）")

    # 扩展字段（用于特殊场景）
    extensions: Optional[Dict[str, Any]] = Field(default=None, description="扩展元数据字段")


class BaseChartData(BaseModel):
    """基础图表数据"""
    pass


class PieChartData(BaseChartData):
    """饼图数据"""
    type: Literal["pie"] = "pie"
    data: List[Dict[str, Union[str, float]]] = Field(
        description="饼图数据点列表",
        example=[{"name": "苯", "value": 45.2}, {"name": "甲苯", "value": 32.8}]
    )


class BarChartData(BaseChartData):
    """柱状图数据"""
    type: Literal["bar"] = "bar"
    data: Dict[str, List] = Field(
        description="柱状图数据",
        example={
            "x": ["行业A", "行业B", "行业C"],
            "y": [10.5, 8.3, 6.2]
        }
    )


class LineChartData(BaseChartData):
    """折线图数据（单系列）"""
    type: Literal["line"] = "line"
    data: Dict[str, List] = Field(
        description="折线图数据",
        example={
            "x": ["2025-11-01", "2025-11-02", "2025-11-03"],
            "y": [10.5, 12.3, 8.7]
        }
    )


class TimeSeriesChartData(BaseChartData):
    """时序图数据（多系列）"""
    type: Literal["timeseries"] = "timeseries"
    data: Dict[str, List] = Field(
        description="时序图数据",
        example={
            "x": ["2025-11-01 00:00", "2025-11-01 01:00", "2025-11-01 02:00"],
            "series": [
                {"name": "苯", "data": [10.5, 12.3, 8.7]},
                {"name": "甲苯", "data": [5.2, 6.1, 4.8]}
            ]
        }
    )

    @validator('data')
    def validate_time_series_data(cls, v):
        """验证时序数据格式"""
        if not isinstance(v, dict):
            raise ValueError("data必须是字典类型")

        if 'x' not in v:
            raise ValueError("时序数据必须包含x字段（时间轴）")

        if 'series' not in v:
            raise ValueError("时序数据必须包含series字段（数据系列）")

        x_data = v['x']
        series_data = v['series']

        if not isinstance(x_data, list):
            raise ValueError("x字段必须是列表类型")

        if not isinstance(series_data, list):
            raise ValueError("series字段必须是列表类型")

        if len(series_data) == 0:
            raise ValueError("series不能为空列表")

        # 验证每个系列的数据长度与x轴一致
        for series in series_data:
            if 'data' not in series:
                raise ValueError("每个series必须包含data字段")

            if not isinstance(series['data'], list):
                raise ValueError("series.data必须是列表类型")

            if len(series['data']) != len(x_data):
                raise ValueError(
                    f"series '{series.get('name', 'unknown')}' 的数据长度 ({len(series['data'])}) "
                    f"与x轴长度 ({len(x_data)}) 不一致"
                )

        return v


# ============================================
# 气象图表数据类型 v3.1
# ============================================

class WindRoseChartData(BaseChartData):
    """风向玫瑰图数据"""
    type: Literal["wind_rose"] = "wind_rose"
    data: Dict[str, Any] = Field(
        description="风向玫瑰图数据",
        example={
            "sectors": [
                {
                    "direction": "N",
                    "angle": 0,
                    "avg_speed": 3.5,
                    "max_speed": 8.2,
                    "count": 120,
                    "speed_distribution": {
                        "0-2": 30,
                        "2-5": 60,
                        "5-10": 25,
                        "10+": 5
                    }
                }
            ],
            "legend": {
                "N": "北风",
                "NE": "东北风"
            }
        }
    )


class ProfileChartData(BaseChartData):
    """边界层廓线图数据"""
    type: Literal["profile"] = "profile"
    data: Dict[str, Any] = Field(
        description="边界层廓线数据",
        example={
            "altitudes": [0, 100, 200, 500, 1000, 1500, 2000],
            "elements": [
                {
                    "name": "温度",
                    "unit": "°C",
                    "data": [25.0, 24.5, 23.8, 22.0, 20.5, 18.0, 15.5]
                },
                {
                    "name": "风速",
                    "unit": "m/s",
                    "data": [2.0, 3.5, 5.0, 7.5, 9.0, 10.5, 12.0]
                }
            ]
        }
    )


# ============================================
# 地图数据类型 v3.1（高德地图）
# ============================================

class MapLayer(BaseModel):
    """地图图层"""
    type: Literal["marker", "polygon", "heatmap", "path"] = Field(description="图层类型")
    data: List[Dict[str, Any]] = Field(description="图层数据")
    style: Optional[Dict[str, Any]] = Field(default=None, description="图层样式")
    visible: bool = Field(default=True, description="是否可见")


class MapChartData(BaseChartData):
    """地图图表数据（高德地图）"""
    type: Literal["map"] = "map"
    data: Dict[str, Any] = Field(
        description="地图数据",
        example={
            "map_center": {"lng": 114.0579, "lat": 22.5431},
            "zoom": 12,
            "layers": [
                {
                    "type": "marker",
                    "data": [
                        {
                            "lng": 114.0579,
                            "lat": 22.5431,
                            "title": "深圳南山站",
                            "content": "PM2.5: 35 μg/m³",
                            "color": "green"
                        }
                    ],
                    "visible": True
                },
                {
                    "type": "heatmap",
                    "data": [
                        {"lng": 114.05, "lat": 22.54, "value": 45.2},
                        {"lng": 114.06, "lat": 22.55, "value": 32.8}
                    ],
                    "visible": True
                }
            ]
        }
    )


# ============================================
# 通用扩展数据类型（用于3D图表等）
# ============================================

class GenericChartData(BaseChartData):
    """通用图表数据（用于扩展类型）

    适用于：radar, heatmap, scatter3d, surface3d等
    """
    type: str = Field(description="图表类型（动态）")
    data: Dict[str, Any] = Field(description="图表数据（灵活格式）")


# ============================================
# 联合类型：所有支持的图表数据类型 v3.1
# ============================================

ChartDataType = Union[
    # 基础图表
    PieChartData,
    BarChartData,
    LineChartData,
    TimeSeriesChartData,

    # 气象图表
    WindRoseChartData,
    ProfileChartData,

    # 地图
    MapChartData,

    # 通用扩展（3D图表、雷达图、热力图等）
    GenericChartData
]


class ChartResponse(BaseModel):
    """统一图表响应格式 v3.1

    这是前后端数据交换的标准格式。
    所有图表生成工具必须返回此格式。
    """
    id: str = Field(
        description="图表唯一标识符",
        example="chart_001"
    )
    type: ChartType = Field(
        description="图表类型（v3.1扩展枚举）",
        example="timeseries"
    )
    title: str = Field(
        description="图表标题",
        example="莲花山VOCs浓度时序变化"
    )
    data: ChartDataType = Field(
        description="图表数据（根据type确定具体结构）"
    )
    meta: Optional[ChartMeta] = Field(
        default=None,
        description="图表元数据（v3.1扩展字段）"
    )

    class Config:
        # 示例配置
        schema_extra = {
            "example": {
                "id": "vocs_unified_timeseries_莲花山",
                "type": "timeseries",
                "title": "莲花山VOCs浓度时序变化",
                "data": {
                    "type": "timeseries",
                    "x": [
                        "2025-11-05 00:00:00",
                        "2025-11-05 01:00:00"
                    ],
                    "series": [
                        {
                            "name": "1-己烯",
                            "data": [0.012, 0.008]
                        }
                    ]
                },
                "meta": {
                    "schema_version": "3.1",
                    "unit": "ppb",
                    "station_name": "莲花山",
                    "pollutant": "VOCs",
                    "data_source": "smart_chart_generator",
                    "record_count": 67,
                    "generator": "smart_chart_generator",
                    "scenario": "vocs_analysis"
                }
            }
        }


# ============================================
# 向后兼容映射（逐步弃用）
# ============================================

# 这些字段在v3.0中将被移除，当前保持向后兼容
COMPATIBILITY_MAPPING = {
    # 旧的字段名 -> 新的字段名
    "option": "data",      # 旧字段：option -> 新字段：data
    "payload": "data",     # 旧字段：payload -> 新字段：data
    "chartType": "type",   # 旧字段：chartType -> 新字段：type
}


class ChartResponseV2(BaseModel):
    """v2.0 兼容格式（逐步弃用）

    此格式在v3.0中将被移除
    当前保持向后兼容，用于平滑迁移
    """
    id: Optional[str] = None
    type: Optional[str] = None
    title: Optional[str] = None
    data: Optional[Dict] = None

    # 兼容字段（将被弃用）
    option: Optional[Dict] = Field(default=None, deprecated=True)
    payload: Optional[Dict] = Field(default=None, deprecated=True)
    chartType: Optional[str] = Field(default=None, deprecated=True)
    meta: Optional[Dict] = None

    def to_v3(self) -> ChartResponse:
        """转换为v3.0标准格式"""
        # 智能选择数据字段
        chart_data = self.data
        if not chart_data and self.option:
            chart_data = self.option
        if not chart_data and self.payload:
            chart_data = self.payload

        # 智能选择图表类型
        chart_type = self.type
        if not chart_type and self.chartType:
            chart_type = self.chartType

        return ChartResponse(
            id=self.id or "unknown",
            type=chart_type or "bar",  # 默认类型
            title=self.title or "图表",
            data=chart_data or {},
            meta=self.meta
        )
