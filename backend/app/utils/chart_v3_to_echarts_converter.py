"""
v3.1图表数据 → ECharts配置转换器

功能：将前端使用的v3.1格式图表数据转换为ECharts原生配置
用途：后端渲染静态PNG图片（Word/PPT报告）

对应前端的 ChartPanel.vue 中的 buildOption() 函数
"""

from typing import Any, Dict, List, Optional, Union
import structlog

logger = structlog.get_logger()


class ChartV3ToEChartsConverter:
    """v3.1图表数据转ECharts配置转换器"""

    def __init__(self):
        """初始化转换器"""
        logger.info("ChartV3ToEChartsConverter initialized")

    def convert(
        self,
        chart_type: str,
        chart_data: Any,
        title: str = "",
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        转换v3.1图表数据为ECharts配置

        Args:
            chart_type: 图表类型（pie, bar, line, timeseries等）
            chart_data: v3.1格式的图表数据
            title: 图表标题
            meta: 元数据（包含unit、station_name等）

        Returns:
            ECharts配置字典
        """
        try:
            meta = meta or {}
            chart_type_lower = chart_type.lower()

            # 处理嵌套的data字段（v3.1格式的ChartData）
            actual_data = chart_data
            if isinstance(chart_data, dict) and chart_data.get("type"):
                actual_data = chart_data.get("data", chart_data)

            # 根据图表类型调用对应的转换函数
            converter_map = {
                "pie": self._convert_pie,
                "bar": self._convert_bar,
                "polar_bar": self._convert_bar,  # 极坐标柱状图复用bar逻辑
                "line": self._convert_line,
                "timeseries": self._convert_timeseries,
                "radar": self._convert_radar,
                "heatmap": self._convert_heatmap,
                "wind_rose": self._convert_wind_rose,
                "weather_timeseries": self._convert_weather_timeseries,
                "pressure_pbl_timeseries": self._convert_pressure_pbl_timeseries,
                "stacked_timeseries": self._convert_stacked_timeseries,
                "scatter": self._convert_scatter,
                "scatter3d": self._convert_scatter_3d,
                "surface3d": self._convert_surface_3d,
                "line3d": self._convert_line_3d,
                "bar3d": self._convert_bar_3d,
                "volume3d": self._convert_volume_3d,
                "profile": self._convert_profile,
                "facet_timeseries": self._convert_facet_timeseries,
            }

            converter_func = converter_map.get(chart_type_lower)
            if converter_func:
                option = converter_func(actual_data, title, meta)
            else:
                # 默认尝试通用转换
                logger.warning(
                    "unknown_chart_type",
                    chart_type=chart_type,
                    using_generic_converter=True
                )
                option = self._convert_generic(actual_data, title, meta)

            # 如果转换失败，返回空字典
            if not option:
                logger.error(
                    "conversion_returned_empty",
                    chart_type=chart_type,
                    data_type=type(actual_data).__name__
                )
                return {}

            # 添加通用配置
            option = self._add_common_config(option, title)

            return option

        except Exception as e:
            logger.error(
                "chart_conversion_failed",
                chart_type=chart_type,
                error=str(e),
                exc_info=True
            )
            return {}

    def _add_common_config(self, option: Dict[str, Any], title: str) -> Dict[str, Any]:
        """添加通用配置（toolbox等）"""
        if not option or "toolbox" not in option:
            option["toolbox"] = {
                "show": True,
                "right": 20,
                "top": 10,
                "feature": {
                    "saveAsImage": {
                        "show": True,
                        "title": "保存为图片",
                        "type": "png",
                        "pixelRatio": 2,
                        "name": title or "图表"
                    }
                }
            }
        return option

    # ==================== 饼图 ====================

    def _convert_pie(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换饼图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        pie_data = data if isinstance(data, list) else []

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "tooltip": {
                "trigger": "item",
                "formatter": "{b}: {c} ({d}%)"
            },
            "legend": {
                "orient": "vertical",
                "left": "left",
                "top": "10%"
            },
            "series": [{
                "type": "pie",
                "radius": ["40%", "70%"],
                "center": ["50%", "60%"],
                "data": pie_data,
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 10,
                        "shadowOffsetX": 0,
                        "shadowColor": "rgba(0, 0, 0, 0.5)"
                    }
                },
                "label": {
                    "show": True,
                    "position": "outside",
                    "formatter": "{b}: {d}%"
                }
            }]
        }

    # ==================== 柱状图 ====================

    def _convert_bar(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换柱状图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        x_data = data.get("x", []) if isinstance(data, dict) else []
        y_data = data.get("y", []) if isinstance(data, dict) else []
        series_list = data.get("series", []) if isinstance(data, dict) else []

        chart_series = []
        has_legend = False

        if series_list and len(series_list) > 0:
            # 多序列格式
            has_legend = True
            colors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272']
            chart_series = [
                {
                    "name": s.get("name", f"系列{i}"),
                    "type": "bar",
                    "data": s.get("data", []),
                    "itemStyle": {
                        "color": colors[i % len(colors)]
                    },
                    "emphasis": {
                        "itemStyle": {
                            "color": "#91cc75"
                        }
                    }
                }
                for i, s in enumerate(series_list)
            ]
        elif y_data and len(y_data) > 0:
            # 单序列格式
            has_legend = False
            chart_series = [{
                "name": title or "数据",
                "type": "bar",
                "data": y_data,
                "itemStyle": {
                    "color": "#5470c6"
                },
                "emphasis": {
                    "itemStyle": {
                        "color": "#91cc75"
                    }
                }
            }]

        legend_config = {
            "data": [s.get("name") for s in series_list],
            "top": 55
        } if has_legend else {
            "show": False
        }

        grid_top = 100 if has_legend else 60

        return {
            "title": {
                "text": title,
                "left": "center",
                "top": 10,
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {
                    "type": "shadow"
                }
            },
            "legend": legend_config,
            "grid": {
                "top": grid_top,
                "left": "3%",
                "right": "4%",
                "bottom": "3%",
                "containLabel": True
            },
            "xAxis": {
                "type": "category",
                "data": x_data,
                "axisLabel": {
                    "rotate": 45 if len(x_data) > 10 else 0,
                    "fontSize": 12
                }
            },
            "yAxis": {
                "type": "value",
                "name": meta.get("unit", "")
            },
            "series": chart_series
        }

    # ==================== 折线图/时序图 ====================

    def _convert_line(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换折线图数据（单系列）"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        x_data = data.get("x", []) if isinstance(data, dict) else []
        y_data = data.get("y", []) if isinstance(data, dict) else []

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "tooltip": {
                "trigger": "axis"
            },
            "xAxis": {
                "type": "category",
                "data": x_data,
                "boundaryGap": False
            },
            "yAxis": {
                "type": "value",
                "name": meta.get("unit", "")
            },
            "series": [{
                "name": title or "数据",
                "type": "line",
                "data": y_data,
                "smooth": True,
                "areaStyle": {
                    "opacity": 0.1
                }
            }]
        }

    def _convert_timeseries(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换时序图数据（多系列）"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        x_data = data.get("x", []) if isinstance(data, dict) else []
        series_list = data.get("series", []) if isinstance(data, dict) else []

        colors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272',
                  '#fc8452', '#9a60b4', '#ea7ccc']

        chart_series = [
            {
                "name": s.get("name", f"系列{i}"),
                "type": "line",
                "data": s.get("data", []),
                "smooth": True,
                "itemStyle": {
                    "color": colors[i % len(colors)]
                }
            }
            for i, s in enumerate(series_list)
        ]

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "tooltip": {
                "trigger": "axis"
            },
            "legend": {
                "data": [s.get("name") for s in series_list],
                "top": 55
            },
            "grid": {
                "top": 100,
                "left": "3%",
                "right": "4%",
                "bottom": "3%",
                "containLabel": True
            },
            "xAxis": {
                "type": "category",
                "data": x_data,
                "boundaryGap": False
            },
            "yAxis": {
                "type": "value",
                "name": meta.get("unit", "")
            },
            "series": chart_series
        }

    # ==================== 雷达图 ====================

    def _convert_radar(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换雷达图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        dimensions = data.get("dimensions", []) if isinstance(data, dict) else []
        series_list = data.get("series", []) if isinstance(data, dict) else []

        radar_indicator = [
            {
                "name": dim,
                "max": 100  # 可以从数据中计算
            }
            for dim in dimensions
        ]

        chart_series = [
            {
                "name": s.get("name", f"系列{i}"),
                "type": "radar",
                "data": [
                    {
                        "value": s.get("values", []),
                        "name": s.get("name", "")
                    }
                ]
            }
            for i, s in enumerate(series_list)
        ]

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "tooltip": {
                "trigger": "item"
            },
            "legend": {
                "data": [s.get("name") for s in series_list]
            },
            "radar": {
                "indicator": radar_indicator
            },
            "series": chart_series
        }

    # ==================== 热力图 ====================

    def _convert_heatmap(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换热力图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        # 热力图数据格式：[[x, y, value], ...]
        heatmap_data = data if isinstance(data, list) else []

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "tooltip": {
                "position": "top"
            },
            "visualMap": {
                "min": 0,
                "max": 100,
                "calculable": True,
                "orient": "horizontal",
                "left": "center",
                "bottom": "15%"
            },
            "grid": {
                "height": "50%",
                "top": "10%"
            },
            "xAxis": {
                "type": "category",
                "data": [item[0] for item in heatmap_data],
                "splitArea": {
                    "show": True
                }
            },
            "yAxis": {
                "type": "category",
                "data": [item[1] for item in heatmap_data],
                "splitArea": {
                    "show": True
                }
            },
            "series": [{
                "type": "heatmap",
                "data": heatmap_data,
                "label": {
                    "show": True
                },
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 10,
                        "shadowColor": "rgba(0, 0, 0, 0.5)"
                    }
                }
            }]
        }

    # ==================== 风向玫瑰图 ====================

    def _convert_wind_rose(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换风向玫瑰图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        # 风向玫瑰图通常是完整的ECharts配置（极坐标）
        # 如果不是，返回空配置
        if isinstance(data, dict) and "polar" in data:
            return data

        logger.warning("wind_rose_data_not_complete", data=data)
        return {}

    # ==================== 气象时序图 ====================

    def _convert_weather_timeseries(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换气象时序图数据（带风向指针）"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        # 复用普通时序图逻辑
        return self._convert_timeseries(data, title, meta)

    # ==================== 气压+边界层高度双Y轴图 ====================

    def _convert_pressure_pbl_timeseries(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换气压+边界层高度双Y轴图"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        x_data = data.get("x", []) if isinstance(data, dict) else []
        series_list = data.get("series", []) if isinstance(data, dict) else []

        chart_series = []
        for i, s in enumerate(series_list):
            series_config = {
                "name": s.get("name", f"系列{i}"),
                "type": "line",
                "data": s.get("data", []),
                "smooth": True
            }

            # 第一个系列用左Y轴，第二个用右Y轴
            if i == 1:
                series_config["yAxisIndex"] = 1

            chart_series.append(series_config)

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "tooltip": {
                "trigger": "axis"
            },
            "legend": {
                "data": [s.get("name") for s in series_list],
                "top": 55
            },
            "grid": {
                "top": 100,
                "left": "3%",
                "right": "4%",
                "bottom": "3%",
                "containLabel": True
            },
            "xAxis": {
                "type": "category",
                "data": x_data,
                "boundaryGap": False
            },
            "yAxis": [
                {
                    "type": "value",
                    "name": series_list[0].get("name", "") if series_list else "",
                    "position": "left"
                },
                {
                    "type": "value",
                    "name": series_list[1].get("name", "") if len(series_list) > 1 else "",
                    "position": "right"
                }
            ],
            "series": chart_series
        }

    # ==================== 堆叠时序图 ====================

    def _convert_stacked_timeseries(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换堆叠时序图数据（支持双Y轴）"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        x_data = data.get("x", []) if isinstance(data, dict) else []
        series_list = data.get("series", []) if isinstance(data, dict) else []

        # 检查是否有双Y轴配置（颗粒物堆叠时序图）
        has_dual_y_axis = isinstance(data.get("yAxis"), list)

        # 验证数据完整性
        if not x_data:
            logger.warning(
                "stacked_timeseries_empty_x_data",
                has_series=len(series_list) > 0,
                data_keys=list(data.keys()) if isinstance(data, dict) else "not_dict"
            )
            return {}

        if not series_list:
            logger.warning(
                "stacked_timeseries_empty_series",
                x_count=len(x_data),
                data_keys=list(data.keys()) if isinstance(data, dict) else "not_dict"
            )
            return {}

        chart_series = []
        for i, s in enumerate(series_list):
            series_config = {
                "name": s.get("name", f"系列{i}"),
                "type": "line",
                "data": s.get("data", []),
                "stack": "total",
                "areaStyle": {},
                "emphasis": {
                    "focus": "series"
                }
            }

            # 如果原数据有yAxisIndex，保留它（用于双Y轴）
            if "yAxisIndex" in s:
                series_config["yAxisIndex"] = s["yAxisIndex"]

            chart_series.append(series_config)

        # 构建配置
        option = {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {
                    "type": "cross"
                }
            },
            "legend": {
                "data": [s.get("name") for s in series_list],
                "top": 55
            },
            "grid": {
                "top": 100,
                "left": "3%",
                "right": "4%",
                "bottom": "3%",
                "containLabel": True
            },
            "xAxis": {
                "type": "category",
                "data": x_data,
                "boundaryGap": False
            },
            "yAxis": {
                "type": "value",
                "name": meta.get("unit", "")
            },
            "series": chart_series
        }

        # 如果原数据有双Y轴配置，使用原配置
        if has_dual_y_axis:
            option["yAxis"] = data["yAxis"]
            option["grid"]["right"] = "6%"  # 为右Y轴留出更多空间

        return option

    # ==================== 散点图 ====================

    def _convert_scatter(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换散点图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        # 散点图数据格式：[[x, y], ...]
        scatter_data = data if isinstance(data, list) else []

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "tooltip": {
                "trigger": "item"
            },
            "xAxis": {
                "type": "value",
                "splitLine": {
                    "show": False
                }
            },
            "yAxis": {
                "type": "value",
                "splitLine": {
                    "show": False
                }
            },
            "series": [{
                "type": "scatter",
                "data": scatter_data,
                "symbolSize": 10
            }]
        }

    # ==================== 3D图表 ====================

    def _convert_scatter_3d(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换3D散点图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        scatter_3d_data = data if isinstance(data, list) else []

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "visualMap": {
                "show": True,
                "dimension": 2,
                "min": 0,
                "max": 100,
                "inRange": {
                    "color": ['#313695', '#4575b4', '#74add1', '#abd9e9',
                             '#e0f3f8', '#ffffcc', '#fee090', '#fdae61',
                             '#f46d43', '#d73027', '#a50026']
                }
            },
            "xAxis3D": {
                "type": "value"
            },
            "yAxis3D": {
                "type": "value"
            },
            "zAxis3D": {
                "type": "value"
            },
            "grid3D": {
                "boxWidth": 200,
                "boxHeight": 80,
                "boxDepth": 200,
                "viewControl": {
                    "autoRotate": True
                }
            },
            "series": [{
                "type": "scatter3D",
                "data": scatter_3d_data,
                "symbolSize": 5
            }]
        }

    def _convert_surface_3d(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换3D曲面图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        return self._convert_scatter_3d(data, title, meta)

    def _convert_line_3d(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换3D线图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        line_3d_data = data if isinstance(data, list) else []

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "xAxis3D": {
                "type": "value"
            },
            "yAxis3D": {
                "type": "value"
            },
            "zAxis3D": {
                "type": "value"
            },
            "grid3D": {
                "boxWidth": 200,
                "boxHeight": 80,
                "boxDepth": 200
            },
            "series": [{
                "type": "line3D",
                "data": line_3d_data,
                "lineStyle": {
                    "width": 4
                }
            }]
        }

    def _convert_bar_3d(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换3D柱状图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        bar_3d_data = data if isinstance(data, list) else []

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "xAxis3D": {
                "type": "category"
            },
            "yAxis3D": {
                "type": "category"
            },
            "zAxis3D": {
                "type": "value"
            },
            "grid3D": {
                "boxWidth": 200,
                "boxHeight": 80,
                "boxDepth": 200
            },
            "series": [{
                "type": "bar3D",
                "data": bar_3d_data,
                "shading": "lambert"
            }]
        }

    def _convert_volume_3d(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换3D体素图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        # 体素图数据格式复杂，直接返回原数据
        return data if isinstance(data, dict) else {}

    # ==================== 边界层廓线图 ====================

    def _convert_profile(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换边界层廓线图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        altitudes = data.get("altitudes", []) if isinstance(data, dict) else []
        elements = data.get("elements", []) if isinstance(data, dict) else []

        chart_series = []
        for element in elements:
            chart_series.append({
                "name": element.get("name", ""),
                "type": "line",
                "xAxisIndex": 0,
                "yAxisIndex": 0,
                "data": element.get("data", []),
                "smooth": True
            })

        return {
            "title": {
                "text": title,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold"}
            },
            "tooltip": {
                "trigger": "axis"
            },
            "legend": {
                "data": [e.get("name") for e in elements],
                "top": 55
            },
            "grid": {
                "top": 100,
                "left": "10%",
                "right": "10%",
                "bottom": "10%",
                "containLabel": True
            },
            "xAxis": {
                "type": "value"
            },
            "yAxis": {
                "type": "category",
                "data": altitudes,
                "inverse": True  # 高度从上到下
            },
            "series": chart_series
        }

    # ==================== 分面时序图 ====================

    def _convert_facet_timeseries(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换分面时序图数据"""
        # 检测是否已经是ECharts配置
        if self._is_echarts_config(data):
            return data

        # 分面图数据格式复杂，直接返回原数据
        return data if isinstance(data, dict) else {}

    # ==================== 通用转换 ====================

    def _convert_generic(
        self,
        data: Any,
        title: str,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """通用转换逻辑（当类型不匹配时）"""
        # 先检查是否已经是ECharts配置
        if self._is_echarts_config(data):
            logger.info("generic_converter_detected_echarts_config")
            return data

        # 尝试检测数据格式
        if isinstance(data, dict):
            keys = list(data.keys())
            logger.info(
                "generic_converter_analyzing_dict",
                keys=keys,
                has_x=("x" in data),
                has_y=("y" in data),
                has_series=("series" in data)
            )

            # 检查是否有时序图格式
            if "x" in data and "series" in data:
                logger.info("generic_converter_using_timeseries")
                return self._convert_timeseries(data, title, meta)
            # 检查是否有折线图格式
            elif "x" in data and "y" in data:
                logger.info("generic_converter_using_line")
                return self._convert_line(data, title, meta)

        # 无法识别，返回空配置
        logger.warning(
            "unknown_chart_format",
            data_type=type(data).__name__,
            data_keys=list(data.keys()) if isinstance(data, dict) else "not_dict"
        )
        return {}

    # ==================== 辅助方法 ====================

    def _is_echarts_config(self, data: Any) -> bool:
        """
        检测数据是否已经是完整的ECharts配置

        完整的ECharts配置通常包含以下字段之一：
        - xAxis + yAxis + series
        - polar + angleAxis + radiusAxis + series
        - radar + series
        - grid3D + xAxis3D + yAxis3D + zAxis3D + series
        - dataset + series
        """
        if not isinstance(data, dict):
            return False

        # 检查常见的ECharts配置字段
        has_series = "series" in data
        has_xaxis = "xAxis" in data or "xaxis" in data or "xAxis3D" in data
        has_yaxis = "yAxis" in data or "yaxis" in data or "yAxis3D" in data
        has_polar = "polar" in data
        has_radar = "radar" in data
        has_grid3d = "grid3D" in data or "grid3d" in data
        has_dataset = "dataset" in data
        has_title = "title" in data
        has_tooltip = "tooltip" in data
        has_legend = "legend" in data

        # 如果包含series和至少一个坐标轴配置，认为是ECharts配置
        if has_series and (has_xaxis or has_yaxis or has_polar or has_radar or has_grid3d):
            return True

        # 如果包含dataset，认为是ECharts配置
        if has_dataset and has_series:
            return True

        # 如果包含多个ECharts特征字段（title, tooltip, legend, series），认为是ECharts配置
        echart_features = sum([has_title, has_tooltip, has_legend, has_series])
        if echart_features >= 3:
            return True

        return False


# ==================== 单例实例 ====================

_converter_instance = None


def get_chart_v3_converter() -> ChartV3ToEChartsConverter:
    """获取转换器单例"""
    global _converter_instance
    if _converter_instance is None:
        _converter_instance = ChartV3ToEChartsConverter()
    return _converter_instance
