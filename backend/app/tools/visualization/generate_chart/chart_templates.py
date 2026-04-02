"""
Chart Template Library

保留现有的硬编码优化配置，封装为可复用的模板。

模板库的优势：
- 针对特定场景深度优化（标签位置、颜色、格式）
- 配置稳定可靠
- 性能好（无需LLM决策）
"""
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
import structlog

logger = structlog.get_logger()


class ChartTemplate(Enum):
    """预定义的图表模板（v3.1扩展 + ECharts官方模板）"""
    # 现有模板
    VOCS_ANALYSIS = "vocs_analysis"
    PM_ANALYSIS = "pm_analysis"
    MULTI_INDICATOR_TIMESERIES = "multi_indicator_timeseries"
    REGIONAL_COMPARISON = "regional_comparison"
    GENERIC_TIMESERIES = "generic_timeseries"
    GENERIC_BAR = "generic_bar"
    GENERIC_PIE = "generic_pie"

    # v3.1 新增模板（气象）
    WIND_ROSE = "wind_rose"              # 风向玫瑰图（保留兼容）
    WEATHER_TIMESERIES = "weather_timeseries"  # 带风向指针的气象时序图
    PROFILE = "profile"                  # 边界层廓线图

    # v3.1 新增模板（空间）
    MAP = "map"                          # 地图
    HEATMAP = "heatmap"                  # 热力图

    # v3.1 新增模板（高级）
    RADAR = "radar"                      # 雷达图

    # ============================================
    # v3.3 新增：ECharts官方模板（从echarts-examples提取）
    # ============================================

    # 柱状图模板（3个）
    BAR_STACK_NEGATIVE = "bar_stack_negative"    # 堆叠负值柱状图
    BAR_POLAR_RADIAL = "bar_polar_radial"        # 极坐标径向柱状图
    BAR_WATERFALL = "bar_waterfall"              # 瀑布图

    # 散点图模板（3个）
    SCATTER_CLUSTERING = "scatter_clustering"    # 聚类散点图
    SCATTER_MATRIX = "scatter_matrix"            # 散点矩阵图
    SCATTER_REGRESSION = "scatter_regression"    # 回归散点图

    # 折线图模板（3个）
    LINE_AREA_GRADIENT = "line_area_gradient"    # 渐变面积折线图
    LINE_STEP = "line_step"                      # 阶梯折线图
    LINE_RACE = "line_race"                      # 排名竞赛图

    # 饼图模板（3个）
    PIE_ROSE_TYPE = "pie_rose_type"              # 玫瑰饼图
    PIE_NEST = "pie_nest"                        # 嵌套饼图
    PIE_DOUGHNUT = "pie_doughnut"                # 环形图

    # 仪表盘模板（3个）
    GAUGE_PROGRESS = "gauge_progress"            # 进度仪表盘
    GAUGE_STAGE = "gauge_stage"                  # 分段仪表盘
    GAUGE_RING = "gauge_ring"                    # 环形仪表盘

    # 关系图模板（2个）
    GRAPH_FORCE = "graph_force"                  # 力引导关系图
    GRAPH_CIRCULAR = "graph_circular"            # 环形布局关系图

    # 日历图模板（2个）
    CALENDAR_HEATMAP = "calendar_heatmap"        # 日历热力图
    CALENDAR_PIE = "calendar_pie"                # 日历饼图

    # 矩形树图模板（2个）
    TREEMAP_SIMPLE = "treemap_simple"            # 简单矩形树图
    TREEMAP_DRILL_DOWN = "treemap_drill_down"    # 下钻矩形树图

    # 桑基图模板（2个）
    SANKEY_SIMPLE = "sankey_simple"              # 简单桑基图
    SANKEY_VERTICAL = "sankey_vertical"          # 垂直桑基图


