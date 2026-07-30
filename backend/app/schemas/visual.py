"""
统一的Visual对象格式 - 系统唯一的可视化数据结构

该文件定义了Visual类，作为全系统所有可视化对象（图表、地图、图片、表格等）
的统一数据格式。

设计原则：
1. 单一路径：Visual对象在工具层创建，之后不做任何格式转换，直接传递到前端
2. 单一职责：Visual只负责描述可视化内容，不承担其他职责
3. 零转换：从工具层到前端，Visual对象内容不变，只传递引用

版本：v1.0
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VisualMeta(BaseModel):
    """
    可视化元数据

    描述可视化的生成信息、数据来源等辅助信息
    """
    schema_version: str = Field(default="v1.0", description="格式版本")
    generator: Optional[str] = Field(default=None, description="生成工具名称（如 execute_echarts_python、create_report_chart）")
    scenario: Optional[str] = Field(default=None, description="场景标识（如时序分析、空间分布）")
    source_data_ids: List[str] = Field(default_factory=list, description="源数据ID列表")
    created_at: Optional[str] = Field(default=None, description="创建时间（ISO 8601格式）")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class Visual(BaseModel):
    """
    统一的可视化对象 - 全系统唯一的可视化格式

    该类用于表示所有类型的可视化内容：
    - 图表（chart）：ECharts配置
    - 地图（map）：高德地图配置
    - 图片（image）：图片URL
    - 表格（table）：表格数据

    设计原则：
    1. 在工具层创建Visual对象
    2. 通过tool_result事件直接传递到前端
    3. 前端直接使用，不做任何格式转换

    示例：
    ```python
    # 工具层创建
    visual = Visual(
        id="chart_123",
        type="chart",
        title="污染物浓度时序图",
        data={
            "title": {...},
            "xAxis": {...},
            "series": [...]
        },
        meta=VisualMeta(
            generator="execute_python",
            scenario="时序分析"
        )
    )

    # 通过tool_result返回
    return {
        "status": "success",
        "visuals": [visual]
    }

    # 前端直接使用
    const chartConfig = visual.data  // ECharts配置
    ```
    """

    # 必填字段
    id: str = Field(..., description="唯一标识符")
    type: str = Field(..., description="可视化类型：chart/map/image/table")
    title: str = Field(..., description="可视化标题")
    data: Dict[str, Any] = Field(..., description="核心数据（ECharts配置/图片URL/表格数据等）")

    # 可选字段
    meta: Optional[VisualMeta] = Field(default=None, description="元数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        # 允许任意类型（用于ECharts等复杂配置）
        arbitrary_types_allowed = True


# 类型别名，用于向后兼容
VisualBlock = Visual


# 便捷函数
def create_visual(
    visual_id: str,
    visual_type: str,
    title: str,
    data: Dict[str, Any],
    generator: Optional[str] = None,
    scenario: Optional[str] = None,
    source_data_ids: Optional[List[str]] = None
) -> Visual:
    """
    创建Visual对象的便捷函数

    Args:
        visual_id: 唯一标识符
        visual_type: 可视化类型（chart/map/image/table）
        title: 标题
        data: 核心数据
        generator: 生成工具名称
        scenario: 场景标识
        source_data_ids: 源数据ID列表

    Returns:
        Visual对象

    示例：
        visual = create_visual(
            visual_id="chart_123",
            visual_type="chart",
            title="污染物浓度",
            data={...ECharts配置},
            generator="execute_python"
        )
    """
    return Visual(
        id=visual_id,
        type=visual_type,
        title=title,
        data=data,
        meta=VisualMeta(
            generator=generator,
            scenario=scenario,
            source_data_ids=source_data_ids or [],
            created_at=datetime.now().isoformat()
        )
    )


def create_chart_visual(
    chart_id: str,
    title: str,
    chart_config: Dict[str, Any],
    **meta_kwargs
) -> Visual:
    """
    创建图表类型的Visual对象

    Args:
        chart_id: 图表ID
        title: 图表标题
        chart_config: ECharts配置
        **meta_kwargs: 其他元数据（generator, scenario等）

    Returns:
        Visual对象（type="chart"）

    示例：
        visual = create_chart_visual(
            chart_id="chart_123",
            title="污染物浓度",
            chart_config={...ECharts配置},
            generator="execute_echarts_python"
        )
    """
    return create_visual(
        visual_id=chart_id,
        visual_type="chart",
        title=title,
        data=chart_config,
        **meta_kwargs
    )
