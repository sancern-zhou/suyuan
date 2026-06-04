"""
上风向企业分析工具（Analyze Upwind Enterprises Tool）

基于风向风速数据，识别站点上风向的潜在污染源企业。

适用范围：广东省
限制条件：需要提供有效的风向风速数据
"""
from typing import Dict, Any, Optional
import asyncio
import structlog
import math

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.services.external_apis import upwind_api
from app.models.schemas import WindData
from config.settings import settings

logger = structlog.get_logger()


class AnalyzeUpwindEnterprisesTool(LLMTool):
    """
    上风向企业分析工具

    适用范围：广东省

    根据风向风速数据，识别站点上风向可能的污染源企业。
    返回企业列表、地图URL和详细元数据。
    """

    def __init__(self):
        function_schema = {
            "name": "analyze_upwind_enterprises",
            "description": """
分析指定站点上风向可能的污染源企业（仅适用于广东省）。

【调用方式 - 二选一】

1. 直接指定站点（推荐）：
   - 必填：station_name（站点名称），weather_data_id（气象数据ID）
   - 可选：search_range_km, max_enterprises, top_n, map_type, mode
   - 示例：station_name="广雅中学", city_name="清远市", weather_data_id="weather:v1:xxx"

2. 通过城市自动获取站点：
   - 必填：city_name（城市名称），weather_data_id（气象数据ID）
   - 可选：search_range_km, max_enterprises, top_n, map_type, mode
   - 工具自动获取该城市前2个国控站点进行分析

【参数说明】
- station_name: 站点名称（如"广雅中学"），指定具体监测站点
- city_name: 城市名称（如"清远市"），自动获取该城市站点
- weather_data_id: 气象数据ID（必须提供），工具从context自动提取风向风速
- search_range_km: 搜索半径（公里），默认5.0
- max_enterprises: 最大企业数量，默认10
- top_n: Top-N重点标注数量，默认10
- map_type: 地图类型，normal/satellite，默认normal
- mode: 展示模式，topn_mixed/all，默认topn_mixed

【返回数据】
- 企业列表（名称、行业、距离、方位、排放信息）
- 地图可视化（高德地图静态图）
- 元数据（风向扇区、站点信息等）
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "city_name": {
                        "type": "string",
                        "description": "城市名称（如：清远市、广州），与station_name二选一"
                    },
                    "station_name": {
                        "type": "string",
                        "description": "站点名称（如：广雅中学），与city_name二选一。优先使用station_name"
                    },
                    "weather_data_id": {
                        "type": "string",
                        "description": "气象数据ID（必须提供），get_weather_data返回的data_id"
                    },
                    "search_range_km": {
                        "type": "number",
                        "description": "搜索半径（公里），默认5.0",
                        "default": 5.0
                    },
                    "max_enterprises": {
                        "type": "integer",
                        "description": "最大企业数量，默认10",
                        "default": 10
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Top-N企业数量（重点标注），默认10",
                        "default": 10
                    },
                    "map_type": {
                        "type": "string",
                        "description": "地图类型：normal（普通地图）或 satellite（卫星地图），默认normal",
                        "enum": ["normal", "satellite"],
                        "default": "normal"
                    },
                    "mode": {
                        "type": "string",
                        "description": "展示模式：topn_mixed（Top-N编号+其余分层合并）或 all（所有企业），默认topn_mixed",
                        "enum": ["topn_mixed", "all"],
                        "default": "topn_mixed"
                    }
                },
                "required": ["weather_data_id"]
            }
        }

        super().__init__(
            name="analyze_upwind_enterprises",
            description="Analyze upwind enterprises based on wind data (Guangdong Province only)",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            version="2.0.0"  # 更新版本号：修复 UDF v2.0 规范兼容性
        )

        # Context-Aware V2: 设置需要 context 参数
        self.requires_context = True

        # 工具元数据（不作为__init__参数）
        self.metadata = {
            "region": "Guangdong Province",
            "limitation": "仅支持广东省内站点"
        }

    async def execute(
        self,
        context,  # Context-Aware V2: ExecutionContext 对象
        weather_data_id: str,
        city_name: str = None,
        station_name: str = None,
        search_range_km: float = None,
        max_enterprises: int = None,
        top_n: int = None,
        map_type: str = "normal",
        mode: str = "topn_mixed",
        **kwargs
    ) -> Dict[str, Any]:
        """
        调用上风向企业分析API

        Args:
            context: Context-Aware V2 执行上下文
            weather_data_id: 气象数据ID（从 context.get_data() 获取风场数据）
            city_name: 城市名称（station_name未指定时，自动获取该城市站点）
            station_name: 站点名称（优先使用，直接指定分析站点）
            search_range_km: 搜索半径（公里）
            max_enterprises: 最大企业数量
            top_n: Top-N企业数量
            map_type: 地图类型
            mode: 展示模式

        Returns:
            {
                "success": True,
                "data": {...},
                "data_id": "分析结果ID",
                "visuals": [地图可视化],
                "summary": "摘要信息"
            }
        """
        try:
            # 使用默认值，并强制上限为配置的默认值（避免请求放大到 30）
            if search_range_km is None:
                search_range_km = settings.default_search_range_km
            if max_enterprises is None or max_enterprises > settings.default_max_enterprises:
                max_enterprises = settings.default_max_enterprises
            if top_n is None or top_n > settings.default_top_n_enterprises:
                top_n = settings.default_top_n_enterprises

            # 【Context-Aware V2】从 context 获取风场数据
            winds = None
            if weather_data_id and context is not None:
                logger.info(
                    "retrieving_wind_data_from_context",
                    weather_data_id=weather_data_id
                )
                try:
                    weather_data = context.get_raw_data(weather_data_id)
                    if weather_data and len(weather_data) > 0:
                        # 转换为 winds 格式（符合 UDF v2.0 规范）
                        winds = []
                        for record in weather_data:
                            if isinstance(record, dict):
                                # 提取风向风速字段
                                # 1. 先尝试从顶层获取（兼容扁平结构）
                                wd = record.get("wind_direction_10m") or record.get("wind_direction")
                                ws = record.get("wind_speed_10m") or record.get("wind_speed")
                                time_str = record.get("timestamp") or record.get("time")

                                # 2. 如果顶层没有，按照 UDF v2.0 规范从 measurements 获取
                                if wd is None or ws is None:
                                    measurements = record.get("measurements", {})
                                    if isinstance(measurements, dict):
                                        if wd is None:
                                            wd = measurements.get("wind_direction_10m") or measurements.get("wind_direction")
                                        if ws is None:
                                            ws = measurements.get("wind_speed_10m") or measurements.get("wind_speed")

                                # 3. 验证并过滤数据（检查 NaN 和异常值）
                                if wd is not None and ws is not None:
                                    try:
                                        wd_val = float(wd)
                                        ws_val = float(ws)
                                        # 过滤 NaN 值
                                        if not (math.isnan(wd_val) or math.isnan(ws_val)):
                                            # 验证数值范围
                                            if 0 <= wd_val <= 360 and ws_val >= 0:
                                                winds.append({
                                                    "wd": wd_val,
                                                    "ws": ws_val,
                                                    "time": str(time_str) if time_str else None
                                                })
                                    except (ValueError, TypeError):
                                        pass
                        logger.info(
                            "wind_data_retrieved_from_context",
                            weather_data_id=weather_data_id,
                            record_count=len(winds)
                        )
                    else:
                        logger.warning(
                            "no_wind_data_in_context",
                            weather_data_id=weather_data_id,
                            data=weather_data
                        )
                except Exception as e:
                    logger.error(
                        "failed_to_get_wind_data_from_context",
                        weather_data_id=weather_data_id,
                        error=str(e)
                    )
                    return {
                        "success": False,
                        "error": f"无法从context获取风场数据: {str(e)}",
                        "summary": f"上风向企业分析失败：无法获取风场数据（ID: {weather_data_id}）"
                    }

            # 防御性检查：未能获取风场数据
            if winds is None or len(winds) == 0:
                return {
                    "success": False,
                    "error": "未能获取有效的风向风速数据",
                    "summary": "上风向企业分析失败：气象数据为空或无法获取"
                }

            logger.info(
                "analyze_upwind_enterprises_start",
                city_name=city_name or "目标城市",
                winds_count=len(winds),
                search_range_km=search_range_km,
                max_enterprises=max_enterprises
            )

            # 验证每个wind数据点并进行字段转换（wd_deg, ws_ms）
            valid_winds = []
            for wind in winds:
                if isinstance(wind, dict):
                    # 支持多种字段格式：
                    # 1. wd/ws 格式
                    # 2. wd_deg/ws_ms 格式
                    # 3. measurements 嵌套格式（来自 get_weather_data）
                    wd = None
                    ws = None
                    time_str = wind.get("time") or wind.get("timestamp")

                    # 尝试从 measurements 字段中提取（UDF v2.0 格式）
                    measurements = wind.get("measurements", {})
                    if measurements:
                        wd = measurements.get("wind_direction_10m") or measurements.get("wind_direction")
                        ws = measurements.get("wind_speed_10m") or measurements.get("wind_speed")
                        if not time_str:
                            time_str = wind.get("timestamp")

                    # 如果 measurements 中没有，尝试直接从 wind 字典中获取
                    if wd is None:
                        wd = wind.get("wd") or wind.get("wd_deg") or wind.get("wind_direction_10m") or wind.get("wind_direction")
                    if ws is None:
                        ws = wind.get("ws") or wind.get("ws_ms") or wind.get("wind_speed_10m") or wind.get("wind_speed")

                    if wd is not None and ws is not None:
                        try:
                            wd_val = float(wd)
                            ws_val = float(ws)
                            # 过滤 NaN 值
                            if not (math.isnan(wd_val) or math.isnan(ws_val)):
                                # 验证数值范围
                                if 0 <= wd_val <= 360 and ws_val >= 0:
                                    # API期望的格式：wd_deg, ws_ms
                                    valid_winds.append({
                                        "wd_deg": wd_val,
                                        "ws_ms": ws_val,
                                        "time": str(time_str) if time_str else "2025-12-02T06:00:00Z"
                                    })
                        except (ValueError, TypeError):
                            pass

            if not valid_winds:
                return {
                    "success": False,
                    "error": "没有有效的风向风速数据",
                    "summary": "❌ 上风向企业分析失败：风向风速数据格式无效"
                }

            logger.info(
                "valid_winds_prepared",
                total_winds=len(winds),
                valid_winds=len(valid_winds)
            )

            # 获取目标站点列表
            from app.services.external_apis import station_api

            # 优先使用直接指定的站点名称
            if station_name:
                # 直接使用指定的站点名，构建单站点目标列表
                target_stations = [{"name": station_name}]
                effective_city_name = city_name or "目标城市"
                logger.info(
                    "using_specified_station",
                    station_name=station_name,
                    city_name=effective_city_name
                )
            else:
                # 从城市获取前2个国控站点
                if not city_name:
                    return {
                        "success": False,
                        "error": "缺少city_name参数",
                        "summary": "❌ 上风向企业分析失败：未指定站点名称时必须提供城市名称"
                    }

                stations_result = await station_api.get_city_stations(
                    city_name=city_name,
                    station_type_id=1.0,  # 国控站点
                    fields="name,code,lat,lon"
                )

                if not stations_result or len(stations_result) == 0:
                    return {
                        "success": False,
                        "error": f"未找到{city_name}的国控站点",
                        "summary": f"❌ 上风向企业分析失败：未找到{city_name}的国控站点"
                    }

                # 取前2个站点（快速溯源场景，减少分析站点数量）
                target_stations = stations_result[:2]
                effective_city_name = city_name
                logger.info(
                    "target_stations_selected",
                    city_name=city_name,
                    total_stations=len(stations_result),
                    selected_stations=len(target_stations)
                )

            # 对每个站点进行上风向企业分析（并发执行）
            async def analyze_single_station(station, station_index: int):
                """分析单个站点的上风向企业"""
                station_name = station.get("站点名称") or station.get("name")
                try:
                    result = await upwind_api.analyze_upwind_enterprises(
                        station_name=station_name,
                        winds=[WindData(time=w["time"], wd_deg=w["wd_deg"], ws_ms=w["ws_ms"]) for w in valid_winds],
                        search_range_km=search_range_km,
                        max_enterprises=max_enterprises,
                        top_n=top_n,
                        map_type=map_type,
                        mode=mode,
                    )

                    if isinstance(result, dict) and result.get("status") == "success":
                        enterprises_count = len(result.get("filtered", []))
                        
                        # 优先从API返回的meta.station获取坐标（最可靠）
                        meta_station = result.get("meta", {}).get("station", {})
                        station_lat = (
                            meta_station.get("lat") or
                            station.get("纬度") or 
                            station.get("lat") or
                            station.get("latitude")
                        )
                        station_lon = (
                            meta_station.get("lng") or
                            meta_station.get("lon") or
                            station.get("经度") or 
                            station.get("lon") or
                            station.get("lng") or
                            station.get("longitude")
                        )
                        
                        logger.info(
                            "station_analysis_success",
                            station_name=station_name,
                            station_index=station_index,
                            enterprises_count=enterprises_count,
                            lat=station_lat,
                            lon=station_lon
                        )
                        return {
                            "station_name": station_name,
                            "station_code": station.get("唯一编码") or station.get("code"),
                            "lat": station_lat,
                            "lon": station_lon,
                            "result": result,
                            "enterprise_count": enterprises_count
                        }
                    else:
                        logger.warning(
                            "station_analysis_failed",
                            station_name=station_name,
                            station_index=station_index,
                            error=result.get("error", "Unknown error")
                        )
                        return None
                except Exception as e:
                    logger.error(
                        "station_analysis_exception",
                        station_name=station_name,
                        station_index=station_index,
                        error=str(e)
                    )
                    return None

            # 并发执行所有站点的分析
            logger.info(
                "starting_concurrent_analysis",
                city_name=effective_city_name,
                stations_count=len(target_stations)
            )

            tasks = [
                analyze_single_station(station, idx)
                for idx, station in enumerate(target_stations)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 过滤成功的结果
            all_results = []
            station_summaries = []

            for i, result in enumerate(results):
                if isinstance(result, dict) and result is not None:
                    all_results.append(result)
                    station_summaries.append(f"{result['station_name']}（{result['enterprise_count']}家企业）")

            if not all_results:
                return {
                    "success": False,
                    "error": "所有站点的上风向企业分析都失败了",
                    "summary": "❌ 上风向企业分析失败：无法获取任何站点的企业分析结果"
                }

            # 选择企业数量最多的结果作为主要结果
            primary_result = max(all_results, key=lambda x: x["enterprise_count"])["result"]
            result = primary_result

            logger.info(
                "concurrent_analysis_complete",
                city_name=effective_city_name,
                total_stations=len(target_stations),
                successful_stations=len(all_results),
                primary_station=max(all_results, key=lambda x: x["enterprise_count"])["station_name"]
            )

            # 验证返回结果
            if not isinstance(result, dict):
                return {
                    "success": False,
                    "error": "API返回格式无效",
                    "summary": "❌ 上风向企业分析失败：API响应格式错误"
                }

            # 提取关键信息
            enterprises_count = len(result.get("filtered", []))
            has_map_url = bool(result.get("public_url"))

            logger.info(
                "upwind_analysis_complete",
                city_name=effective_city_name,
                enterprises_count=enterprises_count,
                has_map_url=has_map_url,
                status=result.get("status"),
                stations_analyzed=len(all_results)
            )

            # 构建摘要
            if station_name:
                summary_parts = [f"✅ {station_name}共发现 {enterprises_count} 个上风向企业"]
            else:
                summary_parts = [f"✅ {effective_city_name}前{len(all_results)}个国控站点共发现 {enterprises_count} 个上风向企业"]
            if station_summaries:
                summary_parts.append("；".join(station_summaries))
            if has_map_url:
                summary_parts.append("已生成地图")

            # 【UDF v2.0 + Chart v3.1】为每个站点生成独立的地图
            from app.schemas.unified import VisualBlock
            from datetime import datetime

            timestamp = datetime.now().isoformat()
            visuals_list = []

            def get_station_coords(r):
                """获取站点坐标，优先从结果的meta中获取"""
                lat = r.get("lat")
                lon = r.get("lon")
                if not lat or not lon:
                    meta_station = r.get("result", {}).get("meta", {}).get("station", {})
                    lat = lat or meta_station.get("lat")
                    lon = lon or meta_station.get("lng") or meta_station.get("lon")
                return lat, lon

            # 为每个站点生成独立的地图
            for idx, station_result in enumerate(all_results):
                station_name = station_result["station_name"]
                station_lat, station_lon = get_station_coords(station_result)
                station_enterprises = station_result["result"].get("filtered", [])
                
                # 验证坐标有效性
                if not station_lat or not station_lon:
                    logger.warning(
                        "station_missing_coordinates",
                        city_name=effective_city_name,
                        station_name=station_name,
                        lat=station_lat,
                        lon=station_lon
                    )
                    station_lat = station_lat or 23.1
                    station_lon = station_lon or 113.3

                # 构建单个站点的地图数据
                map_data = {
                    "city_name": effective_city_name,
                    "map_center": {"lng": station_lon, "lat": station_lat},
                    "station": {
                        "lng": station_lon,
                        "lat": station_lat,
                        "name": station_name
                    },
                    "enterprises": station_enterprises,
                    "map_url": station_result["result"].get("public_url"),
                    "meta": station_result["result"].get("meta", {}),
                    "search_range_km": search_range_km,
                    "top_n": top_n,
                    "station_index": idx + 1,
                    "total_stations": len(all_results)
                }

                analysis_id = f"upwind_{effective_city_name}_{station_name}_{idx}"

                visual_block = VisualBlock(
                    id=analysis_id,
                    type="map",
                    schema="chart_config",
                    payload={
                        "id": analysis_id,
                        "type": "map",
                        "title": f"{station_name}上风向企业（{len(station_enterprises)}家）",
                        "data": map_data,
                        "meta": {
                            "schema_version": "3.1",
                            "generator": "analyze_upwind_enterprises",
                            "generator_version": "2.0.0",
                            "source_data_ids": [],
                            "scenario": "upwind_enterprise_analysis",
                            "layout_hint": "map-full",
                            "timestamp": timestamp
                        }
                    },
                    meta={
                        "schema_version": "v2.0",
                        "generator": "analyze_upwind_enterprises",
                        "scenario": "upwind_enterprise_analysis",
                        "layout_hint": "map-full",
                        "timestamp": timestamp
                    }
                )
                visuals_list.append(visual_block.dict())

                logger.info(
                    "station_map_created",
                    city_name=effective_city_name,
                    station_name=station_name,
                    station_index=idx + 1,
                    enterprises_count=len(station_enterprises)
                )

            # 计算总企业数
            total_enterprises = sum(len(r["result"].get("filtered", [])) for r in all_results)

            # 构建摘要
            if station_name:
                summary = f"✅ {station_name}上风向企业分析完成，共发现{total_enterprises}家企业"
            else:
                summary = f"✅ {effective_city_name}前{len(all_results)}个国控站点上风向企业分析完成，共生成{len(visuals_list)}个地图"

            return {
                "status": "success",
                "success": True,
                "data": None,
                "visuals": visuals_list,  # 每个站点一个独立的地图
                "metadata": {
                    "schema_version": "v2.0",
                    "source_data_ids": [],
                    "generator": "analyze_upwind_enterprises",
                    "record_count": total_enterprises,
                    "stations_count": len(all_results),
                    "analysis_params": {
                        "city_name": effective_city_name,
                        "station_name": station_name,
                        "stations_analyzed": len(all_results),
                        "search_range_km": search_range_km,
                        "max_enterprises": max_enterprises,
                        "top_n": top_n
                    }
                },
                "summary": summary
            }

        except Exception as e:
            logger.error(
                "upwind_analysis_failed",
                city_name=city_name or "未知城市",
                error=str(e),
                exc_info=True
            )

            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "data": None,
                "visuals": [],
                "metadata": {
                    "schema_version": "v2.0",
                    "source_data_ids": [],
                    "generator": "analyze_upwind_enterprises",
                    "record_count": 0
                },
                "summary": f"上风向企业分析失败: {str(e)[:50]}"
            }