class ChartTemplateRegistry:
    """
    图表模板注册表

    管理所有预定义的图表模板，提供快速、优化的图表生成。
    """

    def __init__(self):
        self._templates: Dict[str, Callable] = {}
        self._register_builtin_templates()

    def register(self, template_id: str, generator_func: Callable):
        """
        注册模板生成函数

        Args:
            template_id: 模板ID（唯一标识）
            generator_func: 生成函数，接受 (data, **kwargs) 返回 Dict/List
        """
        self._templates[template_id] = generator_func
        logger.info("chart_template_registered", template_id=template_id)

    def generate(
        self,
        template_id: str,
        data: Any,
        **kwargs
    ) -> Dict[str, Any]:
        """
        使用模板生成图表

        Args:
            template_id: 模板ID
            data: 数据（格式取决于模板）
            **kwargs: 额外参数（如 title, station_name 等）

        Returns:
            图表配置（Visual对象或payload）

        Raises:
            ValueError: 模板不存在
        """
        if template_id not in self._templates:
            available = list(self._templates.keys())
            raise ValueError(
                f"未知模板: {template_id}. "
                f"可用模板: {available}"
            )

        generator = self._templates[template_id]

        try:
            result = generator(data, **kwargs)
            logger.info(
                "chart_template_generated",
                template_id=template_id,
                result_type=type(result).__name__
            )
            return result
        except Exception as e:
            logger.error(
                "chart_template_generation_failed",
                template_id=template_id,
                error=str(e),
                exc_info=True
            )
            raise

    def list_templates(self) -> List[str]:
        """列出所有已注册的模板ID"""
        return list(self._templates.keys())

    def register_dynamic(self, template_id: str, generator_func: Callable):
        """
        动态注册模板（运行时插件化）

        支持Agent或后续模块临时注入模板，实现模板的插件化扩展。

        Args:
            template_id: 模板ID（唯一标识）
            generator_func: 生成函数，签名: func(data: Any, **kwargs) -> Dict[str, Any]

        Example:
            def custom_scatter_3d(data, **kwargs):
                return {
                    "id": "custom_3d",
                    "type": "scatter3d",
                    "data": {"x": ..., "y": ..., "z": ...},
                    "meta": {...}
                }

            registry = get_chart_template_registry()
            registry.register_dynamic("custom_3d_scatter", custom_scatter_3d)
        """
        if template_id in self._templates:
            logger.warning(
                "dynamic_template_override",
                template_id=template_id,
                action="覆盖现有模板"
            )

        self.register(template_id, generator_func)
        logger.info(
            "dynamic_template_registered",
            template_id=template_id,
            total_templates=len(self._templates)
        )

    def unregister(self, template_id: str) -> bool:
        """
        注销模板

        Args:
            template_id: 要注销的模板ID

        Returns:
            是否成功注销
        """
        if template_id in self._templates:
            del self._templates[template_id]
            logger.info(
                "template_unregistered",
                template_id=template_id,
                remaining_templates=len(self._templates)
            )
            return True
        else:
            logger.warning("template_not_found", template_id=template_id)
            return False

    def list_templates_detailed(self) -> Dict[str, Dict[str, Any]]:
        """
        列出所有模板的详细信息

        Returns:
            模板ID到详细信息的映射
        """
        templates_info = {}
        for template_id in self._templates.keys():
            templates_info[template_id] = {
                "id": template_id,
                "registered": True,
                "generator": self._templates[template_id].__name__
            }
        return templates_info

    def _register_builtin_templates(self):
        """
        注册内置模板（v3.0标准格式）

        使用 app/utils/visualization.py 中的v3.0标准函数。
        """
        from app.utils.visualization import (
            generate_vocs_analysis_charts,
            generate_particulate_analysis_charts,
            generate_multi_indicator_timeseries_chart,
            generate_regional_comparison_chart,
            generate_timeseries_chart,
            generate_bar_chart,
            generate_pie_chart,
        )

        # ========================================
        # 1. VOCs分析模板（v3.0标准格式）
        # ========================================
        def vocs_analysis_wrapper(data: Dict[str, Any], **kwargs) -> List[Dict[str, Any]]:
            """
            VOCs分析模板 - v3.0标准格式

            输入数据格式:
            {
                "vocs_data": [...],  # VOCs组分数据
                "enterprise_data": [...]  # 企业数据
            }

            输出: ChartResponse对象列表
            """
            vocs_data = data.get("vocs_data", [])
            enterprise_data = data.get("enterprise_data", [])

            chart_responses = generate_vocs_analysis_charts(vocs_data, enterprise_data)
            # v3.1: 现在直接返回字典列表
            return chart_responses

        self.register(ChartTemplate.VOCS_ANALYSIS.value, vocs_analysis_wrapper)

        # ========================================
        # 2. 颗粒物分析模板（v3.0标准格式）
        # ========================================
        def pm_analysis_wrapper(data: Dict[str, Any], **kwargs) -> List[Dict[str, Any]]:
            """
            颗粒物分析模板 - v3.0标准格式

            输入数据格式:
            {
                "particulate_data": [...],  # 颗粒物组分数据
                "enterprise_data": [...]  # 企业数据
            }

            输出: ChartResponse对象列表
            """
            particulate_data = data.get("particulate_data", [])
            enterprise_data = data.get("enterprise_data", [])

            chart_responses = generate_particulate_analysis_charts(particulate_data, enterprise_data)
            # v3.1: 现在直接返回字典列表
            return chart_responses

        self.register(ChartTemplate.PM_ANALYSIS.value, pm_analysis_wrapper)

        # ========================================
        # 3. 多指标时序图模板（v3.0标准格式）
        # ========================================
        def multi_indicator_wrapper(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
            """
            多指标时序图模板 - v3.0标准格式

            输入数据格式:
            {
                "station_data": [...],  # 站点监测数据
                "weather_data": [...]  # 气象数据
            }

            输出: ChartResponse对象
            """
            station_data = data.get("station_data", [])
            weather_data = data.get("weather_data", [])
            pollutant = kwargs.get("pollutant", "O3")
            station_name = kwargs.get("station_name", "")
            venue_name = kwargs.get("venue_name", "")

            chart_response = generate_multi_indicator_timeseries_chart(
                station_data, weather_data, pollutant, station_name, venue_name
            )
            # v3.1: 现在直接返回字典
            return chart_response

        self.register(ChartTemplate.MULTI_INDICATOR_TIMESERIES.value, multi_indicator_wrapper)

        # ========================================
        # 4. 区域对比模板（v3.0标准格式）
        # ========================================
        def regional_comparison_wrapper(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
            """
            区域对比模板 - v3.0标准格式

            输入数据格式:
            {
                "station_data": [...],  # 目标站点数据
                "nearby_stations_data": {  # 周边站点数据
                    "站点A": [...],
                    "站点B": [...]
                }
            }

            输出: ChartResponse对象
            """
            station_data = data.get("station_data", [])
            nearby_stations_data = data.get("nearby_stations_data", {})
            station_name = kwargs.get("station_name", "目标站点")
            venue_name = kwargs.get("venue_name", "")

            chart_response = generate_regional_comparison_chart(
                station_data, nearby_stations_data, station_name, venue_name
            )
            # v3.1: 现在直接返回字典
            return chart_response

        self.register(ChartTemplate.REGIONAL_COMPARISON.value, regional_comparison_wrapper)

        # ========================================
        # 5-7. 通用模板（v3.0标准格式）
        # ========================================
        def generic_timeseries_wrapper(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
            """通用时序图模板 - v3.0标准格式"""
            title = kwargs.get("title", "时序对比图")
            x_axis_key = kwargs.get("x_axis_key", "time")
            y_axis_key = kwargs.get("y_axis_key", "value")
            series_name_key = kwargs.get("series_name_key", "series")
            meta = kwargs.get("meta", {})

            # 检查是否是空数据（带有_error标志）
            if isinstance(data, dict) and data.get("_empty_data"):
                error_msg = data.get("_error", "没有可用的时序数据")
                logger.warning("template_skipped_empty_data", template_id="generic_timeseries", error=error_msg)
                # 抛出一个包含错误信息的异常，而不是让下游处理
                raise ValueError(f"空数据无法生成时序图: {error_msg}")

            chart_response = generate_timeseries_chart(
                data_series=data,
                title=title,
                x_axis_key=x_axis_key,
                y_axis_key=y_axis_key,
                series_name_key=series_name_key,
                meta=meta
            )
            # v3.1: 现在直接返回字典
            return chart_response

        self.register(ChartTemplate.GENERIC_TIMESERIES.value, generic_timeseries_wrapper)

        def generic_bar_wrapper(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
            """通用柱状图模板 - v3.0标准格式"""
            title = kwargs.get("title", "柱状图")
            category_key = kwargs.get("category_key", "category")
            value_key = kwargs.get("value_key", "value")
            meta = kwargs.get("meta", {})

            # 检查是否是空数据（带有_error标志）
            if isinstance(data, dict) and data.get("_empty_data"):
                error_msg = data.get("_error", "没有可用的柱状图数据")
                logger.warning("template_skipped_empty_data", template_id="generic_bar", error=error_msg)
                raise ValueError(f"空数据无法生成柱状图: {error_msg}")

            chart_response = generate_bar_chart(
                data=data,
                title=title,
                category_key=category_key,
                value_key=value_key,
                meta=meta
            )
            # v3.1: 现在直接返回字典
            return chart_response

        self.register(ChartTemplate.GENERIC_BAR.value, generic_bar_wrapper)

        def generic_pie_wrapper(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
            """通用饼图模板 - v3.0标准格式"""
            title = kwargs.get("title", "饼图")
            name_key = kwargs.get("name_key", "name")
            value_key = kwargs.get("value_key", "value")
            meta = kwargs.get("meta", {})

            # 检查是否是空数据（带有_error标志）
            if isinstance(data, dict) and data.get("_empty_data"):
                error_msg = data.get("_error", "没有可用的饼图数据")
                logger.warning("template_skipped_empty_data", template_id="generic_pie", error=error_msg)
                raise ValueError(f"空数据无法生成饼图: {error_msg}")

            # 转换数据格式
            formatted_data = []
            for item in data:
                if isinstance(item, dict):
                    name = item.get(name_key, "Unknown")
                    value = item.get(value_key, 0)
                    formatted_data.append({"name": name, "value": value})

            chart_response = generate_pie_chart(
                data=formatted_data,
                title=title,
                meta=meta
            )
            # v3.1: 现在直接返回字典
            return chart_response

        self.register(ChartTemplate.GENERIC_PIE.value, generic_pie_wrapper)

        # ========================================
        # 别名注册：timeseries → generic_timeseries
        # ========================================
        self.register("timeseries", generic_timeseries_wrapper)
        logger.info("chart_template_alias_registered", alias="timeseries", target="generic_timeseries")

        # ========================================
        # 8. 风向玫瑰图模板（v3.1新增）
        # ========================================
        def wind_rose_wrapper(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
            """
            风向玫瑰图模板 - v3.1格式

            输入数据格式:
            [
                {"wind_speed": 3.5, "wind_direction": 45, "timestamp": "..."},
                {"wind_speed": 5.2, "wind_direction": 90, "timestamp": "..."},
                ...
            ]

            输出: Chart v3.1格式字典
            """
            title = kwargs.get("title", "风向玫瑰图")
            meta = kwargs.get("meta", {})

            # 检查数据是否包含必需字段
            if not data or not isinstance(data, list):
                raise ValueError("wind_rose模板需要列表数据")

            if not data:
                raise ValueError("wind_rose模板数据为空")

            first_item = data[0]
            required_fields = ["wind_speed", "wind_direction"]
            missing_fields = [f for f in required_fields if f not in first_item]

            if missing_fields:
                raise ValueError(
                    f"wind_rose模板需要数据包含{required_fields}字段，"
                    f"缺少: {missing_fields}"
                )

            # 处理风向风速数据，分组到8个方位
            sectors = {
                "N": {"direction": "N", "angle": 0, "speeds": [], "count": 0},
                "NE": {"direction": "NE", "angle": 45, "speeds": [], "count": 0},
                "E": {"direction": "E", "angle": 90, "speeds": [], "count": 0},
                "SE": {"direction": "SE", "angle": 135, "speeds": [], "count": 0},
                "S": {"direction": "S", "angle": 180, "speeds": [], "count": 0},
                "SW": {"direction": "SW", "angle": 225, "speeds": [], "count": 0},
                "W": {"direction": "W", "angle": 270, "speeds": [], "count": 0},
                "NW": {"direction": "NW", "angle": 315, "speeds": [], "count": 0}
            }

            # 分组数据
            for item in data:
                if not isinstance(item, dict):
                    continue

                direction = item.get("wind_direction")
                speed = item.get("wind_speed")

                if direction is None or speed is None:
                    continue

                # 转换为浮点数
                try:
                    direction = float(direction)
                    speed = float(speed)
                except (ValueError, TypeError):
                    continue

                # 判断方位
                if 337.5 <= direction or direction < 22.5:
                    sector_key = "N"
                elif 22.5 <= direction < 67.5:
                    sector_key = "NE"
                elif 67.5 <= direction < 112.5:
                    sector_key = "E"
                elif 112.5 <= direction < 157.5:
                    sector_key = "SE"
                elif 157.5 <= direction < 202.5:
                    sector_key = "S"
                elif 202.5 <= direction < 247.5:
                    sector_key = "SW"
                elif 247.5 <= direction < 292.5:
                    sector_key = "W"
                elif 292.5 <= direction < 337.5:
                    sector_key = "NW"
                else:
                    continue

                sectors[sector_key]["speeds"].append(speed)
                sectors[sector_key]["count"] += 1

            # 计算统计数据
            sectors_data = []
            total_count = sum(s["count"] for s in sectors.values())

            for key in ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]:
                sector = sectors[key]
                speeds = sector["speeds"]

                if speeds:
                    avg_speed = sum(speeds) / len(speeds)
                    max_speed = max(speeds)
                    frequency = sector["count"] / total_count if total_count > 0 else 0

                    # 风速分布
                    speed_dist = {"0-2": 0, "2-5": 0, "5-10": 0, "10+": 0}
                    for s in speeds:
                        if s < 2:
                            speed_dist["0-2"] += 1
                        elif s < 5:
                            speed_dist["2-5"] += 1
                        elif s < 10:
                            speed_dist["5-10"] += 1
                        else:
                            speed_dist["10+"] += 1

                    sectors_data.append({
                        "direction": sector["direction"],
                        "angle": sector["angle"],
                        "avg_speed": round(avg_speed, 2),
                        "max_speed": round(max_speed, 2),
                        "count": sector["count"],
                        "frequency": round(frequency, 3),
                        "speed_distribution": speed_dist
                    })
                else:
                    # 无数据的方向
                    sectors_data.append({
                        "direction": sector["direction"],
                        "angle": sector["angle"],
                        "avg_speed": 0,
                        "max_speed": 0,
                        "count": 0,
                        "frequency": 0,
                        "speed_distribution": {"0-2": 0, "2-5": 0, "5-10": 0, "10+": 0}
                    })

            # 构建Chart v3.1格式
            import uuid
            chart_dict = {
                "id": f"wind_rose_{uuid.uuid4().hex[:8]}",
                "type": "wind_rose",
                "title": title,
                "data": {
                    "sectors": sectors_data,
                    "legend": {
                        "N": "北风", "NE": "东北风", "E": "东风", "SE": "东南风",
                        "S": "南风", "SW": "西南风", "W": "西风", "NW": "西北风"
                    },
                    "statistics": {
                        "total_samples": len(data),
                        "avg_speed_overall": round(sum(s["avg_speed"] for s in sectors_data) / 8, 2),
                        "max_speed_overall": max(s["max_speed"] for s in sectors_data),
                        "dominant_direction": max(sectors_data, key=lambda x: x["frequency"])["direction"]
                    }
                },
                "meta": {
                    **meta,
                    "schema_version": "3.1",
                    "unit": "m/s",
                    "generator": "template:wind_rose",
                    "record_count": len(data)
                }
            }

            return chart_dict

        self.register(ChartTemplate.WIND_ROSE.value, wind_rose_wrapper)

        # ========================================
        # 9. 边界层廓线图模板（v3.1新增）
        # ========================================
        def profile_wrapper(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
            """
            边界层廓线图模板 - v3.1格式

            输入数据格式:
            [
                {"altitude": 0, "temperature": 25, "wind_speed": 2.0, ...},
                {"altitude": 100, "temperature": 24.5, "wind_speed": 3.5, ...},
                ...
            ]

            输出: Chart v3.1格式字典
            """
            title = kwargs.get("title", "边界层廓线图")
            elements = kwargs.get("elements", ["temperature", "wind_speed"])
            meta = kwargs.get("meta", {})

            if not data or not isinstance(data, list):
                raise ValueError("profile模板需要列表数据")

            if not data:
                raise ValueError("profile模板数据为空")

            first_item = data[0]
            altitude_fields = ["altitude", "height"]
            has_altitude = any(f in first_item for f in altitude_fields)

            if not has_altitude:
                raise ValueError("profile模板需要数据包含altitude或height字段")

            # 提取高度数据
            altitudes = []
            altitude_key = None

            # 确定使用哪个高度字段
            for key in altitude_fields:
                if key in first_item:
                    altitude_key = key
                    break

            # 提取数据
            elements_data = {}
            for item in data:
                if not isinstance(item, dict):
                    continue

                alt = item.get(altitude_key)
                if alt is None:
                    continue

                try:
                    alt = float(alt)
                except (ValueError, TypeError):
                    continue

                if alt not in altitudes:
                    altitudes.append(alt)

                # 提取元素数据
                for elem in elements:
                    if elem not in elements_data:
                        elements_data[elem] = {}

                    value = item.get(elem)
                    if value is not None:
                        try:
                            elements_data[elem][alt] = float(value)
                        except (ValueError, TypeError):
                            pass

            # 排序高度
            altitudes.sort()

            # 构建elements列表
            elements_list = []
            element_names = {
                "temperature": "温度",
                "wind_speed": "风速",
                "humidity": "湿度",
                "pressure": "气压"
            }
            element_units = {
                "temperature": "°C",
                "wind_speed": "m/s",
                "humidity": "%",
                "pressure": "hPa"
            }

            for elem, data_map in elements_data.items():
                elements_list.append({
                    "name": element_names.get(elem, elem),
                    "unit": element_units.get(elem, ""),
                    "data": [data_map.get(alt) for alt in altitudes]
                })

            # 构建Chart v3.1格式
            import uuid
            chart_dict = {
                "id": f"profile_{uuid.uuid4().hex[:8]}",
                "type": "profile",
                "title": title,
                "data": {
                    "altitudes": altitudes,
                    "elements": elements_list
                },
                "meta": {
                    **meta,
                    "schema_version": "3.1",
                    "generator": "template:profile",
                    "record_count": len(data),
                    "altitude_range": f"{min(altitudes)}-{max(altitudes)}m"
                }
            }

            return chart_dict

        self.register(ChartTemplate.PROFILE.value, profile_wrapper)

        # ========================================
        # 10. 地图模板（v3.1新增）
        # ========================================
        def map_wrapper(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
            """
            地图模板 - v3.1格式（高德地图）

            输入数据格式:
            [
                {"longitude": 114.05, "latitude": 22.54, "name": "站点A", "value": 35, ...},
                {"longitude": 114.06, "latitude": 22.55, "name": "站点B", "value": 42, ...},
                ...
            ]

            输出: Chart v3.1格式字典
            """
            title = kwargs.get("title", "站点分布地图")
            map_center = kwargs.get("map_center", None)
            zoom = kwargs.get("zoom", 12)
            layer_types = kwargs.get("layer_types", ["marker"])
            meta = kwargs.get("meta", {})

            if not data or not isinstance(data, list):
                raise ValueError("map模板需要列表数据")

            if not data:
                raise ValueError("map模板数据为空")

            first_item = data[0]
            required_fields = ["longitude", "latitude"]
            missing_fields = [f for f in required_fields if f not in first_item]

            if missing_fields:
                raise ValueError(
                    f"map模板需要数据包含{required_fields}字段，"
                    f"缺少: {missing_fields}"
                )

            # 计算地图中心（如果未指定）
            if map_center is None:
                lngs = [item.get("longitude") for item in data if item.get("longitude") is not None]
                lats = [item.get("latitude") for item in data if item.get("latitude") is not None]

                if lngs and lats:
                    map_center = {
                        "lng": sum(lngs) / len(lngs),
                        "lat": sum(lats) / len(lats)
                    }
                else:
                    map_center = {"lng": 114.05, "lat": 22.54}  # 默认深圳

            # 构建标记点数据
            markers = []
            for item in data:
                if not isinstance(item, dict):
                    continue

                lng = item.get("longitude")
                lat = item.get("latitude")

                if lng is None or lat is None:
                    continue

                marker = {
                    "lng": lng,
                    "lat": lat,
                    "name": item.get("name", item.get("station_name", "站点")),
                }

                # 可选字段
                if "value" in item:
                    marker["value"] = item["value"]
                if "pollutant" in item:
                    marker["pollutant"] = item["pollutant"]
                if "industry" in item:
                    marker["industry"] = item["industry"]
                if "distance" in item:
                    marker["distance"] = item["distance"]

                markers.append(marker)

            # 构建Chart v3.1格式
            import uuid
            chart_dict = {
                "id": f"map_{uuid.uuid4().hex[:8]}",
                "type": "map",
                "title": title,
                "data": {
                    "map_center": map_center,
                    "zoom": zoom,
                    "layers": [
                        {
                            "type": "marker",
                            "data": markers,
                            "visible": True
                        }
                    ]
                },
                "meta": {
                    **meta,
                    "schema_version": "3.1",
                    "generator": "template:map",
                    "record_count": len(data),
                    "marker_count": len(markers)
                }
            }

            return chart_dict

        self.register(ChartTemplate.MAP.value, map_wrapper)

        # ========================================
        # 11. 热力图模板（v3.1新增）
        # ========================================
        def heatmap_wrapper(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
            """
            热力图模板 - v3.1格式

            输入数据格式:
            [
                {"longitude": 114.05, "latitude": 22.54, "value": 45.2, ...},
                {"longitude": 114.06, "latitude": 22.55, "value": 32.8, ...},
                ...
            ]

            输出: Chart v3.1格式字典
            """
            title = kwargs.get("title", "空间分布热力图")
            value_field = kwargs.get("value_field", "value")
            meta = kwargs.get("meta", {})

            if not data or not isinstance(data, list):
                raise ValueError("heatmap模板需要列表数据")

            if not data:
                raise ValueError("heatmap模板数据为空")

            first_item = data[0]
            required_fields = ["longitude", "latitude", value_field]
            missing_fields = [f for f in required_fields if f not in first_item]

            if missing_fields:
                raise ValueError(
                    f"heatmap模板需要数据包含{required_fields}字段，"
                    f"缺少: {missing_fields}"
                )

            # 构建热力点数据
            points = []
            for item in data:
                if not isinstance(item, dict):
                    continue

                lng = item.get("longitude")
                lat = item.get("latitude")
                value = item.get(value_field)

                if lng is None or lat is None or value is None:
                    continue

                try:
                    points.append({
                        "lng": float(lng),
                        "lat": float(lat),
                        "value": float(value)
                    })
                except (ValueError, TypeError):
                    continue

            # 构建Chart v3.1格式
            import uuid
            chart_dict = {
                "id": f"heatmap_{uuid.uuid4().hex[:8]}",
                "type": "heatmap",
                "title": title,
                "data": {
                    "points": points
                },
                "meta": {
                    **meta,
                    "schema_version": "3.1",
                    "generator": "template:heatmap",
                    "record_count": len(data),
                    "point_count": len(points),
                    "value_range": {
                        "min": min(p["value"] for p in points) if points else 0,
                        "max": max(p["value"] for p in points) if points else 0
                    }
                }
            }

            return chart_dict

        self.register(ChartTemplate.HEATMAP.value, heatmap_wrapper)

        # ========================================
        # 12. 雷达图模板（v3.1新增）
        # ========================================
        def radar_wrapper(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
            """
            雷达图模板 - v3.1格式

            输入数据格式:
            {
                "dimensions": ["维度1", "维度2", "维度3", "维度4", "维度5"],
                "series": [
                    {"name": "系列1", "values": [80, 90, 70, 85, 75]},
                    {"name": "系列2", "values": [70, 85, 75, 80, 90]}
                ]
            }

            输出: Chart v3.1格式字典
            """
            title = kwargs.get("title", "雷达图")
            meta = kwargs.get("meta", {})

            if not isinstance(data, dict):
                raise ValueError("radar模板需要字典数据")

            required_fields = ["dimensions", "series"]
            missing_fields = [f for f in required_fields if f not in data]

            if missing_fields:
                raise ValueError(
                    f"radar模板需要数据包含{required_fields}字段，"
                    f"缺少: {missing_fields}"
                )

            # 构建Chart v3.1格式
            import uuid
            chart_dict = {
                "id": f"radar_{uuid.uuid4().hex[:8]}",
                "type": "radar",
                "title": title,
                "data": {
                    "dimensions": data["dimensions"],
                    "series": data["series"]
                },
                "meta": {
                    **meta,
                    "schema_version": "3.1",
                    "generator": "template:radar",
                    "dimension_count": len(data["dimensions"]),
                    "series_count": len(data["series"])
                }
            }

            return chart_dict

        self.register(ChartTemplate.RADAR.value, radar_wrapper)

        # ========================================
        # 13. 带风向指针的气象时序图模板（v3.2新增）
        # ========================================
        def weather_timeseries_wrapper(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
            """
            带风向指针的气象时序图 - 集成风速曲线和风向指针
            
            将风向玫瑰图的信息集成到时序图中，在风速曲线上显示风向箭头。
            
            输入数据格式:
            [
                {
                    "time": "2025-01-01 00:00",
                    "wind_speed": 3.5,           # 风速 (必需)
                    "wind_direction": 45,        # 风向角度 (必需)
                    "temperature": 25.0,         # 温度 (可选)
                    "humidity": 65,              # 湿度 (可选)
                    "pressure": 1013.25          # 气压 (可选)
                },
                ...
            ]
            
            输出: Chart v3.1格式字典，type="weather_timeseries"
            前端将在风速曲线上以箭头标记显示风向
            """
            title = kwargs.get("title", "气象要素时序变化（含风向）")
            show_elements = kwargs.get("show_elements", ["wind_speed", "temperature", "humidity"])
            meta = kwargs.get("meta", {})
            station_name = kwargs.get("station_name", "")
            
            if not data or not isinstance(data, list):
                raise ValueError("weather_timeseries模板需要列表数据")
            
            first_item = data[0]
            required_fields = ["time", "wind_speed", "wind_direction"]
            missing_fields = [f for f in required_fields if f not in first_item]
            
            if missing_fields:
                raise ValueError(
                    f"weather_timeseries模板需要数据包含{required_fields}字段，"
                    f"缺少: {missing_fields}"
                )
            
            # 提取时间轴
            x_data = []
            for item in data:
                time_val = item.get("time") or item.get("timestamp") or item.get("datetime")
                if time_val:
                    # 简化时间显示
                    if isinstance(time_val, str) and len(time_val) > 10:
                        time_val = time_val[5:16]  # MM-DD HH:MM
                    x_data.append(time_val)
            
            # 构建数据系列
            series = []
            wind_data = []  # 风速+风向数据（特殊处理）
            
            # 字段映射
            field_mapping = {
                "wind_speed": {"name": "风速", "unit": "m/s", "yAxisIndex": 0},
                "temperature": {"name": "温度", "unit": "°C", "yAxisIndex": 1},
                "humidity": {"name": "相对湿度", "unit": "%", "yAxisIndex": 1},
                "pressure": {"name": "气压", "unit": "hPa", "yAxisIndex": 1},
                "cloud_cover": {"name": "云量", "unit": "%", "yAxisIndex": 1},
                "precipitation": {"name": "降水", "unit": "mm", "yAxisIndex": 1},
            }
            
            # 风速+风向数据（带箭头标记）
            for item in data:
                ws = item.get("wind_speed") or item.get("wind_speed_10m") or 0
                wd = item.get("wind_direction") or item.get("wind_direction_10m") or 0
                try:
                    wind_data.append({
                        "value": float(ws),
                        "direction": float(wd)
                    })
                except (ValueError, TypeError):
                    wind_data.append({"value": 0, "direction": 0})
            
            series.append({
                "name": "风速",
                "type": "wind",  # 特殊类型，前端会特殊处理
                "data": wind_data,
                "unit": "m/s",
                "yAxisIndex": 0
            })
            
            # 其他气象要素
            for field in show_elements:
                if field == "wind_speed":
                    continue  # 已处理
                
                if field not in field_mapping:
                    continue
                
                field_info = field_mapping[field]
                values = []
                
                for item in data:
                    val = item.get(field)
                    if val is not None:
                        try:
                            values.append(float(val))
                        except (ValueError, TypeError):
                            values.append(None)
                    else:
                        values.append(None)
                
                # 只添加有数据的系列
                if any(v is not None for v in values):
                    series.append({
                        "name": field_info["name"],
                        "type": "line",
                        "data": values,
                        "unit": field_info["unit"],
                        "yAxisIndex": field_info["yAxisIndex"]
                    })
            
            # 计算风向统计
            wind_directions = [item.get("wind_direction", 0) for item in data]
            valid_directions = [d for d in wind_directions if d is not None]
            
            # 主导风向计算
            direction_names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            direction_counts = [0] * 8
            for d in valid_directions:
                try:
                    idx = int((float(d) + 22.5) % 360 / 45)
                    direction_counts[idx] += 1
                except (ValueError, TypeError):
                    pass
            
            dominant_idx = direction_counts.index(max(direction_counts)) if direction_counts else 0
            dominant_direction = direction_names[dominant_idx]
            
            # 构建Chart v3.1格式
            import uuid
            
            full_title = title
            if station_name:
                full_title = f"{station_name} - {title}"
            
            chart_dict = {
                "id": f"weather_ts_{uuid.uuid4().hex[:8]}",
                "type": "weather_timeseries",
                "title": full_title,
                "data": {
                    "x": x_data,
                    "series": series,
                    "wind_statistics": {
                        "dominant_direction": dominant_direction,
                        "avg_speed": round(sum(w["value"] for w in wind_data) / len(wind_data), 1) if wind_data else 0,
                        "max_speed": round(max(w["value"] for w in wind_data), 1) if wind_data else 0,
                        "direction_distribution": {
                            direction_names[i]: direction_counts[i] 
                            for i in range(8)
                        }
                    }
                },
                "meta": {
                    **meta,
                    "schema_version": "3.1",
                    "generator": "template:weather_timeseries",
                    "record_count": len(data),
                    "station_name": station_name,
                    "dominant_wind_direction": dominant_direction,
                    "layout_hint": "wide"
                }
            }
            
            return chart_dict
        
        self.register(ChartTemplate.WEATHER_TIMESERIES.value, weather_timeseries_wrapper)

        # ========================================
        # 注册 ECharts 扩展模板（v3.3新增）
        # ========================================
        try:
            from app.tools.visualization.generate_chart.chart_templates_extended import ECHARTS_EXTENDED_TEMPLATES

            for template_id, template_func in ECHARTS_EXTENDED_TEMPLATES.items():
                self.register(template_id, template_func)

            logger.info(
                "echarts_extended_templates_registered",
                count=len(ECHARTS_EXTENDED_TEMPLATES),
                templates=list(ECHARTS_EXTENDED_TEMPLATES.keys())
            )
        except ImportError as e:
            logger.warning(
                "echarts_extended_templates_import_failed",
                error=str(e),
                message="ECharts扩展模板将不可用"
            )

        logger.info(
            "builtin_chart_templates_registered",
            count=len(self._templates),
            templates=list(self._templates.keys())
        )


# 全局模板注册表实例（单例）
_global_template_registry: Optional[ChartTemplateRegistry] = None


def get_chart_template_registry() -> ChartTemplateRegistry:
    """获取全局图表模板注册表（单例）"""
    global _global_template_registry

    if _global_template_registry is None:
        _global_template_registry = ChartTemplateRegistry()

    return _global_template_registry
