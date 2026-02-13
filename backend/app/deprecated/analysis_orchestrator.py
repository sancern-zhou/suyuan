"""
Main analysis orchestrator that coordinates the entire traceability workflow.
"""
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from app.models.schemas import (
    ExtractedParams,
    AnalysisResponseData,
    ModuleResult,
    QueryInfo,
    VisualizationCapability,
    StationInfo,
    WindData,
)
from app.services.external_apis import (
    station_api,
    monitoring_api,
    weather_api,
    upwind_api,
)
from app.services.llm_service import llm_service
from app.services.history_service import history_service, AnalysisHistoryRecord
# from app.utils.data_processing import (
#     extract_city_district,
#     format_weather_to_winds,
#     extract_public_url,
#     normalize_city_name,
# )  # 已迁移到本地实现
from app.utils.time_utils import normalize_time_param, validate_time_range
from app.utils.visualization import (
    generate_map_payload,
    generate_vocs_analysis_visuals,
    generate_particulate_analysis_visuals,
    generate_regional_comparison_visual,
    generate_timeseries_payload,
    generate_multi_indicator_timeseries,
)
from config.settings import settings
import structlog

# Import city analysis orchestrator for city-level queries
from app.services.city_analysis_orchestrator import city_orchestrator

logger = structlog.get_logger()


def normalize_city_name(city: str) -> str:
    """
    Normalize city name by removing '市' suffix.
    """
    if not city:
        return ""
    return city.replace("市", "").strip()


