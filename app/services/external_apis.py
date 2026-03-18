"""
Client wrappers for external API services.
"""
from typing import List, Dict, Any, Optional
from app.utils.http_client import http_client
from app.models.schemas import WindData, StationInfo, EnterpriseInfo
from config.settings import settings
from app.config.config_manager import config_manager
import structlog

logger = structlog.get_logger()


class StationAPIClient:
    """Client for Station & District Query API (port 9092)."""

    def __init__(self):
        self.base_url = settings.station_api_base_url

    async def get_station_by_name(
        self, station_name: str, top_k: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Query station district info by name.

        Args:
            station_name: Station name (supports fuzzy matching)
            top_k: Number of top matches to return

        Returns:
            Station information dict
        """
        try:
            url = f"{self.base_url}/api/station-district/by-station-name"
            params = {"station_name": station_name, "top_k": top_k}
            response = await http_client.get(url, params=params)

            if response.get("status") == "success":
                data = response.get("data")
                return data if isinstance(data, dict) else (data[0] if data else None)
            return None
        except Exception as e:
            logger.error("station_query_failed", station_name=station_name, error=str(e))
            return None

    async def get_nearby_stations(
        self,
        station_name: str,
        max_distance: float = 10.0,
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Query nearby stations by station name.

        Args:
            station_name: Reference station name
            max_distance: Maximum distance in kilometers
            max_results: Maximum number of results

        Returns:
            List of nearby stations
        """
        try:
            url = f"{self.base_url}/api/nearest-stations/by-station-name"
            params = {
                "station_name": station_name,
                "max_distance": max_distance,
                "max_results": max_results,
            }
            response = await http_client.get(url, params=params)

            if response.get("status") == "success":
                return response.get("data", [])
            return []
        except Exception as e:
            logger.error("nearby_stations_failed", station_name=station_name, error=str(e))
            return []

    async def get_city_stations(
        self,
        city_name: str,
        station_type_id: Optional[float] = None,
        fields: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query all stations in a city with optional type filtering.

        Args:
            city_name: City name (supports fuzzy matching)
            station_type_id: Station type ID filter (1.0 = 国控站点)
            fields: Comma-separated field list (name,code,lat,lon,district,township,type_id)

        Returns:
            List of stations in the city
        """
        try:
            url = f"{self.base_url}/api/station-district/by-city"
            params = {"city_name": city_name}

            if station_type_id is not None:
                params["station_type_id"] = station_type_id

            if fields:
                params["fields"] = fields

            response = await http_client.get(url, params=params)

            if response.get("status") == "success":
                return response.get("data", [])
            return []
        except Exception as e:
            logger.error("city_stations_failed", city_name=city_name, error=str(e))
            return []

    async def get_nearby_cities(
        self,
        city_name: str,
        k: int = 3,
        station_type_id: Optional[float] = None,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query nearby cities and their stations (based on city centroid distance).

        Args:
            city_name: City name (supports fuzzy matching)
            k: Number of nearby cities to return (3-5)
            station_type_id: Station type ID filter (1.0 = 国控站点)
            fields: Comma-separated field list

        Returns:
            Dict with neighbors list containing city info and stations
        """
        try:
            url = f"{self.base_url}/api/nearest-stations/by-city-neighbors"
            params = {"city_name": city_name, "k": k}

            if station_type_id is not None:
                params["station_type_id"] = station_type_id

            if fields:
                params["fields"] = fields

            response = await http_client.get(url, params=params)

            if response.get("status") == "success":
                return response
            return {"neighbors": []}
        except Exception as e:
            logger.error("nearby_cities_failed", city_name=city_name, error=str(e))
            return {"neighbors": []}

    async def get_nearest_superstation(
        self,
        station_name: str,
        max_distance: float = 100.0,
        max_results: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """
        Query nearest superstation (component station with code ending in 'B') by station name.

        Args:
            station_name: Regular station name (supports fuzzy matching)
            max_distance: Maximum distance in kilometers (default 100.0)
            max_results: Number of nearest superstations to return (default 1)

        Returns:
            Nearest superstation info dict, or None if not found
        """
        try:
            url = f"{self.base_url}/api/nearest-stations/by-station-name-nearest-super"
            params = {
                "station_name": station_name,
                "max_distance": max_distance,
                "max_results": max_results,
            }
            response = await http_client.get(url, params=params)

            if response.get("status") == "success":
                data = response.get("data", [])
                if data and len(data) > 0:
                    logger.info(
                        "nearest_superstation_found",
                        station_name=station_name,
                        superstation_name=data[0].get("站点名称"),
                        distance_km=data[0].get("距离"),
                    )
                    return data[0]
                else:
                    logger.warning(
                        "nearest_superstation_not_found",
                        station_name=station_name,
                        max_distance=max_distance,
                    )
                    return None
            return None
        except Exception as e:
            logger.error("nearest_superstation_failed", station_name=station_name, error=str(e))
            return None


class MonitoringDataAPIClient:
    """Client for monitoring data APIs."""

    def __init__(self):
        self.monitoring_url = settings.monitoring_data_api_url
        self.vocs_url = settings.vocs_data_api_url
        self.particulate_url = settings.particulate_data_api_url

    async def get_station_pollutant_data(
        self,
        station_name: str,
        pollutant: str,
        start_time: str,
        end_time: str,
    ) -> List[Dict[str, Any]]:
        """
        Get station pollutant concentration data (24-hour).

        Args:
            station_name: Station name
            pollutant: Pollutant type (SO2, CO, O3, PM2.5, PM10, NOX)
            start_time: Start time (YYYY-MM-DD HH:MM:SS)
            end_time: End time (YYYY-MM-DD HH:MM:SS)

        Returns:
            List of monitoring data points
        """
        try:
            url = f"{self.monitoring_url}/api/uqp/query"
            # Get template from config_manager (supports runtime modification)
            template = config_manager.get_value("station_query_templates", "station_pollutant")
            if not template:
                # Fallback to settings if config_manager doesn't have it yet
                template = settings.query_template_station_pollutant

            question = template.format(
                station_name=station_name,
                pollutant=pollutant,
                start_time=start_time,
                end_time=end_time
            )
            json_data = {"question": question}
            response = await http_client.post(url, json_data=json_data)

            # Handle nested response format: {"data": {"result": [...]}} or {"data": {"results": [...]}}
            if isinstance(response, dict):
                if "data" in response and isinstance(response["data"], dict):
                    # Try both "result" and "results" keys
                    result = response["data"].get("result", None)
                    if result is None:
                        result = response["data"].get("results", [])
                    return result if isinstance(result, list) else []
            return response if isinstance(response, list) else []
        except Exception as e:
            logger.error(
                "monitoring_data_failed",
                station=station_name,
                pollutant=pollutant,
                error=str(e),
            )
            return []

    async def get_city_pollutant_data(
        self,
        city: str,
        pollutant: str,
        start_time: str,
        end_time: str,
    ) -> List[Dict[str, Any]]:
        """
        Get city-level pollutant concentration data (hourly average).

        Args:
            city: City name
            pollutant: Pollutant type (SO2, CO, O3, PM2.5, PM10, NOX)
            start_time: Start time (YYYY-MM-DD HH:MM:SS)
            end_time: End time (YYYY-MM-DD HH:MM:SS)

        Returns:
            List of monitoring data points (city average)
        """
        try:
            url = f"{self.monitoring_url}/api/uqp/query"
            # Get template from config_manager (supports runtime modification)
            template = config_manager.get_value("city_query_templates", "city_pollutant")
            if not template:
                # Fallback to settings if config_manager doesn't have it yet
                template = settings.query_template_city_pollutant

            question = template.format(
                city=city,
                pollutant=pollutant,
                start_time=start_time,
                end_time=end_time
            )
            json_data = {"question": question}

            logger.info(
                "city_pollutant_query",
                city=city,
                pollutant=pollutant,
                question=question
            )

            response = await http_client.post(url, json_data=json_data)

            # DEBUG: Log response structure for city pollutant data
            logger.info(
                "city_pollutant_response_received",
                city=city,
                response_type=type(response).__name__,
                is_dict=isinstance(response, dict),
                is_list=isinstance(response, list),
            )

            # Handle nested response format
            if isinstance(response, dict):
                # Log dict keys for debugging
                logger.info(
                    "city_pollutant_response_dict_keys",
                    city=city,
                    keys=list(response.keys()) if isinstance(response, dict) else None
                )

                if "data" in response and isinstance(response["data"], dict):
                    data_keys = list(response["data"].keys())
                    logger.info(
                        "city_pollutant_response_data_keys",
                        city=city,
                        data_keys=data_keys
                    )

                    result = response["data"].get("result", None)
                    if result is None:
                        result = response["data"].get("results", [])
                        logger.info(
                            "city_pollutant_using_results",
                            city=city,
                            results_type=type(result).__name__,
                            results_len=len(result) if isinstance(result, list) else None
                        )
                    else:
                        logger.info(
                            "city_pollutant_using_result",
                            city=city,
                            result_type=type(result).__name__,
                            result_len=len(result) if isinstance(result, list) else None
                        )

                    if isinstance(result, list):
                        if len(result) > 0:
                            # Log first item structure
                            first_item = result[0]
                            logger.info(
                                "city_pollutant_first_item",
                                city=city,
                                first_item_type=type(first_item).__name__,
                                first_item_keys=list(first_item.keys()) if isinstance(first_item, dict) else None,
                                has_concentration=first_item.get("concentration") is not None if isinstance(first_item, dict) else None,
                                has_浓度=first_item.get("浓度") is not None if isinstance(first_item, dict) else None,
                            )
                        logger.info(
                            "city_pollutant_data_fetched",
                            city=city,
                            data_points=len(result)
                        )
                        return result
                    else:
                        logger.warning(
                            "city_pollutant_result_not_list",
                            city=city,
                            result_type=type(result).__name__
                        )
                        return []
                else:
                    logger.warning(
                        "city_pollutant_no_data_key",
                        city=city,
                        keys=list(response.keys())
                    )
                    return []

            if isinstance(response, list):
                logger.info(
                    "city_pollutant_direct_list",
                    city=city,
                    data_points=len(response)
                )
                return response

            logger.warning(
                "city_pollutant_unexpected_format",
                city=city,
                response_type=type(response).__name__
            )
            return []
        except Exception as e:
            logger.error(
                "city_pollutant_data_failed",
                city=city,
                pollutant=pollutant,
                error=str(e),
            )
            return []

    async def get_vocs_component_data(
        self,
        station_name: str,
        start_time: str,
        end_time: str,
    ) -> List[Dict[str, Any]]:
        """
        Get VOCs component and OFP data for a specific station.

        Args:
            station_name: Station name (superstation/component station)
            start_time: Start time
            end_time: End time

        Returns:
            List of VOCs component data
        """
        try:
            url = f"{self.vocs_url}/api/uqp/query"
            question = (
                f"查询{station_name}站点的OFP前十数据，"
                f"时间周期为{start_time}至{end_time}，时间精度为小时"
            )
            json_data = {"question": question}
            response = await http_client.post(url, json_data=json_data)

            # Handle nested response format:
            # {"data": {"concurrent_results": [{"data": {"data": {"hours": [...]}}}]}}
            if isinstance(response, dict):
                if "data" in response and isinstance(response["data"], dict):
                    data_dict = response["data"]

                    # Try "concurrent_results" field (new format from test results)
                    concurrent_results = data_dict.get("concurrent_results", None)
                    if concurrent_results is not None and isinstance(concurrent_results, list) and len(concurrent_results) > 0:
                        # Extract data from: concurrent_results[0].data.data.hours
                        first_result = concurrent_results[0]
                        if isinstance(first_result, dict) and "data" in first_result:
                            result_data = first_result["data"]
                            if isinstance(result_data, dict) and "data" in result_data:
                                inner_data = result_data["data"]
                                if isinstance(inner_data, dict) and "hours" in inner_data:
                                    hours_data = inner_data["hours"]
                                    if isinstance(hours_data, list):
                                        logger.info(
                                            "vocs_data_fetched",
                                            station_name=station_name,
                                            data_points=len(hours_data),
                                            source="concurrent_results.hours"
                                        )
                                        return hours_data

                    # Fallback: Try "result" field (old format)
                    result = data_dict.get("result", None)
                    if result is not None:
                        # Case 1: result is already a list
                        if isinstance(result, list):
                            logger.info("vocs_data_fetched", station_name=station_name, data_points=len(result), source="result_list")
                            return result

                        # Case 2: result is a dict containing nested data
                        elif isinstance(result, dict):
                            # Check for common nested field names
                            if "hours" in result and isinstance(result["hours"], list):
                                logger.info("vocs_data_fetched", station_name=station_name, data_points=len(result["hours"]), source="result.hours")
                                return result["hours"]
                            elif "ofpresults" in result and isinstance(result["ofpresults"], list):
                                logger.info("vocs_data_fetched", station_name=station_name, data_points=len(result["ofpresults"]), source="result.ofpresults")
                                return result["ofpresults"]
                            elif "data" in result and isinstance(result["data"], list):
                                logger.info("vocs_data_fetched", station_name=station_name, data_points=len(result["data"]), source="result.data")
                                return result["data"]
                            elif "datalistOrderByOFP" in result and isinstance(result["datalistOrderByOFP"], list):
                                logger.info("vocs_data_fetched", station_name=station_name, data_points=len(result["datalistOrderByOFP"]), source="result.datalistOrderByOFP")
                                return result["datalistOrderByOFP"]
                            else:
                                logger.warning(
                                    "vocs_result_dict_no_known_fields",
                                    station_name=station_name,
                                    result_keys=list(result.keys()),
                                    hint="result is dict but no known nested fields found"
                                )

                        # Case 3: result is a JSON string (rare case)
                        elif isinstance(result, str):
                            try:
                                import json
                                parsed_result = json.loads(result)
                                if isinstance(parsed_result, list):
                                    logger.info("vocs_data_fetched", station_name=station_name, data_points=len(parsed_result), source="result_json_string")
                                    return parsed_result
                            except:
                                pass

                    # Fallback: Try "results" field (old format)
                    results = data_dict.get("results", None)
                    if results is not None and isinstance(results, list):
                        extracted_data = []
                        for item in results:
                            if isinstance(item, dict) and "data" in item:
                                item_data = item["data"]
                                if isinstance(item_data, dict):
                                    # Check for nested "data" field (list)
                                    if "data" in item_data and isinstance(item_data["data"], list):
                                        extracted_data.extend(item_data["data"])
                                    # Check for "result" field (can be list or dict)
                                    elif "result" in item_data:
                                        result_field = item_data["result"]
                                        if isinstance(result_field, list):
                                            # Direct list: extend immediately
                                            extracted_data.extend(result_field)
                                        elif isinstance(result_field, dict):
                                            # Dict containing arrays: check common field names
                                            # Format: {"ofpresults": [...], "datalistOrderByOFP": [...], ...}
                                            if "ofpresults" in result_field and isinstance(result_field["ofpresults"], list):
                                                extracted_data.extend(result_field["ofpresults"])
                                            elif "hours" in result_field and isinstance(result_field["hours"], list):
                                                extracted_data.extend(result_field["hours"])
                                            elif "data" in result_field and isinstance(result_field["data"], list):
                                                extracted_data.extend(result_field["data"])
                                            elif "datalistOrderByOFP" in result_field and isinstance(result_field["datalistOrderByOFP"], list):
                                                extracted_data.extend(result_field["datalistOrderByOFP"])
                                            else:
                                                # Fallback: append the dict itself
                                                extracted_data.append(result_field)
                                    else:
                                        extracted_data.append(item_data)
                                elif isinstance(item_data, list):
                                    extracted_data.extend(item_data)

                        logger.info(
                            "vocs_data_fetched",
                            station_name=station_name,
                            results_count=len(results),
                            extracted_count=len(extracted_data),
                            source="results"
                        )
                        return extracted_data

                    logger.warning(
                        "vocs_data_no_expected_field",
                        station_name=station_name,
                        data_keys=list(data_dict.keys()),
                        expected_fields=["concurrent_results", "result", "results"]
                    )
                    return []

            # Fallback: response is already a list
            if isinstance(response, list):
                logger.info("vocs_data_fetched", station_name=station_name, data_points=len(response), source="direct_list")
                return response

            logger.warning("vocs_data_invalid_format", station_name=station_name, response_type=type(response).__name__)
            return []
        except Exception as e:
            logger.error(
                "vocs_data_failed",
                station_name=station_name,
                error=str(e),
            )
            return []

    async def get_particulate_component_data(
        self,
        station_name: str,
        start_time: str,
        end_time: str,
    ) -> List[Dict[str, Any]]:
        """
        Get particulate component reconstruction data for a specific station.

        Args:
            station_name: Station name (superstation/component station)
            start_time: Start time
            end_time: End time

        Returns:
            List of particulate component data
        """
        try:
            url = f"{self.particulate_url}/api/uqp/query"
            question = (
                f"查询{station_name}站点颗粒物组分重构数据，"
                f"时间周期为{start_time}至{end_time}，时间精度为小时"
            )
            json_data = {"question": question}
            response = await http_client.post(url, json_data=json_data)

            # Handle nested response format: {"data": {"result": [...]}} or {"data": {"results": [...]}}
            if isinstance(response, dict):
                if "data" in response and isinstance(response["data"], dict):
                    # Try both "result" and "results" keys
                    result = response["data"].get("result", None)
                    if result is None:
                        result = response["data"].get("results", [])
                    return result if isinstance(result, list) else []
            return response if isinstance(response, list) else []
        except Exception as e:
            logger.error(
                "particulate_data_failed",
                station_name=station_name,
                error=str(e),
            )
            return []


class MeteorologicalAPIClient:
    """Client for meteorological data API."""

    def __init__(self):
        self.base_url = settings.meteorological_api_url
        self.api_key = settings.meteorological_api_key

    async def get_weather_data(
        self,
        city_name: str,
        district_name: str,
        begin_time: str,
        end_time: str,
    ) -> List[Dict[str, Any]]:
        """
        Get meteorological data (wind speed, direction, temperature, etc.).

        Args:
            city_name: City name
            district_name: District/county name
            begin_time: Begin time (YYYY-MM-DD HH:MM:SS)
            end_time: End time (YYYY-MM-DD HH:MM:SS)

        Returns:
            List of weather data points
        """
        try:
            def _normalize_date(value: str) -> str:
                """Ensure the API receives dates in YYYY-MM-DD HH:MM:SS format."""
                if not isinstance(value, str):
                    return value
                value = value.strip()
                # Keep the full datetime format - API needs it to return all hourly data
                # If only date is provided, API returns only first hour (1 record instead of 24)
                return value

            params = {
                "beginTime": _normalize_date(begin_time),
                "endTime": _normalize_date(end_time),
                "directName": district_name,
                "cityName": city_name,
            }

            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Basic {self.api_key}"

            response = await http_client.get(
                self.base_url, params=params, headers=headers
            )

            # If district-level query returns empty, try city-level query
            if isinstance(response, list) and len(response) == 0 and district_name:
                logger.info(
                    "weather_data_district_empty_trying_city",
                    city=city_name,
                    district=district_name,
                )
                # Retry without district filter to get city-level data
                params_city = {
                    "beginTime": _normalize_date(begin_time),
                    "endTime": _normalize_date(end_time),
                    "cityName": city_name,
                    # Omit directName to get all available districts
                }
                response = await http_client.get(
                    self.base_url, params=params_city, headers=headers
                )
                if isinstance(response, list) and len(response) > 0:
                    logger.info(
                        "weather_data_city_level_success",
                        city=city_name,
                        districts_count=len(set(r.get("directName") for r in response)),
                        records_count=len(response),
                    )

            # Note: This API may only provide current/recent data, not historical data
            # If result is empty, it's expected for historical dates
            return response if isinstance(response, list) else []
        except Exception as e:
            logger.error(
                "weather_data_failed",
                city=city_name,
                district=district_name,
                error=str(e),
            )
            return []


class UpwindAnalysisAPIClient:
    """Client for upwind enterprise analysis API."""

    def __init__(self):
        self.base_url = settings.upwind_analysis_api_url

    async def analyze_upwind_enterprises(
        self,
        station_name: str,
        winds: List[WindData],
        search_range_km: float = 5.0,
        max_enterprises: int = 10,
        top_n: int = 10,
        map_type: str = "normal",
        mode: str = "topn_mixed",
    ) -> Dict[str, Any]:
        """
        Analyze upwind enterprises based on wind data.

        Args:
            station_name: Station name
            winds: List of wind data points
            search_range_km: Search range in kilometers
            max_enterprises: Maximum enterprises to analyze
            top_n: Top N enterprises to return
            map_type: Map type (normal/satellite)
            mode: Analysis mode (topn_mixed/all)

        Returns:
            Analysis result with public_url and enterprise list
        """
        try:
            url = f"{self.base_url}/api/external/wind/upwind-and-map"
            winds_data = [
                {"time": w.time, "wd_deg": w.wd_deg, "ws_ms": w.ws_ms}
                for w in winds
            ]
            json_data = {
                "station_name": station_name,
                "winds": winds_data,
                "search_range_km": search_range_km,
                "max_enterprises": max_enterprises,
                "map_type": map_type,
                "mode": mode,
                "top_n": top_n,
            }
            
            # Debug: Print first few wind data points
            import json as json_lib
            print(f"\n[UPWIND API] Preparing request to: {url}")
            print(f"Station: {station_name}")
            print(f"Winds count: {len(winds)}")
            print(f"First 3 winds data:")
            for i, w in enumerate(winds_data[:3]):
                print(f"  [{i}] {json_lib.dumps(w, ensure_ascii=False)}")
            print(f"Request parameters: search_range={search_range_km}km, max_enterprises={max_enterprises}, top_n={top_n}, mode={mode}")
            
            logger.info(
                "upwind_api_request",
                url=url,
                station=station_name,
                winds_count=len(winds),
                search_range=search_range_km,
                first_wind=winds_data[0] if winds_data else None,
            )
            
            response = await http_client.post(url, json_data=json_data)
            
            # Log response details
            if isinstance(response, dict):
                filtered_count = len(response.get("filtered", []))
                has_url = bool(response.get("public_url"))
                status = response.get("status", "unknown")
                
                logger.info(
                    "upwind_api_response",
                    station=station_name,
                    status=status,
                    filtered_count=filtered_count,
                    has_url=has_url,
                )
                
                # Warn if no enterprises found
                if filtered_count == 0:
                    logger.warning(
                        "upwind_no_enterprises",
                        station=station_name,
                        search_range=search_range_km,
                        message="No enterprises found in upwind direction",
                    )
            else:
                logger.warning(
                    "upwind_invalid_response_type",
                    station=station_name,
                    response_type=type(response).__name__,
                )
            
            return response
        except Exception as e:
            logger.error(
                "upwind_analysis_failed",
                station=station_name,
                error=str(e),
                error_type=type(e).__name__,
                url=f"{self.base_url}/api/external/wind/upwind-and-map",
            )
            return {}


# Global client instances
station_api = StationAPIClient()
monitoring_api = MonitoringDataAPIClient()
weather_api = MeteorologicalAPIClient()
upwind_api = UpwindAnalysisAPIClient()
