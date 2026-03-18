"""
Visualization payload generators for ECharts and AMap.

此模块负责生成标准化的图表数据，统一遵循 Chart v3.1 格式。
所有函数直接返回 v3.1 格式的字典，避免多次转换。

版本: v3.1
更新时间: 2025-11-20
"""
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger()


def generate_timeseries_chart(
    data_series: List[Dict[str, Any]],
    title: str = "时序对比图",
    x_axis_key: str = "time",
    y_axis_key: str = "value",
    series_name_key: str = "series",
    meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate standardized timeseries chart (v3.1 format).

    Args:
        data_series: List of data points with time, value, and series name
        title: Chart title
        x_axis_key: Key for x-axis (time)
        y_axis_key: Key for y-axis (value)
        series_name_key: Key for series name
        meta: Additional metadata

    Returns:
        Chart v3.1 格式的字典
    """
    # Group data by series
    series_map = {}
    time_points = set()

    for point in data_series:
        if not isinstance(point, dict):
            continue

        series_name = point.get(series_name_key, "未知")
        time_val = point.get(x_axis_key)
        y_val = point.get(y_axis_key)

        if time_val is None or y_val is None:
            continue

        # Convert string values to float for ECharts compatibility
        try:
            if isinstance(y_val, str):
                y_val = float(y_val)
        except (ValueError, TypeError):
            # Keep original value if conversion fails
            pass

        time_points.add(time_val)
        if series_name not in series_map:
            series_map[series_name] = {}
        series_map[series_name][time_val] = y_val

    # Sort time points
    x_data = sorted(list(time_points))

    # Build series array
    series = []
    for name, values_dict in series_map.items():
        data = [values_dict.get(t) for t in x_data]
        series.append({"name": name, "data": data})

    # Construct standardized timeseries data
    payload = {
        "x": x_data,
        "series": series,
    }

    # Build meta with v3.1 schema
    chart_meta = {
        "schema_version": "3.1",
        "generator": "visualization",
        "series_count": len(series),
        "time_points": len(x_data),
    }
    if meta:
        chart_meta.update(meta)

    # Return v3.1 format directly
    return {
        "id": f"timeseries_{abs(hash(title)) % 10000}",
        "type": "timeseries",
        "title": title,
        "data": {
            "type": "timeseries",
            "data": payload
        },
        "meta": chart_meta
    }


# 兼容旧函数（逐步弃用）
def generate_timeseries_payload(
    data_series: List[Dict[str, Any]],
    title: str = "时序对比图",
    x_axis_key: str = "time",
    y_axis_key: str = "value",
    series_name_key: str = "series",
) -> Dict[str, Any]:
    """
    [DEPRECATED] Generate ECharts timeseries payload.

    此函数将在v3.0中移除，请使用 generate_timeseries_chart()

    Args:
        data_series: List of data points with time, value, and series name
        title: Chart title
        x_axis_key: Key for x-axis (time)
        y_axis_key: Key for y-axis (value)
        series_name_key: Key for series name

    Returns:
        Legacy payload dict
    """
    logger.warning(
        "using_deprecated_function",
        function="generate_timeseries_payload",
        replacement="generate_timeseries_chart"
    )

    # Use new function and extract payload
    chart_result = generate_timeseries_chart(
        data_series=data_series,
        title=title,
        x_axis_key=x_axis_key,
        y_axis_key=y_axis_key,
        series_name_key=series_name_key
    )

    # Return legacy format for backward compatibility
    # Extract from v3.1 format: data.data contains {x, series}
    chart_data = chart_result.get("data", {}).get("data", {})
    return {
        "x": chart_data.get("x", []),
        "series": chart_data.get("series", [])
    }


def generate_bar_payload(
    data: List[Dict[str, Any]],
    title: str = "柱状图",
    category_key: str = "category",
    value_key: str = "value",
) -> Dict[str, Any]:
    """
    Generate ECharts bar chart payload.

    Args:
        data: List of data points with category and value
        title: Chart title
        category_key: Key for category (x-axis)
        value_key: Key for value (y-axis)

    Returns:
        ECharts-compatible payload dict
    """
    categories = []
    values = []

    for item in data:
        if not isinstance(item, dict):
            continue

        cat = item.get(category_key)
        val = item.get(value_key)

        if cat is not None and val is not None:
            # Convert string values to float for ECharts compatibility
            try:
                if isinstance(val, str):
                    val = float(val)
            except (ValueError, TypeError):
                # Keep original value if conversion fails
                pass

            categories.append(str(cat))
            values.append(val)

    # Return format expected by frontend ChartsPanel
    payload = {
        "x": categories,  # Frontend expects 'x' for categories
        "y": values,      # Frontend expects 'y' for values
    }

    return payload


def generate_pie_payload(
    data: List[Dict[str, Any]],
    title: str = "饼图",
    name_key: str = "name",
    value_key: str = "value",
) -> List[Dict[str, Any]]:
    """
    Generate ECharts pie chart payload.

    Args:
        data: List of data points with name and value
        title: Chart title (not used, kept for compatibility)
        name_key: Key for slice name
        value_key: Key for slice value

    Returns:
        List of pie data items (frontend expects array directly)
    """
    pie_data = []

    for item in data:
        if not isinstance(item, dict):
            continue

        name = item.get(name_key)
        value = item.get(value_key)

        if name is not None and value is not None:
            # Convert string values to float for ECharts compatibility
            try:
                if isinstance(value, str):
                    value = float(value)
            except (ValueError, TypeError):
                # Keep original value if conversion fails
                pass

            pie_data.append({"name": str(name), "value": value})

    # Frontend expects array directly, not wrapped in object
    return pie_data


def _to_float(value: Any) -> Optional[float]:
    """Safely convert value to float."""
    if value is None:
        return None
    try:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                return None
            return float(stripped)
        return float(value)
    except (TypeError, ValueError):
        return None


def generate_map_payload(
    station: Dict[str, Any],
    enterprises: List[Dict[str, Any]],
    upwind_paths: Optional[List[Dict[str, Any]]] = None,
    sectors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Generate AMap payload for displaying station, enterprises, and wind analysis.

    Args:
        station: Station info with lng, lat, name
        enterprises: List of enterprises with lng, lat, name, industry, score, etc.
        upwind_paths: Optional upwind trajectory paths
        sectors: Optional wind sectors

    Returns:
        AMap-compatible payload dict
    """
    # Default map center to station location
    # Support multiple field name variations for coordinates:
    # - longitude/latitude: standardized format (station-level)
    # - lng/lat: common abbreviation (enterprise data)
    # - lon/lat: city-level API format
    station_lng = _to_float(
        station.get("longitude") or
        station.get("lng") or
        station.get("lon") or
        station.get("经度")
    )
    station_lat = _to_float(
        station.get("latitude") or
        station.get("lat") or
        station.get("纬度")
    )

    if station_lng is None:
        station_lng = 113.3
    if station_lat is None:
        station_lat = 23.1

    map_center = {"lng": station_lng, "lat": station_lat}

    # Format station
    station_marker = {
        "lng": station_lng,
        "lat": station_lat,
        "name": station.get("station_name", station.get("name", "目标站点")),
    }

    # Format enterprises
    enterprise_markers = []
    for ent in enterprises:
        if not isinstance(ent, dict):
            continue

        # Support multiple field name variations for enterprise coordinates
        lng = _to_float(
            ent.get("longitude") or
            ent.get("lng") or
            ent.get("lon") or
            ent.get("经度")
        )
        lat = _to_float(
            ent.get("latitude") or
            ent.get("lat") or
            ent.get("纬度")
        )

        if lng is None or lat is None:
            logger.debug("map_enterprise_skipped", reason="invalid_coordinates", enterprise=ent.get("name"))
            continue

        marker = {
            "lng": lng,
            "lat": lat,
            "name": ent.get("name", ent.get("企业名称", "企业")),
            "industry": ent.get("industry", ent.get("行业", "")),
            "distance": ent.get("distance", ent.get("距离")),
        }

        # Optional fields
        if "score" in ent or "评分" in ent:
            marker["score"] = ent.get("score", ent.get("评分"))
        if "emissions" in ent or "排放信息" in ent:
            marker["emissions"] = ent.get("emissions", ent.get("排放信息"))

        enterprise_markers.append(marker)

    payload = {
        "map_center": map_center,
        "station": station_marker,
        "enterprises": enterprise_markers,
    }

    # Add optional elements
    if upwind_paths:
        payload["upwind_paths"] = upwind_paths
    if sectors:
        payload["sectors"] = sectors

    return payload


def generate_vocs_analysis_visuals(
    vocs_data: List[Dict[str, Any]],
    enterprise_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generate visualizations for VOCs analysis module.

    遵循数据存储层规范，支持两种输入格式：
    1. 统一格式 (UnifiedVOCsData): species_data字段包含物种字典
    2. 扁平格式 (PascalCase): DisplayName, val, ofp字段

    Args:
        vocs_data: List of VOCs data points (UnifiedVOCsData or flat format)
        enterprise_data: List of enterprise objects

    Returns:
        List of visual objects (ECharts pie/bar charts)
    """
    logger.info(
        "generate_vocs_visuals_called",
        vocs_data_count=len(vocs_data) if isinstance(vocs_data, list) else 'N/A',
        enterprise_data_count=len(enterprise_data) if isinstance(enterprise_data, list) else 'N/A',
        vocs_data_type=type(vocs_data).__name__
    )

    visuals = []

    # Extract VOCs data - support multiple formats
    # Format 1 (unified): UnifiedVOCsData models with species_data field
    # Format 2 (flat): [{DisplayName: "乙烯", val: 10.5, ofp: 3.2}, ...]
    # Format 3 (nested): [{result: {datalistOrderByOFP: [...], datalistOrderByval: [...]}}]
    all_ofp_data = []
    all_val_data = []

    # If vocs_data is a data_id dict, it's not a list - return empty visuals
    if isinstance(vocs_data, dict):
        logger.warning("vocs_data_is_data_id", data_id=vocs_data.get('data_id') if 'data_id' in vocs_data else str(vocs_data))
        logger.info("vocs_visuals_generated", total_visuals=0)
        return []

    # Detect format by checking first item
    is_unified_format = False
    is_flat_format = False
    if vocs_data and len(vocs_data) > 0:
        first_item = vocs_data[0]
        if isinstance(first_item, dict):
            # Check if it's UnifiedVOCsData format (has species_data field)
            if "species_data" in first_item:
                is_unified_format = True
                logger.info("vocs_detected_unified_format")
            # If first item has 'DisplayName' and 'ofp' fields, it's flat format
            elif "DisplayName" in first_item or "displayName" in first_item:
                is_flat_format = True
                logger.info("vocs_detected_flat_format")

    if is_unified_format:
        # UnifiedVOCsData format: extract species_data from each record
        for item in vocs_data:
            if isinstance(item, dict) and "species_data" in item:
                species_data = item["species_data"]
                if isinstance(species_data, dict):
                    # Convert species_data dict to flat format for consistency
                    for species_name, concentration in species_data.items():
                        # Create a dict mimicking flat format for concentration
                        all_val_data.append({
                            "DisplayName": species_name,
                            "val": concentration,
                            "concentration": concentration
                        })
                        # For OFP, we'd need OFP factors - using concentration as placeholder for now
                        # TODO: Integrate OFP calculation factors from external data
                        all_ofp_data.append({
                            "DisplayName": species_name,
                            "ofp": concentration * 1.0,  # Default OFP factor = 1.0 (placeholder)
                            "val": concentration
                        })
    elif is_flat_format:
        # Flat format: data points are directly in the array
        for item in vocs_data:
            if isinstance(item, dict):
                # Check if item has required fields
                has_display_name = "DisplayName" in item or "displayName" in item
                has_ofp = "ofp" in item or "OFP" in item
                has_val = "val" in item or "value" in item or "concentration" in item

                if has_display_name and (has_ofp or has_val):
                    # Add to both lists (we'll sort them separately)
                    all_ofp_data.append(item)
                    all_val_data.append(item)
    else:
        # Nested format: extract from result field
        for item in vocs_data:
            if isinstance(item, dict) and "result" in item:
                result = item["result"]

                # Handle result being None (API returns null when no data available)
                if result is None:
                    logger.warning("vocs_result_is_none", item_keys=list(item.keys()), success=item.get("success"))
                    continue

                if isinstance(result, dict):
                    # Extract OFP-ordered list
                    ofp_list = result.get("datalistOrderByOFP", [])
                    if isinstance(ofp_list, list):
                        all_ofp_data.extend(ofp_list)

                    # Extract concentration-ordered list
                    val_list = result.get("datalistOrderByval", [])
                    if isinstance(val_list, list):
                        all_val_data.extend(val_list)

    # For unified and flat formats, sort by ofp and val respectively
    if is_unified_format or is_flat_format:
        # Sort by OFP descending
        all_ofp_data = sorted(
            all_ofp_data,
            key=lambda x: float(x.get("ofp", x.get("OFP", 0)) or 0),
            reverse=True
        )
        # Sort by concentration descending
        all_val_data = sorted(
            all_val_data,
            key=lambda x: float(x.get("val", x.get("value", x.get("concentration", 0))) or 0),
            reverse=True
        )

    logger.info(
        "vocs_visuals_data_extracted",
        format="unified" if is_unified_format else "flat" if is_flat_format else "nested",
        ofp_count=len(all_ofp_data),
        val_count=len(all_val_data)
    )

    # 1. VOCs concentration top 10 pie chart (use datalistOrderByval)
    if all_val_data:
        # Take top 10 (already sorted for flat format)
        top_val_data = all_val_data[:10]

        pie_data = [
            {
                "name": item.get("DisplayName", item.get("displayName", "Unknown")),
                "value": item.get("val", item.get("value", item.get("concentration", 0))),
            }
            for item in top_val_data
            if isinstance(item, dict)
        ]

        pie_payload = generate_pie_payload(
            pie_data,
            title="VOCs浓度前十物种",
            name_key="name",
            value_key="value",
        )

        visuals.append({
            "id": "vocs_concentration_pie",
            "type": "pie",
            "chartType": "pie",  # 添加 chartType 字段
            "title": "VOCs浓度前十物种",
            "mode": "dynamic",
            "option": pie_payload,  # 使用 option 字段
            "payload": pie_payload,
            "meta": {
                "unit": "μg/m³",
                # ECharts配置：解决标签重叠问题
                "echarts_config": {
                    "series": [{
                        "type": "pie",
                        "radius": ["40%", "70%"],  # 环形饼图
                        "avoidLabelOverlap": True,
                        "label": {
                            "show": True,
                            "position": "outside",
                            "formatter": "{b}: {d}%",
                            "fontSize": 12,
                        },
                        "labelLine": {
                            "show": True,
                            "length": 15,
                            "length2": 10,
                            "smooth": False,
                        },
                        "emphasis": {
                            "label": {
                                "show": True,
                                "fontSize": 14,
                                "fontWeight": "bold"
                            }
                        }
                    }]
                }
            },
        })

    # 2. OFP contribution top 10 bar chart (use datalistOrderByOFP)
    if all_ofp_data:
        # Take top 10 (already sorted for flat format)
        top_ofp_data = all_ofp_data[:10]

        bar_data = [
            {
                "category": item.get("DisplayName", item.get("displayName", "Unknown")),
                "value": item.get("ofp", item.get("OFP", 0)),
            }
            for item in top_ofp_data
            if isinstance(item, dict)
        ]

        bar_payload = generate_bar_payload(
            bar_data,
            title="OFP贡献前十物种",
            category_key="category",
            value_key="value",
        )

        visuals.append({
            "id": "ofp_contribution_bar",
            "type": "bar",
            "chartType": "bar",  # 添加 chartType 字段
            "title": "OFP贡献前十物种",
            "mode": "dynamic",
            "option": bar_payload,  # 使用 option 字段
            "payload": bar_payload,
            "meta": {"unit": "ppb"},
        })

    logger.info("vocs_visuals_generated", total_visuals=len(visuals))

    return visuals


def generate_multi_indicator_timeseries(
    station_data: List[Dict[str, Any]],
    weather_data: List[Dict[str, Any]],
    pollutant: str = "O3",
    station_name: str = "",
    venue_name: str = "",
) -> Dict[str, Any]:
    """
    Generate multi-indicator timeseries chart with dual Y-axes.

    Left Y-axis: All available pollutants + AQI (dynamic detection)
    Right Y-axis: Temperature, Humidity, Wind Speed (if available)

    特性：
    - 动态检测所有可用污染物（O3, PM2.5, PM10, SO2, NO2, CO, AQI）
    - 有哪些数据就显示哪些，不要求所有字段必须存在
    - 即使缺少气象数据或某些污染物数据，也能正常生成图表

    Args:
        station_data: Station monitoring data with pollutant and AQI
        weather_data: Weather data with temperature, humidity, wind speed
        pollutant: Main pollutant (used for title, not limiting display)
        station_name: Station name for title (e.g., "高明孔堂")
        venue_name: Venue name if applicable (e.g., "佛山市高明体育中心")

    Returns:
        Visual object with dual-axis timeseries payload
    """
    logger.info(
        "generating_multi_indicator_chart",
        station_data_count=len(station_data),
        weather_data_count=len(weather_data),
        pollutant=pollutant
    )

    def normalize_time_format(time_str: str) -> str:
        """
        统一时间格式为 "YYYY-MM-DD HH:MM" 便于匹配和显示。

        支持的输入格式:
        - "2025-08-09 12:00:00" → "2025-08-09 12:00"
        - "2025-08-09T12:00:00" → "2025-08-09 12:00"
        - "12:00" → "YYYY-MM-DD 12:00" (补充日期部分)
        - "12:00:00" → "YYYY-MM-DD 12:00" (补充日期部分)
        """
        if not isinstance(time_str, str):
            return str(time_str)

        time_str = time_str.strip()

        # 1. 完整格式 "YYYY-MM-DD HH:MM:SS" → "YYYY-MM-DD HH:MM"
        if len(time_str) >= 16 and (' ' in time_str or 'T' in time_str):
            # 替换T为空格
            time_str = time_str.replace('T', ' ')
            # 截取到分钟
            parts = time_str.split(':')
            if len(parts) >= 2:
                return f"{parts[0]}:{parts[1]}"  # "YYYY-MM-DD HH:MM"

        # 2. 仅时间格式 "HH:MM" 或 "HH:MM:SS"
        if ':' in time_str and len(time_str) <= 8:
            # 需要从其他数据点推断日期，这里先返回原值
            # 实际使用中，应该从查询参数中获取日期
            return time_str

        return time_str

    # Build time-indexed data maps
    time_points = set()  # 所有时间点的集合（统一格式）

    # 污染物数据字典（动态检测所有可用污染物）
    pollutant_maps = {
        "O3": {},
        "PM2.5": {},
        "PM10": {},
        "SO2": {},
        "NO2": {},
        "CO": {},
        "AQI": {}
    }

    # 气象数据字典
    temp_map = {}
    humidity_map = {}
    wind_speed_map = {}

    # Process station data - 动态检测所有污染物
    for point in station_data:
        if not isinstance(point, dict):
            continue

        time_val = point.get("timePoint") or point.get("time") or point.get("时间")
        if not time_val:
            continue

        # 🔧 关键修复：统一时间格式
        time_normalized = normalize_time_format(time_val)
        time_points.add(time_normalized)

        # 动态提取所有污染物字段 - 使用统一字段映射接口
        from app.utils.data_standardizer import get_measurement_value

        for pollutant_name, data_map in pollutant_maps.items():
            # 使用统一接口获取字段值（自动处理字段映射）
            value = get_measurement_value(point, pollutant_name)

            if value is not None:
                try:
                    data_map[time_normalized] = float(value) if isinstance(value, str) else value
                except (ValueError, TypeError):
                    pass

    # Process weather data
    for point in weather_data:
        if not isinstance(point, dict):
            continue

        time_val = point.get("timePoint") or point.get("time") or point.get("时间")
        if not time_val:
            continue

        # 🔧 关键修复：统一时间格式
        time_normalized = normalize_time_format(time_val)
        time_points.add(time_normalized)

        # Temperature
        temp_val = point.get("temperature") or point.get("气温") or point.get("temp")
        if temp_val is not None:
            try:
                temp_map[time_normalized] = float(temp_val) if isinstance(temp_val, str) else temp_val
            except (ValueError, TypeError):
                pass

        # Humidity
        humidity_val = point.get("humidity") or point.get("湿度") or point.get("rh")
        if humidity_val is not None:
            try:
                humidity_map[time_normalized] = float(humidity_val) if isinstance(humidity_val, str) else humidity_val
            except (ValueError, TypeError):
                pass

        # Wind Speed
        wind_speed_val = point.get("windSpeed") or point.get("风速") or point.get("ws")
        if wind_speed_val is not None:
            try:
                wind_speed_map[time_normalized] = float(wind_speed_val) if isinstance(wind_speed_val, str) else wind_speed_val
            except (ValueError, TypeError):
                pass

    # Sort time points (使用并集 - 这是正确的做法)
    # 🔧 修复：统一时间格式后，确保监测数据和气象数据的时间点能够匹配
    x_data = sorted(list(time_points))

    logger.info(
        "multi_indicator_time_points_collected",
        total_points=len(time_points),
        sample_times=x_data[:3] if len(x_data) >= 3 else x_data
    )

    # Build series data - 动态添加所有有数据的污染物
    series = []

    # 污染物颜色配置
    pollutant_colors = {
        "O3": "#FF6B6B",      # 红色
        "PM2.5": "#FFA500",   # 橙色
        "PM10": "#FFD700",    # 金色
        "SO2": "#FF69B4",     # 粉红色
        "NO2": "#8B4513",     # 棕色
        "CO": "#9370DB",      # 紫色
        "AQI": "#32CD32"      # 绿色
    }

    # Left Y-axis series - 添加所有有数据的污染物
    detected_pollutants = []
    for pollutant_name, data_map in pollutant_maps.items():
        if data_map:  # 只添加有数据的污染物
            series.append({
                "name": pollutant_name,
                "type": "line",
                "yAxisIndex": 0,
                "data": [data_map.get(t) for t in x_data],
                "smooth": True,
                "itemStyle": {"color": pollutant_colors.get(pollutant_name, "#999999")}
            })
            detected_pollutants.append(pollutant_name)

    # Right Y-axis series (meteorological indicators) - 只添加有数据的气象指标
    detected_weather = []
    if temp_map:
        series.append({
            "name": "温度",
            "type": "line",
            "yAxisIndex": 1,
            "data": [temp_map.get(t) for t in x_data],
            "smooth": True,
            "itemStyle": {"color": "#4ECDC4"}  # Cyan for temperature
        })
        detected_weather.append("温度")

    if humidity_map:
        series.append({
            "name": "湿度",
            "type": "line",
            "yAxisIndex": 1,
            "data": [humidity_map.get(t) for t in x_data],
            "smooth": True,
            "itemStyle": {"color": "#95E1D3"}  # Light green for humidity
        })
        detected_weather.append("湿度")

    if wind_speed_map:
        series.append({
            "name": "风速",
            "type": "line",
            "yAxisIndex": 1,
            "data": [wind_speed_map.get(t) for t in x_data],
            "smooth": True,
            "itemStyle": {"color": "#A8E6CF"}  # Pale green for wind speed
        })
        detected_weather.append("风速")

    # Format time labels - 使用规范化后的时间直接作为标签
    # 因为已经统一为 "YYYY-MM-DD HH:MM" 格式，可以直接使用或简化显示
    x_labels = []
    for t in x_data:
        if isinstance(t, str) and len(t) >= 16:
            # "YYYY-MM-DD HH:MM" → 可以选择只显示日期+时间或完整格式
            # 这里保持完整格式，让前端ECharts自动处理
            x_labels.append(t)
        else:
            x_labels.append(t)

    # 动态构建Y轴标签
    left_axis_name = " / ".join(detected_pollutants) if detected_pollutants else "污染物指标"
    right_axis_name = " / ".join(detected_weather) if detected_weather else "气象指标"

    # Construct payload with dual Y-axes
    payload = {
        "x": x_labels,
        "series": series,
        "yAxis": [
            {
                "type": "value",
                "name": left_axis_name,
                "position": "left",
                "axisLabel": {"formatter": "{value}"}
            },
            {
                "type": "value",
                "name": right_axis_name,
                "position": "right",
                "axisLabel": {"formatter": "{value}"}
            }
        ]
    }

    logger.info(
        "multi_indicator_chart_generated",
        x_count=len(x_labels),
        series_count=len(series),
        series_names=[s.get("name") for s in series],
        detected_pollutants=detected_pollutants,
        detected_weather=detected_weather
    )

    # Generate title based on venue/station context
    # 动态生成标题，反映实际检测到的指标
    if detected_pollutants:
        main_indicators = " & ".join(detected_pollutants[:3])  # 最多显示前3个污染物
        if len(detected_pollutants) > 3:
            main_indicators += f"等{len(detected_pollutants)}项"
    else:
        main_indicators = "空气质量"

    if venue_name:
        title = f"{venue_name}({station_name}){main_indicators}综合趋势"
    elif station_name:
        title = f"{station_name}{main_indicators}综合趋势"
    else:
        title = f"{main_indicators}综合趋势"

    # 容错处理：即使没有series也返回有效图表
    if not series:
        logger.warning(
            "multi_indicator_no_series_detected",
            message="未检测到任何有效数据series，返回空图表",
            station_data_count=len(station_data),
            weather_data_count=len(weather_data)
        )

    return {
        "id": "multi_indicator_timeseries",
        "type": "timeseries",
        "chartType": "timeseries",  # 添加 chartType 字段
        "title": title,
        "mode": "dynamic",
        "option": payload,  # 使用 option 字段
        "payload": payload,
        "meta": {
            "dual_axis": True,
            "left_axis_indicators": detected_pollutants,
            "right_axis_indicators": detected_weather,
            "left_axis_unit": "μg/m³",
            "right_axis_unit": "混合单位",
            "total_series": len(series),
            "has_pollutants": bool(detected_pollutants),
            "has_weather": bool(detected_weather)
        }
    }


def generate_particulate_analysis_visuals(
    particulate_data: List[Dict[str, Any]],
    enterprise_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generate visualizations for particulate analysis module.

    Returns:
        List of visual objects (ECharts charts)
    """
    visuals = []

    # 1. Particulate component pie chart
    if particulate_data:
        comp_sorted = sorted(
            particulate_data,
            key=lambda x: x.get("concentration", x.get("浓度", 0)),
            reverse=True,
        )[:10]

        pie_data = [
            {
                "name": item.get("component", item.get("组分", "Unknown")),
                "value": item.get("concentration", item.get("浓度", 0)),
            }
            for item in comp_sorted
        ]

        pie_payload = generate_pie_payload(
            pie_data,
            title="颗粒物主要组分",
            name_key="name",
            value_key="value",
        )

        visuals.append({
            "id": "particulate_component_pie",
            "type": "pie",
            "chartType": "pie",  # 添加 chartType 字段
            "title": "颗粒物主要组分",
            "mode": "dynamic",
            "option": pie_payload,  # 使用 option 字段
            "payload": pie_payload,
            "meta": {
                "unit": "μg/m³",
                # ECharts配置：解决标签重叠问题
                "echarts_config": {
                    "series": [{
                        "type": "pie",
                        "radius": ["40%", "70%"],  # 环形饼图
                        "avoidLabelOverlap": True,
                        "label": {
                            "show": True,
                            "position": "outside",
                            "formatter": "{b}: {d}%",
                            "fontSize": 12,
                        },
                        "labelLine": {
                            "show": True,
                            "length": 15,
                            "length2": 10,
                            "smooth": False,
                        },
                        "emphasis": {
                            "label": {
                                "show": True,
                                "fontSize": 14,
                                "fontWeight": "bold"
                            }
                        }
                    }]
                }
            },
        })

    # 2. Industry PM emission bar chart
    if enterprise_data:
        industry_map = {}
        for ent in enterprise_data:
            industry = ent.get("industry", ent.get("行业", "其他"))
            pm_emission = 0

            emissions = ent.get("emissions", ent.get("排放信息", {}))
            if isinstance(emissions, dict):
                # 支持中英文字段名
                pm25 = (
                    emissions.get("PM2.5", 0) or
                    emissions.get("pm2.5", 0) or
                    emissions.get("细颗粒物", 0) or
                    0
                )
                pm10 = (
                    emissions.get("PM10", 0) or
                    emissions.get("pm10", 0) or
                    emissions.get("可吸入颗粒物", 0) or
                    0
                )

                # 处理字符串转数字
                if isinstance(pm25, str):
                    try:
                        pm25 = float(pm25)
                    except (ValueError, TypeError):
                        pm25 = 0
                if isinstance(pm10, str):
                    try:
                        pm10 = float(pm10)
                    except (ValueError, TypeError):
                        pm10 = 0

                pm_emission = pm25 + pm10

            industry_map[industry] = industry_map.get(industry, 0) + pm_emission

        bar_data = [
            {"category": industry, "value": emission}
            for industry, emission in sorted(
                industry_map.items(), key=lambda x: x[1], reverse=True
            )[:8]
        ]

        bar_payload = generate_bar_payload(
            bar_data,
            title="行业颗粒物排放贡献",
            category_key="category",
            value_key="value",
        )

        visuals.append({
            "id": "industry_pm_bar",
            "type": "bar",
            "chartType": "bar",  # 添加 chartType 字段
            "title": "行业颗粒物排放贡献",
            "mode": "dynamic",
            "option": bar_payload,  # 使用 option 字段
            "payload": bar_payload,
            "meta": {"unit": "吨/年"},
        })

    return visuals


def generate_regional_comparison_visual(
    station_data: List[Dict[str, Any]],
    nearby_stations_data: Dict[str, List[Dict[str, Any]]],
    station_name: str = "目标站点",
    venue_name: str = "",
) -> Dict[str, Any]:
    """
    Generate timeseries comparison chart for regional analysis.

    Args:
        station_data: Target station data
        nearby_stations_data: Dict of station_name -> data_points
        station_name: Target station name for title
        venue_name: Venue name if applicable (e.g., "佛山市高明体育中心")

    Returns:
        Visual object with timeseries payload
    """
    logger.info(
        "generating_regional_comparison",
        station_data_count=len(station_data),
        nearby_stations_count=len(nearby_stations_data),
        nearby_stations=list(nearby_stations_data.keys())
    )

    # DEBUG: Print first data point to see structure
    if station_data and len(station_data) > 0:
        logger.info(
            "DEBUG_station_data_sample",
            first_point_keys=list(station_data[0].keys()) if isinstance(station_data[0], dict) else "not_dict",
            first_point=station_data[0] if isinstance(station_data[0], dict) else None
        )

    if nearby_stations_data:
        for station_name, points in nearby_stations_data.items():
            if points and len(points) > 0:
                logger.info(
                    "DEBUG_nearby_station_sample",
                    station=station_name,
                    first_point_keys=list(points[0].keys()) if isinstance(points[0], dict) else "not_dict",
                    first_point=points[0] if isinstance(points[0], dict) else None
                )
                break  # Only show first station sample

    # Combine all data into single list with series markers
    all_data = []

    # Add target station data
    matched_count = 0
    skipped_count = 0
    for point in station_data:
        if isinstance(point, dict):
            # Try multiple field name variations for time
            time_val = point.get("timePoint") or point.get("time") or point.get("时间") or point.get("timestamp")

            # Try multiple field name variations for value - ADD POLLUTANT-SPECIFIC FIELDS
            value_val = (
                point.get("value") or
                point.get("concentration") or
                point.get("浓度") or
                point.get("值") or
                # Try pollutant-specific fields (lowercase and uppercase)
                point.get("o3") or point.get("O3") or
                point.get("pm2.5") or point.get("PM2.5") or
                point.get("pm10") or point.get("PM10") or
                point.get("so2") or point.get("SO2") or
                point.get("no2") or point.get("NO2") or
                point.get("co") or point.get("CO")
            )

            station_val = point.get("station") or point.get("站点") or point.get("stationName") or "目标站点"

            if time_val is not None and value_val is not None:
                all_data.append({
                    "time": time_val,
                    "value": value_val,
                    "series": station_val,
                })
                matched_count += 1
            else:
                skipped_count += 1
                if skipped_count <= 2:  # Only log first 2 skipped items
                    logger.warning(
                        "DEBUG_skipped_station_point",
                        reason="missing_time_or_value",
                        time_val=time_val,
                        value_val=value_val,
                        available_keys=list(point.keys())
                    )

    logger.info(
        "DEBUG_station_data_processing",
        total_points=len(station_data),
        matched=matched_count,
        skipped=skipped_count
    )

    # Add nearby stations data
    for station_name, points in nearby_stations_data.items():
        station_matched = 0
        station_skipped = 0
        for point in points:
            if isinstance(point, dict):
                # Try multiple field name variations for time
                time_val = point.get("timePoint") or point.get("time") or point.get("时间") or point.get("timestamp")

                # Try multiple field name variations for value - ADD POLLUTANT-SPECIFIC FIELDS
                value_val = (
                    point.get("value") or
                    point.get("concentration") or
                    point.get("浓度") or
                    point.get("值") or
                    # Try pollutant-specific fields
                    point.get("o3") or point.get("O3") or
                    point.get("pm2.5") or point.get("PM2.5") or
                    point.get("pm10") or point.get("PM10") or
                    point.get("so2") or point.get("SO2") or
                    point.get("no2") or point.get("NO2") or
                    point.get("co") or point.get("CO")
                )

                if time_val is not None and value_val is not None:
                    all_data.append({
                        "time": time_val,
                        "value": value_val,
                        "series": station_name,
                    })
                    station_matched += 1
                else:
                    station_skipped += 1

        logger.info(
            "DEBUG_nearby_station_processing",
            station=station_name,
            total_points=len(points),
            matched=station_matched,
            skipped=station_skipped
        )

    logger.info(
        "regional_comparison_data_prepared",
        total_points=len(all_data),
        sample_point=all_data[0] if all_data else None
    )
    
    payload = generate_timeseries_payload(
        all_data,
        title="站点浓度时序对比",
        x_axis_key="time",
        y_axis_key="value",
        series_name_key="series",
    )

    logger.info(
        "regional_comparison_payload_generated",
        x_count=len(payload.get("x", [])),
        series_count=len(payload.get("series", [])),
        series_names=[s.get("name") for s in payload.get("series", [])]
    )

    # Generate title based on venue/station context
    if venue_name:
        title = f"{venue_name}({station_name})与周边站点浓度对比"
    else:
        title = f"{station_name}与周边站点浓度对比"

    return {
        "id": "regional_comparison_timeseries",
        "type": "timeseries",
        "chartType": "timeseries",  # 添加 chartType 字段
        "title": title,
        "mode": "dynamic",
        "option": payload,  # 使用 option 字段
        "payload": payload,
        "meta": {"unit": "μg/m³"},
    }


# ============================================
# 标准化图表生成函数（v3.1）
# 这些函数直接返回 Chart v3.1 格式的字典
# ============================================


def generate_pie_chart(
    data: List[Dict[str, Any]],
    title: str = "饼图",
    meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate standardized pie chart (v3.1 format).

    Args:
        data: List of data points with name and value
        title: Chart title
        meta: Additional metadata

    Returns:
        Chart v3.1 格式的字典
    """
    pie_data = []
    for item in data:
        if isinstance(item, dict):
            name = item.get("name", item.get("category", "Unknown"))
            value = item.get("value", item.get("concentration", 0))
            pie_data.append({"name": str(name), "value": value})

    # Build meta with v3.1 schema
    chart_meta = {
        "schema_version": "3.1",
        "generator": "visualization",
        "data_count": len(pie_data),
    }
    if meta:
        chart_meta.update(meta)

    return {
        "id": f"pie_{abs(hash(title)) % 10000}",
        "type": "pie",
        "title": title,
        "data": {
            "type": "pie",
            "data": pie_data
        },
        "meta": chart_meta
    }


def generate_bar_chart(
    data: List[Dict[str, Any]],
    title: str = "柱状图",
    category_key: str = "category",
    value_key: str = "value",
    meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate standardized bar chart (v3.1 format).

    Args:
        data: List of data points with category and value
        title: Chart title
        category_key: Key for category (x-axis)
        value_key: Key for value (y-axis)
        meta: Additional metadata

    Returns:
        Chart v3.1 格式的字典
    """
    categories = []
    values = []

    for item in data:
        if isinstance(item, dict):
            cat = item.get(category_key)
            val = item.get(value_key)
            if cat is not None and val is not None:
                categories.append(str(cat))
                values.append(val)

    payload = {
        "x": categories,
        "y": values,
    }

    # Build meta with v3.1 schema
    chart_meta = {
        "schema_version": "3.1",
        "generator": "visualization",
        "category_count": len(categories),
    }
    if meta:
        chart_meta.update(meta)

    return {
        "id": f"bar_{abs(hash(title)) % 10000}",
        "type": "bar",
        "title": title,
        "data": {
            "type": "bar",
            "data": payload
        },
        "meta": chart_meta
    }


def generate_line_chart(
    data: Dict[str, List],
    title: str = "折线图",
    meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate standardized line chart (v3.1 format).

    Args:
        data: Chart data with x and y arrays
        title: Chart title
        meta: Additional metadata

    Returns:
        Chart v3.1 格式的字典
    """
    # Build meta with v3.1 schema
    chart_meta = {
        "schema_version": "3.1",
        "generator": "visualization",
    }
    if meta:
        chart_meta.update(meta)

    return {
        "id": f"line_{abs(hash(title)) % 10000}",
        "type": "line",
        "title": title,
        "data": {
            "type": "line",
            "data": data
        },
        "meta": chart_meta
    }


def generate_multi_indicator_timeseries_chart(
    station_data: List[Dict[str, Any]],
    weather_data: List[Dict[str, Any]],
    pollutant: str = "O3",
    station_name: str = "",
    venue_name: str = ""
) -> Dict[str, Any]:
    """
    Generate standardized multi-indicator timeseries chart (v3.1 format).

    Args:
        station_data: Station monitoring data
        weather_data: Weather data
        pollutant: Main pollutant type
        station_name: Station name
        venue_name: Venue name

    Returns:
        Chart v3.1 格式的字典
    """
    # Use existing logic - already returns v3.1 format
    result = generate_multi_indicator_timeseries(
        station_data=station_data,
        weather_data=weather_data,
        pollutant=pollutant,
        station_name=station_name,
        venue_name=venue_name
    )

    # Ensure v3.1 meta
    if "meta" not in result:
        result["meta"] = {}
    result["meta"]["schema_version"] = "3.1"

    return result


def generate_regional_comparison_chart(
    station_data: List[Dict[str, Any]],
    nearby_stations_data: Dict[str, List[Dict[str, Any]]],
    station_name: str = "目标站点",
    venue_name: str = "",
    meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate standardized regional comparison chart (v3.1 format).

    Args:
        station_data: Target station data
        nearby_stations_data: Nearby stations data
        station_name: Target station name
        venue_name: Venue name
        meta: Additional metadata

    Returns:
        Chart v3.1 格式的字典
    """
    # Use existing function - already returns v3.1 format
    result = generate_regional_comparison_visual(
        station_data=station_data,
        nearby_stations_data=nearby_stations_data,
        station_name=station_name,
        venue_name=venue_name
    )

    # Ensure v3.1 meta
    if "meta" not in result:
        result["meta"] = {}
    result["meta"]["schema_version"] = "3.1"
    if meta:
        result["meta"].update(meta)

    return result


# ============================================
# 统一VOCs和颗粒物分析生成（v3.1）
# ============================================


def generate_vocs_analysis_charts(
    vocs_data: List[Dict[str, Any]],
    enterprise_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generate standardized VOCs analysis charts (v3.1 format).

    Args:
        vocs_data: VOCs data points
        enterprise_data: Enterprise objects

    Returns:
        List of Chart v3.1 格式的字典
    """
    # Use existing function - already returns v3.1-like format
    visuals = generate_vocs_analysis_visuals(
        vocs_data=vocs_data,
        enterprise_data=enterprise_data
    )

    # Ensure v3.1 meta for each visual
    for visual in visuals:
        if "meta" not in visual:
            visual["meta"] = {}
        visual["meta"]["schema_version"] = "3.1"

    return visuals


def generate_particulate_analysis_charts(
    particulate_data: List[Dict[str, Any]],
    enterprise_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generate standardized particulate analysis charts (v3.1 format).

    Args:
        particulate_data: Particulate data points
        enterprise_data: Enterprise objects

    Returns:
        List of Chart v3.1 格式的字典
    """
    # Use existing function - already returns v3.1-like format
    visuals = generate_particulate_analysis_visuals(
        particulate_data=particulate_data,
        enterprise_data=enterprise_data
    )

    # Ensure v3.1 meta for each visual
    for visual in visuals:
        if "meta" not in visual:
            visual["meta"] = {}
        visual["meta"]["schema_version"] = "3.1"

    return visuals
