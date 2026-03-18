"""
统一图表数据转换器 v2.0.2 - UDF v2.0 + Chart v3.1

本模块是图表数据转换的核心入口，集成了所有专业的转换器：
- PMF转换器 (PMFChartConverter)
- OBM转换器 (OBMChartConverter)
- VOCs转换器 (VOCsChartConverter)
- 气象转换器 (MeteorologyChartConverter)
- 3D图表转换器 (D3ChartConverter)
- 地图转换器 (MapChartConverter)

遵循最新的UDF v2.0数据规范和Chart v3.1图表规范。

设计原则：
- 使用统一的字段映射系统（data_standardizer）
- 模块化架构，每个转换器独立负责特定数据类型
- 简洁的API，自动检测数据类型
- 完全移除冗余代码

版本历史：
- v3.1: 初始版本（4422行，超长文件）
- v2.0: 重构版本，模块化拆分，移除冗余代码
- v2.0.2: 修复空气质量数据转换，使用统一字段映射

重构时间: 2025-11-20
"""

from typing import Any, Dict, List, Optional, Union
import structlog

from app.utils.chart_converters.pmf_converter import PMFChartConverter
from app.utils.chart_converters.obm_converter import OBMChartConverter
from app.utils.chart_converters.vocs_converter import VOCsChartConverter
from app.utils.chart_converters.meteorology_converter import MeteorologyChartConverter
from app.utils.chart_converters.d3_converter import D3ChartConverter
from app.utils.chart_converters.map_converter import MapChartConverter

logger = structlog.get_logger()


