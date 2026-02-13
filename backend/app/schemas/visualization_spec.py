"""
可视化规范 - 借鉴Vega-Lite的声明式设计
V1.0 - 2025-01

核心理念：
1. 声明式：描述"要什么"，而非"怎么做"
2. 安全性：JSON规范，无代码注入风险
3. 语言无关：前端可直接使用
4. 可存储：支持版本控制和回溯

参考资料：
- Vega-Lite: https://vega.github.io/vega-lite/
- Microsoft LIDA: https://microsoft.github.io/lida/
"""

from __future__ import annotations
from typing import Union, List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime


# ============================================
# 基础类型定义
# ============================================

class DataReference(BaseModel):
    """数据引用"""
    data_id: str = Field(description="数据ID，格式：schema:version:hash")
    schema: str = Field(description="数据类型，如vocs、pmf_result、air_quality等")

    class Config:
        schema_extra = {
            "example": {
                "data_id": "vocs:v1:abc123",
                "schema": "vocs"
            }
        }


class EncodingChannel(BaseModel):
    """
    编码通道 - 数据字段到视觉属性的映射

    这是Vega-Lite的核心概念：将数据字段映射到视觉通道（x、y、color、size等）
    """

    field: str = Field(description="数据字段名")

    type: Literal["quantitative", "nominal", "ordinal", "temporal"] = Field(
        description="字段类型：quantitative(数值)、nominal(类别)、ordinal(有序类别)、temporal(时间)"
    )

    aggregate: Optional[Literal["sum", "mean", "median", "min", "max", "count"]] = Field(
        default=None,
        description="聚合函数"
    )

    title: Optional[str] = Field(default=None, description="轴标题或图例标题")

    scale: Optional[Dict[str, Any]] = Field(
        default=None,
        description="刻度配置，如domain、range等"
    )

    axis: Optional[Dict[str, Any]] = Field(
        default=None,
        description="坐标轴配置，如grid、labels等"
    )

    legend: Optional[Dict[str, Any]] = Field(
        default=None,
        description="图例配置"
    )

    class Config:
        schema_extra = {
            "example": {
                "field": "PM2.5",
                "type": "quantitative",
                "title": "PM2.5浓度(μg/m³)",
                "scale": {"domain": [0, 100]}
            }
        }


class Transform(BaseModel):
    """数据转换操作"""

    type: Literal["filter", "aggregate", "bin", "calculate", "sort", "window"] = Field(
        description="转换类型"
    )

    params: Dict[str, Any] = Field(description="转换参数")

    class Config:
        schema_extra = {
            "example": {
                "type": "filter",
                "params": {"field": "PM2.5", "gt": 35}
            }
        }


# ============================================
# 可视化规范（核心）
# ============================================

class VisualizationSpec(BaseModel):
    """
    统一的可视化规范 - 类Vega-Lite设计

    核心概念：
    - mark: 图形标记（bar、line、point等）
    - encoding: 数据字段到视觉通道的映射
    - data: 数据引用
    - transform: 数据转换（可选）

    参考：https://vega.github.io/vega-lite/docs/spec.html
    """

    # ========== 核心字段 ==========

    mark: Literal[
        "bar", "line", "point", "area", "pie",
        "timeseries", "scatter", "heatmap",
        "wind_rose", "profile", "map_trajectory",
        "boxplot", "radar",
        "scatter3d", "surface3d", "line3d", "bar3d", "volume3d"
    ] = Field(description="图形标记类型")

    data: Union[DataReference, Dict[str, Any]] = Field(
        description="数据引用（data_id）或内联数据"
    )

    encoding: Dict[str, EncodingChannel] = Field(
        description="编码映射：x、y、color、size等通道"
    )

    # ========== 可选字段 ==========

    transform: Optional[List[Transform]] = Field(
        default=None,
        description="数据转换流程"
    )

    title: Optional[str] = Field(default=None, description="图表标题")

    description: Optional[str] = Field(default=None, description="图表描述")

    width: Optional[int] = Field(default=None, description="图表宽度（像素）")

    height: Optional[int] = Field(default=None, description="图表高度（像素）")

    # ========== 交互配置 ==========

    selection: Optional[Dict[str, Any]] = Field(
        default=None,
        description="交互选择配置（如brush、interval等）"
    )

    # ========== 样式配置 ==========

    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="全局样式配置"
    )

    # ========== 元数据 ==========

    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="元数据，如生成方式、质量分数等"
    )

    @validator('encoding')
    def validate_encoding(cls, v, values):
        """验证编码配置的合理性"""
        mark = values.get('mark')

        if not mark:
            return v

        # 基础图表需要x和y
        if mark in ['bar', 'line', 'point', 'area', 'scatter', 'timeseries']:
            if 'x' not in v or 'y' not in v:
                raise ValueError(f"{mark}图表必须包含x和y编码")

        # 3D图表需要x、y和z
        if mark in ['scatter3d', 'surface3d', 'line3d', 'bar3d', 'volume3d']:
            if 'x' not in v or 'y' not in v or 'z' not in v:
                raise ValueError(f"{mark}图表必须包含x、y和z编码")

        # 饼图需要角度或值
        if mark == 'pie':
            if 'theta' not in v and 'value' not in v:
                raise ValueError("饼图必须包含theta或value编码")

        # 风玫瑰图需要方向和半径
        if mark == 'wind_rose':
            if 'theta' not in v or 'radius' not in v:
                raise ValueError("风玫瑰图必须包含theta和radius编码")

        # 热力图需要x、y和color
        if mark == 'heatmap':
            if 'x' not in v or 'y' not in v or 'color' not in v:
                raise ValueError("热力图必须包含x、y和color编码")

        return v

    class Config:
        schema_extra = {
            "example": {
                "mark": "line",
                "data": {
                    "data_id": "air_quality:v1:abc123",
                    "schema": "air_quality"
                },
                "encoding": {
                    "x": {
                        "field": "timePoint",
                        "type": "temporal",
                        "title": "时间"
                    },
                    "y": {
                        "field": "PM2.5",
                        "type": "quantitative",
                        "title": "PM2.5浓度(μg/m³)"
                    },
                    "color": {
                        "field": "station_name",
                        "type": "nominal",
                        "title": "站点"
                    }
                },
                "title": "各站点PM2.5时序变化",
                "width": 800,
                "height": 400
            }
        }