def format_weather_to_winds(weather_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert weather data to winds array format.
    """
    winds = []
    for item in weather_data:
        if not isinstance(item, dict):
            continue
        wind_direction = item.get("windDirection")
        wind_speed = item.get("windSpeed")
        time_point = item.get("timePoint")
        if wind_direction is None or wind_speed is None or not time_point:
            continue
        original_time = str(time_point)
        time_iso = original_time.replace(" ", "T")
        if not time_iso.endswith("Z"):
            time_part = time_iso.split("T")[-1] if "T" in time_iso else time_iso
            if time_part.count(":") == 1:
                time_iso += ":00"
            elif time_part.count(":") == 0:
                time_iso += ":00:00"
            time_iso += "Z"
        winds.append({
            "time": time_iso,
            "wd_deg": float(wind_direction),
            "ws_ms": float(wind_speed),
        })
    return winds


def extract_city_district(response_data: Any) -> Tuple[str, str]:
    """
    Extract city and district names from API response.
    """
    import re
    CN_RE = re.compile(r"[\u4e00-\u9fff]+")

    def only_cn(s: Any) -> str:
        return "".join(CN_RE.findall(str(s or "")))

    def deep_loads(x: Any, max_round: int = 20) -> Any:
        cur = x
        for _ in range(max_round):
            if isinstance(cur, (dict, list)):
                return cur
            if not isinstance(cur, str):
                return cur
            s = cur.strip()
            if not s:
                return {}
            try:
                import json
                nxt = json.loads(s)
                if nxt == cur:
                    return nxt
                cur = nxt
                continue
            except Exception:
                return cur
        return cur

    city = ""
    dist = ""
    resp = deep_loads(response_data)
    if isinstance(resp, dict):
        body_raw = resp.get("body", response_data)
        body = deep_loads(body_raw)
        data = body.get("data", {}) if isinstance(body, dict) else {}
        if isinstance(data, dict):
            for key in ["城市", "City", "CityName"]:
                if key in data:
                    city = only_cn(data[key])
                    break
            for key in ["区县", "District", "DirectName"]:
                if key in data:
                    dist = only_cn(data[key])
                    break
    return city, dist


def extract_public_url(response_data: Any) -> Optional[str]:
    """
    Extract public_url from upwind analysis API response.
    """
    import json

    def deep_loads(x: Any) -> Any:
        cur = x
        for _ in range(5):
            if isinstance(cur, dict):
                return cur
            if isinstance(cur, str):
                try:
                    cur = json.loads(cur.strip())
                    continue
                except Exception:
                    try:
                        unesc = cur.encode("utf-8").decode("unicode_escape")
                        cur = json.loads(unesc)
                        continue
                    except Exception:
                        return None
            return None
        return cur

    obj = deep_loads(response_data)
    if isinstance(obj, dict):
        url = obj.get("public_url")
        if isinstance(url, str) and url:
            return url
        urls = obj.get("public_urls")
        if isinstance(urls, list) and urls and isinstance(urls[0], str):
            return urls[0]
        body = obj.get("body")
        if isinstance(body, dict):
            url = body.get("public_url")
            if isinstance(url, str) and url:
                return url
    return None


class AnalysisOrchestrator:
    """
    Main orchestrator for pollution source traceability analysis.

    Workflow:
    1. Extract parameters from user query
    2. Fetch station info and validate
    3. Fetch monitoring data (target station + nearby stations)
    4. Fetch meteorological data
    5. Analyze upwind enterprises
    6. Fetch component data (VOCs or Particulate) based on pollutant
    7. Run LLM analyses:
       - Component analysis (VOCs or Particulate)
       - Regional comparison
       - Weather analysis
    8. Generate comprehensive summary
    9. Assemble response with visualizations
    """

    async def analyze(self, query: str) -> AnalysisResponseData:
        """
        Main analysis entry point.

        Args:
            query: User's natural language query

        Returns:
            Complete analysis response data
        """
        logger.info("analysis_start", query=query[:100])

        try:
            # Step 1: Extract parameters
            params = await self._extract_parameters(query)
            logger.info("params_extracted", params=params, scale=params.scale)

            # Route to different workflows based on scale
            if params.scale == "city":
                # City-level analysis workflow - delegate to city orchestrator
                logger.info("routing_to_city_orchestrator", city=params.city)
                return await city_orchestrator.analyze_city(params)

            # Station-level analysis workflow (default)
            # Step 2: Validate and fetch station info
            station_info = await self._get_station_info(params)
            if not station_info:
                return self._create_error_response("无法找到指定站点")

            # Step 3: Parallel data fetching
            import time
            step3_start = time.time()

            (
                station_data,
                weather_data,
                nearby_stations,
                nearby_stations_data,
                nearest_superstation,
            ) = await self._fetch_core_data(params, station_info)

            step3_duration = time.time() - step3_start
            logger.info("step3_timing", duration=f"{step3_duration:.2f}s")

            # Wave 1: Parallel data fetching (upwind + component data)
            wave1_start = time.time()
            logger.info("wave1_start", tasks=["upwind_analysis", "component_data"])

            upwind_result, component_data = await asyncio.gather(
                self._analyze_upwind_enterprises(params, station_info, weather_data),
                self._fetch_component_data(params, nearest_superstation),
                return_exceptions=True,
            )

            # Handle exceptions
            if isinstance(upwind_result, Exception):
                logger.error("upwind_analysis_failed", error=str(upwind_result))
                upwind_result = {}
            if isinstance(component_data, Exception):
                logger.error("component_data_fetch_failed", error=str(component_data))
                component_data = []

            # Extract enterprise list for LLM analysis
            enterprises = upwind_result.get("filtered", []) if upwind_result else []

            wave1_duration = time.time() - wave1_start
            logger.info(
                "wave1_complete",
                duration=f"{wave1_duration:.2f}s",
                upwind_enterprises=len(enterprises),
                component_data_points=len(component_data),
            )

            # Wave 2: Parallel LLM analyses (component + regional + weather)
            wave2_start = time.time()
            logger.info(
                "wave2_start",
                tasks=["component_analysis_llm", "regional_comparison_llm", "weather_analysis"],
            )

            # Prepare regional analysis task (conditional)
            if nearby_stations_data:
                regional_task = self._analyze_regional_comparison(
                    params, station_info, station_data, nearby_stations_data
                )
            else:
                # Create dummy task that returns default result
                async def no_regional_analysis():
                    logger.info("skip_regional_analysis", reason="no_nearby_stations")
                    return ModuleResult(
                        analysis_type="regional_analysis",
                        content="**区域对比分析**\n\n暂无周边站点数据，无法进行区域对比分析。",
                        confidence=0.0,
                        visuals=[],
                        anchors=[],
                    )
                regional_task = no_regional_analysis()

            # Execute Wave 2 parallel tasks
            component_analysis, regional_analysis, weather_analysis = await asyncio.gather(
                self._analyze_components(
                    params, station_data, weather_data, enterprises, component_data
                ),
                regional_task,
                self._analyze_weather_impact(
                    params, station_info, station_data, weather_data, enterprises, upwind_result
                ),
                return_exceptions=True,
            )

            # Handle exceptions
            if isinstance(component_analysis, Exception):
                logger.error("component_analysis_failed", error=str(component_analysis))
                component_analysis = None
            if isinstance(regional_analysis, Exception):
                logger.error("regional_analysis_failed", error=str(regional_analysis))
                regional_analysis = ModuleResult(
                    analysis_type="regional_analysis",
                    content="**区域对比分析**\n\n分析失败，请稍后重试。",
                    confidence=0.0,
                )
            if isinstance(weather_analysis, Exception):
                logger.error("weather_analysis_failed", error=str(weather_analysis))
                weather_analysis = ModuleResult(
                    analysis_type="weather_analysis",
                    content="**气象分析**\n\n分析失败，请稍后重试。",
                    confidence=0.0,
                )

            wave2_duration = time.time() - wave2_start
            logger.info("wave2_complete", duration=f"{wave2_duration:.2f}s")

            # Wave 3: Comprehensive summary (depends on all Wave 2 results)
            wave3_start = time.time()
            logger.info("wave3_start", task="comprehensive_summary_llm")

            comprehensive_analysis = await self._generate_comprehensive_summary(
                params,
                station_info,
                upwind_result,
                weather_analysis,
                regional_analysis,
                component_analysis,
            )

            wave3_duration = time.time() - wave3_start
            logger.info("wave3_complete", duration=f"{wave3_duration:.2f}s")

            # Total workflow timing
            total_duration = time.time() - step3_start
            logger.info(
                "workflow_timing_summary",
                step3_core_data=f"{step3_duration:.2f}s",
                wave1_parallel_fetch=f"{wave1_duration:.2f}s",
                wave2_parallel_llm=f"{wave2_duration:.2f}s",
                wave3_comprehensive=f"{wave3_duration:.2f}s",
                total_after_params=f"{total_duration:.2f}s",
            )

            # Step 10: Assemble response
            response = self._assemble_response(
                params,
                station_info,
                upwind_result,
                weather_analysis,
                regional_analysis,
                component_analysis,
                comprehensive_analysis,
            )

            # Step 11: Save to history database
            try:
                history_record = AnalysisHistoryRecord(
                    query_text=query,
                    scale=params.scale,
                    location=params.location,
                    city=params.city or station_info.get("city"),
                    pollutant=params.pollutant,
                    start_time=params.start_time,
                    end_time=params.end_time,
                    # Raw data
                    meteorological_data=weather_data,
                    monitoring_data=station_data,
                    nearby_stations_data=[{"name": k, "data": v} for k, v in nearby_stations_data.items()],
                    vocs_data=component_data if params.pollutant == "O3" else None,
                    particulate_data=component_data if params.pollutant in ["PM2.5", "PM10"] else None,
                    upwind_enterprises=upwind_result.get("filtered", []) if upwind_result else None,
                    upwind_map_url=upwind_result.get("public_url") if upwind_result else None,
                    station_info=station_info,
                    # Analysis results
                    weather_analysis=weather_analysis.content,
                    regional_comparison=regional_analysis.content,
                    vocs_source_analysis=component_analysis.content if component_analysis and params.pollutant == "O3" else None,
                    particulate_source_analysis=component_analysis.content if component_analysis and params.pollutant in ["PM2.5", "PM10"] else None,
                    comprehensive_summary=comprehensive_analysis.content,
                    modules_data=response.dict() if hasattr(response, "dict") else None,
                    # Metadata
                    status="completed",
                    duration_seconds=total_duration,
                )

                session_id = await history_service.save_analysis(history_record)
                logger.info("analysis_saved_to_history", session_id=session_id, station=params.location)
            except Exception as e:
                logger.warning("failed_to_save_history", error=str(e), exc_info=True)

            logger.info("analysis_complete", station=params.location)
            return response

        except Exception as e:
            logger.error("analysis_failed", error=str(e), exc_info=True)
            return self._create_error_response(f"分析失败: {str(e)}")

    async def _extract_parameters(self, query: str) -> ExtractedParams:
        """Extract structured parameters from query using LLM."""
        params_dict = await llm_service.extract_parameters(query)

        # 🔧 修复：如果scale为None，设置默认值为"station"
        if params_dict.get("scale") is None:
            params_dict["scale"] = "station"

        # ✅ 验证必需参数，支持城市和站点两种查询尺度
        missing_params = []
        scale = params_dict.get("scale", "station")

        # 站点级别查询：需要站点名称
        if scale == "station":
            if not params_dict.get("location"):
                missing_params.append("站点名称")
        # 城市级别查询：需要城市名称（location可选）
        elif scale == "city":
            if not params_dict.get("city"):
                missing_params.append("城市名称")

        # 公共必需参数
        if not params_dict.get("pollutant"):
            missing_params.append("污染物类型")
        if not params_dict.get("start_time"):
            missing_params.append("开始时间")
        if not params_dict.get("end_time"):
            missing_params.append("结束时间")

        if missing_params:
            missing_str = "、".join(missing_params)
            error_msg = f"⚠️ 查询信息不完整，缺少关键参数：**{missing_str}**\n\n"
            error_msg += "**请提供完整的查询信息，例如：**\n"
            if scale == "station":
                error_msg += "- 分析广州天河站2025年8月9日的O3污染情况\n"
                error_msg += "- 查询深圳南山站昨天的PM2.5数据\n"
                error_msg += "- 分析珠海香洲站最近24小时的NO2浓度\n\n"
                error_msg += "**必需信息包括：**\n"
                error_msg += "1. 站点名称（如：天河站、南山站）\n"
                error_msg += "2. 污染物类型（如：O3、PM2.5、PM10、NO2、SO2、CO）\n"
                error_msg += "3. 时间范围（如：2025-08-09、昨天、最近24小时）"
            else:  # city
                error_msg += "- 分析广州市2025年8月9日的O3污染情况\n"
                error_msg += "- 查询深圳市昨天的PM2.5数据\n"
                error_msg += "- 分析珠海市最近24小时的NO2浓度\n\n"
                error_msg += "**必需信息包括：**\n"
                error_msg += "1. 城市名称（如：广州市、深圳市）\n"
                error_msg += "2. 污染物类型（如：O3、PM2.5、PM10、NO2、SO2、CO）\n"
                error_msg += "3. 时间范围（如：2025-08-09、昨天、最近24小时）"

            logger.warning("incomplete_query_params", missing=missing_params, scale=scale, query=query[:100])
            raise ValueError(error_msg)

        # Normalize city name
        if params_dict.get("city"):
            params_dict["city"] = normalize_city_name(params_dict["city"])

        # 🔧 关键修复：规范化时间格式，确保两个API接收到相同格式的时间参数
        # 问题：LLM可能返回仅日期格式 "YYYY-MM-DD"，导致气象API只返回1小时数据
        # 解决：将时间统一规范化为 "YYYY-MM-DD HH:MM:SS" 格式
        if params_dict.get("start_time"):
            original_start = params_dict["start_time"]
            params_dict["start_time"] = normalize_time_param(
                params_dict["start_time"], is_end_time=False
            )
            if original_start != params_dict["start_time"]:
                logger.info(
                    "start_time_normalized",
                    original=original_start,
                    normalized=params_dict["start_time"]
                )

        if params_dict.get("end_time"):
            original_end = params_dict["end_time"]
            params_dict["end_time"] = normalize_time_param(
                params_dict["end_time"], is_end_time=True
            )
            if original_end != params_dict["end_time"]:
                logger.info(
                    "end_time_normalized",
                    original=original_end,
                    normalized=params_dict["end_time"]
                )

        # 验证时间范围
        if params_dict.get("start_time") and params_dict.get("end_time"):
            if not validate_time_range(params_dict["start_time"], params_dict["end_time"]):
                logger.warning(
                    "time_range_validation_warning",
                    start=params_dict["start_time"],
                    end=params_dict["end_time"]
                )

        return ExtractedParams(**params_dict)

    async def _get_station_info(self, params: ExtractedParams) -> Optional[Dict[str, Any]]:
        """Get station information and validate."""
        if not params.location:
            logger.warning("no_station_location")
            return None

        # Query station by name
        station_data = await station_api.get_station_by_name(params.location, top_k=1)

        if not station_data:
            logger.warning("station_not_found", location=params.location)
            return None

        # Extract city and district
        city, district = extract_city_district(station_data)

        # Merge info
        station_info = {
            "station_name": station_data.get("站点名称", params.location),
            "station_code": station_data.get("唯一编码"),
            "city": city or params.city or station_data.get("城市", ""),
            "district": district or station_data.get("区县", ""),
            "longitude": station_data.get("经度", 0),
            "latitude": station_data.get("纬度", 0),
            "address": station_data.get("详细地址", ""),
        }

        logger.info("station_info_resolved", station_info=station_info)
        return station_info

    def _generate_dashboard_title(self, params: ExtractedParams) -> str:
        """
        Generate dynamic dashboard title based on analysis parameters.

        Format:
        - Station level: 城市+站点名称+污染物指标+溯源分析报告
        - City level: 城市+污染物指标+溯源分析报告
        - Venue level: 城市+场馆名称（站点名称）+污染物+溯源分析报告

        Args:
            params: Extracted parameters with location, city, pollutant, scale, venue_name

        Returns:
            Formatted dashboard title string
        """
        city = params.city or ""
        location = params.location or ""
        pollutant = params.pollutant or ""
        scale = params.scale
        venue_name = params.venue_name or ""

        # City-level analysis
        if scale == "city":
            return f"{city}{pollutant}溯源分析报告"

        # Station-level analysis
        if location:
            # Venue-type station: if venue_name field exists, use venue format
            if venue_name:
                # Venue format: 城市+场馆名称（站点名称）+污染物+报告
                return f"{city}{venue_name}（{location}）{pollutant}溯源分析报告"
            else:
                # Regular station format: 城市+站点名称+污染物+报告
                return f"{city}{location}{pollutant}溯源分析报告"

        # Fallback to default title
        return "大气污染溯源分析助手"

    async def _fetch_core_data(
        self, params: ExtractedParams, station_info: Dict[str, Any]
    ) -> Tuple[List, List, List, Dict, Optional[Dict]]:
        """
        Fetch core data in parallel:
        - Station monitoring data
        - Weather data
        - Nearby stations
        - Nearest superstation (component station)
        - Nearby stations monitoring data (fetched after parallel tasks)
        """
        station_name = station_info["station_name"]
        city = station_info["city"]
        district = station_info["district"]

        # Parallel fetch (4 concurrent requests)
        results = await asyncio.gather(
            # Station pollutant data
            monitoring_api.get_station_pollutant_data(
                station_name,
                params.pollutant or "O3",
                params.start_time or "",
                params.end_time or "",
            ),
            # Weather data
            weather_api.get_weather_data(
                city, district, params.start_time or "", params.end_time or ""
            ),
            # Nearby stations
            station_api.get_nearby_stations(
                station_name,
                max_distance=settings.nearby_stations_radius_km,
                max_results=settings.nearby_stations_max_results,
            ),
            # Nearest superstation (NEW: 4th parallel request)
            station_api.get_nearest_superstation(
                station_name,
                max_distance=100.0,  # Search within 100km
                max_results=1,
            ),
            return_exceptions=True,
        )

        station_data = results[0] if not isinstance(results[0], Exception) else []
        weather_data = results[1] if not isinstance(results[1], Exception) else []
        nearby_stations = results[2] if not isinstance(results[2], Exception) else []
        nearest_superstation = results[3] if not isinstance(results[3], Exception) else None

        # Fetch nearby stations data
        nearby_stations_data = {}
        if nearby_stations:
            logger.info(
                "DEBUG_nearby_stations_list",
                count=len(nearby_stations),
                stations=[n.get("站点名称", n.get("name")) for n in nearby_stations[:5]]
            )

            tasks = []
            station_names = []
            for nearby in nearby_stations[:3]:  # Limit to 3 nearby stations
                nearby_name = nearby.get("站点名称", nearby.get("name"))
                if nearby_name:
                    station_names.append(nearby_name)
                    tasks.append(
                        monitoring_api.get_station_pollutant_data(
                            nearby_name,
                            params.pollutant or "O3",
                            params.start_time or "",
                            params.end_time or "",
                        )
                    )
                    logger.info(
                        "DEBUG_fetching_nearby_station",
                        station_name=nearby_name,
                        index=len(tasks)-1
                    )

            if tasks:
                nearby_results = await asyncio.gather(*tasks, return_exceptions=True)

                for i, nearby_name in enumerate(station_names):
                    if i < len(nearby_results):
                        result = nearby_results[i]
                        if isinstance(result, Exception):
                            logger.error(
                                "DEBUG_nearby_station_failed",
                                station_name=nearby_name,
                                error=str(result),
                                error_type=type(result).__name__
                            )
                        elif isinstance(result, list):
                            nearby_stations_data[nearby_name] = result
                            logger.info(
                                "DEBUG_nearby_station_success",
                                station_name=nearby_name,
                                data_points=len(result)
                            )
                        else:
                            logger.warning(
                                "DEBUG_nearby_station_invalid_type",
                                station_name=nearby_name,
                                result_type=type(result).__name__
                            )

        logger.info(
            "core_data_fetched",
            station_points=len(station_data),
            weather_points=len(weather_data),
            nearby_stations=len(nearby_stations),
            nearest_superstation=nearest_superstation.get("站点名称") if nearest_superstation else None,
            nearby_stations_with_data=len(nearby_stations_data),
            nearby_stations_names=list(nearby_stations_data.keys())
        )

        return station_data, weather_data, nearby_stations, nearby_stations_data, nearest_superstation

    async def _analyze_upwind_enterprises(
        self,
        params: ExtractedParams,
        station_info: Dict[str, Any],
        weather_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Analyze upwind enterprises based on meteorological conditions.

        Returns:
            Complete upwind API response with:
            - public_url: AMap static map URL
            - public_urls: Multiple URLs if paginated
            - filtered: List of enterprises with industry and emissions
            - meta: Metadata including legend, station info, etc.
        """
        if not weather_data:
            logger.warning("no_weather_data_for_upwind")
            return {}

        # Format weather data to winds
        winds = format_weather_to_winds(weather_data)

        if not winds:
            logger.warning("no_valid_wind_data")
            return {}

        # Call upwind analysis API (port 9095, /api/external/wind/upwind-and-map)
        result = await upwind_api.analyze_upwind_enterprises(
            station_name=station_info["station_name"],
            winds=winds,
            search_range_km=settings.default_search_range_km,
            max_enterprises=settings.default_max_enterprises,
            top_n=settings.default_top_n_enterprises,
            map_type="normal",  # or "satellite"
            mode="topn_mixed",  # Top-N numbered + others merged by tier
        )

        # Log result
        if isinstance(result, dict):
            enterprises_count = len(result.get("filtered", []))
            has_map_url = bool(result.get("public_url"))
            logger.info(
                "upwind_analysis_complete",
                enterprises_count=enterprises_count,
                has_map_url=has_map_url,
                status=result.get("status"),
            )
        else:
            logger.warning("upwind_analysis_invalid_response", result_type=type(result))

        return result if isinstance(result, dict) else {}

    async def _fetch_component_data(
        self, params: ExtractedParams, nearest_superstation: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Fetch component data from nearest superstation (runs in Wave 1 parallel).
        - O3: VOCs component data from nearest superstation
        - PM2.5/PM10: Particulate component data from nearest superstation

        Args:
            params: Extracted parameters
            nearest_superstation: Nearest superstation info (from Step 3)

        Returns:
            List of component data points
        """
        pollutant = params.pollutant or ""
        component_data = []

        # If no nearest superstation found, return empty data
        if not nearest_superstation:
            logger.warning(
                "no_nearest_superstation_for_component_data",
                pollutant=pollutant,
                location=params.location,
            )
            return []

        # Get superstation name
        superstation_name = nearest_superstation.get("站点名称", "")
        if not superstation_name:
            logger.warning("superstation_has_no_name", superstation_data=nearest_superstation)
            return []

        if pollutant == "O3":
            component_data = await monitoring_api.get_vocs_component_data(
                superstation_name, params.start_time or "", params.end_time or ""
            )
            logger.info(
                "vocs_data_fetched",
                superstation_name=superstation_name,
                data_points=len(component_data),
            )
        elif pollutant in ["PM2.5", "PM10"]:
            component_data = await monitoring_api.get_particulate_component_data(
                superstation_name, params.start_time or "", params.end_time or ""
            )
            logger.info(
                "particulate_data_fetched",
                superstation_name=superstation_name,
                data_points=len(component_data),
            )

        return component_data

    async def _analyze_components(
        self,
        params: ExtractedParams,
        station_data: List[Dict[str, Any]],
        weather_data: List[Dict[str, Any]],
        enterprises: List[Dict[str, Any]],
        component_data: List[Dict[str, Any]],
    ) -> Optional[ModuleResult]:
        """
        Analyze components using pre-fetched data (runs in Wave 2 parallel).
        - O3: VOCs component analysis
        - PM2.5/PM10: Particulate component analysis
        """
        pollutant = params.pollutant or ""
        city = params.city or ""

        if not component_data:
            logger.warning("no_component_data_for_analysis", pollutant=pollutant)
            return None

        analysis_result = None

        if pollutant == "O3":
            # Generate LLM analysis
            analysis_text = await llm_service.analyze_vocs_source(
                station_name=params.location or "",
                city=city,
                pollutant=pollutant,
                start_time=params.start_time or "",
                end_time=params.end_time or "",
                station_data=station_data,
                weather_data=weather_data,
                vocs_data=component_data,
                enterprise_data=enterprises,
                scale=params.scale,  # 传递 scale 参数
            )

            # Generate visualizations
            visuals = generate_vocs_analysis_visuals(component_data, enterprises)

            analysis_result = ModuleResult(
                analysis_type="voc_analysis",
                content=analysis_text,
                confidence=0.75,
                visuals=visuals,
                anchors=[
                    {"ref": "vocs_concentration_pie", "label": "VOCs浓度分布"},
                    {"ref": "ofp_contribution_bar", "label": "OFP贡献"},
                ],
            )

        elif pollutant in ["PM2.5", "PM10"]:
            # Generate LLM analysis
            analysis_text = await llm_service.analyze_particulate_source(
                station_name=params.location or "",
                city=city,
                pollutant=pollutant,
                start_time=params.start_time or "",
                end_time=params.end_time or "",
                station_data=station_data,
                weather_data=weather_data,
                particulate_data=component_data,
                enterprise_data=enterprises,
                scale=params.scale,  # 传递 scale 参数
            )

            # Generate visualizations
            visuals = generate_particulate_analysis_visuals(component_data, enterprises)

            analysis_result = ModuleResult(
                analysis_type="particulate_analysis",
                content=analysis_text,
                confidence=0.75,
                visuals=visuals,
                anchors=[
                    {"ref": "particulate_component_pie", "label": "颗粒物组分"},
                    {"ref": "industry_pm_bar", "label": "行业贡献"},
                ],
            )

        logger.info(
            "component_analysis_complete",
            pollutant=pollutant,
            data_points=len(component_data),
        )

        return analysis_result

    async def _analyze_regional_comparison(
        self,
        params: ExtractedParams,
        station_info: Dict[str, Any],
        station_data: List[Dict[str, Any]],
        nearby_stations_data: Dict[str, List[Dict[str, Any]]],
    ) -> ModuleResult:
        """Generate regional comparison analysis."""
        # Generate LLM analysis
        analysis_text = await llm_service.analyze_regional_comparison(
            station_name=station_info["station_name"],
            station_data=station_data,
            nearby_stations_data=nearby_stations_data,
            scale=params.scale,  # 传递 scale 参数
            city_name=params.city or station_info.get("city", ""),  # 城市级别需要城市名
        )

        # Generate visualization
        visual = generate_regional_comparison_visual(
            station_data,
            nearby_stations_data,
            station_name=station_info["station_name"],
            venue_name=params.venue_name or ""
        )

        return ModuleResult(
            analysis_type="regional_analysis",
            content=analysis_text,
            confidence=0.80,
            visuals=[visual],
            anchors=[{"ref": "regional_comparison_timeseries", "label": "站点对比图"}],
        )

    async def _analyze_weather_impact(
        self,
        params: ExtractedParams,
        station_info: Dict[str, Any],
        station_data: List[Dict[str, Any]],
        weather_data: List[Dict[str, Any]],
        enterprises: List[Dict[str, Any]],
        upwind_result: Optional[Dict[str, Any]] = None,
    ) -> ModuleResult:
        """
        Generate weather and upwind impact analysis, including a dynamic map
        when upwind enterprise data is available.
        """
        lines = [
            "**天气形势分析**",
            "",
            f"**站点**: {station_info['station_name']} ({station_info['city']} {station_info['district']})",
            f"**日期**: {params.start_time} - {params.end_time}",
            "",
        ]

        # Check if weather data is missing (历史数据不可用)
        if not weather_data:
            lines.append("⚠️ **气象数据未获取**")
            lines.append("")
            lines.append("当前查询时间段的气象数据不可用（可能是历史数据或API限制）。")
            lines.append("由于缺少风向风速数据，无法进行上风向企业分析和气象要素统计。")
            lines.append("")
            logger.warning(
                "weather_data_missing_for_station",
                station=station_info['station_name'],
                message="Weather data unavailable - cannot perform upwind analysis"
            )
        else:
            lines.append("**气象要素**:")

        if weather_data:
            wind_speeds = [w.get("windSpeed") for w in weather_data if w.get("windSpeed") is not None]
            wind_dirs = [w.get("windDirection") for w in weather_data if w.get("windDirection") is not None]

            if wind_speeds:
                avg_ws = sum(wind_speeds) / len(wind_speeds)
                lines.append(f"- 平均风速: {avg_ws:.1f} m/s")

            if wind_dirs:
                avg_wd = sum(wind_dirs) / len(wind_dirs)
                sectors = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                sector_idx = int((avg_wd + 22.5) / 45) % 8
                lines.append(f"- 主导风向: {sectors[sector_idx]} ({avg_wd:.0f} deg)")

        visuals: List[Dict[str, Any]] = []
        anchors: List[Dict[str, str]] = []

        # Generate multi-indicator timeseries chart (pollutant + meteorological indicators)
        if station_data and weather_data:
            multi_indicator_visual = generate_multi_indicator_timeseries(
                station_data=station_data,
                weather_data=weather_data,
                pollutant=params.pollutant or "O3",
                station_name=station_info["station_name"],
                venue_name=params.venue_name or ""
            )
            visuals.append(multi_indicator_visual)
            anchors.append({"ref": "multi_indicator_timeseries", "label": "多指标趋势图"})

        if enterprises:
            lines.append("")
            lines.append(f"**上风向企业**: 发现{len(enterprises)}个潜在污染源。")
            lines.append("")
            lines.append("**TOP K上风向企业**:")
            lines.append("")

            # 列出前10家企业的详细信息
            for i, ent in enumerate(enterprises[:10], 1):
                name = ent.get("name", ent.get("企业名称", "Unknown"))
                industry = ent.get("industry", ent.get("行业", "N/A"))
                distance = ent.get("distance_km", ent.get("距离", 0))
                bearing = ent.get("bearing_deg", ent.get("方位", 0))

                # 方位角转换为方向
                directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                direction_idx = int((bearing + 22.5) / 45) % 8
                direction = directions[direction_idx]

                lines.append(f"{i}. **{name}**")
                lines.append(f"   - 行业: {industry}")
                lines.append(f"   - 距离: {distance:.2f} km")
                lines.append(f"   - 方位: {direction} ({bearing:.0f}°)")
                lines.append("")

            if len(enterprises) > 10:
                lines.append(f"*...and {len(enterprises) - 10} more enterprises*")
                lines.append("")

            upwind_paths = None
            wind_sectors = None
            if upwind_result:
                upwind_paths = (
                    upwind_result.get("upwind_paths")
                    or upwind_result.get("paths")
                    or (upwind_result.get("meta") or {}).get("paths")
                )
                meta = upwind_result.get("meta") or {}
                wind_sectors = meta.get("sectors") or meta.get("wind_sectors")

            map_payload = generate_map_payload(
                station_info,
                enterprises,
                upwind_paths=upwind_paths,
                sectors=wind_sectors,
            )

            visuals.append(
                {
                    "id": "upwind_enterprise_map",
                    "type": "map",
                    "title": f"{station_info['station_name']}上风向企业分布",
                    "mode": "dynamic",
                    "payload": map_payload,
                }
            )
            anchors.append({"ref": "upwind_enterprise_map", "label": "Upwind map"})

        analysis_text = "\n".join(lines)

        return ModuleResult(
            analysis_type="weather_analysis",
            content=analysis_text,
            confidence=0.85,
            visuals=visuals,
            anchors=anchors,
        )

    async def _generate_comprehensive_summary(
        self,
        params: ExtractedParams,
        station_info: Dict[str, Any],
        upwind_result: Dict[str, Any],
        weather_analysis: ModuleResult,
        regional_analysis: ModuleResult,
        component_analysis: Optional[ModuleResult],
    ) -> ModuleResult:
        """
        Generate comprehensive summary using LLM.

        Integrates two data sources:
        1. Upwind enterprises (from port 9095 API)
        2. Component source analysis (VOCs or particulate)
        """
        # Prepare upwind enterprise summary
        enterprises = upwind_result.get("filtered", [])
        enterprise_summary = "\n".join([
            f"- {ent.get('name', '')} ({ent.get('industry', '')})"
            f" - 距离: {ent.get('distance_km', 0):.1f}km"
            for ent in enterprises[:8]
        ])

        # Generate LLM summary (without KPI)
        summary_text = await llm_service.generate_comprehensive_summary(
            station_name=station_info["station_name"],
            pollutant=params.pollutant or "",
            weather_analysis=weather_analysis.content,
            regional_analysis=regional_analysis.content,
            component_analysis=component_analysis.content if component_analysis else "",
            enterprise_summary=enterprise_summary,
            scale=params.scale,  # 传递 scale 参数
            city_name=params.city or station_info.get("city", ""),  # 城市级别需要城市名
        )

        return ModuleResult(
            analysis_type="comprehensive_analysis",
            content=summary_text,
            confidence=0.80,
            visuals=None,  # Comprehensive analysis is text-only
            anchors=None,
        )

    def _assemble_response(
        self,
        params: ExtractedParams,
        station_info: Dict[str, Any],
        upwind_result: Dict[str, Any],
        weather_analysis: ModuleResult,
        regional_analysis: ModuleResult,
        component_analysis: Optional[ModuleResult],
        comprehensive_analysis: ModuleResult,
    ) -> AnalysisResponseData:
        """Assemble final response data (without KPI)."""
        from app.models.schemas import UpwindEnterpriseData

        query_info = QueryInfo(
            location=params.location,
            city=station_info["city"],
            pollutant=params.pollutant,
            start_time=params.start_time,
            end_time=params.end_time,
            scale=params.scale,
        )

        viz_capability = VisualizationCapability(
            supports_dynamic_map=True,
            supports_echarts=True,
            supports_small_multiples=False,
            supports_animation=False,
        )

        # Prepare upwind enterprise data for frontend
        upwind_enterprises = None
        if upwind_result:
            upwind_enterprises = UpwindEnterpriseData(
                public_url=upwind_result.get("public_url"),
                public_urls=upwind_result.get("public_urls"),
                filtered=upwind_result.get("filtered", []),
                meta=upwind_result.get("meta", {}),
            )

        # Assign component analysis to appropriate module
        voc_analysis = None
        particulate_analysis = None

        if component_analysis:
            if params.pollutant == "O3":
                voc_analysis = component_analysis
            elif params.pollutant in ["PM2.5", "PM10"]:
                particulate_analysis = component_analysis

        return AnalysisResponseData(
            query_info=query_info,
            visualization_capability=viz_capability,
            upwind_enterprises=upwind_enterprises,
            weather_analysis=weather_analysis,
            regional_analysis=regional_analysis,
            voc_analysis=voc_analysis,
            particulate_analysis=particulate_analysis,
            comprehensive_analysis=comprehensive_analysis,
        )

    def _create_error_response(self, message: str) -> AnalysisResponseData:
        """Create error response with basic structure (without KPI)."""
        return AnalysisResponseData(
            query_info=QueryInfo(),
            comprehensive_analysis=ModuleResult(
                analysis_type="error",
                content=f"**分析错误**\n\n{message}",
                confidence=0.0,
            ),
        )

    async def analyze_streaming(self, query: str):
        """
        Streaming analysis entry point that yields modules as they complete.

        This method implements true streaming by yielding results as soon as they're ready,
        rather than waiting for all tasks to complete. This improves perceived performance
        by showing fast-completing modules (weather) before slow ones (component analysis).

        Yields:
            dict: Events with format:
                - {'event': 'step', 'step': str, 'status': str, 'message': str}
                - {'event': 'module_complete', 'module': str, 'data': ModuleResult}
                - {'event': 'done', 'data': AnalysisResponseData}
                - {'event': 'error', 'error': str}
        """
        logger.info("streaming_analysis_start", query=query[:100])

        try:
            import time
            workflow_start = time.time()

            # Step 1: Extract parameters
            yield {
                'event': 'step',
                'step': 'parameter_extraction',
                'status': 'start',
                'message': '正在解析查询参数...'
            }

            params = await self._extract_parameters(query)
            logger.info("params_extracted", params=params, scale=params.scale)

            yield {
                'event': 'step',
                'step': 'parameter_extraction',
                'status': 'success',
                'message': f'参数解析完成：{"城市=" + params.city if params.scale == "city" else "站点=" + (params.location or "")}，污染物={params.pollutant}'
            }

            # 生成并发送动态标题
            dashboard_title = self._generate_dashboard_title(params)
            yield {
                'event': 'title',
                'title': dashboard_title
            }
            logger.info("dashboard_title_sent", title=dashboard_title)

            # Route based on scale
            if params.scale == "city":
                # City-level queries: delegate to city orchestrator with streaming
                logger.info("streaming_routing_to_city_orchestrator", city=params.city)

                # ✅ Use streaming method for city-level analysis
                async for event in city_orchestrator.analyze_city_streaming(params):
                    yield event
                return

            # Station-level analysis workflow (default)
            # Step 2: Validate and fetch station info
            yield {
                'event': 'step',
                'step': 'station_info',
                'status': 'start',
                'message': '正在获取站点信息...'
            }

            station_info = await self._get_station_info(params)
            if not station_info:
                yield {
                    'event': 'error',
                    'error': '无法找到指定站点'
                }
                return

            yield {
                'event': 'step',
                'step': 'station_info',
                'status': 'success',
                'message': f'站点信息获取完成：{station_info["station_name"]}'
            }

            # Step 3: Parallel data fetching
            yield {
                'event': 'step',
                'step': 'core_data_fetch',
                'status': 'start',
                'message': '正在获取监测数据、气象数据和周边站点...'
            }

            step3_start = time.time()
            (
                station_data,
                weather_data,
                nearby_stations,
                nearby_stations_data,
                nearest_superstation,
            ) = await self._fetch_core_data(params, station_info)

            step3_duration = time.time() - step3_start

            yield {
                'event': 'step',
                'step': 'core_data_fetch',
                'status': 'success',
                'message': f'核心数据获取完成（耗时{step3_duration:.1f}s）：监测点={len(station_data)}，气象点={len(weather_data)}，周边站点={len(nearby_stations_data)}'
            }

            # Wave 1: Parallel data fetching (upwind + component data)
            yield {
                'event': 'step',
                'step': 'wave1_parallel',
                'status': 'start',
                'message': '正在并行获取上风向企业和组分数据...'
            }

            wave1_start = time.time()
            upwind_result, component_data = await asyncio.gather(
                self._analyze_upwind_enterprises(params, station_info, weather_data),
                self._fetch_component_data(params, nearest_superstation),
                return_exceptions=True,
            )

            # Handle exceptions
            if isinstance(upwind_result, Exception):
                logger.error("upwind_analysis_failed", error=str(upwind_result))
                upwind_result = {}
            if isinstance(component_data, Exception):
                logger.error("component_data_fetch_failed", error=str(component_data))
                component_data = []

            enterprises = upwind_result.get("filtered", []) if upwind_result else []
            wave1_duration = time.time() - wave1_start

            yield {
                'event': 'step',
                'step': 'wave1_parallel',
                'status': 'success',
                'message': f'Wave 1完成（耗时{wave1_duration:.1f}s）：上风向企业={len(enterprises)}，组分数据点={len(component_data)}'
            }

            # Wave 2: Create parallel tasks (but don't await gather - yield as completed!)
            yield {
                'event': 'step',
                'step': 'wave2_parallel',
                'status': 'start',
                'message': '正在并行执行3个分析任务（气象、区域、组分），将按完成顺序展示...'
            }

            wave2_start = time.time()

            # Prepare regional analysis task (conditional)
            if nearby_stations_data:
                regional_task = asyncio.create_task(
                    self._analyze_regional_comparison(
                        params, station_info, station_data, nearby_stations_data
                    )
                )
            else:
                async def no_regional_analysis():
                    logger.info("skip_regional_analysis", reason="no_nearby_stations")
                    return ModuleResult(
                        analysis_type="regional_analysis",
                        content="**区域对比分析**\n\n暂无周边站点数据，无法进行区域对比分析。",
                        confidence=0.0,
                        visuals=[],
                        anchors=[],
                    )
                regional_task = asyncio.create_task(no_regional_analysis())

            # Create all Wave 2 tasks
            tasks = {
                'weather_analysis': asyncio.create_task(
                    self._analyze_weather_impact(
                        params, station_info, station_data, weather_data, enterprises, upwind_result
                    )
                ),
                'regional_analysis': regional_task,
                'component_analysis': asyncio.create_task(
                    self._analyze_components(
                        params, station_data, weather_data, enterprises, component_data
                    )
                ),
            }

            # Store results for later comprehensive summary
            wave2_results = {}
            completed_count = 0
            total_tasks = len(tasks)

            # Yield modules as they complete (key improvement!)
            for coro in asyncio.as_completed(tasks.values()):
                try:
                    result = await coro
                    completed_count += 1

                    # Find which task completed
                    module_name = None
                    for name, task in tasks.items():
                        if task == coro or task.done():
                            # Check if this is the task that just completed
                            try:
                                if task.result() == result:
                                    module_name = name
                                    break
                            except:
                                pass

                    # Fallback: find by matching result
                    if not module_name:
                        for name, task in tasks.items():
                            if name not in wave2_results:
                                try:
                                    if task.done() and task.result() == result:
                                        module_name = name
                                        break
                                except:
                                    pass

                    if not module_name:
                        # Last resort: use first uncompleted task name
                        for name in tasks.keys():
                            if name not in wave2_results:
                                module_name = name
                                break

                    if module_name:
                        wave2_results[module_name] = result

                        task_duration = time.time() - wave2_start
                        yield {
                            'event': 'step',
                            'step': f'{module_name}_complete',
                            'status': 'success',
                            'message': f'{module_name}完成（{completed_count}/{total_tasks}，耗时{task_duration:.1f}s）'
                        }

                        # Yield the module result immediately
                        yield {
                            'event': 'module_complete',
                            'module': module_name,
                            'data': result.dict() if result else None
                        }

                except Exception as e:
                    logger.error("wave2_task_failed", error=str(e), exc_info=True)
                    completed_count += 1
                    yield {
                        'event': 'step',
                        'step': 'wave2_task_error',
                        'status': 'warning',
                        'message': f'某个分析任务失败（{completed_count}/{total_tasks}）：{str(e)[:50]}'
                    }

            wave2_duration = time.time() - wave2_start

            yield {
                'event': 'step',
                'step': 'wave2_parallel',
                'status': 'success',
                'message': f'Wave 2完成（总耗时{wave2_duration:.1f}s）'
            }

            # Wave 3: Comprehensive summary (depends on all Wave 2 results)
            yield {
                'event': 'step',
                'step': 'wave3_comprehensive',
                'status': 'start',
                'message': '正在生成综合分析报告...'
            }

            wave3_start = time.time()

            # Extract module results with proper error handling
            weather_analysis = wave2_results.get('weather_analysis')
            regional_analysis = wave2_results.get('regional_analysis')
            component_analysis = wave2_results.get('component_analysis')

            # Handle missing/failed modules
            if not weather_analysis or isinstance(weather_analysis, Exception):
                weather_analysis = ModuleResult(
                    analysis_type="weather_analysis",
                    content="**气象分析**\n\n分析失败，请稍后重试。",
                    confidence=0.0,
                )
            if not regional_analysis or isinstance(regional_analysis, Exception):
                regional_analysis = ModuleResult(
                    analysis_type="regional_analysis",
                    content="**区域对比分析**\n\n分析失败，请稍后重试。",
                    confidence=0.0,
                )

            comprehensive_analysis = await self._generate_comprehensive_summary(
                params,
                station_info,
                upwind_result,
                weather_analysis,
                regional_analysis,
                component_analysis,
            )

            wave3_duration = time.time() - wave3_start

            yield {
                'event': 'step',
                'step': 'wave3_comprehensive',
                'status': 'success',
                'message': f'综合分析完成（耗时{wave3_duration:.1f}s）'
            }

            # Yield comprehensive analysis module
            yield {
                'event': 'module_complete',
                'module': 'comprehensive_analysis',
                'data': comprehensive_analysis.dict()
            }

            # Total workflow timing
            total_duration = time.time() - workflow_start
            logger.info(
                "streaming_workflow_complete",
                wave1=f"{wave1_duration:.2f}s",
                wave2=f"{wave2_duration:.2f}s",
                wave3=f"{wave3_duration:.2f}s",
                total=f"{total_duration:.2f}s",
            )

            # Assemble final response
            response = self._assemble_response(
                params,
                station_info,
                upwind_result,
                weather_analysis,
                regional_analysis,
                component_analysis,
                comprehensive_analysis,
            )

            # Save to history database (for streaming analysis)
            try:
                history_record = AnalysisHistoryRecord(
                    query_text=query,
                    scale=params.scale,
                    location=params.location,
                    city=params.city or station_info.get("city"),
                    pollutant=params.pollutant,
                    start_time=params.start_time,
                    end_time=params.end_time,
                    # Raw data
                    meteorological_data=weather_data,
                    monitoring_data=station_data,
                    nearby_stations_data=[{"name": k, "data": v} for k, v in nearby_stations_data.items()],
                    vocs_data=component_data if params.pollutant == "O3" else None,
                    particulate_data=component_data if params.pollutant in ["PM2.5", "PM10"] else None,
                    upwind_enterprises=upwind_result.get("filtered", []) if upwind_result else None,
                    upwind_map_url=upwind_result.get("public_url") if upwind_result else None,
                    station_info=station_info,
                    # Analysis results
                    weather_analysis=weather_analysis.content,
                    regional_comparison=regional_analysis.content,
                    vocs_source_analysis=component_analysis.content if component_analysis and params.pollutant == "O3" else None,
                    particulate_source_analysis=component_analysis.content if component_analysis and params.pollutant in ["PM2.5", "PM10"] else None,
                    comprehensive_summary=comprehensive_analysis.content,
                    modules_data=response.dict() if hasattr(response, "dict") else None,
                    # Metadata
                    status="completed",
                    duration_seconds=total_duration,
                )

                session_id = await history_service.save_analysis(history_record)
                logger.info("streaming_analysis_saved_to_history", session_id=session_id, station=params.location)
            except Exception as e:
                logger.warning("streaming_failed_to_save_history", error=str(e), exc_info=True)

            # DEBUG: Log response before yielding
            response_dict = response.dict()
            logger.info("DEBUG_orchestrator_done_event",
                        has_response=bool(response),
                        response_keys=list(response_dict.keys()) if isinstance(response_dict, dict) else None,
                        response_size=len(str(response_dict)))

            yield {
                'event': 'done',
                'data': response_dict
            }

        except Exception as e:
            logger.error("streaming_analysis_failed", error=str(e), exc_info=True)
            yield {
                'event': 'error',
                'error': f"分析失败: {str(e)}"
            }


# Global orchestrator instance
orchestrator = AnalysisOrchestrator()