class ChartDataConverter:
    """统一图表数据转换器

    集成所有专业转换器，提供统一的图表数据转换接口
    """

    def __init__(self):
        """初始化转换器"""
        self.pmf_converter = PMFChartConverter()
        self.obm_converter = OBMChartConverter()
        self.vocs_converter = VOCsChartConverter()
        self.meteorology_converter = MeteorologyChartConverter()
        self.d3_converter = D3ChartConverter()
        self.map_converter = MapChartConverter()

        logger.info("ChartDataConverter initialized with all converters")

    # ====================
    # 公共转换方法
    # ====================

    def convert_pmf_result(
        self,
        pmf_result: Union[Any, List[Any], Dict[str, Any]],
        chart_type: str = "pie",
        **kwargs
    ) -> Dict[str, Any]:
        """转换PMF结果为图表数据

        Args:
            pmf_result: PMF分析结果
            chart_type: 图表类型（pie, bar, timeseries）
            **kwargs: 额外参数

        Returns:
            图表数据
        """
        return self.pmf_converter.convert_to_chart(pmf_result, chart_type, **kwargs)

    def convert_obm_result(
        self,
        obm_result: Union[Any, List[Any], Dict[str, Any]],
        chart_type: str = "bar",
        **kwargs
    ) -> Dict[str, Any]:
        """转换OBM结果为图表数据

        Args:
            obm_result: OBM/OFP分析结果
            chart_type: 图表类型（pie, bar, radar）
            **kwargs: 额外参数

        Returns:
            图表数据
        """
        return self.obm_converter.convert_to_chart(obm_result, chart_type, **kwargs)

    def convert_vocs_data(
        self,
        data: Union[List[Any], Dict[str, Any]],
        chart_type: str = "timeseries",
        **kwargs
    ) -> Dict[str, Any]:
        """转换VOCs数据为图表数据

        Args:
            data: VOCs数据
            chart_type: 图表类型（timeseries, pie, bar）
            **kwargs: 额外参数

        Returns:
            图表数据
        """
        return self.vocs_converter.convert_to_chart(data, chart_type, **kwargs)

    def convert_particulate_unified_data(
        self,
        data: Union[List[Any], Dict[str, Any]],
        chart_type: str = "pie",
        **kwargs
    ) -> Dict[str, Any]:
        """转换统一颗粒物数据为图表数据

        适用场景：
        - 颗粒物组分饼图：展示各组分占比（SO4, NO3, NH4, OC, EC等）
        - 颗粒物堆叠时序图：展示各组分随时间变化（双Y轴：左侧离子堆叠，右侧PM2.5曲线）
        - 颗粒物柱状图：多站点/多时刻组分对比

        数据格式（UnifiedParticulateData）：
        {
            "station_code": "ZX001",
            "station_name": "肇庆莲花山",
            "timestamp": "2025-01-01 08:00:00",
            "unit": "ug/m3",
            "components": {"SO4": 5.2, "NO3": 3.8, "NH4": 2.1, "OC": 8.5, "EC": 2.3, ...},
            "qc_flag": "A",
            "metadata": {...}
        }

        Args:
            data: 统一颗粒物数据
            chart_type: 图表类型（pie, bar, timeseries, line, stacked_timeseries）
            **kwargs: 额外参数（selected_components, station_name, title等）

        Returns:
            图表数据（Chart v3.1格式）
        """
        logger.info(
            "particulate_unified_conversion_start",
            chart_type=chart_type,
            record_count=len(data) if isinstance(data, list) else 1
        )

        # 处理输入数据格式
        records = []
        if isinstance(data, dict):
            if "data" in data:
                records = data["data"]
            elif "components" in data:
                # 单条记录
                records = [data]
        elif isinstance(data, list):
            records = data
        else:
            records = [data] if data else []

        if not records:
            return {"error": "颗粒物数据为空"}

        # 获取选中的组分（默认为None，表示所有组分）
        selected_components = kwargs.pop("selected_components", None)

        # 获取站点名称
        station_name = kwargs.get("station_name")
        if not station_name and records:
            station_name = records[0].get("station_name", records[0].get("station_code", "Unknown"))

        # 根据图表类型路由
        if chart_type == "pie":
            return self._generate_particulate_pie(records, selected_components, station_name, **kwargs)
        elif chart_type == "carbon_stacked_bar":
            return self._generate_carbon_stacked_bar(records, station_name, **kwargs)
        elif chart_type == "stacked_timeseries":
            # 堆叠时序图（双Y轴：左侧离子堆叠，右侧PM2.5曲线）
            return self._generate_particulate_stacked_timeseries(records, selected_components, station_name, **kwargs)
        elif chart_type in ["bar", "timeseries", "line"]:
            return self._generate_particulate_timeseries(records, selected_components, station_name, chart_type, **kwargs)

        return {"error": f"不支持的颗粒物图表类型: {chart_type}"}

    def _generate_particulate_pie(
        self,
        records: List[Dict],
        selected_components: Optional[List[str]],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成颗粒物组分饼图

        Args:
            records: 数据记录列表
            selected_components: 选中的组分列表
            station_name: 站点名称
            **kwargs: 额外参数

        Returns:
            饼图数据
        """
        from collections import defaultdict

        # 收集所有组分数据（多记录聚合）
        component_values = defaultdict(list)

        for record in records:
            if not isinstance(record, dict):
                continue
            components = record.get("components", {})
            if isinstance(components, dict):
                for comp_name, comp_value in components.items():
                    try:
                        component_values[comp_name].append(float(comp_value))
                    except (ValueError, TypeError):
                        pass

        # 计算平均值
        pie_data = []
        for comp_name, values in component_values.items():
            if values:
                avg_value = sum(values) / len(values)
                # 如果指定了选中组分，只显示选中的
                if selected_components is None or comp_name in selected_components:
                    pie_data.append({
                        "name": comp_name,
                        "value": round(avg_value, 3)
                    })

        # 按值排序
        pie_data = sorted(pie_data, key=lambda x: x["value"], reverse=True)

        # 限制最多显示10个组分
        if len(pie_data) > 10:
            other_sum = sum(item["value"] for item in pie_data[10:])
            pie_data = pie_data[:10]
            pie_data.append({"name": "其他", "value": round(other_sum, 3)})

        # 标题
        title = kwargs.get("title", f"{station_name}颗粒物组分分布")

        # 构建meta信息
        meta = {
            "unit": "μg/m³",
            "data_source": "particulate_unified",
            "station_name": station_name,
            "record_count": len(records),
            "components_count": len(pie_data),
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        chart_id = f"particulate_pie_{station_name}" if station_name else "particulate_pie"

        return {
            "id": chart_id,
            "type": "pie",
            "title": title,
            "data": pie_data,
            "meta": meta
        }

    def _generate_particulate_stacked_timeseries(
        self,
        records: List[Dict],
        selected_components: Optional[List[str]],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成颗粒物组分堆叠时序图（双Y轴）

        图表特性：
        - 主Y轴（左）：离子组分堆叠面积图（SO4, NO3, NH4, OC, EC等）
        - 右Y轴：PM2.5浓度曲线（如果有PM2.5数据）

        数据字段要求：
        - 必需：components字段包含离子数据（SO4, NO3, NH4等）
        - 可选：components中包含PM2.5或顶层字段PM2_5

        Args:
            records: 数据记录列表
            selected_components: 选中的离子组分列表（None表示所有）
            station_name: 站点名称
            **kwargs: 额外参数

        Returns:
            堆叠时序图数据（Chart v3.1格式，双Y轴）
        """
        from collections import defaultdict

        # 按时间分组：{timestamp: {component: value}}
        time_data = defaultdict(dict)
        all_timestamps = []
        all_components = set()
        pm25_data = []  # PM2.5数据

        # 定义常见的离子组分（排除PM2.5）
        ion_components = ["SO4", "NO3", "NH4", "OC", "EC", "Cl", "K", "Ca", "Na", "Mg"]

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取时间戳
            timestamp = record.get("timestamp") or record.get("time_point") or record.get("DataTime")
            if not timestamp:
                continue
            all_timestamps.append(timestamp)

            # 提取离子组分数据
            components = record.get("components", {})
            if isinstance(components, dict):
                for comp_name, comp_value in components.items():
                    # 排除PM2.5作为离子组分
                    if comp_name in ["PM2_5", "PM2.5"]:
                        try:
                            pm25_data.append({"timestamp": timestamp, "value": float(comp_value)})
                        except (ValueError, TypeError):
                            pass
                        continue

                    # 如果指定了选中组分，只显示选中的
                    if selected_components is None or comp_name in selected_components:
                        all_components.add(comp_name)
                        try:
                            time_data[timestamp][comp_name] = float(comp_value)
                        except (ValueError, TypeError):
                            time_data[timestamp][comp_name] = None

            # 检查顶层是否有PM2.5字段
            pm25_value = record.get("PM2_5") or record.get("PM2.5")
            if pm25_value is not None:
                try:
                    pm25_data.append({"timestamp": timestamp, "value": float(pm25_value)})
                except (ValueError, TypeError):
                    pass

        # 排序时间点
        time_points = sorted(all_timestamps)
        if not time_points:
            return {"error": "颗粒物数据缺少时间字段"}

        # 构建堆叠面积图数据
        component_names = sorted(list(all_components))

        # 颜色映射（常用组分颜色）
        color_map = {
            "SO4": "#5470c6",
            "NO3": "#91cc75",
            "NH4": "#fac858",
            "OC": "#ee6666",
            "EC": "#73c0de",
            "Cl": "#3ba272",
            "K": "#fc8452",
            "Mg": "#9a60b4",
            "Na": "#ea7ccc",
            "Ca": "#ff9f7f"
        }

        # 构建series数组（堆叠面积图）
        series_stacked = []
        for comp_name in component_names:
            values = []
            for timestamp in time_points:
                value = time_data[timestamp].get(comp_name)
                values.append(value)

            series_stacked.append({
                "name": comp_name,
                "data": values,
                "type": "line",
                "stack": "total",  # 堆叠
                "areaStyle": {},   # 面积图
                "smooth": True,
                "itemStyle": {"color": color_map.get(comp_name, "#999999")},
                "emphasis": {"focus": "series"}
            })

        # 构建PM2.5曲线数据（右侧Y轴）
        series_pm25 = []
        pm25_timestamps = [item["timestamp"] for item in pm25_data]
        pm25_values = []
        for timestamp in time_points:
            # 查找对应时间的PM2.5值
            value = None
            for item in pm25_data:
                if item["timestamp"] == timestamp:
                    value = item["value"]
                    break
            pm25_values.append(value)

        if any(v is not None for v in pm25_values):
            series_pm25 = [{
                "name": "PM2.5",
                "data": pm25_values,
                "type": "line",
                "yAxisIndex": 1,  # 右Y轴
                "smooth": True,
                "itemStyle": {"color": "#E74C3C"},
                "lineStyle": {"width": 3},
                "symbol": "circle",
                "symbolSize": 8
            }]

        # 合并所有series
        all_series = series_stacked + series_pm25

        # 构建ECharts option格式
        option = {
            "x": time_points,
            "series": all_series,
            "yAxis": [
                {
                    "type": "value",
                    "name": "离子浓度 (μg/m³)",
                    "position": "left",
                    "axisLine": {"show": True, "lineStyle": {"color": "#5470c6"}},
                    "axisLabel": {"color": "#5470c6"},
                    "splitLine": {"show": True}
                },
                {
                    "type": "value",
                    "name": "PM2.5 (μg/m³)",
                    "position": "right",
                    "offset": 0,
                    "axisLine": {"show": True, "lineStyle": {"color": "#E74C3C"}},
                    "axisLabel": {"color": "#E74C3C"},
                    "splitLine": {"show": False}
                }
            ],
            "legend": {
                "data": component_names + (["PM2.5"] if series_pm25 else []),
                "top": 0
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "cross"}
            }
        }

        # 标题
        title = kwargs.get("title", f"{station_name}颗粒物组分堆叠时序变化")

        # 构建meta信息
        meta = {
            "unit": "μg/m³",
            "data_source": "particulate_unified",
            "station_name": station_name,
            "record_count": len(records),
            "time_points": len(time_points),
            "components": component_names,
            "has_pm25_curve": len(series_pm25) > 0,
            "schema_version": "3.1",
            "chart_type": "stacked_timeseries",
            "features": {
                "stacked_area": True,
                "dual_y_axis": len(series_pm25) > 0,
                "show_pm25_curve": len(series_pm25) > 0
            }
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        chart_id = f"particulate_stacked_timeseries_{station_name}" if station_name else "particulate_stacked_timeseries"

        return {
            "id": chart_id,
            "type": "stacked_timeseries",
            "title": title,
            "data": option,
            "meta": meta
        }

    def _generate_carbon_stacked_bar(
        self,
        records: List[Dict],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成碳组分堆积图（带PM2.5和EC/OC曲线）

        图表特性：
        - 主Y轴：SOC、POC、EC堆积柱状图（时序）
        - 右Y轴1：PM2.5浓度曲线
        - 右Y轴2：EC/OC比值曲线（虚线）

        数据字段要求：
        - 必需：SOC, POC, EC（碳组分浓度）
        - 可选：PM2.5, EC_OC（叠加曲线数据）

        Args:
            records: 数据记录列表（包含SOC, POC, EC, PM2.5, EC_OC字段）
            station_name: 站点名称
            **kwargs: 额外参数

        Returns:
            碳组分堆积图数据（Chart v3.1格式，支持双Y轴）
        """
        from collections import defaultdict
        import numpy as np

        # 按时间分组：{timestamp: {SOC, POC, EC, PM2.5, EC_OC}}
        time_data = defaultdict(dict)
        all_timestamps = []

        carbon_fields = ["SOC", "POC", "EC"]
        optional_fields = ["PM2_5", "PM2.5", "EC_OC", "EC_OC_ratio"]

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取时间戳
            timestamp = record.get("timestamp") or record.get("time_point") or record.get("DataTime")
            if not timestamp:
                # 如果没有时间戳，使用索引
                continue
            all_timestamps.append(timestamp)

            # 提取碳组分数据
            for field in carbon_fields:
                value = record.get(field)
                if value is not None:
                    try:
                        time_data[timestamp][field] = float(value)
                    except (ValueError, TypeError):
                        time_data[timestamp][field] = None

            # 提取可选字段
            for field in optional_fields:
                value = record.get(field)
                if value is not None:
                    try:
                        # 统一字段名映射
                        if field in ["PM2_5", "PM2.5"]:
                            time_data[timestamp]["PM2_5"] = float(value)
                        elif field in ["EC_OC", "EC_OC_ratio"]:
                            time_data[timestamp]["EC_OC"] = float(value)
                    except (ValueError, TypeError):
                        pass

        # 排序时间点
        time_points = sorted(all_timestamps)
        if not time_points:
            return {"error": "碳组分数据缺少时间字段"}

        # 构建堆积柱状图数据
        # x轴为时间点
        # series: [SOC数据, POC数据, EC数据]
        series_stacked = []
        series_pm25 = []
        series_ecoc = []

        for timestamp in time_points:
            data = time_data.get(timestamp, {})

            # 碳组分数据（处理NaN）
            soc_val = data.get("SOC")
            poc_val = data.get("POC")
            ec_val = data.get("EC")

            series_stacked.append({
                "SOC": round(soc_val, 3) if soc_val is not None else None,
                "POC": round(poc_val, 3) if poc_val is not None else None,
                "EC": round(ec_val, 3) if ec_val is not None else None
            })

            # PM2.5数据
            pm25_val = data.get("PM2_5")
            series_pm25.append(round(pm25_val, 3) if pm25_val is not None else None)

            # EC/OC数据
            ecoc_val = data.get("EC_OC")
            series_ecoc.append(round(ecoc_val, 3) if ecoc_val is not None else None)

        # 构建ECharts option格式
        # 堆积图：使用 stacked: true + stack 相同的值
        # 双Y轴：使用 yAxisIndex 指定不同的Y轴

        option = {
            "x": time_points,
            "series": [
                # SOC堆积柱
                {
                    "name": "SOC",
                    "data": [s["SOC"] for s in series_stacked],
                    "type": "bar",
                    "stack": "carbon",
                    "itemStyle": {"color": "#2E8B57"}
                },
                # POC堆积柱
                {
                    "name": "POC",
                    "data": [s["POC"] for s in series_stacked],
                    "type": "bar",
                    "stack": "carbon",
                    "itemStyle": {"color": "#87CEEB"}
                },
                # EC堆积柱
                {
                    "name": "EC",
                    "data": [s["EC"] for s in series_stacked],
                    "type": "bar",
                    "stack": "carbon",
                    "itemStyle": {"color": "#2F4F4F"}
                },
                # PM2.5曲线（右Y轴1）
                {
                    "name": "PM2.5",
                    "data": series_pm25,
                    "type": "line",
                    "yAxisIndex": 1,
                    "smooth": True,
                    "itemStyle": {"color": "#E74C3C"},
                    "lineStyle": {"width": 2},
                    "symbol": "circle",
                    "symbolSize": 6
                },
                # EC/OC曲线（右Y轴2）
                {
                    "name": "EC/OC",
                    "data": series_ecoc,
                    "type": "line",
                    "yAxisIndex": 2,
                    "smooth": False,
                    "lineStyle": {"type": "dashed", "width": 2},
                    "itemStyle": {"color": "#8E44AD"},
                    "symbol": "square",
                    "symbolSize": 5
                }
            ],
            "yAxis": [
                {
                    "type": "value",
                    "name": "碳组分浓度 (μg/m³)",
                    "position": "left",
                    "axisLine": {"show": True, "lineStyle": {"color": "#2E8B57"}},
                    "axisLabel": {"color": "#2E8B57"}
                },
                {
                    "type": "value",
                    "name": "PM2.5浓度 (μg/m³)",
                    "position": "right",
                    "offset": 0,
                    "axisLine": {"show": True, "lineStyle": {"color": "#E74C3C"}},
                    "axisLabel": {"color": "#E74C3C"},
                    "splitLine": {"show": False}
                },
                {
                    "type": "value",
                    "name": "EC/OC 比值",
                    "position": "right",
                    "offset": 60,
                    "axisLine": {"show": True, "lineStyle": {"color": "#8E44AD"}},
                    "axisLabel": {"color": "#8E44AD"},
                    "splitLine": {"show": False}
                }
            ],
            "legend": {
                "data": ["SOC", "POC", "EC", "PM2.5", "EC/OC"],
                "top": 0
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "cross"}
            }
        }

        # 标题
        title = kwargs.get("title", f"{station_name}碳组分堆积图与污染物变化趋势分析")

        # 构建meta信息
        meta = {
            "unit": "μg/m³（碳组分和PM2.5）",
            "data_source": "carbon_analysis",
            "station_name": station_name,
            "record_count": len(records),
            "time_points": len(time_points),
            "components": carbon_fields,
            "schema_version": "3.1",
            "chart_type": "carbon_stacked_bar",
            "features": {
                "stacked_bar": True,
                "dual_y_axis": True,
                "show_pm25_curve": any(v is not None for v in series_pm25),
                "show_ecoc_curve": any(v is not None for v in series_ecoc)
            }
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        chart_id = f"carbon_stacked_bar_{station_name}" if station_name else "carbon_stacked_bar"

        return {
            "id": chart_id,
            "type": "carbon_stacked_bar",
            "title": title,
            "data": option,
            "meta": meta
        }

    def _generate_particulate_timeseries(
        self,
        records: List[Dict],
        selected_components: Optional[List[str]],
        station_name: str,
        chart_type: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成颗粒物组分时序图或柱状图

        Args:
            records: 数据记录列表
            selected_components: 选中的组分列表
            station_name: 站点名称
            chart_type: 图表类型（timeseries, line, bar）
            **kwargs: 额外参数

        Returns:
            时序图或柱状图数据
        """
        from collections import defaultdict

        # 按时间分组：{timestamp: {component: value}}
        time_data = defaultdict(dict)
        all_timestamps = set()
        all_components = set()

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取时间戳
            timestamp = record.get("timestamp")
            if not timestamp:
                continue
            all_timestamps.add(timestamp)

            # 提取组分数据
            components = record.get("components", {})
            if isinstance(components, dict):
                for comp_name, comp_value in components.items():
                    if selected_components is None or comp_name in selected_components:
                        all_components.add(comp_name)
                        try:
                            time_data[timestamp][comp_name] = float(comp_value)
                        except (ValueError, TypeError):
                            pass

        # 排序时间点
        time_points = sorted(list(all_timestamps))

        # 构建series数组
        series = []
        component_names = sorted(list(all_components))

        # 颜色映射（常用组分颜色）
        color_map = {
            "SO4": "#5470c6",
            "NO3": "#91cc75",
            "NH4": "#fac858",
            "OC": "#ee6666",
            "EC": "#73c0de",
            "Ca": "#3ba272",
            "K": "#fc8452",
            "Mg": "#9a60b4",
            "Na": "#ea7ccc"
        }

        for comp_name in component_names:
            values = []
            for timestamp in time_points:
                value = time_data[timestamp].get(comp_name)
                values.append(value)

            series.append({
                "name": comp_name,
                "data": values,
                "type": "line" if chart_type == "line" else "bar",
                "smooth": chart_type == "line"
            })

        # 构建图表数据
        option = {
            "x": time_points,
            "series": series
        }

        # 标题
        title = kwargs.get("title", f"{station_name}颗粒物组分时序变化")

        # 构建meta信息
        meta = {
            "unit": "μg/m³",
            "data_source": "particulate_unified",
            "station_name": station_name,
            "record_count": len(records),
            "time_points": len(time_points),
            "components": component_names,
            "schema_version": "3.1",
            "chart_type": chart_type
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        chart_id = f"particulate_{chart_type}_{station_name}" if station_name else f"particulate_{chart_type}"

        return {
            "id": chart_id,
            "type": chart_type,
            "title": title,
            "data": option,
            "meta": meta
        }

    def convert_air_quality_data(
        self,
        data: Union[List[Dict], Dict[str, Any]],
        chart_type: str = "timeseries",
        **kwargs
    ) -> Dict[str, Any]:
        """转换空气质量统一数据为图表数据

        Args:
            data: 空气质量统一数据（包含PM2.5、O3等污染物）
            chart_type: 图表类型（timeseries, bar, heatmap, radar）
            **kwargs: 额外参数（selected_pollutants、selected_stations等）

        Returns:
            图表数据
        """
        logger.info(
            "air_quality_conversion_start",
            chart_type=chart_type,
            record_count=len(data) if isinstance(data, list) else 0
        )

        # 处理输入数据格式
        records = []
        if isinstance(data, dict) and "data" in data:
            records = data["data"]
        elif isinstance(data, dict) and "status" in data and "success" in data:
            # UDF v2.0格式
            records = data.get("data", [])
        elif isinstance(data, list):
            records = data
        else:
            records = [data] if data else []

        if not records:
            return {"error": "空气质量数据为空"}

        # 获取选中的污染物（默认为None，表示自动检测所有污染物）
        selected_pollutants = kwargs.pop("selected_pollutants", None)

        # 获取选中的站点（默认为None，表示所有站点）
        selected_stations = kwargs.pop("selected_stations", None)

        # 如果未指定污染物，自动检测数据中所有可用的污染物
        if selected_pollutants is None:
            selected_pollutants = self._auto_detect_pollutants(records)
            logger.info(
                "auto_detected_pollutants",
                pollutants=selected_pollutants,
                count=len(selected_pollutants)
            )

        # 如果指定了站点过滤，应用过滤
        if selected_stations:
            records = [r for r in records if r.get("station_name") in selected_stations]
            logger.info(
                "filtered_stations",
                selected_stations=selected_stations,
                filtered_count=len(records)
            )

        # 根据图表类型路由到不同的生成方法
        if chart_type == "timeseries":
            return self._generate_air_quality_timeseries(records, selected_pollutants, **kwargs)
        elif chart_type == "facet_timeseries":
            # 【新增】分面时序图：多站点+多污染物场景
            return self._generate_air_quality_facet_timeseries(records, selected_pollutants, **kwargs)
        elif chart_type == "bar":
            return self._generate_air_quality_bar(records, selected_pollutants, **kwargs)
        elif chart_type == "heatmap":
            return self._generate_air_quality_heatmap(records, selected_pollutants, **kwargs)
        elif chart_type == "radar":
            return self._generate_air_quality_radar(records, selected_pollutants, **kwargs)

        return {"error": f"不支持的空气质量图表类型: {chart_type}"}

    def _generate_air_quality_timeseries(
        self,
        records: List[Dict],
        selected_pollutants: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """生成空气质量时序图

        适用场景：
        - 单站点的时序变化趋势
        - 多站点时，为每个站点生成独立的时间序列（多条线）

        Args:
            records: 数据记录列表
            selected_pollutants: 选中的污染物列表
            **kwargs: 额外参数

        Returns:
            时序图数据
        """
        from app.utils.data_standardizer import get_data_standardizer
        from collections import defaultdict

        # 使用统一字段映射器
        standardizer = get_data_standardizer()
        schema_type = kwargs.get("schema_type")
        comparison_type = kwargs.get("comparison_type")  # 新增：支持从expert_plan传入的comparison_type参数
        # 支持两种参数传递方式：comparison_type='city' 或 schema_type='regional_city_comparison'
        entity_label = "城市" if (comparison_type == "city" or schema_type == "regional_city_comparison") else "站点"

        # 按站点/城市分组：{station_name: {timestamp: {pollutant: value}}}
        station_data = defaultdict(lambda: defaultdict(dict))
        all_timestamps = set()

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取时间戳（使用统一字段映射）
            timestamp = self._get_standardized_value(record, standardizer, "timestamp")
            if not timestamp:
                continue

            all_timestamps.add(timestamp)

            # 提取站点/城市名称（兼容城市对比数据）
            station_name = (
                record.get("station_name")
                or record.get("city_name")
                or record.get("city")
                or record.get("name")
                or record.get("station")
                or record.get("district")
                or record.get("code")
                or "Unknown"
            )

            # 提取污染物数据
            measurements = record.get("measurements", {})
            if not measurements:
                # 如果没有measurements字段，尝试从record直接获取
                measurements = {
                    k: v for k, v in record.items()
                    if k not in [
                        "timestamp", "time_point",
                        "station_name", "station_code", "station",
                        "city_name", "city", "district",
                        "lat", "lon", "record_id", "created_time", "modified_time",
                        "aqi_indices", "air_quality_status", "metadata"
                    ]
                }
                # 单一污染物场景：如果只有 value 字段，则映射到当前选中污染物
                if "value" in record and len(selected_pollutants) == 1:
                    measurements[selected_pollutants[0]] = record.get("value")

            # 为每个选中的污染物存储数值
            for pollutant in selected_pollutants:
                value = self._get_pollutant_value(measurements, pollutant, standardizer)
                if value is not None:
                    try:
                        station_data[station_name][timestamp][pollutant] = float(value)
                    except (ValueError, TypeError):
                        station_data[station_name][timestamp][pollutant] = None

        # 排序时间点
        time_points = sorted(list(all_timestamps))

        # 检查站点数量
        station_names = list(station_data.keys())
        is_multi_station = len(station_names) > 1

        # 污染物显示名称映射
        pollutant_names = {
            "PM2_5": "PM2.5",
            "PM10": "PM10",
            "O3": "臭氧(O₃)",
            "O3_8h": "臭氧(O₃-8h)",
            "NO2": "二氧化氮(NO₂)",
            "SO2": "二氧化硫(SO₂)",
            "CO": "一氧化碳(CO)",
            "AQI": "AQI"
        }

        # 构建series数组
        series = []

        if is_multi_station:
            # 多站点：每个站点×污染物组合生成一条线
            for station_name in station_names:
                for pollutant in selected_pollutants:
                    values = []
                    for timestamp in time_points:
                        value = station_data[station_name][timestamp].get(pollutant)
                        values.append(value)

                    series_name = f"{station_name} - {pollutant_names.get(pollutant, pollutant)}"
                    series.append({
                        "name": series_name,
                        "data": values
                    })
        else:
            # 单站点：每个污染物生成一条线
            station_name = station_names[0] if station_names else "Unknown"
            for pollutant in selected_pollutants:
                values = []
                for timestamp in time_points:
                    value = station_data[station_name][timestamp].get(pollutant)
                    values.append(value)

                series.append({
                    "name": pollutant_names.get(pollutant, pollutant),
                    "data": values
                })

        option = {
            "x": time_points,
            "series": series
        }

        # 构建meta信息
        station_name_display = station_names[0] if len(station_names) == 1 else f"{len(station_names)}个{entity_label}"
        meta = {
            "unit": "μg/m³",
            "data_source": "air_quality_unified",
            "station_name": station_name_display,
            "stations": station_names,
            "pollutants": selected_pollutants,
            "record_count": len(records),
            "time_points": len(time_points),
            "is_multi_station": is_multi_station,
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        chart_id = f"air_quality_timeseries_{station_names[0]}" if len(station_names) == 1 else f"air_quality_timeseries_multi_{len(station_names)}stations"

        return {
            "id": chart_id,
            "type": "timeseries",
            "title": kwargs.get("title", f"{station_name_display}空气质量时序变化"),
            "data": option,
            "meta": meta
        }

    def _generate_air_quality_facet_timeseries(
        self,
        records: List[Dict],
        selected_pollutants: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """生成空气质量分面时序图（多站点+多污染物场景）

        适用场景：
        - 多站点（>=3）+ 多污染物（>=2）+ 多时间点
        - 每个污染物一个子图，避免线条过多导致图表难以阅读

        图表特性：
        - 每个污染物一个独立的时序子图
        - 每个子图中显示所有站点的趋势线
        - 便于对比同一污染物在不同站点的表现

        Args:
            records: 数据记录列表
            selected_pollutants: 选中的污染物列表
            **kwargs: 额外参数

        Returns:
            分面时序图数据（Chart v3.1格式）
        """
        from app.utils.data_standardizer import get_data_standardizer
        from collections import defaultdict

        # 使用统一字段映射器
        standardizer = get_data_standardizer()
        schema_type = kwargs.get("schema_type")
        comparison_type = kwargs.get("comparison_type")  # 新增：支持从expert_plan传入的comparison_type参数
        # 支持两种参数传递方式：comparison_type='city' 或 schema_type='regional_city_comparison'
        entity_label = "城市" if (comparison_type == "city" or schema_type == "regional_city_comparison") else "站点"

        # 按站点/城市分组：{station_name: {timestamp: {pollutant: value}}}
        station_data = defaultdict(lambda: defaultdict(dict))
        all_timestamps = set()

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取时间戳
            timestamp = self._get_standardized_value(record, standardizer, "timestamp")
            if not timestamp:
                continue

            all_timestamps.add(timestamp)

            # 提取站点/城市名称
            station_name = (
                record.get("station_name")
                or record.get("city_name")
                or record.get("city")
                or record.get("name")
                or record.get("station")
                or record.get("district")
                or record.get("code")
                or "Unknown"
            )

            # 提取污染物数据
            measurements = record.get("measurements", {})
            if not measurements:
                measurements = {
                    k: v for k, v in record.items()
                    if k not in [
                        "timestamp", "time_point",
                        "station_name", "station_code", "station",
                        "city_name", "city", "district",
                        "lat", "lon", "record_id", "created_time", "modified_time",
                        "aqi_indices", "air_quality_status", "metadata"
                    ]
                }
                if "value" in record and len(selected_pollutants) == 1:
                    measurements[selected_pollutants[0]] = record.get("value")

            # 为每个选中的污染物存储数值
            for pollutant in selected_pollutants:
                value = self._get_pollutant_value(measurements, pollutant, standardizer)
                if value is not None:
                    try:
                        station_data[station_name][timestamp][pollutant] = float(value)
                    except (ValueError, TypeError):
                        station_data[station_name][timestamp][pollutant] = None

        # 排序时间点
        time_points = sorted(list(all_timestamps))

        # 获取站点列表
        station_names = list(station_data.keys())

        # 污染物显示名称映射
        pollutant_names = {
            "PM2_5": "PM2.5",
            "PM10": "PM10",
            "O3": "臭氧(O3)",
            "O3_8h": "臭氧(8h)",
            "NO2": "二氧化氮",
            "SO2": "二氧化硫",
            "CO": "一氧化碳",
            "AQI": "AQI"
        }

        # 站点颜色映射（用于区分不同站点）
        station_colors = [
            "#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
            "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#ff9f7f"
        ]

        # 构建分面数据
        # facet_data 结构: {pollutant: {x: time_points, series: [...]}}
        facet_data = {}

        for pollutant in selected_pollutants:
            pollutant_facet_data = {
                "x": time_points,
                "series": []
            }

            for idx, station_name in enumerate(station_names):
                values = []
                for timestamp in time_points:
                    value = station_data[station_name][timestamp].get(pollutant)
                    values.append(value)

                pollutant_facet_data["series"].append({
                    "name": station_name,
                    "data": values,
                    "type": "line",
                    "smooth": True
                })

            facet_data[pollutant] = pollutant_facet_data

        # 构建图表数据
        option = {
            "facets": [
                {
                    "pollutant": pollutant,
                    "pollutant_name": pollutant_names.get(pollutant, pollutant),
                    "x": facet_data[pollutant]["x"],
                    "series": facet_data[pollutant]["series"]
                }
                for pollutant in selected_pollutants
            ],
            "layout": "vertical"  # 垂直分面（每个污染物一个子图上下排列）
        }

        # 构建meta信息
        station_name_display = f"{len(station_names)}个{entity_label}"
        meta = {
            "unit": "μg/m³",
            "data_source": "air_quality_unified",
            "station_name": station_name_display,
            "stations": station_names,
            "pollutants": selected_pollutants,
            "record_count": len(records),
            "time_points": len(time_points),
            "station_count": len(station_names),
            "facet_count": len(selected_pollutants),
            "facet_by": "pollutant",
            "schema_version": "3.1",
            "chart_type": "facet_timeseries",
            "features": {
                "multi_station_multi_pollutant": True,
                "facet_layout": "vertical"
            }
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        chart_id = f"air_quality_facet_timeseries_{len(station_names)}stations_{len(selected_pollutants)}pollutants"

        return {
            "id": chart_id,
            "type": "facet_timeseries",
            "title": kwargs.get("title", f"{station_name_display}多污染物时序变化（分面图）"),
            "data": option,
            "meta": meta
        }

    def _generate_air_quality_bar(
        self,
        records: List[Dict],
        selected_pollutants: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """生成空气质量柱状对比图（多站点/多城市）

        适用场景：
        - 多站点同一时刻的污染物浓度对比
        - 多城市空气质量指标对比

        Args:
            records: 数据记录列表
            selected_pollutants: 选中的污染物列表
            **kwargs: 额外参数

        Returns:
            柱状图数据
        """
        from app.utils.data_standardizer import get_data_standardizer

        # 使用统一字段映射器
        standardizer = get_data_standardizer()

        # 污染物显示名称映射
        pollutant_names = {
            "PM2_5": "PM2.5",
            "PM10": "PM10",
            "O3": "臭氧(O3)",
            "O3_8h": "臭氧(O3-8h)",
            "NO2": "二氧化氮(NO2)",
            "SO2": "二氧化硫(SO2)",
            "CO": "一氧化碳(CO)",
            "AQI": "AQI"
        }

        # 提取站点名称作为X轴
        stations = []
        series_data = {pollutant: [] for pollutant in selected_pollutants}

        for record in records:
            if not isinstance(record, dict):
                continue

            station_name = record.get("station_name", "Unknown")
            if station_name not in stations:
                stations.append(station_name)

            # 提取污染物数据
            measurements = record.get("measurements", {})
            if not measurements:
                # 如果没有measurements字段，尝试从record直接获取
                measurements = {
                    k: v for k, v in record.items()
                    if k not in ["timestamp", "time_point", "station_name", "station_code", "lat", "lon", "record_id", "created_time", "modified_time", "aqi_indices", "air_quality_status", "metadata"]
                }

            # 为每个选中的污染物提取数值
            for pollutant in selected_pollutants:
                value = self._get_pollutant_value(measurements, pollutant, standardizer)
                if value is not None:
                    try:
                        series_data[pollutant].append(float(value))
                    except (ValueError, TypeError):
                        series_data[pollutant].append(0)
                else:
                    series_data[pollutant].append(0)

        # 构建series数组
        series = []
        for pollutant in selected_pollutants:
            series.append({
                "name": pollutant_names.get(pollutant, pollutant),
                "data": series_data[pollutant]
            })

        option = {
            "x": stations,
            "series": series
        }

        # 构建meta信息
        meta = {
            "unit": "μg/m³",
            "data_source": "air_quality_unified",
            "pollutants": selected_pollutants,
            "stations": stations,
            "record_count": len(records),
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        chart_id = f"air_quality_bar_{'_'.join(stations[:2])}"
        if len(stations) > 2:
            chart_id += f"_plus{len(stations) - 2}"

        return {
            "id": chart_id,
            "type": "bar",
            "title": kwargs.get("title", f"多站点空气质量对比分析"),
            "data": option,
            "meta": meta
        }

    def _generate_air_quality_heatmap(
        self,
        records: List[Dict],
        selected_pollutants: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """生成空气质量热力图（站点×污染物矩阵）

        适用场景：
        - 多站点×多污染物的浓度矩阵可视化
        - 快速识别高污染区域和高浓度污染物

        Args:
            records: 数据记录列表
            selected_pollutants: 选中的污染物列表
            **kwargs: 额外参数

        Returns:
            热力图数据
        """
        from app.utils.data_standardizer import get_data_standardizer

        # 使用统一字段映射器
        standardizer = get_data_standardizer()

        # 污染物显示名称映射
        pollutant_names = {
            "PM2_5": "PM2.5",
            "PM10": "PM10",
            "O3": "臭氧(O3)",
            "O3_8h": "臭氧(O3-8h)",
            "NO2": "二氧化氮(NO2)",
            "SO2": "二氧化硫(SO2)",
            "CO": "一氧化碳(CO)",
            "AQI": "AQI"
        }

        # 提取站点名称和污染物数据
        stations = []
        station_data = {}

        for record in records:
            if not isinstance(record, dict):
                continue

            station_name = record.get("station_name", "Unknown")
            if station_name not in stations:
                stations.append(station_name)
                station_data[station_name] = {}

            # 提取污染物数据
            measurements = record.get("measurements", {})
            if not measurements:
                # 如果没有measurements字段，尝试从record直接获取
                measurements = {
                    k: v for k, v in record.items()
                    if k not in ["timestamp", "time_point", "station_name", "station_code", "lat", "lon", "record_id", "created_time", "modified_time", "aqi_indices", "air_quality_status", "metadata"]
                }

            # 为每个选中的污染物提取数值
            for pollutant in selected_pollutants:
                value = self._get_pollutant_value(measurements, pollutant, standardizer)
                if value is not None:
                    try:
                        station_data[station_name][pollutant] = float(value)
                    except (ValueError, TypeError):
                        station_data[station_name][pollutant] = 0
                else:
                    station_data[station_name][pollutant] = 0

        # 构建热力图数据：[[x_index, y_index, value], ...]
        # x轴: 站点, y轴: 污染物
        heatmap_data = []
        for x_idx, station in enumerate(stations):
            for y_idx, pollutant in enumerate(selected_pollutants):
                value = station_data[station].get(pollutant, 0)
                heatmap_data.append([x_idx, y_idx, value])

        # 构建y轴标签（污染物名称）
        y_labels = [pollutant_names.get(p, p) for p in selected_pollutants]

        option = {
            "xAxis": stations,
            "yAxis": y_labels,
            "data": heatmap_data
        }

        # 构建meta信息
        meta = {
            "unit": "μg/m³",
            "data_source": "air_quality_unified",
            "pollutants": selected_pollutants,
            "stations": stations,
            "record_count": len(records),
            "schema_version": "3.1",
            "visualization_type": "heatmap"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        chart_id = f"air_quality_heatmap_{len(stations)}stations_{len(selected_pollutants)}pollutants"

        return {
            "id": chart_id,
            "type": "heatmap",
            "title": kwargs.get("title", "站点污染物浓度热力分布"),
            "data": option,
            "meta": meta
        }

    def _generate_air_quality_radar(
        self,
        records: List[Dict],
        selected_pollutants: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """生成空气质量雷达图（单站点多指标评估）

        适用场景：
        - 单站点或多站点的多污染物综合评估
        - 污染物浓度相对关系可视化

        Args:
            records: 数据记录列表
            selected_pollutants: 选中的污染物列表
            **kwargs: 额外参数

        Returns:
            雷达图数据
        """
        from app.utils.data_standardizer import get_data_standardizer

        # 使用统一字段映射器
        standardizer = get_data_standardizer()

        # 污染物显示名称映射
        pollutant_names = {
            "PM2_5": "PM2.5",
            "PM10": "PM10",
            "O3": "臭氧(O3)",
            "O3_8h": "臭氧(O3-8h)",
            "NO2": "二氧化氮(NO2)",
            "SO2": "二氧化硫(SO2)",
            "CO": "一氧化碳(CO)",
            "AQI": "AQI"
        }

        # 污染物标准限值（用于归一化）
        # 参考《环境空气质量标准》GB 3095-2012 二级标准
        standard_limits = {
            "PM2_5": 75,      # 24h平均
            "PM10": 150,      # 24h平均
            "O3": 200,        # 1h平均
            "O3_8h": 160,     # 8h平均
            "NO2": 200,       # 1h平均
            "SO2": 500,       # 1h平均
            "CO": 10000,      # 1h平均 (mg/m³ -> μg/m³)
            "AQI": 200        # 轻度污染阈值
        }

        # 提取站点数据
        stations = []
        station_values = {}

        for record in records:
            if not isinstance(record, dict):
                continue

            station_name = record.get("station_name", "Unknown")
            if station_name not in stations:
                stations.append(station_name)
                station_values[station_name] = []

            # 提取污染物数据
            measurements = record.get("measurements", {})
            if not measurements:
                # 如果没有measurements字段，尝试从record直接获取
                measurements = {
                    k: v for k, v in record.items()
                    if k not in ["timestamp", "time_point", "station_name", "station_code", "lat", "lon", "record_id", "created_time", "modified_time", "aqi_indices", "air_quality_status", "metadata"]
                }

            # 为每个选中的污染物提取数值（归一化到0-100）
            values = []
            for pollutant in selected_pollutants:
                value = self._get_pollutant_value(measurements, pollutant, standardizer)
                if value is not None:
                    try:
                        raw_value = float(value)
                        # 归一化：(实际值 / 标准限值) * 100
                        limit = standard_limits.get(pollutant, 100)
                        normalized_value = (raw_value / limit) * 100
                        values.append(min(normalized_value, 200))  # 限制最大值为200%
                    except (ValueError, TypeError):
                        values.append(0)
                else:
                    values.append(0)

            station_values[station_name] = values

        # 构建指标配置
        indicators = []
        for pollutant in selected_pollutants:
            indicators.append({
                "name": pollutant_names.get(pollutant, pollutant),
                "max": 200  # 归一化后最大值为200%（超标2倍）
            })

        # 构建系列数据
        series = []
        for station in stations:
            series.append({
                "name": station,
                "value": station_values[station]
            })

        option = {
            "indicator": indicators,
            "series": series
        }

        # 构建meta信息
        meta = {
            "unit": "标准限值百分比(%)",
            "data_source": "air_quality_unified",
            "pollutants": selected_pollutants,
            "stations": stations,
            "record_count": len(records),
            "schema_version": "3.1",
            "visualization_type": "radar",
            "normalization": "relative_to_standard_limit"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        chart_id = f"air_quality_radar_{'_'.join(stations[:2])}"
        if len(stations) > 2:
            chart_id += f"_plus{len(stations) - 2}"

        return {
            "id": chart_id,
            "type": "radar",
            "title": kwargs.get("title", "空气质量综合评估雷达图"),
            "data": option,
            "meta": meta
        }

    def _get_pollutant_value(self, measurements: Dict, pollutant: str, standardizer) -> Any:
        """使用统一字段映射获取污染物值

        Args:
            measurements: 测量数据（已标准化字段名）
            pollutant: 污染物名称（标准字段名，如PM2_5, O3）
            standardizer: 数据标准化器

        Returns:
            污染物值
        """
        if not isinstance(measurements, dict):
            return None

        def _normalize_numeric(value: Any) -> Optional[float]:
            """尽可能把传入的值转成浮点数."""
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return None
            if isinstance(value, dict):
                # 常见的嵌套字段名称
                for nested_key in ("value", "val", "avg", "average", "mean", "data", "measurement", "concentration"):
                    if nested_key in value:
                        normalized = _normalize_numeric(value.get(nested_key))
                        if normalized is not None:
                            return normalized
            return None

        candidate_keys = []
        if standardizer:
            std_name = standardizer._get_standard_field_name(pollutant)
            if std_name:
                candidate_keys.append(std_name)
        candidate_keys.append(pollutant)
        candidate_keys.append("value")  # 单指标数据兜底

        # 直接在当前measurements中查找
        for key in candidate_keys:
            if key in measurements:
                normalized_value = _normalize_numeric(measurements.get(key))
                if normalized_value is not None:
                    return normalized_value

        # 兼容嵌套结构：values / data / measurements / metrics
        nested_keys = ("values", "data", "measurements", "metrics")
        for container_key in nested_keys:
            nested = measurements.get(container_key)
            if isinstance(nested, dict):
                for key in candidate_keys:
                    if key in nested:
                        normalized_value = _normalize_numeric(nested.get(key))
                        if normalized_value is not None:
                            return normalized_value

        return None

    def _get_standardized_value(self, record: Dict, standardizer, field_name: str) -> Any:
        """使用统一字段映射获取字段值

        Args:
            record: 数据记录
            standardizer: 数据标准化器
            field_name: 字段名

        Returns:
            字段值
        """
        # 使用统一字段映射查找实际字段名
        actual_field_name = standardizer._get_standard_field_name(field_name)

        if actual_field_name:
            return record.get(actual_field_name)

        # 如果标准字段名没有找到，尝试原始字段名
        return record.get(field_name)

    def _auto_detect_pollutants(self, records: List[Dict]) -> List[str]:
        """自动检测数据中所有可用的污染物指标

        Args:
            records: 数据记录列表（已标准化）

        Returns:
            检测到的污染物字段名列表（标准字段名）
        """
        if not records or len(records) == 0:
            logger.warning("auto_detect_pollutants_empty_records")
            return []

        # 定义标准污染物字段名（符合转换后的字段格式）
        standard_pollutants = [
            "PM2_5", "PM10", "O3", "O3_8h", "NO2", "SO2", "CO", "AQI"
        ]

        detected_pollutants = []

        # 检查第一条记录的字段
        first_record = records[0]
        if not isinstance(first_record, dict):
            logger.warning("auto_detect_pollutants_invalid_record_type", record_type=type(first_record).__name__)
            return []

        from app.utils.data_standardizer import get_data_standardizer
        standardizer = get_data_standardizer()

        def _normalize_key(field_name: str) -> str:
            normalized = standardizer._get_standard_field_name(field_name)
            return normalized or field_name

        def _collect_keys(container: Dict[str, Any]) -> set:
            keys = set()
            for key, value in container.items():
                normalized = _normalize_key(key)
                keys.add(normalized)
                if isinstance(value, dict):
                    keys.update(_collect_keys(value))
            return keys

        measurement_fields = set()
        measurements = first_record.get("measurements", {})
        if isinstance(measurements, dict):
            measurement_fields = _collect_keys(measurements)

        record_fields = _collect_keys(first_record)

        # 特殊场景：记录里有 pollutant/pollutant_name + value 时，使用该污染物名
        for key in ("pollutant", "pollutant_name", "pollutant_code"):
            if key in first_record:
                p = first_record.get(key)
                if isinstance(p, str) and p:
                    normalized = _normalize_key(p)
                    detected_pollutants.append(normalized)
                    break

        for pollutant in standard_pollutants:
            if pollutant in measurement_fields or pollutant in record_fields:
                detected_pollutants.append(pollutant)

        if not detected_pollutants:
            logger.warning(
                "auto_detect_pollutants_no_standard_fields_found",
                available_fields=list(measurement_fields)[:10] if measurement_fields else list(record_fields)[:10]
            )
            # 降级处理：返回默认污染物列表
            return ["PM2_5", "O3", "NO2"]

        logger.info(
            "auto_detect_pollutants_success",
            detected_count=len(detected_pollutants),
            pollutants=detected_pollutants
        )

        return detected_pollutants

    def convert_meteorology_data(
        self,
        data: Union[List[Dict], Dict[str, Any]],
        chart_type: str = "wind_rose",
        **kwargs
    ) -> Dict[str, Any]:
        """转换气象数据为图表数据

        Args:
            data: 气象数据
            chart_type: 图表类型（wind_rose, timeseries, profile）
            **kwargs: 额外参数

        Returns:
            图表数据
        """
        return self.meteorology_converter.convert_to_chart(data, chart_type, **kwargs)

    def convert_meteorology_data_group(
        self,
        data: Union[List[Dict], Dict[str, Any]],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """转换气象数据为专业分组图表（推荐使用）
        
        生成专业的气象图表组合：
        1. 风向玫瑰图：风向+风速分布
        2. 常规气象时序图：温度、湿度、风速、降水、云量、能见度
        3. 气压时序图：单独展示（数值范围特殊）
        4. 边界层高度图：单独展示（数值范围大）

        Args:
            data: 气象数据
            **kwargs: 额外参数（station_name等）

        Returns:
            图表列表（Chart v3.1格式）
        """
        return self.meteorology_converter.convert_to_chart_group(data, **kwargs)

    def convert_3d_data(
        self,
        data: Union[List[Dict], Dict[str, Any]],
        chart_type: str = "scatter3d",
        **kwargs
    ) -> Dict[str, Any]:
        """转换3D数据为图表数据

        Args:
            data: 3D数据
            chart_type: 图表类型（scatter3d, surface3d, line3d, bar3d, volume3d）
            **kwargs: 额外参数

        Returns:
            图表数据
        """
        return self.d3_converter.convert_to_chart(data, chart_type, **kwargs)

    def convert_map_data(
        self,
        data: Union[List[Dict], Dict[str, Any]],
        chart_type: str = "map",
        **kwargs
    ) -> Dict[str, Any]:
        """转换地图数据为图表数据

        Args:
            data: 空间数据
            chart_type: 图表类型（map, heatmap）
            **kwargs: 额外参数

        Returns:
            图表数据
        """
        return self.map_converter.convert_to_chart(data, chart_type, **kwargs)

    def convert_raw_data(
        self,
        data: Union[List[Dict], Dict[str, Any]],
        data_type: str = "generic"
    ) -> Dict[str, Any]:
        """转换原始数据为图表数据

        Args:
            data: 原始数据
            data_type: 数据类型（vocs, pm, generic）

        Returns:
            图表数据
        """
        logger.info("raw_data_conversion", data_type=data_type)

        if data_type == "vocs":
            if isinstance(data, list) and data:
                pie_data = []
                for item in data:
                    if isinstance(item, dict):
                        name = item.get("DisplayName", item.get("displayName", "Unknown"))
                        value = item.get("val", item.get("value", item.get("concentration", 0)))
                        if value is not None:
                            try:
                                pie_data.append({
                                    "name": str(name),
                                    "value": float(value)
                                })
                            except (ValueError, TypeError):
                                pass

                pie_data = sorted(pie_data, key=lambda x: x["value"], reverse=True)[:10]

                return {
                    "id": "vocs_concentration_raw",
                    "type": "pie",
                    "title": "VOCs浓度分布",
                    "data": pie_data,
                    "meta": {
                        "unit": "μg/m³",
                        "data_source": "raw_vocs_data",
                        "record_count": len(pie_data),
                        "schema_version": "3.1"
                    }
                }

        elif data_type == "pm":
            if isinstance(data, list) and data:
                pie_data = []
                for item in data:
                    if isinstance(item, dict):
                        name = item.get("component", item.get("组分", "Unknown"))
                        value = item.get("concentration", item.get("浓度", 0))
                        if value is not None:
                            try:
                                pie_data.append({
                                    "name": str(name),
                                    "value": float(value)
                                })
                            except (ValueError, TypeError):
                                pass

                pie_data = sorted(pie_data, key=lambda x: x["value"], reverse=True)[:10]

                return {
                    "id": "pm_component_raw",
                    "type": "pie",
                    "title": "颗粒物组分分布",
                    "data": pie_data,
                    "meta": {
                        "unit": "μg/m³",
                        "data_source": "raw_pm_data",
                        "record_count": len(pie_data),
                        "schema_version": "3.1"
                    }
                }

        return {
            "error": f"不支持的数据类型或数据为空: {data_type}",
            "data_sample": str(data)[:200] if data else None
        }

    def convert_with_recommendations(
        self,
        data: Any,
        data_type: Optional[str] = None,
        chart_type: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        带建议的图表数据转换

        Args:
            data: 输入数据
            data_type: 数据类型
            chart_type: 图表类型
            **kwargs: 额外参数

        Returns:
            转换结果 + 优化建议
        """
        logger.info("convert_with_recommendations", data_type=data_type, chart_type=chart_type)

        # 首先进行标准转换
        conversion_result = convert_chart_data(
            data=data,
            data_type=data_type,
            chart_type=chart_type,
            **kwargs
        )

        # 如果转换失败，返回错误和建议
        if "error" in conversion_result:
            return conversion_result

        # 生成转换建议
        recommendations = self._generate_conversion_recommendations(
            data=data,
            chart_type=chart_type or "auto",
            conversion_result=conversion_result
        )

        # 将建议添加到结果中
        conversion_result["recommendations"] = recommendations
        conversion_result["suggested_alternatives"] = self._suggest_alternative_charts(
            data=data,
            chart_type=chart_type,
            conversion_result=conversion_result
        )

        return conversion_result

    def _generate_conversion_recommendations(
        self,
        data: Any,
        chart_type: str,
        conversion_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        生成图表优化建议

        Args:
            data: 输入数据
            chart_type: 图表类型
            conversion_result: 转换结果

        Returns:
            优化建议列表
        """
        recommendations = []

        # 基于数据特征的建议
        if isinstance(data, list) and data:
            first_item = data[0] if isinstance(data, list) else data
            if isinstance(first_item, dict):
                # 数据大小建议
                if len(data) > 50:
                    recommendations.append({
                        "type": "data_size",
                        "title": "数据量较大",
                        "description": f"数据包含{len(data)}条记录，建议使用抽样或聚合显示以提高性能",
                        "suggestion": "考虑使用数据聚合或分页显示"
                    })

                # 时间序列建议
                if self._check_data_has_time_field(data):
                    recommendations.append({
                        "type": "time_series",
                        "title": "时间序列数据",
                        "description": "检测到时间字段，建议使用时序图或折线图",
                        "suggestion": f"当前图表类型: {chart_type}，可考虑切换为 timeseries 或 line"
                    })

                # 多维数据建议
                pollutant_count = self._count_pollutants(data)
                if pollutant_count > 3:
                    recommendations.append({
                        "type": "multi_dimension",
                        "title": "多维数据",
                        "description": f"数据包含{pollutant_count}个指标，建议使用雷达图或热力图",
                        "suggestion": "当前图表可能难以展示所有维度，可考虑使用 radar 或 heatmap"
                    })

                # 空间数据建议
                if self._check_data_has_fields(data, ["longitude", "latitude"]):
                    recommendations.append({
                        "type": "spatial_data",
                        "title": "空间数据",
                        "description": "检测到经纬度字段，建议使用地图或热力图",
                        "suggestion": f"当前图表类型: {chart_type}，可考虑切换为 map 或 heatmap"
                    })

        # 基于转换结果的建议
        chart_data = conversion_result.get("data", {})
        if isinstance(chart_data, dict):
            # 数据点密度建议
            series_data = chart_data.get("series", [])
            if series_data:
                total_points = sum(len(s.get("data", [])) for s in series_data if isinstance(s, dict))
                if total_points > 1000:
                    recommendations.append({
                        "type": "performance",
                        "title": "数据点过多",
                        "description": f"图表包含{total_points}个数据点，可能影响渲染性能",
                        "suggestion": "建议使用数据抽样或聚合，减少数据点数量"
                    })

        return recommendations

    def _suggest_alternative_charts(
        self,
        data: Any,
        chart_type: Optional[str],
        conversion_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        建议替代图表类型

        Args:
            data: 输入数据
            chart_type: 当前图表类型
            conversion_result: 转换结果

        Returns:
            替代图表建议列表
        """
        alternatives = []

        # 基于数据特征推荐替代图表
        if isinstance(data, list) and data:
            first_item = data[0] if isinstance(data, list) else data
            if isinstance(first_item, dict):
                # 时间序列数据推荐
                if self._check_data_has_time_field(data):
                    alternatives.append({
                        "type": "timeseries",
                        "description": "时序图 - 适合展示时间趋势",
                        "reason": "检测到时间字段"
                    })
                    alternatives.append({
                        "type": "line",
                        "description": "折线图 - 适合单一指标趋势",
                        "reason": "简洁的趋势展示"
                    })

                # 空间数据推荐
                if self._check_data_has_fields(data, ["longitude", "latitude"]):
                    alternatives.append({
                        "type": "map",
                        "description": "地图 - 适合空间分布",
                        "reason": "检测到经纬度字段"
                    })
                    alternatives.append({
                        "type": "heatmap",
                        "description": "热力图 - 适合空间密度",
                        "reason": "展示空间强度分布"
                    })

                # 气象数据推荐
                if self._check_data_has_fields(data, ["wind_speed", "wind_direction"]):
                    alternatives.append({
                        "type": "wind_rose",
                        "description": "风向玫瑰图 - 适合风场分析",
                        "reason": "检测到风向风速字段"
                    })

                # 多指标推荐
                pollutant_count = self._count_pollutants(data)
                if pollutant_count >= 3:
                    alternatives.append({
                        "type": "radar",
                        "description": "雷达图 - 适合多指标对比",
                        "reason": f"检测到{pollutant_count}个指标"
                    })
                    alternatives.append({
                        "type": "heatmap",
                        "description": "热力图 - 适合多维矩阵",
                        "reason": "适合展示多维数据关系"
                    })

        return alternatives

    # ====================
    # 自动检测和转换
    # ====================

    def auto_detect_and_convert(
        self,
        data: Any,
        prefer_chart_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """自动检测数据类型并转换

        Args:
            data: 输入数据
            prefer_chart_type: 优先的图表类型

        Returns:
            转换后的图表数据
        """
        # 检测PMF结果（新格式：sources对象列表）
        if isinstance(data, dict) and "sources" in data and isinstance(data.get("sources"), list):
            logger.info("auto_convert_detected_pmf_new")
            return self.pmf_converter.convert_to_chart(data, prefer_chart_type or "pie")

        # 检测PMF结果（旧格式：source_contributions字典 + timeseries）
        if isinstance(data, dict) and "source_contributions" in data and "timeseries" in data:
            logger.info("auto_convert_detected_pmf_legacy")
            return self.pmf_converter.convert_to_chart(data, prefer_chart_type or "pie")

        # 检测OBM结果
        if isinstance(data, dict) and "species_ofp" in data:
            logger.info("auto_convert_detected_obm")
            return self.obm_converter.convert_to_chart(data, prefer_chart_type or "bar")

        # 检测VOCs统一数据（vocs_unified格式）
        if isinstance(data, list) and data:
            first_item = data[0] if isinstance(data, list) else None
            if isinstance(first_item, dict):
                # 检查是否是UnifiedVOCsData格式（包含station_code和species_data字段）
                if "station_code" in first_item and "species_data" in first_item and "timestamp" in first_item:
                    logger.info("auto_convert_detected_vocs_unified")
                    return self.vocs_converter.convert_to_chart(data, prefer_chart_type or "timeseries")
                # 检测是否是UnifiedParticulateData格式（包含station_code和components字段）
                elif "station_code" in first_item and "components" in first_item and "timestamp" in first_item:
                    logger.info("auto_convert_detected_particulate_unified")
                    return self.convert_particulate_unified_data(data, prefer_chart_type or "stacked_timeseries")
                # 检测VOCs原始数据
                elif "DisplayName" in first_item or "species" in first_item:
                    logger.info("auto_convert_detected_vocs_raw")
                    return self.convert_raw_data(data, "vocs")

        # 检测颗粒物原始数据
        if isinstance(data, list) and data:
            first_item = data[0] if isinstance(data, list) else None
            if isinstance(first_item, dict) and ("component" in first_item or "组分" in first_item):
                logger.info("auto_convert_detected_pm_raw")
                return self.convert_raw_data(data, "pm")

        logger.warning("auto_convert_unknown_type", data_type=type(data).__name__)
        return {
            "error": "无法识别数据格式",
            "data_type": type(data).__name__,
            "suggestion": "请指定明确的data_type或使用适当的工具转换数据"
        }


# ====================
# 便利函数
# ====================

def convert_chart_data(
    data: Any,
    data_type: Optional[str] = None,
    chart_type: Optional[str] = None,
    context: Any = None,
    **kwargs
) -> Dict[str, Any]:
    """统一的图表数据转换接口

    这是全局便利函数，简化调用方式

    Args:
        data: 输入数据
        data_type: 数据类型（pmf, obm, vocs, vocs_unified, pm, air_quality, generic）
        chart_type: 图表类型（pie, bar, timeseries, sensitivity）
        context: 执行上下文（用于解析data_ref）
        **kwargs: 额外参数（pollutant, station_name, venue_name等）

    Returns:
        转换后的图表数据
    """
    converter = ChartDataConverter()

    # 自动检测
    if data_type is None and chart_type is None:
        return converter.auto_detect_and_convert(data)

    # 根据data_type转换
    if data_type in ["pmf", "pmf_result"]:
        return converter.convert_pmf_result(data, chart_type or "pie", **kwargs)
    elif data_type in ["obm", "obm_ofp_result"]:
        return converter.convert_obm_result(data, chart_type or "bar", **kwargs)
    elif data_type in ["vocs_unified", "vocs_unified_data"]:
        return converter.convert_vocs_data(data, chart_type or "timeseries", **kwargs)
    elif data_type in ["air_quality_unified", "air_quality", "guangdong_stations",
                       "regional_city_comparison", "regional_station_comparison",
                       "regional_nearby_stations_comparison"]:
        # 空气质量统一数据转换（包括区域对比数据）
        return converter.convert_air_quality_data(data, chart_type or "timeseries", **kwargs)
    elif data_type in ["vocs", "pm", "particulate"]:
        return converter.convert_raw_data(data, data_type)
    elif data_type in ["particulate_unified"]:
        # 统一颗粒物数据转换
        return converter.convert_particulate_unified_data(data, chart_type or "stacked_timeseries", **kwargs)
    elif data_type in ["particulate", "particulate_analysis", "carbon_analysis"]:
        # 颗粒物分析结果转换（calculate_soluble/carbon/crustal等工具的输出）
        # 如果数据中已有visuals，直接返回
        if isinstance(data, dict) and data.get("visuals"):
            logger.info("particulate_analysis_returning_existing_visuals")
            return {"visuals": data["visuals"], "has_visuals": True}
        # 如果指定了 carbon_stacked_bar 图表类型，尝试转换为堆积图
        if chart_type == "carbon_stacked_bar":
            # 处理输入数据格式
            records = []
            if isinstance(data, dict):
                if "data" in data:
                    records = data["data"]
                elif "result_df" in data:
                    # calculate_carbon 的 result_df 格式
                    records = data["result_df"] if isinstance(data["result_df"], list) else [data["result_df"]]
            elif isinstance(data, list):
                records = data

            if records:
                station_name = records[0].get("station_name", "Unknown") if isinstance(records[0], dict) else "Unknown"
                return converter._generate_carbon_stacked_bar(records, station_name, **kwargs)

        # 其他图表类型返回空结果，由工具自身的visuals字段处理
        return {"error": "particulate_analysis 数据由工具直接生成visuals，无需转换"}
    elif data_type in ["meteorology", "meteorology_unified", "weather", "meteo"]:
        # 气象数据转换（支持风向玫瑰图、时序图、边界层廓线）
        return converter.convert_meteorology_data(data, chart_type or "wind_rose", **kwargs)
    elif data_type in ["3d", "three_dimensional", "spatial"]:
        # 3D数据转换（支持3D散点图、3D曲面图等）
        return converter.convert_3d_data(data, chart_type or "scatter3d", **kwargs)
    elif data_type in ["map", "heatmap", "location", "geo"]:
        # 地图数据转换（支持地图、热力图）
        return converter.convert_map_data(data, chart_type or "map", **kwargs)

    return {"error": f"不支持的数据类型: {data_type}"}


# ====================
# 兼容性函数（已简化）
# ====================

def _normalize_field_name_for_logging(field_name: str) -> str:
    """标准化字段名以避免Unicode字符在Windows GBK环境下导致编码错误

    Args:
        field_name: 原始字段名

    Returns:
        标准化后的字段名
    """
    import unicodedata
    normalized = unicodedata.normalize('NFKD', field_name)
    normalized = normalized.replace('₃', '3')
    normalized = normalized.replace('₂', '2')
    normalized = normalized.replace('₁', '1')
    normalized = normalized.replace('₀', '0')
    return normalized


def _validate_and_enhance_chart_v3_1(
    chart: Dict[str, Any],
    generator: str = "chart_data_converter",
    original_data_ids: Optional[List[str]] = None,
    scenario: Optional[str] = None
) -> Dict[str, Any]:
    """验证并增强图表配置为v3.1标准

    Args:
        chart: 原始图表配置
        generator: 生成器标识
        original_data_ids: 原始数据ID列表
        scenario: 场景标识

    Returns:
        增强后的图表配置
    """
    # 验证必需字段
    required_fields = ["id", "type", "title", "data"]
    missing = [f for f in required_fields if f not in chart]

    if missing:
        logger.warning(
            "chart_v3_1_validation_failed",
            missing_fields=missing,
            chart_id=chart.get("id", "unknown")
        )
        return {
            "error": f"图表格式不完整，缺少字段: {missing}",
            "required_fields": required_fields
        }

    # 确保meta存在
    if "meta" not in chart:
        chart["meta"] = {}

    # 增强meta字段（v3.1）
    chart["meta"]["schema_version"] = "3.1"

    if generator:
        chart["meta"]["generator"] = generator

    if original_data_ids:
        chart["meta"]["original_data_ids"] = original_data_ids

    if scenario:
        chart["meta"]["scenario"] = scenario

    logger.debug(
        "chart_enhanced_to_v3_1",
        chart_id=chart.get("id"),
        chart_type=chart.get("type"),
        generator=generator
    )

    return chart


# ====================
# 版本信息
# ====================

__version__ = "2.1.0"
__author__ = "Claude Code"
__refactor_date__ = "2025-11-20"

# 更新日志：
# v2.1.0: 扩展空气质量图表类型，新增bar、heatmap、radar三种图表支持
# v2.0.2: 修复空气质量数据转换，使用统一字段映射，支持O3和O3_8h区分
# v2.0.1: 添加air_quality_unified数据类型支持，修复smart_chart_generator工具调用失败问题

# 重构说明：
# 1. 模块化拆分：原4422行代码拆分为7个独立模块
# 2. 移除冗余：删除所有重复的字段映射和验证逻辑
# 3. 统一字段映射：使用data_standardizer统一处理字段映射
# 4. 简化API：保持公共接口不变，内部实现完全重构
# 5. 提升可维护性：每个转换器独立测试和维护