# ============================================
# 图表配置（向后兼容v3.0格式）
# ============================================

class ChartConfig(BaseModel):
    """
    图表配置 - 包含规范和渲染提示

    用于存储和传输完整的图表信息
    """

    chart_id: str = Field(description="图表唯一标识")

    specification: VisualizationSpec = Field(description="可视化规范")

    # 向后兼容字段
    legacy_format: Optional[Dict[str, Any]] = Field(
        default=None,
        description="v3.0格式（用于兼容现有前端）"
    )

    # 渲染提示
    render_hints: Optional[Dict[str, Any]] = Field(
        default=None,
        description="前端渲染提示，如推荐的组件、库等"
    )

    # 质量评估
    quality_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="图表质量分数（0-1）"
    )

    # 生成信息
    generated_at: datetime = Field(default_factory=datetime.now)
    generated_by: Literal["template", "smart_recommend", "llm_custom", "fallback"] = Field(
        description="生成方式"
    )

    # 数据摘要
    data_summary: Optional[str] = Field(
        default=None,
        description="数据的自然语言摘要"
    )

    class Config:
        schema_extra = {
            "example": {
                "chart_id": "chart_001",
                "specification": {
                    "mark": "bar",
                    "data": {"data_id": "vocs:v1:abc", "schema": "vocs"},
                    "encoding": {
                        "x": {"field": "species_name", "type": "nominal"},
                        "y": {"field": "concentration", "type": "quantitative"}
                    }
                },
                "render_hints": {
                    "preferred_library": "vega-lite",
                    "fallback_library": "echarts",
                    "frontend_component": "VegaLitePanel"
                },
                "quality_score": 0.85,
                "generated_by": "smart_recommend",
                "data_summary": "广东72个站点的PM2.5数据，时间范围2025-01-01至01-07"
            }
        }


# ============================================
# 辅助函数
# ============================================

def spec_to_vegalite(spec: VisualizationSpec) -> Dict[str, Any]:
    """
    将VisualizationSpec转换为标准Vega-Lite格式

    用于前端直接使用Vega-Lite渲染器

    参考：https://vega.github.io/vega-lite/docs/spec.html
    """
    vegalite_spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "mark": spec.mark,
        "encoding": {}
    }

    # 转换encoding
    for channel, enc in spec.encoding.items():
        vegalite_spec["encoding"][channel] = {
            "field": enc.field,
            "type": enc.type
        }

        if enc.aggregate:
            vegalite_spec["encoding"][channel]["aggregate"] = enc.aggregate

        if enc.title:
            vegalite_spec["encoding"][channel]["title"] = enc.title

        if enc.scale:
            vegalite_spec["encoding"][channel]["scale"] = enc.scale

        if enc.axis:
            vegalite_spec["encoding"][channel]["axis"] = enc.axis

        if enc.legend:
            vegalite_spec["encoding"][channel]["legend"] = enc.legend

    # 添加可选字段
    if spec.title:
        vegalite_spec["title"] = spec.title

    if spec.description:
        vegalite_spec["description"] = spec.description

    if spec.width:
        vegalite_spec["width"] = spec.width

    if spec.height:
        vegalite_spec["height"] = spec.height

    if spec.config:
        vegalite_spec["config"] = spec.config

    # 处理数据引用
    if isinstance(spec.data, DataReference):
        vegalite_spec["data"] = {"name": spec.data.data_id}
    else:
        vegalite_spec["data"] = {"values": spec.data}

    # 处理数据转换
    if spec.transform:
        vegalite_spec["transform"] = []
        for t in spec.transform:
            vegalite_spec["transform"].append({
                "type": t.type,
                **t.params
            })

    return vegalite_spec


