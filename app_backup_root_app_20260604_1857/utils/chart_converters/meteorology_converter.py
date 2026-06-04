"""
气象数据图表转换器 - UDF v2.0 + Chart v3.1

将气象数据转换为标准图表格式，支持风向玫瑰图、时序图、边界层廓线图等。
遵循最新的UDF v2.0数据规范和Chart v3.1图表规范。

版本：v2.1 - 优化图表分组展示
更新：
- 常规气象时序图：温度、湿度、风速、降水、云量、能见度
- 气压单独展示：数值范围特殊（~1013hPa）
- 边界层高度单独展示：数值范围大（百~千米）
- 风向玫瑰图：专业展示风向频率分布
"""

from typing import Any, Dict, List, Optional, Union
import structlog

logger = structlog.get_logger()


class MeteorologyChartConverter:
    """气象数据图表转换器

    专门负责将气象数据转换为各种图表格式
    
    图表分组策略（v2.1）：
    1. 常规气象时序图：温度、湿度、风速、降水、云量、能见度（数值范围相近）
    2. 气压时序图：单独展示（数值~1013hPa，与其他不兼容）
    3. 边界层高度图：单独展示（数值范围大，百~千米）
    4. 风向玫瑰图：风向+风速分布（专业图表）
    """

    @staticmethod
    def convert_to_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        chart_type: str = "wind_rose",
        **kwargs
    ) -> Dict[str, Any]:
        """将气象数据转换为图表数据

        Args:
            data: 气象数据（UDF格式或字典列表）
            chart_type: 图表类型（wind_rose, timeseries, profile）
            **kwargs: 额外参数（station_name等）

        Returns:
            图表数据（Chart v3.1格式）
        """
        logger.info(
            "meteorology_conversion_start",
            input_type=type(data).__name__,
            chart_type=chart_type,
            record_count=len(data) if isinstance(data, list) else 0
        )

        # 处理输入数据格式
        if isinstance(data, dict) and "data" in data:
            data = data["data"]

        if not data:
            return {"error": "气象数据为空"}

        # 获取站点名称
        station_name = kwargs.get("station_name", "气象站点")

        if chart_type == "wind_rose":
            return MeteorologyChartConverter._generate_wind_rose_chart(data, station_name, **kwargs)
        elif chart_type == "timeseries":
            return MeteorologyChartConverter._generate_timeseries_chart(data, station_name, **kwargs)
        elif chart_type == "profile":
            return MeteorologyChartConverter._generate_profile_chart(data, station_name, **kwargs)
        elif chart_type == "weather_timeseries":
            return MeteorologyChartConverter._generate_weather_timeseries_chart(data, station_name, **kwargs)

        return {"error": f"不支持的气象图表类型: {chart_type}"}

    @staticmethod
    def convert_to_chart_group(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """将气象数据转换为分组图表（推荐使用）
        
        生成专业的气象图表组合：
        1. 常规气象时序图：温度、湿度、风速、降水、云量、能见度
        2. 气压时序图：单独展示
        3. 边界层高度时序图：单独展示
        4. 风向玫瑰图：风向+风速分布

        Args:
            data: 气象数据（UDF格式或字典列表）
            **kwargs: 额外参数（station_name等）

        Returns:
            图表列表（Chart v3.1格式）
        """
        logger.info(
            "meteorology_chart_group_start",
            input_type=type(data).__name__,
            record_count=len(data) if isinstance(data, list) else 0
        )

        # 处理输入数据格式
        if isinstance(data, dict) and "data" in data:
            data = data["data"]

        if not data:
            return [{"error": "气象数据为空"}]

        station_name = kwargs.pop("station_name", None) or "气象站点"
        charts = []

        # 【调试】记录输入数据信息
        logger.info(
            "meteorology_chart_group_input",
            input_type=type(data).__name__,
            record_count=len(data) if isinstance(data, list) else 0,
            station_name=station_name
        )

        # 1. 带风向指针的气象时序图（替代风向玫瑰图+常规气象时序图）
        # 将风速曲线和风向指针集成在一张图中
        logger.debug("meteorology_chart_group_generating_weather_timeseries")
        weather_ts = MeteorologyChartConverter._generate_weather_timeseries_chart(data, station_name, **kwargs)
        if "error" in weather_ts:
            logger.warning(
                "meteorology_chart_group_weather_timeseries_failed",
                error=weather_ts.get("error")
            )
        else:
            weather_ts["meta"]["layout_hint"] = "wide"
            charts.append(weather_ts)
            logger.info(
                "meteorology_chart_group_weather_timeseries_success",
                chart_id=weather_ts.get("id"),
                chart_type=weather_ts.get("type")
            )

        # 2. 气压+边界层高度合并图（双Y轴）
        logger.debug("meteorology_chart_group_generating_pressure_pbl")
        pressure_pbl_chart = MeteorologyChartConverter._generate_pressure_pbl_chart(data, station_name, **kwargs)
        if "error" in pressure_pbl_chart:
            logger.warning(
                "meteorology_chart_group_pressure_pbl_failed",
                error=pressure_pbl_chart.get("error")
            )
        else:
            pressure_pbl_chart["meta"]["layout_hint"] = "wide"
            charts.append(pressure_pbl_chart)
            logger.info(
                "meteorology_chart_group_pressure_pbl_success",
                chart_id=pressure_pbl_chart.get("id"),
                chart_type=pressure_pbl_chart.get("type")
            )

        logger.info(
            "meteorology_chart_group_complete",
            chart_count=len(charts),
            chart_types=[c.get("type") for c in charts],
            input_record_count=len(data) if isinstance(data, list) else 0
        )

        return charts

    @staticmethod
    def _generate_weather_timeseries_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成带风向指针的气象时序图（替代风向玫瑰图）

        将风速曲线和风向指针集成在一张图中展示。
        风向以箭头形式标注在风速曲线上。

        Args:
            data: 气象数据
            station_name: 站点名称
            **kwargs: 额外参数

        Returns:
            weather_timeseries 图表数据 (Chart v3.1格式)
        """
        import uuid
        logger.info("weather_timeseries_generation_start", station_name=station_name)

        records = data if isinstance(data, list) else [data]

        # 【调试】记录原始数据条数和样例
        logger.debug(
            "weather_timeseries_raw_data_info",
            record_count=len(records),
            sample_fields=list(records[0].keys()) if records else []
        )

        # 过滤数据
        filtered_records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            metadata = record.get("metadata", {})
            record_type = metadata.get("type", "")
            if record_type in ["forecast_hourly", ""] or not record_type:
                filtered_records.append(record)

        if filtered_records:
            records = filtered_records
            logger.debug("weather_timeseries_filtered", filtered_count=len(filtered_records))

        # 【调试】记录过滤后数据的第一条记录的可用字段
        if records:
            first_record = records[0]
            data_source = first_record.get("measurements", first_record)
            logger.debug(
                "weather_timeseries_available_fields",
                available_fields=list(data_source.keys()) if isinstance(data_source, dict) else []
            )

        # 提取时间序列数据
        time_points = []
        wind_data = []  # 风速+风向
        other_series = {}  # 其他气象要素

        # 字段映射
        # 左Y轴(yAxisIndex=0): 温度、风速、降水（混合单位，数值范围相近）
        # 右Y轴(yAxisIndex=1): 湿度、云量（都是%）
        elements = {
            "temperature": ["temperature", "temp", "气温", "temperature_2m", "apparent_temperature"],
            "precipitation": ["precipitation", "rain", "降水量", "降水"],
            "humidity": ["humidity", "rh", "湿度", "relative_humidity_2m", "relative_humidity"],
            "cloudCover": ["cloudCover", "cloud_cover", "云量", "cloud"],
        }

        element_names = {
            "temperature": "温度",
            "precipitation": "降水",
            "humidity": "湿度",
            "cloudCover": "云量",
        }

        element_units = {
            "temperature": "°C",
            "precipitation": "mm",
            "humidity": "%",
            "cloudCover": "%",
        }
        
        # Y轴分配：左轴(0)=温度/降水，右轴(1)=湿度/云量(%)
        element_y_axis = {
            "temperature": 0,
            "precipitation": 0,
            "humidity": 1,
            "cloudCover": 1,
        }

        for idx, record in enumerate(records):
            if not isinstance(record, dict):
                continue

            # 提取时间
            time_val = MeteorologyChartConverter._get_field_value(
                record,
                ["timestamp", "time_point", "timePoint", "time", "DataTime", "datetime", "时间点", "时间"]
            )
            if not time_val:
                continue

            # 简化时间显示
            if isinstance(time_val, str) and len(time_val) > 10:
                time_val = time_val[5:16]  # MM-DD HH:MM

            time_points.append(time_val)
            data_source = record.get("measurements", record)
            if not isinstance(data_source, dict):
                data_source = record

            # 提取风速和风向
            wind_speed = MeteorologyChartConverter._get_field_value(
                data_source,
                ["windSpeed", "wind_speed", "wind_speed_10m", "WS", "ws", "风速"]
            )
            wind_direction = MeteorologyChartConverter._get_field_value(
                data_source,
                ["windDirection", "wind_direction", "wind_direction_10m", "WD", "wd", "风向"]
            )

            # 【调试】记录风速风向提取结果
            logger.debug(
                "weather_timeseries_wind_extraction",
                record_idx=idx,
                wind_speed=wind_speed,
                wind_direction=wind_direction
            )

            try:
                ws = float(wind_speed) if wind_speed is not None else 0
                wd = float(wind_direction) if wind_direction is not None else 0
                wind_data.append({"value": ws, "direction": wd})
            except (ValueError, TypeError):
                wind_data.append({"value": 0, "direction": 0})

            # 提取其他气象要素
            for element_name, field_names in elements.items():
                if element_name not in other_series:
                    other_series[element_name] = []
                
                value = None
                for field_name in field_names:
                    if field_name in data_source:
                        try:
                            value = float(data_source[field_name])
                            break
                        except (ValueError, TypeError):
                            continue
                
                other_series[element_name].append(value)

        # 【调试】记录提取结果统计
        logger.debug(
            "weather_timeseries_extraction_summary",
            time_points_count=len(time_points),
            wind_data_count=len(wind_data),
            has_valid_wind_data=any(w["value"] != 0 or w["direction"] != 0 for w in wind_data)
        )

        if not time_points:
            logger.warning("weather_timeseries_missing_time_points", reason="气象数据中缺少时间信息")
            return {"error": "气象数据中缺少时间信息"}

        if not wind_data:
            logger.warning("weather_timeseries_missing_wind_data", reason="气象数据中缺少风速风向信息")
            return {"error": "气象数据中缺少风速风向信息"}

        # 构建series
        series = []
        
        # 风速+风向系列（特殊类型）
        series.append({
            "name": "风速",
            "type": "wind",
            "data": wind_data,
            "unit": "m/s",
            "yAxisIndex": 0
        })

        # 其他气象要素系列
        for element_name, values in other_series.items():
            # 只添加有有效数据的系列
            if any(v is not None for v in values):
                series.append({
                    "name": element_names.get(element_name, element_name),
                    "type": "line",
                    "data": values,
                    "unit": element_units.get(element_name, ""),
                    "yAxisIndex": element_y_axis.get(element_name, 1)  # 使用配置的Y轴
                })

        # 计算风向统计
        direction_names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        direction_counts = [0] * 8
        
        for wd in wind_data:
            try:
                idx = int((float(wd["direction"]) + 22.5) % 360 / 45)
                direction_counts[idx] += 1
            except (ValueError, TypeError):
                pass

        dominant_idx = direction_counts.index(max(direction_counts)) if any(direction_counts) else 0
        dominant_direction = direction_names[dominant_idx]
        
        avg_speed = sum(w["value"] for w in wind_data) / len(wind_data) if wind_data else 0
        max_speed = max(w["value"] for w in wind_data) if wind_data else 0

        # 构建Chart v3.1格式
        chart_dict = {
            "id": f"weather_ts_{uuid.uuid4().hex[:8]}",
            "type": "weather_timeseries",
            "title": f"{station_name} - 气象要素时序变化（含风向）",
            "data": {
                "x": time_points,
                "series": series,
                "wind_statistics": {
                    "dominant_direction": dominant_direction,
                    "avg_speed": round(avg_speed, 1),
                    "max_speed": round(max_speed, 1),
                    "direction_distribution": {
                        direction_names[i]: direction_counts[i] 
                        for i in range(8)
                    }
                }
            },
            "meta": {
                "schema_version": "3.1",
                "generator": "meteorology_converter:weather_timeseries",
                "record_count": len(time_points),
                "station_name": station_name,
                "dominant_wind_direction": dominant_direction,
                "layout_hint": "wide"
            }
        }

        logger.info(
            "weather_timeseries_generation_complete",
            station_name=station_name,
            record_count=len(time_points),
            series_count=len(series),
            dominant_direction=dominant_direction
        )

        return chart_dict

    @staticmethod
    def _generate_wind_rose_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成风向玫瑰图（保留兼容性）

        Args:
            data: 气象数据
            station_name: 站点名称
            **kwargs: 额外参数

        Returns:
            风向玫瑰图数据
        """
        logger.info("wind_rose_generation_start", station_name=station_name)

        # 提取风向和风速数据
        wind_data = {}

        # 处理输入数据
        records = []
        if isinstance(data, dict) and "data" in data:
            records = data["data"]
        elif isinstance(data, list):
            records = data
        else:
            records = [data]

        for record in records:
            if not isinstance(record, dict):
                continue

            # 支持两种数据结构：扁平结构和嵌套 measurements 结构
            data_source = record.get("measurements", record)
            if not isinstance(data_source, dict):
                data_source = record

            # 提取风向（使用统一字段映射，支持 Open-Meteo 格式）
            wind_direction = MeteorologyChartConverter._get_field_value(
                data_source,
                ["windDirection", "wind_direction", "wind_direction_10m", "WD", "wd", "风向"]
            )

            # 提取风速（使用统一字段映射，支持 Open-Meteo 格式）
            wind_speed = MeteorologyChartConverter._get_field_value(
                data_source,
                ["windSpeed", "wind_speed", "wind_speed_10m", "WS", "ws", "风速"]
            )

            if wind_direction is None or wind_speed is None:
                continue

            try:
                # 标准化风向到0-360度范围
                direction = float(wind_direction)
                if direction < 0 or direction >= 360:
                    direction = direction % 360

                speed = float(wind_speed)
                if speed < 0:
                    continue

                if direction not in wind_data:
                    wind_data[direction] = []

                wind_data[direction].append(speed)
            except (ValueError, TypeError):
                continue

        if not wind_data:
            return {"error": "气象数据中缺少风向或风速信息"}

        # 按16个风向方位分组（每22.5度一个方位）
        wind_sectors = {
            "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
            "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
            "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
            "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5
        }

        # 计算每个方位的统计信息
        sector_data = []
        for direction_name, center_angle in wind_sectors.items():
            # 找到最接近该方位的所有数据点
            sector_speeds = []
            for direction, speeds in wind_data.items():
                # 计算方向差值（考虑环形）
                diff = min(
                    abs(direction - center_angle),
                    abs(direction - center_angle - 360),
                    abs(direction - center_angle + 360)
                )
                if diff <= 11.25:  # 允许±11.25度的误差
                    sector_speeds.extend(speeds)

            if sector_speeds:
                # 计算平均风速
                avg_speed = sum(sector_speeds) / len(sector_speeds)
                max_speed = max(sector_speeds)
                count = len(sector_speeds)

                sector_data.append({
                    "direction": direction_name,
                    "angle": center_angle,
                    "avg_speed": round(avg_speed, 2),
                    "max_speed": round(max_speed, 2),
                    "count": count,
                    "speed_distribution": {
                        "0-2": len([s for s in sector_speeds if 0 <= s < 2]),
                        "2-5": len([s for s in sector_speeds if 2 <= s < 5]),
                        "5-10": len([s for s in sector_speeds if 5 <= s < 10]),
                        "10+": len([s for s in sector_speeds if s >= 10])
                    }
                })

        # 构建meta信息
        meta = {
            "unit": "m/s",
            "data_source": "meteorology",
            "station_name": station_name,
            "sector_count": len(sector_data),
            "wind_directions": list(wind_sectors.keys()),
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        logger.info(
            "wind_rose_generation_complete",
            sector_count=len(sector_data),
            total_records=sum(s["count"] for s in sector_data)
        )

        return {
            "id": f"wind_rose_{station_name}",
            "type": "wind_rose",
            "title": f"{station_name}风向玫瑰图",
            "data": {
                "sectors": sector_data,
                "legend": {
                    "N": "北风",
                    "NNE": "东北偏北风",
                    "NE": "东北风",
                    "ENE": "东北偏东风",
                    "E": "东风",
                    "ESE": "东南偏东风",
                    "SE": "东南风",
                    "SSE": "东南偏南风",
                    "S": "南风",
                    "SSW": "西南偏南风",
                    "SW": "西南风",
                    "WSW": "西南偏西风",
                    "W": "西风",
                    "WNW": "西北偏西风",
                    "NW": "西北风",
                    "NNW": "西北偏北风"
                }
            },
            "meta": meta
        }

    @staticmethod
    def _generate_timeseries_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成气象要素时序图

        Args:
            data: 气象数据
            station_name: 站点名称
            **kwargs: 额外参数
                - elements: List[str] 指定要显示的气象要素（可选）
                - exclude: List[str] 指定要排除的气象要素（可选）
                - single_element: bool 是否只显示单一要素（用于标题生成）

        Returns:
            时序图数据
        """
        # 获取筛选参数
        include_elements = kwargs.get("elements", None)  # 只显示指定的要素
        exclude_elements = kwargs.get("exclude", [])  # 排除指定的要素
        single_element = kwargs.get("single_element", False)  # 单一要素模式
        
        logger.info(
            "meteorology_timeseries_generation_start", 
            station_name=station_name,
            include_elements=include_elements,
            exclude_elements=exclude_elements
        )

        # 提取时间序列数据
        time_points = []
        series_data = {}

        # 处理输入数据
        records = []
        if isinstance(data, dict) and "data" in data:
            records = data["data"]
        elif isinstance(data, list):
            records = data
        else:
            records = [data]

        # 过滤掉重复的数据类型，只保留 forecast_hourly 类型
        # 避免 boundary_layer_hourly、wind_profile 等类型造成数据重复
        filtered_records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            # 检查 metadata.type 字段
            metadata = record.get("metadata", {})
            record_type = metadata.get("type", "")
            # 只保留 forecast_hourly 或没有 type 字段的记录
            if record_type in ["forecast_hourly", ""] or not record_type:
                filtered_records.append(record)
        
        if filtered_records:
            records = filtered_records
            logger.info("meteorology_timeseries_filtered", 
                       original_count=len(records) if isinstance(data, list) else 1,
                       filtered_count=len(filtered_records))

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取时间戳
            time_val = MeteorologyChartConverter._get_field_value(
                record,
                ["timestamp", "time_point", "timePoint", "time", "DataTime", "datetime", "时间点", "时间"]
            )

            if not time_val:
                continue

            time_points.append(time_val)

            # 支持两种数据结构：
            # 1. 扁平结构: {"temperature_2m": 17.5, ...}
            # 2. 嵌套结构: {"measurements": {"temperature_2m": 17.5, ...}}
            data_source = record.get("measurements", record)
            if not isinstance(data_source, dict):
                data_source = record

            # 提取气象要素（温度、湿度、风速、气压等）
            # 支持 Open-Meteo 格式字段（如 temperature_2m, wind_speed_10m）
            all_elements = {
                "temperature": ["temperature", "temp", "气温", "temperature_2m", "apparent_temperature"],
                "humidity": ["humidity", "rh", "湿度", "relative_humidity_2m", "relative_humidity"],
                "windSpeed": ["windSpeed", "ws", "wind_speed", "风速", "wind_speed_10m", "wind_gusts_10m"],
                "windDirection": ["windDirection", "wd", "wind_direction", "风向", "wind_direction_10m"],
                "pressure": ["pressure", "press", "p", "气压", "surface_pressure", "pressure_msl"],
                "cloudCover": ["cloudCover", "cloud_cover", "云量", "cloud"],
                "precipitation": ["precipitation", "rain", "降水量", "降水"],
                "visibility": ["visibility", "能见度"],
                "boundaryLayerHeight": ["boundary_layer_height", "pblh", "边界层高度"]
            }

            # 应用筛选条件：只保留指定的要素，排除不需要的要素
            elements_to_use = {}
            for element_name, field_names in all_elements.items():
                # 如果指定了 include_elements，只包含这些要素
                if include_elements is not None:
                    if element_name not in include_elements:
                        continue
                # 如果在排除列表中，跳过
                if element_name in exclude_elements:
                    continue
                elements_to_use[element_name] = field_names

            for element_name, field_names in elements_to_use.items():
                for field_name in field_names:
                    if field_name in data_source and element_name not in series_data:
                        series_data[element_name] = []

            for element_name, field_names in elements_to_use.items():
                for field_name in field_names:
                    if field_name in data_source:
                        try:
                            value = float(data_source[field_name])
                            # 如果该要素还没有数据，使用空值填充之前的时间点
                            while len(series_data.get(element_name, [])) < len(time_points) - 1:
                                if element_name not in series_data:
                                    series_data[element_name] = []
                                series_data[element_name].append(None)

                            series_data[element_name].append(value)
                            break
                        except (ValueError, TypeError):
                            pass

        if not time_points or not series_data:
            return {"error": "气象数据中缺少时间或气象要素信息"}

        # 构建series数组
        series = []
        element_names = {
            "temperature": "温度",
            "humidity": "湿度",
            "windSpeed": "风速",
            "windDirection": "风向",
            "pressure": "气压",
            "cloudCover": "云量",
            "precipitation": "降水量",
            "visibility": "能见度",
            "boundaryLayerHeight": "边界层高度"
        }
        
        element_units = {
            "temperature": "°C",
            "humidity": "%",
            "windSpeed": "m/s",
            "windDirection": "°",
            "pressure": "hPa",
            "cloudCover": "%",
            "precipitation": "mm",
            "visibility": "m",
            "boundaryLayerHeight": "m"
        }

        for element_name, values in series_data.items():
            # 填充缺失的时间点
            while len(values) < len(time_points):
                values.append(None)

            series.append({
                "name": element_names.get(element_name, element_name),
                "data": values,
                "unit": element_units.get(element_name, "")
            })

        option = {
            "x": time_points,
            "series": series
        }

        # 构建meta信息
        meta = {
            "unit": "mixed",
            "data_source": "meteorology",
            "station_name": station_name,
            "element_count": len(series),
            "time_range": [time_points[0], time_points[-1]] if time_points else [],
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        logger.info(
            "meteorology_timeseries_generation_complete",
            time_points_count=len(time_points),
            series_count=len(series),
            elements_used=list(series_data.keys())
        )

        # 根据筛选的要素生成合适的标题和ID
        if single_element and len(series) == 1:
            # 单一要素模式：使用要素名称作为标题
            element_key = list(series_data.keys())[0]
            element_display_name = element_names.get(element_key, element_key)
            chart_title = f"{station_name}{element_display_name}变化"
            chart_id = f"{element_key}_{station_name}"
        elif include_elements and len(include_elements) <= 2:
            # 指定了少量要素：列出要素名称
            element_display_names = [element_names.get(e, e) for e in series_data.keys()]
            chart_title = f"{station_name}{'、'.join(element_display_names)}变化"
            chart_id = f"meteorology_{'_'.join(series_data.keys())}_{station_name}"
        else:
            # 默认：通用标题
            chart_title = f"{station_name}气象要素时序变化"
            chart_id = f"meteorology_timeseries_{station_name}"

        return {
            "id": chart_id,
            "type": "timeseries",
            "title": chart_title,
            "data": option,
            "meta": meta
        }

    @staticmethod
    def _generate_profile_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成边界层廓线图

        Args:
            data: 气象数据
            station_name: 站点名称
            **kwargs: 额外参数

        Returns:
            廓线图数据
        """
        logger.info("pbl_profile_generation_start", station_name=station_name)

        # 提取边界层高度和要素数据
        profiles = {}

        # 处理输入数据
        records = []
        if isinstance(data, dict) and "data" in data:
            records = data["data"]
        elif isinstance(data, list):
            records = data
        else:
            records = [data]

        for record in records:
            if not isinstance(record, dict):
                continue

            # 支持两种数据结构：扁平结构和嵌套 measurements 结构
            data_source = record.get("measurements", record)
            if not isinstance(data_source, dict):
                data_source = record

            # 提取高度
            altitude = MeteorologyChartConverter._get_field_value(
                data_source,
                ["altitude", "height", "z", "高度"]
            )

            if altitude is None:
                continue

            try:
                altitude = float(altitude)

                # 提取要素（温度、风速等，支持 Open-Meteo 格式）
                temperature = MeteorologyChartConverter._get_field_value(
                    data_source,
                    ["temperature", "temp", "气温", "temperature_2m"]
                )

                wind_speed = MeteorologyChartConverter._get_field_value(
                    data_source,
                    ["windSpeed", "ws", "风速", "wind_speed_10m"]
                )

                pbl_value = MeteorologyChartConverter._get_field_value(
                    data_source,
                    ["pbl", "PBL", "boundary_layer_height", "边界层高度"]
                )

                if altitude not in profiles:
                    profiles[altitude] = {}

                if temperature is not None:
                    try:
                        profiles[altitude]["temperature"] = float(temperature)
                    except (ValueError, TypeError):
                        pass

                if wind_speed is not None:
                    try:
                        profiles[altitude]["windSpeed"] = float(wind_speed)
                    except (ValueError, TypeError):
                        pass

                if pbl_value is not None:
                    try:
                        profiles[altitude]["pbl"] = float(pbl_value)
                    except (ValueError, TypeError):
                        pass

            except (ValueError, TypeError):
                continue

        if not profiles:
            return {"error": "气象数据中缺少高度或边界层信息"}

        # 按高度排序
        sorted_altitudes = sorted(profiles.keys(), reverse=True)

        # 构建廓线数据
        profile_data = {
            "altitudes": sorted_altitudes,
            "elements": []
        }

        # 温度廓线
        if any("temperature" in profiles[alt] for alt in sorted_altitudes):
            profile_data["elements"].append({
                "name": "温度",
                "unit": "°C",
                "data": [profiles[alt].get("temperature") for alt in sorted_altitudes]
            })

        # 风速廓线
        if any("windSpeed" in profiles[alt] for alt in sorted_altitudes):
            profile_data["elements"].append({
                "name": "风速",
                "unit": "m/s",
                "data": [profiles[alt].get("windSpeed") for alt in sorted_altitudes]
            })

        # 边界层高度
        if any("pbl" in profiles[alt] for alt in sorted_altitudes):
            profile_data["elements"].append({
                "name": "边界层高度",
                "unit": "m",
                "data": [profiles[alt].get("pbl") for alt in sorted_altitudes]
            })

        # 构建meta信息
        meta = {
            "unit": "mixed",
            "data_source": "meteorology",
            "station_name": station_name,
            "altitude_range": [min(sorted_altitudes), max(sorted_altitudes)] if sorted_altitudes else [],
            "element_count": len(profile_data["elements"]),
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        logger.info(
            "pbl_profile_generation_complete",
            altitude_count=len(sorted_altitudes),
            element_count=len(profile_data["elements"])
        )

        return {
            "id": f"pbl_profile_{station_name}",
            "type": "profile",
            "title": f"{station_name}边界层廓线",
            "data": profile_data,
            "meta": meta
        }

    @staticmethod
    def _generate_common_meteorology_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成常规气象要素时序图（温度、湿度、风速、降水、云量、能见度）

        Args:
            data: 气象数据
            station_name: 站点名称
            **kwargs: 额外参数

        Returns:
            时序图数据
        """
        logger.info("common_meteorology_chart_start", station_name=station_name)

        time_points = []
        series_data = {}

        records = data if isinstance(data, list) else [data]
        
        # 过滤数据
        filtered_records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            metadata = record.get("metadata", {})
            record_type = metadata.get("type", "")
            if record_type in ["forecast_hourly", ""] or not record_type:
                filtered_records.append(record)
        
        if filtered_records:
            records = filtered_records

        # 常规气象要素（不含气压和边界层高度）
        elements = {
            "temperature": ["temperature", "temp", "气温", "temperature_2m", "apparent_temperature"],
            "humidity": ["humidity", "rh", "湿度", "relative_humidity_2m", "relative_humidity"],
            "windSpeed": ["windSpeed", "ws", "wind_speed", "风速", "wind_speed_10m"],
            "cloudCover": ["cloudCover", "cloud_cover", "云量", "cloud"],
            "precipitation": ["precipitation", "rain", "降水量", "降水"],
            "visibility": ["visibility", "能见度"]
        }

        element_names = {
            "temperature": "温度(°C)",
            "humidity": "湿度(%)",
            "windSpeed": "风速(m/s)",
            "cloudCover": "云量(%)",
            "precipitation": "降水(mm)",
            "visibility": "能见度(km)"
        }

        for record in records:
            if not isinstance(record, dict):
                continue

            time_val = MeteorologyChartConverter._get_field_value(
                record,
                ["timestamp", "time_point", "timePoint", "time", "DataTime", "datetime", "时间点", "时间"]
            )
            if not time_val:
                continue

            time_points.append(time_val)
            data_source = record.get("measurements", record)
            if not isinstance(data_source, dict):
                data_source = record

            for element_name, field_names in elements.items():
                if element_name not in series_data:
                    series_data[element_name] = []
                
                value = None
                for field_name in field_names:
                    if field_name in data_source:
                        try:
                            value = float(data_source[field_name])
                            # 能见度转换为km
                            if element_name == "visibility" and value > 100:
                                value = value / 1000
                            break
                        except (ValueError, TypeError):
                            pass
                
                while len(series_data[element_name]) < len(time_points) - 1:
                    series_data[element_name].append(None)
                series_data[element_name].append(value)

        if not time_points:
            return {"error": "气象数据中缺少时间信息"}

        # 构建series
        series = []
        for element_name, values in series_data.items():
            if any(v is not None for v in values):
                while len(values) < len(time_points):
                    values.append(None)
                series.append({
                    "name": element_names.get(element_name, element_name),
                    "data": values
                })

        if not series:
            return {"error": "气象数据中缺少常规气象要素"}

        meta = {
            "unit": "mixed",
            "data_source": "meteorology",
            "station_name": station_name,
            "element_count": len(series),
            "time_range": [time_points[0], time_points[-1]] if time_points else [],
            "schema_version": "3.1",
            "generator": kwargs.get("generator", "meteorology_converter")
        }

        return {
            "id": f"common_meteorology_{station_name}",
            "type": "timeseries",
            "title": f"{station_name}气象要素时序变化",
            "data": {"x": time_points, "series": series},
            "meta": meta
        }

    @staticmethod
    def _generate_pressure_pbl_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成气压+边界层高度合并时序图（双Y轴）

        左Y轴: 气压 (hPa)
        右Y轴: 边界层高度 (m)

        Args:
            data: 气象数据
            station_name: 站点名称
            **kwargs: 额外参数

        Returns:
            合并时序图数据
        """
        import uuid
        logger.info("pressure_pbl_chart_start", station_name=station_name)

        time_points = []
        pressure_values = []
        pbl_values = []

        records = data if isinstance(data, list) else [data]

        # 【调试】记录原始数据信息
        logger.debug(
            "pressure_pbl_raw_data_info",
            record_count=len(records),
            sample_fields=list(records[0].keys()) if records else []
        )

        # 过滤数据
        filtered_records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            metadata = record.get("metadata", {})
            record_type = metadata.get("type", "")
            if record_type in ["forecast_hourly", ""] or not record_type:
                filtered_records.append(record)

        if filtered_records:
            records = filtered_records
            logger.debug("pressure_pbl_filtered", filtered_count=len(filtered_records))

        pressure_fields = ["pressure", "press", "p", "气压", "surface_pressure", "pressure_msl"]
        pbl_fields = ["boundaryLayerHeight", "boundary_layer_height", "pbl", "pblh", "边界层高度", 
                      "planetary_boundary_layer_height", "boundary_layer"]

        for record in records:
            if not isinstance(record, dict):
                continue

            time_val = MeteorologyChartConverter._get_field_value(
                record,
                ["timestamp", "time_point", "timePoint", "time", "DataTime", "datetime", "时间点", "时间"]
            )
            if not time_val:
                continue

            # 简化时间显示
            if isinstance(time_val, str) and len(time_val) > 10:
                time_val = time_val[5:16]  # MM-DD HH:MM

            data_source = record.get("measurements", record)
            if not isinstance(data_source, dict):
                data_source = record

            pressure = MeteorologyChartConverter._get_field_value(data_source, pressure_fields)
            pbl = MeteorologyChartConverter._get_field_value(data_source, pbl_fields)
            
            # 只要有气压或边界层高度数据就添加时间点
            if pressure is not None or pbl is not None:
                time_points.append(time_val)
                
                try:
                    pressure_values.append(float(pressure) if pressure is not None else None)
                except (ValueError, TypeError):
                    pressure_values.append(None)
                    
                try:
                    pbl_values.append(float(pbl) if pbl is not None else None)
                except (ValueError, TypeError):
                    pbl_values.append(None)

        # 【调试】记录提取结果统计
        logger.debug(
            "pressure_pbl_extraction_summary",
            time_points_count=len(time_points),
            pressure_values_count=len(pressure_values),
            pbl_values_count=len(pbl_values),
            has_pressure=any(v is not None for v in pressure_values),
            has_pbl=any(v is not None for v in pbl_values)
        )

        # 检查是否有有效数据
        has_pressure = any(v is not None for v in pressure_values)
        has_pbl = any(v is not None for v in pbl_values)

        if not time_points:
            logger.warning("pressure_pbl_missing_time_points", reason="气象数据中缺少时间信息")
            return {"error": "气象数据中缺少时间信息"}

        if not has_pressure and not has_pbl:
            logger.warning(
                "pressure_pbl_missing_data",
                reason="气象数据中缺少气压和边界层高度信息",
                pressure_fields_tried=pressure_fields,
                pbl_fields_tried=pbl_fields
            )
            return {"error": "气象数据中缺少气压和边界层高度信息"}

        # 构建series
        series = []
        
        if has_pressure:
            series.append({
                "name": "气压",
                "type": "line",
                "data": pressure_values,
                "unit": "hPa",
                "yAxisIndex": 0
            })
        
        if has_pbl:
            series.append({
                "name": "边界层高度",
                "type": "line",
                "data": pbl_values,
                "unit": "m",
                "yAxisIndex": 1
            })

        chart_dict = {
            "id": f"pressure_pbl_{uuid.uuid4().hex[:8]}",
            "type": "pressure_pbl_timeseries",
            "title": f"{station_name} - 气压与边界层高度变化",
            "data": {
                "x": time_points,
                "series": series
            },
            "meta": {
                "schema_version": "3.1",
                "generator": kwargs.get("generator", "meteorology_converter:pressure_pbl"),
                "station_name": station_name,
                "has_pressure": has_pressure,
                "has_pbl": has_pbl,
                "record_count": len(time_points),
                "layout_hint": "wide"
            }
        }

        logger.info(
            "pressure_pbl_chart_complete",
            station_name=station_name,
            record_count=len(time_points),
            has_pressure=has_pressure,
            has_pbl=has_pbl
        )

        return chart_dict

    @staticmethod
    def _generate_pressure_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成气压时序图（保留兼容性）

        Args:
            data: 气象数据
            station_name: 站点名称
            **kwargs: 额外参数

        Returns:
            气压时序图数据
        """
        logger.info("pressure_chart_start", station_name=station_name)

        time_points = []
        pressure_values = []

        records = data if isinstance(data, list) else [data]
        
        filtered_records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            metadata = record.get("metadata", {})
            record_type = metadata.get("type", "")
            if record_type in ["forecast_hourly", ""] or not record_type:
                filtered_records.append(record)
        
        if filtered_records:
            records = filtered_records

        pressure_fields = ["pressure", "press", "p", "气压", "surface_pressure", "pressure_msl"]

        for record in records:
            if not isinstance(record, dict):
                continue

            time_val = MeteorologyChartConverter._get_field_value(
                record,
                ["timestamp", "time_point", "timePoint", "time", "DataTime", "datetime", "时间点", "时间"]
            )
            if not time_val:
                continue

            data_source = record.get("measurements", record)
            if not isinstance(data_source, dict):
                data_source = record

            pressure = MeteorologyChartConverter._get_field_value(data_source, pressure_fields)
            
            if pressure is not None:
                try:
                    time_points.append(time_val)
                    pressure_values.append(float(pressure))
                except (ValueError, TypeError):
                    pass

        if not time_points or not pressure_values:
            return {"error": "气象数据中缺少气压信息"}

        meta = {
            "unit": "hPa",
            "data_source": "meteorology",
            "station_name": station_name,
            "time_range": [time_points[0], time_points[-1]] if time_points else [],
            "schema_version": "3.1",
            "generator": kwargs.get("generator", "meteorology_converter")
        }

        return {
            "id": f"pressure_{station_name}",
            "type": "timeseries",
            "title": f"{station_name}气压变化",
            "data": {
                "x": time_points,
                "series": [{"name": "气压(hPa)", "data": pressure_values}]
            },
            "meta": meta
        }

    @staticmethod
    def _generate_pbl_height_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        station_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成边界层高度时序图（单独展示）

        Args:
            data: 气象数据
            station_name: 站点名称
            **kwargs: 额外参数

        Returns:
            边界层高度时序图数据
        """
        logger.info("pbl_height_chart_start", station_name=station_name)

        time_points = []
        pbl_values = []

        records = data if isinstance(data, list) else [data]
        
        filtered_records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            metadata = record.get("metadata", {})
            record_type = metadata.get("type", "")
            if record_type in ["forecast_hourly", ""] or not record_type:
                filtered_records.append(record)
        
        if filtered_records:
            records = filtered_records

        pbl_fields = ["boundary_layer_height", "pblh", "pbl", "边界层高度", "PBL"]

        for record in records:
            if not isinstance(record, dict):
                continue

            time_val = MeteorologyChartConverter._get_field_value(
                record,
                ["timestamp", "time_point", "timePoint", "time", "DataTime", "datetime", "时间点", "时间"]
            )
            if not time_val:
                continue

            data_source = record.get("measurements", record)
            if not isinstance(data_source, dict):
                data_source = record

            pbl = MeteorologyChartConverter._get_field_value(data_source, pbl_fields)
            
            if pbl is not None:
                try:
                    time_points.append(time_val)
                    pbl_values.append(float(pbl))
                except (ValueError, TypeError):
                    pass

        if not time_points or not pbl_values:
            return {"error": "气象数据中缺少边界层高度信息"}

        meta = {
            "unit": "m",
            "data_source": "meteorology",
            "station_name": station_name,
            "time_range": [time_points[0], time_points[-1]] if time_points else [],
            "schema_version": "3.1",
            "generator": kwargs.get("generator", "meteorology_converter")
        }

        return {
            "id": f"pbl_height_{station_name}",
            "type": "timeseries",
            "title": f"{station_name}边界层高度变化",
            "data": {
                "x": time_points,
                "series": [{"name": "边界层高度(m)", "data": pbl_values}]
            },
            "meta": meta
        }

    @staticmethod
    def _get_field_value(record: Dict[str, Any], field_names: List[str]) -> Any:
        """智能获取字段值（使用统一字段映射）

        Args:
            record: 数据记录
            field_names: 候选字段名列表

        Returns:
            字段值
        """
        for field_name in field_names:
            if field_name in record:
                return record[field_name]
        return None
