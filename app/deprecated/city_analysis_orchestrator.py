"""
City-level analysis orchestrator that handles city-wide pollution traceability.

This module implements a COMPLETE city workflow including:
1. Fetch all national control stations in the city
2. Fetch nearby cities for regional comparison
3. Analyze EACH station with full workflow (weather, upwind, components)
4. Combine results by station for display
5. Generate city-level comprehensive analysis

Key differences from station-level:
- Operates on ALL stations in a city (10-15 stations)
- Regional comparison is city-to-city (not station-to-station)
- Results are combined by station for display
"""
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from app.models.schemas import (
    ExtractedParams,
    AnalysisResponseData,
    ModuleResult,
    QueryInfo,
    VisualizationCapability,
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
#     format_weather_to_winds,
#     normalize_city_name,
# )  # 已迁移到本地实现
from app.utils.visualization import (
    generate_map_payload,
    generate_vocs_analysis_visuals,
    generate_particulate_analysis_visuals,
    generate_timeseries_payload,
)
from config.settings import settings
import structlog

logger = structlog.get_logger()


def normalize_city_name(city: str) -> str:
    """
    Normalize city name by removing '市' suffix.

    Args:
        city: City name (may include 市)

    Returns:
        Normalized city name without 市
    """
    if not city:
        return ""
    return city.replace("市", "").strip()


def format_weather_to_winds(weather_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert weather data to winds array format for upwind analysis API.

    Args:
        weather_data: List of weather data points with windDirection, windSpeed, timePoint

    Returns:
        List of WindData objects
    """
    import structlog
    logger = structlog.get_logger()

    logger.info("format_weather_to_winds_start", input_count=len(weather_data))

    winds = []
    filtered_count = 0

    for item in weather_data:
        if not isinstance(item, dict):
            continue

        wind_direction = item.get("windDirection")
        wind_speed = item.get("windSpeed")
        time_point = item.get("timePoint")

        # Filter invalid data
        if wind_direction is None or wind_direction >= 360 or wind_direction < 0:
            filtered_count += 1
            continue
        if wind_speed is None:
            filtered_count += 1
            continue
        if not time_point:
            filtered_count += 1
            continue

        # Convert time format: "2025-08-09 00:00" -> "2025-08-09T00:00:00Z"
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

    logger.info("format_weather_to_winds_complete",
               input_count=len(weather_data),
               output_count=len(winds),
               filtered_count=filtered_count)

    return winds


class StationAnalysisResult:
    """Single station analysis result within city workflow"""
    def __init__(
        self,
        station_name: str,
        station_info: Dict[str, Any],
        station_data: List[Dict[str, Any]],
        weather_data: List[Dict[str, Any]],
        upwind_result: Dict[str, Any],
        component_analysis: Optional[ModuleResult],
        weather_analysis: ModuleResult,
    ):
        self.station_name = station_name
        self.station_info = station_info
        self.station_data = station_data
        self.weather_data = weather_data
        self.upwind_result = upwind_result
        self.component_analysis = component_analysis
        self.weather_analysis = weather_analysis


class CityAnalysisOrchestrator:
    """
    Orchestrator for city-level pollution analysis.

    Complete Workflow:
    1. Get all national control stations in city + nearby cities
    2. Fetch core data (weather, component, monitoring for all stations)
    3. Start city comparison LLM asynchronously
    4. Analyze each station (weather match → upwind → component → weather analysis)
    5. Wait for city comparison + generate comprehensive summary
    6. Assemble response by specified display order
    """

    @staticmethod
    def _get_concentration(data_point: Dict[str, Any], pollutant: str) -> Optional[float]:
        """
        Extract concentration value from data point based on pollutant type.

        City-level API returns pollutant-specific fields (e.g., 'o3', 'pM2_5'),
        while station-level API returns 'concentration' or '浓度' fields.

        Args:
            data_point: Data point dict from API
            pollutant: Pollutant type (O3, PM2.5, PM10, etc.)

        Returns:
            Concentration as float, or None if not found
        """
        # Try standard fields first (station-level format)
        value = data_point.get("concentration") or data_point.get("浓度")
        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                pass

        # Try pollutant-specific fields (city-level format)
        pollutant_field_map = {
            "O3": "o3",
            "PM2.5": "pM2_5",
            "PM10": "pM10",
            "CO": "co",
            "NO2": "nO2",
            "NOX": "nOx",
            "SO2": "sO2",
        }

        field_name = pollutant_field_map.get(pollutant.upper())
        if field_name:
            value = data_point.get(field_name)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    pass

        return None

    async def analyze_city(self, params: ExtractedParams) -> AnalysisResponseData:
        """
        Main city-level analysis entry point.

        Args:
            params: Extracted parameters with scale="city"

        Returns:
            City-level analysis response
        """
        city = params.city or ""
        logger.info("city_analysis_start", city=city, pollutant=params.pollutant)

        try:
            import time
            workflow_start = time.time()

            # Step 2: Parallel fetch stations and nearby cities
            stations, nearby_cities = await self._fetch_stations_and_cities(params)

            if not stations:
                return self._create_error_response(f"未找到城市 {city} 的国控站点")

            logger.info(
                "city_stations_fetched",
                city=city,
                station_count=len(stations),
                nearby_cities_count=len(nearby_cities)
            )

            # Step 3: Four-way parallel core data fetch
            step3_start = time.time()
            (
                weather_data_all,
                component_data,
                station_monitoring_data,
                nearby_city_data,
            ) = await self._fetch_city_core_data(params, stations, nearby_cities)

            step3_duration = time.time() - step3_start
            logger.info(
                "city_core_data_fetched",
                duration=f"{step3_duration:.2f}s",
                weather_districts=len(set(w.get("directName", "") for w in weather_data_all)),
                component_data_points=len(component_data),
                stations_with_data=len(station_monitoring_data),
                nearby_cities_with_data=len(nearby_city_data)
            )

            # Step 4: Start city comparison LLM asynchronously (does not block station analysis)
            city_comparison_task = asyncio.create_task(
                self._generate_city_regional_comparison_llm(
                    params, station_monitoring_data, nearby_city_data
                )
            )
            logger.info("city_comparison_llm_started", status="async_running")

            # Step 5: Analyze all stations (Semaphore=5)
            step5_start = time.time()
            station_results = await self._analyze_all_stations(
                params, stations, station_monitoring_data,
                weather_data_all, component_data
            )

            step5_duration = time.time() - step5_start
            logger.info(
                "city_stations_analyzed",
                duration=f"{step5_duration:.2f}s",
                total_stations=len(stations),
                successful_stations=len(station_results)
            )

            # Step 6: Wait for city comparison + generate comprehensive summary
            step6_start = time.time()

            regional_analysis = await city_comparison_task
            logger.info("city_comparison_llm_complete")

            comprehensive_analysis = await self._generate_city_comprehensive_summary(
                params, stations, station_results, regional_analysis
            )

            step6_duration = time.time() - step6_start
            logger.info("city_comprehensive_complete", duration=f"{step6_duration:.2f}s")

            # Total workflow timing
            total_duration = time.time() - workflow_start
            logger.info(
                "city_workflow_complete",
                total_duration=f"{total_duration:.2f}s",
                step3_data_fetch=f"{step3_duration:.2f}s",
                step5_station_analysis=f"{step5_duration:.2f}s",
                step6_llm_summary=f"{step6_duration:.2f}s"
            )

            # Step 7: Assemble city response
            response = self._assemble_city_response(
                params,
                stations,
                station_results,
                component_data,
                regional_analysis,
                comprehensive_analysis,
            )

            # Step 8: Save to history database
            try:
                # Aggregate all station data for storage
                all_station_data = {name: data for name, data in station_monitoring_data.items()}
                all_enterprises = []
                for result in station_results:
                    all_enterprises.extend(result.upwind_result.get("filtered", []))

                history_record = AnalysisHistoryRecord(
                    query_text=f"分析{params.city}市{params.pollutant}污染",
                    scale=params.scale,
                    location=None,
                    city=params.city,
                    pollutant=params.pollutant,
                    start_time=params.start_time,
                    end_time=params.end_time,
                    # Raw data
                    meteorological_data=weather_data_all,
                    monitoring_data=all_station_data,
                    nearby_stations_data=nearby_city_data,
                    vocs_data=component_data if params.pollutant == "O3" else None,
                    particulate_data=component_data if params.pollutant in ["PM2.5", "PM10"] else None,
                    upwind_enterprises=all_enterprises,
                    upwind_map_url=None,  # City level has multiple maps
                    station_info={"stations": [r.station_info for r in station_results]},
                    # Analysis results
                    weather_analysis=None,  # City level combines all stations
                    regional_comparison=regional_analysis.content,
                    vocs_source_analysis=None,  # Aggregated in modules_data
                    particulate_source_analysis=None,  # Aggregated in modules_data
                    comprehensive_summary=comprehensive_analysis.content,
                    kpi_data=None,  # No KPI for city level
                    modules_data=response.dict() if hasattr(response, "dict") else None,
                    # Metadata
                    status="completed",
                    duration_seconds=total_duration,
                )

                session_id = await history_service.save_analysis(history_record)
                logger.info("city_analysis_saved_to_history", session_id=session_id, city=params.city)
            except Exception as e:
                logger.warning("failed_to_save_city_history", error=str(e), exc_info=True)

            return response

        except Exception as e:
            logger.error("city_analysis_failed", error=str(e), exc_info=True)
            return self._create_error_response(f"城市级别分析失败: {str(e)}")

    async def _fetch_stations_and_cities(
        self, params: ExtractedParams
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Step 2: Parallel fetch stations list and nearby cities.

        Returns:
            (stations, nearby_cities)
        """
        city = params.city or ""

        results = await asyncio.gather(
            # Get all national control stations in city
            station_api.get_city_stations(
                city_name=city,
                station_type_id=1.0,  # 国控站点
                fields="name,code,lat,lon,district,address"
            ),
            # Get 3 nearby cities
            station_api.get_nearby_cities(
                city_name=city,
                k=3,
                station_type_id=1.0,
                fields="name,code,lat,lon,district"
            ),
            return_exceptions=True
        )

        stations = results[0] if not isinstance(results[0], Exception) else []
        nearby_cities_response = results[1] if not isinstance(results[1], Exception) else {"neighbors": []}

        nearby_cities = nearby_cities_response.get("neighbors", []) if isinstance(nearby_cities_response, dict) else []

        return stations, nearby_cities

    async def _fetch_city_core_data(
        self,
        params: ExtractedParams,
        stations: List[Dict[str, Any]],
        nearby_cities: List[Dict[str, Any]],
    ) -> Tuple[List[Dict], List[Dict], Dict[str, List], Dict[str, List]]:
        """
        Step 3: Four-way parallel core data fetch.

        Returns:
            (weather_data_all, component_data, station_monitoring_data, nearby_city_data)
        """
        city = params.city or ""
        pollutant = params.pollutant or "O3"
        start_time = params.start_time or ""
        end_time = params.end_time or ""

        # Prepare tasks for all stations monitoring data
        station_tasks = []
        station_names = []
        for station in stations:
            station_name = station.get("站点名称", station.get("name", ""))
            if station_name:
                station_names.append(station_name)
                station_tasks.append(
                    monitoring_api.get_station_pollutant_data(
                        station_name, pollutant, start_time, end_time
                    )
                )

        # Prepare tasks for nearby cities monitoring data
        nearby_city_tasks = []
        nearby_city_names = []
        for neighbor in nearby_cities[:3]:
            neighbor_city = neighbor.get("city", "")
            if neighbor_city and neighbor_city != city:
                nearby_city_names.append(neighbor_city)
                nearby_city_tasks.append(
                    monitoring_api.get_city_pollutant_data(
                        neighbor_city, pollutant, start_time, end_time
                    )
                )

        # Four-way parallel fetch
        results = await asyncio.gather(
            # 1. City weather data (all districts)
            weather_api.get_weather_data(city, "", start_time, end_time),

            # 2. City component data (VOCs or PM)
            self._fetch_city_component_data(params),

            # 3. All stations monitoring data
            asyncio.gather(*station_tasks, return_exceptions=True) if station_tasks else asyncio.sleep(0),

            # 4. Nearby cities monitoring data
            asyncio.gather(*nearby_city_tasks, return_exceptions=True) if nearby_city_tasks else asyncio.sleep(0),

            return_exceptions=True
        )

        # Unpack results
        weather_data_all = results[0] if not isinstance(results[0], Exception) else []
        component_data = results[1] if not isinstance(results[1], Exception) else []
        station_results_raw = results[2] if not isinstance(results[2], Exception) else []
        nearby_city_results_raw = results[3] if not isinstance(results[3], Exception) else []

        # Process station monitoring data into dict
        station_monitoring_data = {}
        if isinstance(station_results_raw, (list, tuple)):
            for i, station_name in enumerate(station_names):
                if i < len(station_results_raw):
                    result = station_results_raw[i]
                    if not isinstance(result, Exception) and isinstance(result, list):
                        station_monitoring_data[station_name] = result

        # Process nearby city data into dict
        nearby_city_data = {}
        if isinstance(nearby_city_results_raw, (list, tuple)):
            logger.info(
                "processing_nearby_city_results",
                nearby_city_count=len(nearby_city_names),
                results_count=len(nearby_city_results_raw)
            )

            for i, city_name in enumerate(nearby_city_names):
                if i < len(nearby_city_results_raw):
                    result = nearby_city_results_raw[i]

                    if isinstance(result, Exception):
                        logger.error(
                            "nearby_city_data_exception",
                            city=city_name,
                            error=str(result),
                            error_type=type(result).__name__
                        )
                    elif isinstance(result, list):
                        nearby_city_data[city_name] = result
                        logger.info(
                            "nearby_city_data_processed",
                            city=city_name,
                            data_points=len(result),
                            has_data=len(result) > 0
                        )

                        # Log first item structure for debugging
                        if len(result) > 0:
                            first_item = result[0]
                            logger.info(
                                "nearby_city_first_item",
                                city=city_name,
                                item_type=type(first_item).__name__,
                                item_keys=list(first_item.keys()) if isinstance(first_item, dict) else None,
                                has_concentration=first_item.get("concentration") is not None if isinstance(first_item, dict) else None,
                                has_浓度=first_item.get("浓度") is not None if isinstance(first_item, dict) else None,
                            )
                    else:
                        logger.warning(
                            "nearby_city_data_invalid_type",
                            city=city_name,
                            result_type=type(result).__name__
                        )
        else:
            logger.warning(
                "nearby_city_results_invalid_format",
                results_type=type(nearby_city_results_raw).__name__
            )

        logger.info(
            "nearby_city_data_summary",
            total_cities_requested=len(nearby_city_names),
            cities_with_data=len(nearby_city_data),
            city_names_with_data=list(nearby_city_data.keys())
        )

        return weather_data_all, component_data, station_monitoring_data, nearby_city_data

    async def _fetch_city_component_data(
        self, params: ExtractedParams
    ) -> List[Dict[str, Any]]:
        """
        Fetch component data (VOCs or PM) for all stations in the city.

        Strategy:
        1. Query nearest superstation for each national control station
        2. Fetch component data from each superstation
        3. Aggregate all component data for city-level analysis

        Args:
            params: Query parameters with city name

        Returns:
            Aggregated component data from all superstations in the city
        """
        city = params.city or ""
        pollutant = params.pollutant or ""

        # Only fetch component data for O3 and PM pollutants
        if pollutant not in ["O3", "PM2.5", "PM10"]:
            logger.info("component_data_skipped", reason=f"Pollutant {pollutant} does not require component analysis")
            return []

        try:
            # Step 1: Get all national control stations in the city
            stations = await station_api.get_city_stations(
                city_name=city,
                station_type_id=1.0,
                fields="name,code"
            )

            if not stations:
                logger.warning("no_stations_for_component_data", city=city)
                return []

            logger.info(
                "fetching_component_data_for_city",
                city=city,
                pollutant=pollutant,
                station_count=len(stations)
            )

            # Step 2: For each station, find nearest superstation and fetch component data
            component_data_tasks = []
            superstation_names = []

            for station in stations:
                station_name = station.get("站点名称", station.get("name", ""))
                if not station_name:
                    continue

                # Find nearest superstation
                superstation_info = await station_api.get_nearest_superstation(
                    station_name=station_name,
                    max_distance=100.0,
                    max_results=1
                )

                if superstation_info:
                    superstation_name = superstation_info.get("站点名称", "")
                    if superstation_name and superstation_name not in superstation_names:
                        superstation_names.append(superstation_name)

                        # Create task to fetch component data
                        if pollutant == "O3":
                            component_data_tasks.append(
                                monitoring_api.get_vocs_component_data(
                                    superstation_name,
                                    params.start_time or "",
                                    params.end_time or ""
                                )
                            )
                        elif pollutant in ["PM2.5", "PM10"]:
                            component_data_tasks.append(
                                monitoring_api.get_particulate_component_data(
                                    superstation_name,
                                    params.start_time or "",
                                    params.end_time or ""
                                )
                            )

            if not component_data_tasks:
                logger.warning(
                    "no_superstations_found_for_city",
                    city=city,
                    stations_checked=len(stations)
                )
                return []

            # Step 3: Fetch all component data in parallel
            logger.info(
                "fetching_component_data_from_superstations",
                city=city,
                superstation_count=len(superstation_names),
                superstations=superstation_names[:3]  # Log first 3
            )

            results = await asyncio.gather(*component_data_tasks, return_exceptions=True)

            # Step 4: Aggregate all component data
            all_component_data = []
            successful_count = 0

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        "component_data_fetch_failed",
                        superstation=superstation_names[i] if i < len(superstation_names) else "unknown",
                        error=str(result)
                    )
                elif isinstance(result, list) and len(result) > 0:
                    all_component_data.extend(result)
                    successful_count += 1
                    logger.info(
                        "component_data_fetched_from_superstation",
                        superstation=superstation_names[i] if i < len(superstation_names) else "unknown",
                        data_points=len(result)
                    )

            logger.info(
                "city_component_data_aggregated",
                city=city,
                pollutant=pollutant,
                superstations_queried=len(superstation_names),
                superstations_successful=successful_count,
                total_data_points=len(all_component_data)
            )

            return all_component_data

        except Exception as e:
            logger.error(
                "city_component_data_fetch_failed",
                city=city,
                pollutant=pollutant,
                error=str(e),
                exc_info=True
            )
            return []

    def _match_weather_by_district(
        self,
        target_district: str,
        weather_data_all: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Match weather data for station's district.

        Strategy (方案B - 基于数据可用性):
        1. Try to match target district
        2. If not found, use district with most data points
        3. If no data at all, return empty

        Args:
            target_district: Station's district (e.g., "天河区")
            weather_data_all: All weather data from city

        Returns:
            Weather data for the matched district
        """
        if not weather_data_all:
            return []

        # Group weather data by district
        weather_by_district = {}
        for record in weather_data_all:
            district = record.get("directName", record.get("区县", ""))
            if district:
                if district not in weather_by_district:
                    weather_by_district[district] = []
                weather_by_district[district].append(record)

        # Try exact match first
        if target_district in weather_by_district:
            logger.info(
                "weather_matched_exact",
                station_district=target_district,
                records=len(weather_by_district[target_district])
            )
            return weather_by_district[target_district]

        # Use district with most data points (方案B)
        if weather_by_district:
            best_district = max(
                weather_by_district.keys(),
                key=lambda d: len(weather_by_district[d])
            )
            logger.info(
                "weather_matched_nearby",
                station_district=target_district,
                used_district=best_district,
                records=len(weather_by_district[best_district])
            )
            return weather_by_district[best_district]

        # No data available
        logger.warning("weather_no_match", station_district=target_district)
        return []

    async def _analyze_single_station(
        self,
        station: Dict[str, Any],
        params: ExtractedParams,
        station_monitoring_data: Dict[str, List],
        weather_data_all: List[Dict],
        component_data: List[Dict],
    ) -> StationAnalysisResult:
        """
        Analyze a single station with COMPLETE workflow.

        This reuses station-level analysis logic:
        1. Match weather data by district
        2. Upwind enterprise analysis
        3. Component analysis (VOCs/PM)
        4. Weather analysis with map

        Args:
            station: Station info dict
            params: Query parameters
            station_monitoring_data: All stations monitoring data
            weather_data_all: All districts weather data
            component_data: City-level component data (shared)

        Returns:
            StationAnalysisResult
        """
        station_name = station.get("站点名称", station.get("name", ""))
        station_district = station.get("区县", station.get("district", ""))

        logger.info(
            "analyzing_single_station",
            station=station_name,
            district=station_district
        )

        # 1. Get station monitoring data
        station_data = station_monitoring_data.get(station_name, [])

        # 2. Match weather data by district (方案B)
        station_weather = self._match_weather_by_district(
            station_district, weather_data_all
        )

        # 3. Upwind enterprise analysis (reuse station logic)
        winds = format_weather_to_winds(station_weather)
        upwind_result = {}
        enterprises = []

        if winds:
            try:
                upwind_result = await upwind_api.analyze_upwind_enterprises(
                    station_name=station_name,
                    winds=winds,
                    search_range_km=settings.default_search_range_km,
                    max_enterprises=settings.default_max_enterprises,
                    top_n=settings.default_top_n_enterprises,
                    map_type="normal",
                    mode="topn_mixed",
                )
                enterprises = upwind_result.get("filtered", [])
            except Exception as e:
                logger.error(
                    "upwind_analysis_failed",
                    station=station_name,
                    error=str(e)
                )

        # 4. Component analysis (VOCs/PM) - reuse station logic
        component_analysis = None
        if component_data:
            try:
                if params.pollutant == "O3":
                    analysis_text = await llm_service.analyze_vocs_source(
                        station_name=station_name,
                        city=params.city or "",
                        pollutant=params.pollutant,
                        start_time=params.start_time or "",
                        end_time=params.end_time or "",
                        station_data=station_data,
                        weather_data=station_weather,
                        vocs_data=component_data,
                        enterprise_data=enterprises,
                        scale="city",
                    )

                    # Note: Visuals will be generated once at city level, not per station
                    component_analysis = ModuleResult(
                        analysis_type="voc_analysis",
                        content=analysis_text,
                        confidence=0.75,
                        visuals=[],  # Empty for now, city level will add
                        anchors=[],
                    )

                elif params.pollutant in ["PM2.5", "PM10"]:
                    analysis_text = await llm_service.analyze_particulate_source(
                        station_name=station_name,
                        city=params.city or "",
                        pollutant=params.pollutant,
                        start_time=params.start_time or "",
                        end_time=params.end_time or "",
                        station_data=station_data,
                        weather_data=station_weather,
                        particulate_data=component_data,
                        enterprise_data=enterprises,
                        scale="city",
                    )

                    component_analysis = ModuleResult(
                        analysis_type="particulate_analysis",
                        content=analysis_text,
                        confidence=0.75,
                        visuals=[],
                        anchors=[],
                    )
            except Exception as e:
                logger.error(
                    "component_analysis_failed",
                    station=station_name,
                    error=str(e)
                )

        # 5. Weather analysis with map (reuse station logic)
        weather_analysis = self._generate_station_weather_analysis(
            station_name, station, station_weather, enterprises, upwind_result
        )

        logger.info(
            "station_analysis_complete",
            station=station_name,
            has_weather=bool(station_weather),
            has_upwind=bool(enterprises),
            has_component=bool(component_analysis)
        )

        return StationAnalysisResult(
            station_name=station_name,
            station_info=station,
            station_data=station_data,
            weather_data=station_weather,
            upwind_result=upwind_result,
            component_analysis=component_analysis,
            weather_analysis=weather_analysis,
        )

    def _generate_station_weather_analysis(
        self,
        station_name: str,
        station_info: Dict[str, Any],
        weather_data: List[Dict[str, Any]],
        enterprises: List[Dict[str, Any]],
        upwind_result: Dict[str, Any],
    ) -> ModuleResult:
        """
        Generate weather analysis for a single station (reuse station logic).
        """
        lines = []

        # Check if weather data is missing (历史数据不可用)
        if not weather_data:
            lines.append("⚠️ **气象数据未获取**")
            lines.append("")
            lines.append("当前查询时间段的气象数据不可用（可能是历史数据或API限制）。")
            lines.append("由于缺少风向风速数据，无法进行上风向企业分析。")
            lines.append("")
            logger.warning(
                "weather_data_missing_for_station",
                station=station_name,
                message="Weather data unavailable - cannot perform upwind analysis"
            )
        # Weather summary
        elif weather_data:
            wind_speeds = [w.get("windSpeed") for w in weather_data if w.get("windSpeed") is not None]
            wind_dirs = [w.get("windDirection") for w in weather_data if w.get("windDirection") is not None]

            if wind_speeds:
                avg_ws = sum(wind_speeds) / len(wind_speeds)
                lines.append(f"- 平均风速: {avg_ws:.1f} m/s")

            if wind_dirs:
                avg_wd = sum(wind_dirs) / len(wind_dirs)
                sectors = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                sector_idx = int((avg_wd + 22.5) / 45) % 8
                lines.append(f"- 主导风向: {sectors[sector_idx]} ({avg_wd:.0f}°)")

        # Upwind enterprises
        if enterprises:
            lines.append(f"- 上风向企业: {len(enterprises)}家")

        visuals = []

        # Generate map
        if enterprises:
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

            visuals.append({
                "id": f"upwind_map_{station_name}",
                "type": "map",
                "title": f"{station_name}上风向企业分布",
                "mode": "dynamic",
                "payload": map_payload,
            })

        return ModuleResult(
            analysis_type="weather_analysis",
            content="\n".join(lines),
            confidence=0.85,
            visuals=visuals,
            anchors=[],
        )

    async def _analyze_all_stations(
        self,
        params: ExtractedParams,
        stations: List[Dict[str, Any]],
        station_monitoring_data: Dict[str, List],
        weather_data_all: List[Dict],
        component_data: List[Dict],
    ) -> List[StationAnalysisResult]:
        """
        Step 5: Analyze all stations with Semaphore=5 concurrency control.

        Args:
            params: Query parameters
            stations: All stations in city
            station_monitoring_data: Monitoring data for all stations
            weather_data_all: Weather data for all districts
            component_data: City-level component data (shared)

        Returns:
            List of StationAnalysisResult
        """
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent stations

        async def analyze_with_limit(station):
            async with semaphore:
                return await self._analyze_single_station(
                    station, params, station_monitoring_data,
                    weather_data_all, component_data
                )

        # Execute all stations in parallel with semaphore control
        results = await asyncio.gather(*[
            analyze_with_limit(s) for s in stations
        ], return_exceptions=True)

        # Filter out exceptions
        valid_results = [
            r for r in results
            if not isinstance(r, Exception)
        ]

        if len(valid_results) < len(stations):
            logger.warning(
                "some_stations_failed",
                total=len(stations),
                successful=len(valid_results),
                failed=len(stations) - len(valid_results)
            )

        return valid_results

    async def _generate_city_regional_comparison_llm(
        self,
        params: ExtractedParams,
        station_monitoring_data: Dict[str, List[Dict[str, Any]]],
        nearby_city_data: Dict[str, List[Dict[str, Any]]],
    ) -> ModuleResult:
        """
        Generate LLM-based regional comparison between target city and nearby cities.
        """
        city = params.city or ""
        pollutant = params.pollutant or "O3"

        # Helper function to extract concentration based on pollutant type
        def get_concentration(data_point: Dict[str, Any], pollutant: str) -> Optional[float]:
            """
            Extract concentration value from data point based on pollutant type.

            City-level API returns pollutant-specific fields (e.g., 'o3', 'pM2_5'),
            while station-level API returns 'concentration' or '浓度' fields.
            """
            # Try standard fields first (station-level format)
            value = data_point.get("concentration") or data_point.get("浓度")
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    pass

            # Try pollutant-specific fields (city-level format)
            pollutant_field_map = {
                "O3": "o3",
                "PM2.5": "pM2_5",
                "PM10": "pM10",
                "CO": "co",
                "NO2": "nO2",
                "NOX": "nOx",
                "SO2": "sO2",
            }

            field_name = pollutant_field_map.get(pollutant.upper())
            if field_name:
                value = data_point.get(field_name)
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        pass

            return None

        # Calculate target city statistics from all stations
        all_target_concentrations = []
        for station_name, data in station_monitoring_data.items():
            concentrations = [
                get_concentration(d, pollutant)
                for d in data
            ]
            # Filter out None values
            concentrations = [c for c in concentrations if c is not None]
            all_target_concentrations.extend(concentrations)

        if all_target_concentrations:
            target_avg = sum(all_target_concentrations) / len(all_target_concentrations)
            target_max = max(all_target_concentrations)
            target_min = min(all_target_concentrations)
        else:
            target_avg = target_max = target_min = 0

        target_city_summary = f"**目标城市**: {city}\n"
        target_city_summary += f"**平均浓度**: {target_avg:.1f}\n"
        target_city_summary += f"**峰值浓度**: {target_max:.1f}\n"
        target_city_summary += f"**最低浓度**: {target_min:.1f}\n"
        target_city_summary += f"**站点数**: {len(station_monitoring_data)}\n"

        # Prepare nearby cities statistics
        nearby_summary_lines = []
        for neighbor_city, city_data in nearby_city_data.items():
            if city_data:
                concentrations = [
                    get_concentration(d, pollutant)
                    for d in city_data
                ]
                # Filter out None values
                concentrations = [c for c in concentrations if c is not None]

                if concentrations:
                    avg_conc = sum(concentrations) / len(concentrations)
                    max_conc = max(concentrations)
                    min_conc = min(concentrations)
                    nearby_summary_lines.append(
                        f"- **{neighbor_city}**: 平均 {avg_conc:.1f}, 峰值 {max_conc:.1f}, 最小值 {min_conc:.1f}"
                    )
                    logger.info(
                        "nearby_city_concentration_extracted",
                        city=neighbor_city,
                        data_points=len(city_data),
                        valid_concentrations=len(concentrations),
                        avg=avg_conc,
                        max=max_conc,
                    )
                else:
                    logger.warning(
                        "nearby_city_no_valid_concentrations",
                        city=neighbor_city,
                        data_points=len(city_data),
                        reason="All concentration values are None after extraction"
                    )

        nearby_summary = "\n".join(nearby_summary_lines) if nearby_summary_lines else "暂无周边城市数据"

        # Build LLM prompt
        prompt = f"""
请分析{city}市与周边城市的{params.pollutant}污染对比情况。

## 目标城市
{target_city_summary}

## 周边城市污染水平
{nearby_summary}

## 分析要求
请生成一个简洁的区域对比分析报告（200-300字），包括：
1. 目标城市与周边城市的污染水平对比
2. 可能的区域传输特征
3. 相对污染压力评估
"""

        # Call LLM
        try:
            if llm_service.provider in ["openai", "deepseek", "minimax", "mimo"]:
                response = await llm_service.client.chat.completions.create(
                    model=llm_service.config["model"],
                    messages=[
                        {"role": "system", "content": "你是大气污染区域分析专家，擅长识别城市间的污染传输特征。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=800,
                )
                analysis_text = response.choices[0].message.content
            elif llm_service.provider == "anthropic":
                response = await llm_service.client.messages.create(
                    model=llm_service.config["model"],
                    max_tokens=800,
                    system="你是大气污染区域分析专家，擅长识别城市间的污染传输特征。",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                )
                analysis_text = response.content[0].text
            else:
                analysis_text = "**城市间区域对比分析**\n\n分析失败：不支持的LLM提供商。"

            # Clean markdown wrappers
            analysis_text = llm_service._clean_markdown_content(analysis_text)

        except Exception as e:
            logger.error("regional_comparison_llm_failed", error=str(e))
            analysis_text = f"**城市间区域对比分析**\n\n{target_city_summary}\n**周边城市对比**:\n{nearby_summary}"

        # Generate timeseries comparison visual
        visuals = []
        try:
            # Prepare timeseries data for chart
            all_chart_data = []

            # Add target city average data (aggregate all stations by time)
            # Group station data by time and calculate average
            time_to_values = {}
            for station_name, data in station_monitoring_data.items():
                for point in data:
                    if isinstance(point, dict):
                        time_val = point.get("timePoint") or point.get("time") or point.get("时间")
                        conc_val = get_concentration(point, pollutant)

                        if time_val and conc_val is not None:
                            if time_val not in time_to_values:
                                time_to_values[time_val] = []
                            time_to_values[time_val].append(conc_val)

            # Calculate average for each time point
            for time_val, values in time_to_values.items():
                if values:
                    avg_value = sum(values) / len(values)
                    all_chart_data.append({
                        "time": time_val,
                        "value": avg_value,
                        "series": city,  # Target city name
                    })

            # Add nearby cities data
            for neighbor_city, city_data in nearby_city_data.items():
                for point in city_data:
                    if isinstance(point, dict):
                        time_val = point.get("timePoint") or point.get("time") or point.get("时间")
                        conc_val = get_concentration(point, pollutant)

                        if time_val and conc_val is not None:
                            all_chart_data.append({
                                "time": time_val,
                                "value": conc_val,
                                "series": neighbor_city,
                            })

            if all_chart_data:
                logger.info(
                    "city_regional_chart_data_prepared",
                    total_points=len(all_chart_data),
                    cities=len(set(d["series"] for d in all_chart_data)),
                    sample=all_chart_data[0] if all_chart_data else None
                )

                # Generate timeseries payload
                payload = generate_timeseries_payload(
                    all_chart_data,
                    title=f"{city}市与周边城市{pollutant}浓度对比",
                    x_axis_key="time",
                    y_axis_key="value",
                    series_name_key="series",
                )

                visuals.append({
                    "id": "city_regional_comparison_timeseries",
                    "type": "timeseries",
                    "title": f"{city}市与周边城市浓度时序对比",
                    "mode": "dynamic",
                    "payload": payload,
                })

                logger.info("city_regional_visual_generated", visual_count=len(visuals))
            else:
                logger.warning("city_regional_no_chart_data", reason="No valid time-value pairs")

        except Exception as e:
            logger.error("city_regional_visual_generation_failed", error=str(e))

        return ModuleResult(
            analysis_type="regional_analysis",
            content=analysis_text,
            confidence=0.75,
            visuals=visuals,
            anchors=[{"ref": "city_regional_comparison_timeseries", "label": "城市对比图"}] if visuals else [],
        )

    def _aggregate_component_analysis(
        self,
        station_results: List[StationAnalysisResult],
        pollutant: str,
    ) -> str:
        """
        Aggregate component analysis conclusions from all stations.

        Args:
            station_results: List of station analysis results
            pollutant: Pollutant type (O3, PM2.5, PM10)

        Returns:
            Formatted component analysis summary
        """
        if not station_results:
            return "暂无组分分析数据"

        # Collect all component analysis content
        component_contents = []
        for result in station_results:
            if result.component_analysis and result.component_analysis.content:
                component_contents.append(
                    f"### {result.station_name}\n{result.component_analysis.content}"
                )

        if not component_contents:
            return "暂无组分分析数据"

        # Format as markdown
        summary = f"### 各站点{pollutant}组分溯源分析结论\n\n"
        summary += "\n\n".join(component_contents)

        logger.info(
            "component_analysis_aggregated",
            stations_with_analysis=len(component_contents),
            total_stations=len(station_results),
        )

        return summary

    def _aggregate_enterprise_summary(
        self,
        station_results: List[StationAnalysisResult],
    ) -> str:
        """
        Aggregate upwind enterprise data from all stations.

        Args:
            station_results: List of station analysis results

        Returns:
            Formatted enterprise summary with:
            - Total unique enterprises
            - Top 10 enterprises by emission
            - Industry statistics
            - Enterprise distribution by district
        """
        if not station_results:
            return "暂无企业数据"

        # Collect all enterprises from all stations
        all_enterprises = []
        station_enterprise_map = {}  # Track which stations have each enterprise

        for result in station_results:
            enterprises = result.upwind_result.get("filtered", [])
            station_name = result.station_name

            for ent in enterprises:
                ent_name = ent.get("name", ent.get("企业名称", ""))
                if ent_name:
                    # Add station reference
                    ent_copy = ent.copy()
                    ent_copy["_station"] = station_name
                    all_enterprises.append(ent_copy)

                    # Track station-enterprise mapping
                    if ent_name not in station_enterprise_map:
                        station_enterprise_map[ent_name] = []
                    station_enterprise_map[ent_name].append(station_name)

        if not all_enterprises:
            return "暂无上风向企业数据"

        # Deduplicate enterprises by name
        unique_enterprises = {}
        for ent in all_enterprises:
            ent_name = ent.get("name", ent.get("企业名称", ""))
            if ent_name and ent_name not in unique_enterprises:
                unique_enterprises[ent_name] = ent

        # Get pollutant field for sorting
        pollutant_field = None
        if unique_enterprises:
            first_ent = next(iter(unique_enterprises.values()))
            for field in ["VOCs排放量", "PM2.5排放量", "PM10排放量", "SO2排放量", "NOx排放量"]:
                if field in first_ent:
                    pollutant_field = field
                    break

        # Sort by emission (if available)
        sorted_enterprises = sorted(
            unique_enterprises.values(),
            key=lambda e: float(e.get(pollutant_field, e.get("排放量", 0)) or 0),
            reverse=True,
        )

        # Industry statistics
        industry_stats = {}
        district_stats = {}
        for ent in sorted_enterprises:
            industry = ent.get("industry", ent.get("行业", "未知"))
            district = ent.get("district", ent.get("区县", "未知"))

            if industry not in industry_stats:
                industry_stats[industry] = {"count": 0, "emission": 0}
            industry_stats[industry]["count"] += 1
            industry_stats[industry]["emission"] += float(
                ent.get(pollutant_field, ent.get("排放量", 0)) or 0
            )

            if district not in district_stats:
                district_stats[district] = 0
            district_stats[district] += 1

        # Sort industry by emission
        sorted_industries = sorted(
            industry_stats.items(),
            key=lambda x: x[1]["emission"],
            reverse=True,
        )

        # Format enterprise summary
        summary_lines = [
            f"### 全市上风向企业统计",
            f"- 企业总数（去重后）：{len(unique_enterprises)}家",
            f"- 涉及站点数：{len(station_results)}个",
            f"",
            f"### 重点企业清单（按排放量排序，前10名）",
            "",
        ]

        # Top 10 enterprises table
        summary_lines.append("| 企业名称 | 行业类型 | 区县 | 排放量(吨/年) | 影响站点 |")
        summary_lines.append("|---------|---------|------|--------------|---------|")

        for i, ent in enumerate(sorted_enterprises[:10], 1):
            name = ent.get("name", ent.get("企业名称", "Unknown"))
            industry = ent.get("industry", ent.get("行业", "N/A"))
            district = ent.get("district", ent.get("区县", "N/A"))
            emission = float(ent.get(pollutant_field, ent.get("排放量", 0)) or 0)
            affected_stations = ", ".join(station_enterprise_map.get(name, []))

            summary_lines.append(
                f"| {name} | {industry} | {district} | {emission:.1f} | {affected_stations} |"
            )

        # Industry statistics
        summary_lines.append("")
        summary_lines.append("### 重点行业排序（按排放量）")
        summary_lines.append("")
        for i, (industry, stats) in enumerate(sorted_industries[:5], 1):
            summary_lines.append(
                f"{i}. **{industry}**: {stats['count']}家企业，排放总量 {stats['emission']:.1f} 吨/年"
            )

        # District distribution
        summary_lines.append("")
        summary_lines.append("### 企业区域分布")
        summary_lines.append("")
        sorted_districts = sorted(district_stats.items(), key=lambda x: x[1], reverse=True)
        for district, count in sorted_districts[:5]:
            summary_lines.append(f"- {district}: {count}家企业")

        logger.info(
            "enterprise_summary_aggregated",
            total_enterprises=len(all_enterprises),
            unique_enterprises=len(unique_enterprises),
            industries=len(industry_stats),
            districts=len(district_stats),
        )

        return "\n".join(summary_lines)

    async def _generate_city_comprehensive_summary(
        self,
        params: ExtractedParams,
        stations: List[Dict[str, Any]],
        station_results: List[StationAnalysisResult],
        regional_analysis: ModuleResult,
    ) -> ModuleResult:
        """
        Generate comprehensive summary for city-level analysis.

        Uses LLM to synthesize insights from all station results.
        """
        city = params.city or ""
        pollutant = params.pollutant or "O3"

        # Aggregate statistics from all stations
        all_concentrations = []
        for result in station_results:
            concentrations = [
                self._get_concentration(d, pollutant)
                for d in result.station_data
            ]
            # Filter out None values
            concentrations = [c for c in concentrations if c is not None]
            all_concentrations.extend(concentrations)

        if all_concentrations:
            city_avg = sum(all_concentrations) / len(all_concentrations)
            city_max = max(all_concentrations)
            city_min = min(all_concentrations)
        else:
            city_avg = city_max = city_min = 0

        # Prepare station summaries
        station_summaries = []
        for result in station_results:
            station_concentrations = [
                self._get_concentration(d, pollutant)
                for d in result.station_data
            ]
            # Filter out None values
            station_concentrations = [c for c in station_concentrations if c is not None]

            if station_concentrations:
                station_avg = sum(station_concentrations) / len(station_concentrations)
                station_max = max(station_concentrations)
                upwind_count = len(result.upwind_result.get("filtered", []))

                station_summaries.append(
                    f"- **{result.station_name}**: 平均 {station_avg:.1f}, 峰值 {station_max:.1f}, 上风向企业 {upwind_count}家"
                )

        station_summary_text = "\n".join(station_summaries) if station_summaries else "暂无站点数据"

        # ==================== 聚合组分溯源分析结论 ====================
        component_analysis_summary = self._aggregate_component_analysis(station_results, pollutant)

        # ==================== 聚合全市上风向企业清单 ====================
        enterprise_summary = self._aggregate_enterprise_summary(station_results)

        # Build comprehensive LLM prompt
        prompt = f"""
请为{city}市的{params.pollutant}污染分析生成综合总结报告。

## 基本信息
- 城市: {city}
- 污染物: {params.pollutant}
- 时间范围: {params.start_time} 至 {params.end_time}

## 城市整体污染数据
- 平均浓度: {city_avg:.1f}
- 峰值浓度: {city_max:.1f}
- 最低浓度: {city_min:.1f}
- 分析站点数: {len(station_results)}

## 各站点污染概况
{station_summary_text}

## 区域对比分析
{regional_analysis.content}

## 组分溯源分析结论
{component_analysis_summary}

## 全市上风向企业清单
{enterprise_summary}

## 要求
请基于以上城市级别的数据，生成一个综合总结报告（400-500字），包括：
1. 总结目标城市的污染特征和时间变化趋势
2. 分析城市内各站点的空间分布特征
3. 结合区域对比分析，评估本市污染压力
4. 结合组分溯源分析，明确主要污染行业类型和来源特征
5. 结合企业清单，识别重点污染区域和管控建议
"""

        # Call LLM
        try:
            if llm_service.provider in ["openai", "deepseek", "minimax", "mimo"]:
                response = await llm_service.client.chat.completions.create(
                    model=llm_service.config["model"],
                    messages=[
                        {"role": "system", "content": "你是大气污染城市级别分析专家，擅长综合城市数据进行污染评估和区域对比。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=1500,
                )
                summary_text = response.choices[0].message.content
            elif llm_service.provider == "anthropic":
                response = await llm_service.client.messages.create(
                    model=llm_service.config["model"],
                    max_tokens=1500,
                    system="你是大气污染城市级别分析专家，擅长综合城市数据进行污染评估和区域对比。",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                )
                summary_text = response.content[0].text
            else:
                summary_text = "综合分析生成失败：不支持的LLM提供商。"

            # Clean markdown wrappers
            summary_text = llm_service._clean_markdown_content(summary_text)

        except Exception as e:
            logger.error("city_comprehensive_llm_failed", error=str(e))
            summary_text = "综合分析生成失败，请查看各站点分析结果。"

        return ModuleResult(
            analysis_type="comprehensive_analysis",
            content=summary_text,
            confidence=0.75,
            visuals=None,
            anchors=None,
        )

    def _assemble_city_response(
        self,
        params: ExtractedParams,
        stations: List[Dict[str, Any]],
        station_results: List[StationAnalysisResult],
        component_data: List[Dict],
        regional_analysis: ModuleResult,
        comprehensive_analysis: ModuleResult,
    ) -> AnalysisResponseData:
        """
        Assemble city-level response with specified display order:
        1. Regional comparison (city-to-city) - 优先展示
        2. Component charts (once) - 组分图表
        3. Combined by station (upwind + component text + weather + map) - 按站点合并
        4. Comprehensive analysis - 综合分析

        Note: NO KPI calculation for city queries.
        """
        city = params.city or ""
        pollutant = params.pollutant or ""

        # Build query info
        query_info = QueryInfo(
            location=None,
            city=city,
            pollutant=pollutant,
            start_time=params.start_time,
            end_time=params.end_time,
            scale="city",
        )

        viz_capability = VisualizationCapability(
            supports_dynamic_map=True,
            supports_echarts=True,
            supports_small_multiples=False,
            supports_animation=False,
        )

        # 2. Component analysis: Charts once + Text by station
        component_analysis_module = None
        if component_data and station_results:
            # Generate component charts ONCE (shared by all stations)
            if pollutant == "O3":
                # Use first station's enterprises for industry analysis
                first_enterprises = station_results[0].upwind_result.get("filtered", []) if station_results else []
                component_visuals = generate_vocs_analysis_visuals(component_data, first_enterprises)

                # Build content: Chart description + Text by station
                lines = [
                    f"## {city}市VOCs组分溯源分析\n",
                    "### 组分数据概览\n",
                    "（以下图表展示城市整体VOCs组分特征）\n",
                ]

                # Add per-station analysis text
                lines.append("\n### 各站点溯源分析\n")
                for result in station_results:
                    lines.append(f"\n#### {result.station_name}\n")
                    if result.component_analysis:
                        lines.append(result.component_analysis.content)
                    lines.append("\n")

                component_analysis_module = ModuleResult(
                    analysis_type="voc_analysis",
                    content="\n".join(lines),
                    confidence=0.75,
                    visuals=component_visuals,
                    anchors=[
                        {"ref": "vocs_concentration_pie", "label": "VOCs浓度分布"},
                        {"ref": "ofp_contribution_bar", "label": "OFP贡献"},
                    ],
                )

            elif pollutant in ["PM2.5", "PM10"]:
                first_enterprises = station_results[0].upwind_result.get("filtered", []) if station_results else []
                component_visuals = generate_particulate_analysis_visuals(component_data, first_enterprises)

                lines = [
                    f"## {city}市颗粒物组分溯源分析\n",
                    "### 组分数据概览\n",
                    "（以下图表展示城市整体颗粒物组分特征）\n",
                ]

                lines.append("\n### 各站点溯源分析\n")
                for result in station_results:
                    lines.append(f"\n#### {result.station_name}\n")
                    if result.component_analysis:
                        lines.append(result.component_analysis.content)
                    lines.append("\n")

                component_analysis_module = ModuleResult(
                    analysis_type="particulate_analysis",
                    content="\n".join(lines),
                    confidence=0.75,
                    visuals=component_visuals,
                    anchors=[
                        {"ref": "particulate_component_pie", "label": "颗粒物组分"},
                        {"ref": "industry_pm_bar", "label": "行业贡献"},
                    ],
                )

        # 3. Weather analysis: Combined by station (upwind + weather + map)
        weather_lines = [f"## {city}市气象与上风向企业分析\n"]
        weather_visuals = []

        for result in station_results:
            weather_lines.append(f"\n### {result.station_name}\n")

            # Add weather summary
            if result.weather_analysis.content:
                weather_lines.append(result.weather_analysis.content)

            # Add upwind enterprises list
            enterprises = result.upwind_result.get("filtered", [])
            if enterprises:
                weather_lines.append(f"\n**上风向企业详情**:\n")
                for i, ent in enumerate(enterprises[:5], 1):
                    name = ent.get("name", ent.get("企业名称", "Unknown"))
                    industry = ent.get("industry", ent.get("行业", "N/A"))
                    distance = ent.get("distance_km", ent.get("距离", 0))
                    weather_lines.append(f"{i}. {name} ({industry}, {distance:.1f}km)")

                if len(enterprises) > 5:
                    weather_lines.append(f"\n*...及其他{len(enterprises)-5}家企业*")

            weather_lines.append("\n")

            # Add map visual
            if result.weather_analysis.visuals:
                weather_visuals.extend(result.weather_analysis.visuals)

        weather_analysis = ModuleResult(
            analysis_type="weather_analysis",
            content="\n".join(weather_lines),
            confidence=0.85,
            visuals=weather_visuals,
            anchors=[],
        )

        # Assign component analysis to appropriate field
        voc_analysis = None
        particulate_analysis = None

        if component_analysis_module:
            if pollutant == "O3":
                voc_analysis = component_analysis_module
            elif pollutant in ["PM2.5", "PM10"]:
                particulate_analysis = component_analysis_module

        return AnalysisResponseData(
            query_info=query_info,
            visualization_capability=viz_capability,
            upwind_enterprises=None,  # No separate upwind for city level
            weather_analysis=weather_analysis,
            regional_analysis=regional_analysis,  # 优先展示
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

    async def analyze_city_streaming(self, params: ExtractedParams):
        """
        Streaming analysis entry point for city-level queries.

        Yields modules as they complete in real-time, similar to station-level streaming.

        Yields:
            dict: Events with format:
                - {'event': 'step', 'step': str, 'status': str, 'message': str}
                - {'event': 'module_complete', 'module': str, 'data': ModuleResult}
                - {'event': 'done', 'data': AnalysisResponseData}
                - {'event': 'error', 'error': str}
        """
        city = params.city or ""
        logger.info("city_streaming_analysis_start", city=city, pollutant=params.pollutant)

        try:
            import time
            workflow_start = time.time()

            # Step 2: Fetch stations and nearby cities
            yield {
                'event': 'step',
                'step': 'fetch_stations',
                'status': 'start',
                'message': f'正在获取{city}市的监测站点和周边城市...'
            }

            stations, nearby_cities = await self._fetch_stations_and_cities(params)

            if not stations:
                yield {
                    'event': 'error',
                    'error': f"未找到城市 {city} 的国控站点"
                }
                return

            yield {
                'event': 'step',
                'step': 'fetch_stations',
                'status': 'success',
                'message': f'获取成功：{len(stations)}个站点，{len(nearby_cities)}个周边城市'
            }

            # Step 3: Four-way parallel core data fetch
            yield {
                'event': 'step',
                'step': 'core_data_fetch',
                'status': 'start',
                'message': '正在并行获取气象数据、组分数据、监测数据...'
            }

            step3_start = time.time()
            (
                weather_data_all,
                component_data,
                station_monitoring_data,
                nearby_city_data,
            ) = await self._fetch_city_core_data(params, stations, nearby_cities)

            step3_duration = time.time() - step3_start

            yield {
                'event': 'step',
                'step': 'core_data_fetch',
                'status': 'success',
                'message': f'核心数据获取完成（耗时{step3_duration:.1f}s）：{len(station_monitoring_data)}个站点有数据'
            }

            # 立即生成组分可视化图表（如果有数据）
            # Note: 组分图表（浓度分布、OFP贡献）不依赖企业数据，可以提前生成
            if component_data and params.pollutant in ["O3", "PM2.5", "PM10"]:
                try:
                    yield {
                        'event': 'step',
                        'step': 'component_visuals',
                        'status': 'start',
                        'message': '正在生成组分分析图表...'
                    }

                    # Generate component charts (no LLM needed, just data transformation)
                    pollutant = params.pollutant
                    if pollutant == "O3":
                        # 传入空企业列表是正常的，图表生成不依赖企业数据
                        component_visuals = generate_vocs_analysis_visuals(component_data, [])

                        component_charts_module = ModuleResult(
                            analysis_type="voc_analysis",
                            content=f"## {city}市VOCs组分分析\n\n（组分图表已生成，站点详细分析正在进行中...）",
                            confidence=0.75,
                            visuals=component_visuals,
                            anchors=[
                                {"ref": "vocs_concentration_pie", "label": "VOCs浓度分布"},
                                {"ref": "ofp_contribution_bar", "label": "OFP贡献"},
                            ],
                        )
                    else:  # PM2.5 or PM10
                        component_visuals = generate_particulate_analysis_visuals(component_data, [])

                        component_charts_module = ModuleResult(
                            analysis_type="particulate_analysis",
                            content=f"## {city}市颗粒物组分分析\n\n（组分图表已生成，站点详细分析正在进行中...）",
                            confidence=0.75,
                            visuals=component_visuals,
                            anchors=[
                                {"ref": "particulate_component_pie", "label": "颗粒物组分"},
                                {"ref": "industry_pm_bar", "label": "行业贡献"},
                            ],
                        )

                    yield {
                        'event': 'module_complete',
                        'module': component_charts_module.analysis_type,
                        'data': component_charts_module.dict()
                    }

                    logger.info("component_visuals_yielded_early", pollutant=pollutant, enterprise_data_provided=False)

                except Exception as e:
                    logger.error("component_visuals_generation_failed", error=str(e))

            # Step 4 & 5: Parallel execution of three main tasks
            yield {
                'event': 'step',
                'step': 'parallel_analyses',
                'status': 'start',
                'message': '正在并行执行区域对比分析、站点分析...'
            }

            parallel_start = time.time()

            # Create parallel tasks
            tasks = {
                'regional_analysis': asyncio.create_task(
                    self._generate_city_regional_comparison_llm(
                        params, station_monitoring_data, nearby_city_data
                    )
                ),
                'station_analyses': asyncio.create_task(
                    self._analyze_all_stations(
                        params, stations, station_monitoring_data,
                        weather_data_all, component_data
                    )
                ),
            }

            # Track completed tasks
            completed_tasks = {}
            completed_count = 0
            total_tasks = len(tasks)
            weather_analysis = None  # Initialize for later use in save logic

            # Yield modules as they complete
            for coro in asyncio.as_completed(tasks.values()):
                try:
                    result = await coro
                    completed_count += 1

                    # Find which task completed
                    module_name = None
                    for name, task in tasks.items():
                        if name not in completed_tasks:
                            try:
                                if task.done() and task.result() == result:
                                    module_name = name
                                    break
                            except:
                                pass

                    if not module_name:
                        # Fallback: use first uncompleted task name
                        for name in tasks.keys():
                            if name not in completed_tasks:
                                module_name = name
                                break

                    if module_name:
                        completed_tasks[module_name] = result
                        task_duration = time.time() - parallel_start

                        yield {
                            'event': 'step',
                            'step': f'{module_name}_complete',
                            'status': 'success',
                            'message': f'{module_name}完成（{completed_count}/{total_tasks}，耗时{task_duration:.1f}s）'
                        }

                        # Yield module result immediately
                        if module_name == 'regional_analysis':
                            # Regional analysis is a ModuleResult
                            yield {
                                'event': 'module_complete',
                                'module': 'regional_analysis',
                                'data': result.dict()
                            }

                        elif module_name == 'station_analyses':
                            # Station analyses is a list of StationAnalysisResult
                            # We need to assemble weather_analysis module from station results
                            station_results = result

                            # Assemble weather analysis module
                            weather_lines = [f"## {city}市气象与上风向企业分析\n"]
                            weather_visuals = []

                            for station_result in station_results:
                                weather_lines.append(f"\n### {station_result.station_name}\n")

                                if station_result.weather_analysis.content:
                                    weather_lines.append(station_result.weather_analysis.content)

                                # Add upwind enterprises list
                                enterprises = station_result.upwind_result.get("filtered", [])
                                if enterprises:
                                    weather_lines.append(f"\n**上风向企业详情**:\n")
                                    for i, ent in enumerate(enterprises[:5], 1):
                                        name = ent.get("name", ent.get("企业名称", "Unknown"))
                                        industry = ent.get("industry", ent.get("行业", "N/A"))
                                        distance = ent.get("distance_km", ent.get("距离", 0))
                                        weather_lines.append(f"{i}. {name} ({industry}, {distance:.1f}km)")

                                    if len(enterprises) > 5:
                                        weather_lines.append(f"\n*...及其他{len(enterprises)-5}家企业*")

                                weather_lines.append("\n")

                                # Add map visual
                                if station_result.weather_analysis.visuals:
                                    weather_visuals.extend(station_result.weather_analysis.visuals)

                            weather_analysis = ModuleResult(
                                analysis_type="weather_analysis",
                                content="\n".join(weather_lines),
                                confidence=0.85,
                                visuals=weather_visuals,
                                anchors=[],
                            )

                            yield {
                                'event': 'module_complete',
                                'module': 'weather_analysis',
                                'data': weather_analysis.dict()
                            }

                except Exception as e:
                    logger.error("parallel_task_failed", error=str(e), exc_info=True)
                    completed_count += 1
                    yield {
                        'event': 'step',
                        'step': 'parallel_task_error',
                        'status': 'warning',
                        'message': f'某个分析任务失败（{completed_count}/{total_tasks}）：{str(e)[:50]}'
                    }

            parallel_duration = time.time() - parallel_start

            yield {
                'event': 'step',
                'step': 'parallel_analyses',
                'status': 'success',
                'message': f'并行分析完成（总耗时{parallel_duration:.1f}s）'
            }

            # Step 6: Generate comprehensive summary
            yield {
                'event': 'step',
                'step': 'comprehensive_analysis',
                'status': 'start',
                'message': '正在生成城市综合分析报告...'
            }

            comprehensive_start = time.time()

            regional_analysis = completed_tasks.get('regional_analysis')
            station_results = completed_tasks.get('station_analyses')

            # Handle missing/failed modules
            if not regional_analysis:
                regional_analysis = ModuleResult(
                    analysis_type="regional_analysis",
                    content="**区域对比分析**\n\n分析失败，请稍后重试。",
                    confidence=0.0,
                )

            if not station_results:
                station_results = []

            comprehensive_analysis = await self._generate_city_comprehensive_summary(
                params, stations, station_results, regional_analysis
            )

            comprehensive_duration = time.time() - comprehensive_start

            yield {
                'event': 'step',
                'step': 'comprehensive_analysis',
                'status': 'success',
                'message': f'综合分析完成（耗时{comprehensive_duration:.1f}s）'
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
                "city_streaming_workflow_complete",
                total_duration=f"{total_duration:.2f}s",
                parallel_duration=f"{parallel_duration:.2f}s",
                comprehensive_duration=f"{comprehensive_duration:.2f}s",
            )

            # Assemble final response
            response = self._assemble_city_response(
                params,
                stations,
                station_results,
                component_data,
                regional_analysis,
                comprehensive_analysis,
            )

            # Step 7: Save to history database (auto-save)
            try:
                # Build history record
                history_record = AnalysisHistoryRecord(
                    query_text=f"分析{params.city}市{params.pollutant}污染",
                    scale=params.scale,
                    city=params.city,
                    location=None,  # City-level has no single station (字段名是 location 不是 station)
                    pollutant=params.pollutant,
                    start_time=params.start_time,
                    end_time=params.end_time,
                    # Analysis results
                    weather_analysis=weather_analysis.content if 'weather_analysis' in locals() else None,
                    regional_comparison=regional_analysis.content if regional_analysis else None,
                    vocs_source_analysis=None,  # Will be extracted from modules
                    particulate_source_analysis=None,  # Will be extracted from modules
                    comprehensive_summary=comprehensive_analysis.content if comprehensive_analysis else None,
                    modules_data=response.dict() if hasattr(response, "dict") else None,
                    # Metadata
                    status="completed",
                    duration_seconds=total_duration,
                )

                # Extract component analysis from response fields
                if response.voc_analysis:
                    history_record.vocs_source_analysis = response.voc_analysis.content
                elif response.particulate_analysis:
                    history_record.particulate_source_analysis = response.particulate_analysis.content

                session_id = await history_service.save_analysis(history_record)
                logger.info("city_streaming_saved_to_history", session_id=session_id, city=params.city)
            except Exception as e:
                logger.warning("city_streaming_failed_to_save_history", error=str(e), exc_info=True)

            # DEBUG: Log response before yielding
            response_dict = response.dict()
            logger.info("DEBUG_city_orchestrator_done_event",
                        has_response=bool(response),
                        response_keys=list(response_dict.keys()) if isinstance(response_dict, dict) else None)

            yield {
                'event': 'done',
                'data': response_dict
            }

        except Exception as e:
            logger.error("city_streaming_analysis_failed", error=str(e), exc_info=True)
            yield {
                'event': 'error',
                'error': f"城市级别流式分析失败: {str(e)}"
            }


# Global city orchestrator instance
city_orchestrator = CityAnalysisOrchestrator()