def spec_to_echarts(spec: VisualizationSpec, data_values: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """
    将VisualizationSpec转换为ECharts配置

    用于前端使用ECharts渲染（中文生态友好）

    Args:
        spec: 可视化规范
        data_values: 实际数据（如果data是引用，需要外部提供）

    Returns:
        ECharts option配置
    """
    option = {
        "title": {"text": spec.title or ""},
        "tooltip": {"trigger": "axis"},
        "legend": {},
        "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True}
    }

    # 根据mark类型生成不同的配置
    if spec.mark in ["bar", "line"]:
        # 柱状图或折线图
        x_encoding = spec.encoding.get("x")
        y_encoding = spec.encoding.get("y")
        color_encoding = spec.encoding.get("color")

        if not x_encoding or not y_encoding:
            raise ValueError("bar/line图表必须包含x和y编码")

        # xAxis配置
        if x_encoding.type == "temporal":
            option["xAxis"] = {
                "type": "time",
                "name": x_encoding.title or x_encoding.field
            }
        elif x_encoding.type in ["nominal", "ordinal"]:
            option["xAxis"] = {
                "type": "category",
                "name": x_encoding.title or x_encoding.field,
                "data": []  # 需要从数据中提取
            }
        else:
            option["xAxis"] = {
                "type": "value",
                "name": x_encoding.title or x_encoding.field
            }

        # yAxis配置
        option["yAxis"] = {
            "type": "value",
            "name": y_encoding.title or y_encoding.field
        }

        # series配置
        option["series"] = [{
            "name": y_encoding.field,
            "type": "bar" if spec.mark == "bar" else "line",
            "data": []  # 需要从数据中提取
        }]

    elif spec.mark == "pie":
        # 饼图
        theta_encoding = spec.encoding.get("theta") or spec.encoding.get("value")
        color_encoding = spec.encoding.get("color")

        option["series"] = [{
            "name": spec.title or "饼图",
            "type": "pie",
            "radius": "50%",
            "data": [],  # 需要从数据中提取
            "emphasis": {
                "itemStyle": {
                    "shadowBlur": 10,
                    "shadowOffsetX": 0,
                    "shadowColor": "rgba(0, 0, 0, 0.5)"
                }
            }
        }]

    elif spec.mark == "scatter":
        # 散点图
        x_encoding = spec.encoding.get("x")
        y_encoding = spec.encoding.get("y")

        option["xAxis"] = {"type": "value", "name": x_encoding.title if x_encoding else ""}
        option["yAxis"] = {"type": "value", "name": y_encoding.title if y_encoding else ""}
        option["series"] = [{
            "type": "scatter",
            "data": []  # 需要从数据中提取
        }]

    # TODO: 支持更多图表类型（wind_rose、heatmap等）

    return option


def spec_to_plotly(spec: VisualizationSpec) -> Dict[str, Any]:
    """
    将VisualizationSpec转换为Plotly配置

    备用方案，用于复杂图表（如3D、科学图表等）
    """
    # TODO: 实现Plotly转换
    raise NotImplementedError("Plotly转换尚未实现")


# ============================================
# 验证和工具函数
# ============================================

def validate_spec(spec: VisualizationSpec) -> Dict[str, Any]:
    """
    验证可视化规范的有效性

    Returns:
        {
            "valid": True/False,
            "errors": [...],
            "warnings": [...]
        }
    """
    errors = []
    warnings = []

    # 检查mark和encoding的匹配
    try:
        # Pydantic的validator会自动执行
        spec.dict()
    except ValueError as e:
        errors.append(str(e))

    # 检查数据引用
    if isinstance(spec.data, DataReference):
        if not spec.data.data_id or not spec.data.schema:
            errors.append("数据引用必须包含data_id和schema")

    # 检查编码字段的合理性
    for channel, encoding in spec.encoding.items():
        # 时间字段应该是temporal类型
        if "time" in encoding.field.lower() or "date" in encoding.field.lower():
            if encoding.type != "temporal":
                warnings.append(f"字段'{encoding.field}'看起来是时间字段，但类型为{encoding.type}")

        # 数值聚合需要quantitative类型
        if encoding.aggregate and encoding.type != "quantitative":
            warnings.append(f"聚合函数'{encoding.aggregate}'通常用于quantitative类型")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }


def create_simple_spec(
    mark: str,
    data_id: str,
    schema: str,
    x_field: str,
    y_field: str,
    x_type: str = "nominal",
    y_type: str = "quantitative",
    title: Optional[str] = None
) -> VisualizationSpec:
    """
    快速创建简单的可视化规范

    示例：
        spec = create_simple_spec(
            mark="bar",
            data_id="vocs:v1:abc123",
            schema="vocs",
            x_field="species_name",
            y_field="concentration",
            title="VOCs浓度分布"
        )
    """
    return VisualizationSpec(
        mark=mark,
        data=DataReference(data_id=data_id, schema=schema),
        encoding={
            "x": EncodingChannel(field=x_field, type=x_type),
            "y": EncodingChannel(field=y_field, type=y_type)
        },
        title=title
    )
