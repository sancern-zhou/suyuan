"""
广东省生态环境厅 Suncere API 客户端

基于 Vanna 项目实现的广东省空气质量数据查询 API 客户端
支持 token 认证、自动刷新和多种查询接口
"""
import requests
import base64
import time
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from functools import lru_cache

logger = structlog.get_logger()


class GDSuncereAPIClient:
    """
    广东省 Suncere API 客户端

    提供广东省空气质量数据的查询功能，包括：
    - Token 认证和自动刷新
    - 城市日报数据查询
    - 站点小时数据查询
    - 综合统计报表查询
    """

    # API 配置
    BASE_URL = "http://113.108.142.147:20161"
    TOKEN_ENDPOINT = "/api/airprovinceproduct/AirCityBaseCommon/GetExternalApiToken"

    # 认证凭据
    USERNAME = "ScGuanLy"
    PASSWORD = "Suncere$0717"

    # Token 缓存配置
    TOKEN_CACHE_DURATION = 1800  # 30分钟

    def __init__(self):
        """初始化 API 客户端"""
        self._token = None
        self._token_expires_at = None
        self._session = requests.Session()

        logger.info(
            "gd_suncere_api_client_initialized",
            base_url=self.BASE_URL,
            token_cache_duration=self.TOKEN_CACHE_DURATION
        )

    def get_token(self, force_refresh: bool = False) -> str:
        """
        获取访问令牌（自动缓存和刷新）

        参考 Vanna 项目实现：
        - 使用 GET 请求
        - 参数通过查询字符串传递 (UserName, Pwd)
        - 需要 SysCode header

        Args:
            force_refresh: 是否强制刷新 token

        Returns:
            访问令牌字符串
        """
        # 检查是否需要刷新 token
        if not force_refresh and self._token is not None:
            if self._token_expires_at and time.time() < self._token_expires_at:
                logger.debug(
                    "using_cached_token",
                    expires_in=int(self._token_expires_at - time.time())
                )
                return self._token

        # 获取新 token
        logger.info("refreshing_api_token")

        try:
            auth_url = f"{self.BASE_URL}{self.TOKEN_ENDPOINT}"

            # 使用 GET 请求 + 查询参数（参考 Vanna 实现）
            headers = {
                "SysCode": "SunAirProvince",
                "syscode": "SunAirProvince"
            }

            params = {
                "UserName": self.USERNAME,
                "Pwd": self.PASSWORD
            }

            logger.debug(
                "token_request",
                url=auth_url,
                method="GET",
                username=self.USERNAME
            )

            # 首选 GET 方式（依据 Vanna 文档）
            response = requests.get(
                auth_url,
                params=params,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                # Vanna API 返回格式: {"success": true, "result": "token_string"}
                if data and data.get("success") and data.get("result"):
                    token = data["result"]
                    self._token = token
                    self._token_expires_at = time.time() + self.TOKEN_CACHE_DURATION

                    logger.info(
                        "token_refreshed_success",
                        token_length=len(token),
                        expires_in=self.TOKEN_CACHE_DURATION
                    )
                    return token
                else:
                    logger.warning(
                        "token_get_failed_invalid_response",
                        response_data=data
                    )
            else:
                logger.warning(
                    "token_get_http_error",
                    status_code=response.status_code,
                    response_text=response.text[:500]
                )

            # 退回 POST form 方式（部分部署可能只接受 POST）
            logger.debug("token_fallback_to_post")
            response2 = requests.post(
                auth_url,
                data=params,  # form data
                headers=headers,
                timeout=10
            )

            if response2.status_code == 200:
                data2 = response2.json()
                if data2 and data2.get("success") and data2.get("result"):
                    token = data2["result"]
                    self._token = token
                    self._token_expires_at = time.time() + self.TOKEN_CACHE_DURATION

                    logger.info(
                        "token_refreshed_success_via_post",
                        token_length=len(token)
                    )
                    return token
                else:
                    logger.warning(
                        "token_post_failed_invalid_response",
                        response_data=data2
                    )
            else:
                logger.warning(
                    "token_post_http_error",
                    status_code=response2.status_code
                )

            raise Exception("Token 获取失败（GET 和 POST 均失败）")

        except Exception as e:
            logger.error(
                "token_refresh_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    def _make_request(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        method: str = "POST",
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        发起 API 请求

        Args:
            endpoint: API 端点路径
            payload: 请求参数
            method: HTTP 方法 (POST/GET)
            timeout: 超时时间（秒）

        Returns:
            API 响应数据
        """
        # 获取 token
        token = self.get_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "SysCode": "SunAirProvince",
            "syscode": "SunAirProvince",
            "Content-Type": "application/json"
        }

        url = f"{self.BASE_URL}{endpoint}"

        logger.info(
            "api_request_start",
            endpoint=endpoint,
            method=method,
            timeout=timeout
        )

        try:
            if method.upper() == "POST":
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )
            else:
                response = requests.get(
                    url,
                    headers=headers,
                    params=payload,
                    timeout=timeout
                )

            logger.info(
                "api_request_complete",
                endpoint=endpoint,
                status_code=response.status_code
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                # Token 可能过期，强制刷新后重试
                logger.warning("token_expired_refreshing")
                token = self.get_token(force_refresh=True)
                headers["Authorization"] = f"Bearer {token}"

                if method.upper() == "POST":
                    response = requests.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=timeout
                    )
                else:
                    response = requests.get(
                        url,
                        headers=headers,
                        params=payload,
                        timeout=timeout
                    )

                if response.status_code == 200:
                    return response.json()
                else:
                    raise Exception(f"API 请求失败（刷新 token 后）: {response.status_code}")
            else:
                raise Exception(f"API 请求失败: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            logger.error("api_request_timeout", endpoint=endpoint, timeout=timeout)
            raise Exception(f"API 请求超时: {endpoint}")
        except Exception as e:
            logger.error(
                "api_request_error",
                endpoint=endpoint,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    def query_city_day_data(
        self,
        city_codes: List[str],
        start_date: str,
        end_date: str,
        data_type: int = 0
    ) -> Dict[str, Any]:
        """
        查询城市日报数据

        API 文档参考：https://server/api/airprovinceproduct/airdata/DATCityDay/GetDATCityDayDisplayListAsync
        请求方式：GET
        参数：
          - codes: 城市代码数组（可重复传多个）
          - timePoint: 时间数组，格式 ["YYYY-MM-DD 00:00:00", "YYYY-MM-DD 23:59:59"]
          - dataType: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况）

        Args:
            city_codes: 城市代码列表（如 ["440100", "440300"] 表示广州、深圳）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            data_type: 数据类型，默认 0（原始实况）

        Returns:
            城市日报数据
        """
        endpoint = "/api/airprovinceproduct/airdata/DATCityDay/GetDATCityDayDisplayListAsync"

        # GET 请求：参数通过查询字符串传递
        params = {
            "codes": city_codes,  # 数组参数会被 requests 展开为 ?codes=x&codes=y
            "timePoint": [
                f"{start_date} 00:00:00",
                f"{end_date} 23:59:59"
            ],
            "dataType": data_type
        }

        logger.info(
            "query_city_day_data",
            city_codes=city_codes,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type
        )

        return self._make_request(endpoint, params, method="GET")

    def query_city_hour_data(
        self,
        city_codes: List[str],
        start_time: str,
        end_time: str,
        data_type: int = 0
    ) -> Dict[str, Any]:
        """
        查询城市小时数据

        API 文档参考：
        https://server/api/airprovinceproduct/airdata/DATCityHour/GetDATCityHourDisplayListAsync

        请求方式：GET
        查询参数：
          - codes: 城市代码数组（可重复）
          - timePoint: 时间数组，格式 ["YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM:SS"]
          - dataType: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况）

        Args:
            city_codes: 城市代码列表（如 ["440100", "440300"] 表示广州、深圳）
            start_time: 开始时间 (YYYY-MM-DD HH:MM:SS)
            end_time: 结束时间 (YYYY-MM-DD HH:MM:SS)
            data_type: 数据类型，默认 0（原始实况）

        Returns:
            城市小时数据
        """
        endpoint = "/api/airprovinceproduct/airdata/DATCityHour/GetDATCityHourDisplayListAsync"

        # GET 请求：参数通过查询字符串传递
        params = {
            "codes": city_codes,
            "timePoint": [
                start_time,
                end_time
            ],
            "dataType": data_type
        }

        logger.info(
            "query_city_hour_data",
            city_codes=city_codes,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type
        )

        return self._make_request(endpoint, params, method="GET")

    def query_station_hour_data(
        self,
        station_codes: List[str],
        start_time: str,
        end_time: str,
        data_type: int = 0
    ) -> Dict[str, Any]:
        """
        查询站点小时数据

        API 文档参考：
        https://server/api/airprovinceproduct/airdata/DATStationHour/GetDATStationHourDisplayListAsync

        请求方式：POST
        Body 参数：
          - codes: 站点代码数组，如 ["1001A", "1002A"]
          - timePoint: 时间数组，格式 ["YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM:SS"]
          - dataType: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况）

        Args:
            station_codes: 站点代码列表（如 ["1001A", "1002A"]）
            start_time: 开始时间 (YYYY-MM-DD HH:MM:SS)
            end_time: 结束时间 (YYYY-MM-DD HH:MM:SS)
            data_type: 数据类型，默认 0（原始实况）

        Returns:
            站点小时数据
        """
        endpoint = "/api/airprovinceproduct/airdata/DATStationHour/GetDATStationHourDisplayListAsync"

        # POST 请求：参数通过 JSON body 传递
        payload = {
            "codes": station_codes,
            "timePoint": [
                start_time,
                end_time
            ],
            "dataType": data_type
        }

        logger.info(
            "query_station_hour_data",
            station_codes=station_codes,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type
        )

        return self._make_request(endpoint, payload, method="POST")

    def query_station_day_data(
        self,
        station_codes: List[str],
        start_date: str,
        end_date: str,
        data_type: int = 0
    ) -> Dict[str, Any]:
        """
        查询站点日报数据

        API 文档参考：
        https://server/api/airprovinceproduct/airdata/DATStationDay/GetDATStationDayDisplayListAsync

        请求方式：POST
        Body 参数：
          - codes: 站点代码数组，如 ["1001A", "1002A"]
          - timePoint: 时间数组，格式 ["YYYY-MM-DD 00:00:00", "YYYY-MM-DD 23:59:59"]
          - dataType: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况）

        Args:
            station_codes: 站点代码列表（如 ["1001A", "1002A"]）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            data_type: 数据类型，默认 0（原始实况）

        Returns:
            站点日报数据
        """
        endpoint = "/api/airprovinceproduct/airdata/DATStationDay/GetDATStationDayDisplayListAsync"

        # POST 请求：参数通过 JSON body 传递
        payload = {
            "codes": station_codes,
            "timePoint": [
                f"{start_date} 00:00:00",
                f"{end_date} 23:59:59"
            ],
            "dataType": data_type
        }

        logger.info(
            "query_station_day_data",
            station_codes=station_codes,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type
        )

        return self._make_request(endpoint, payload, method="POST")

    def query_report_data(
        self,
        city_codes: List[str],
        start_time: str,
        end_time: str,
        pollutant_codes: Optional[List[str]] = None,
        data_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        综合统计报表查询

        Args:
            city_codes: 城市代码列表
            start_time: 开始时间
            end_time: 结束时间
            pollutant_codes: 污染物代码列表
            data_types: 数据类型列表 (hour, day, month)

        Returns:
            统计报表数据
        """
        endpoint = "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangeListFilterAsync"

        if pollutant_codes is None:
            pollutant_codes = ["PM2.5", "PM10", "SO2", "NO2", "O3", "CO"]

        if data_types is None:
            data_types = ["hour"]

        payload = {
            "request_params": {
                "dataSource": "all",
                "startTime": start_time,
                "endTime": end_time,
                "cityCodes": city_codes,
                "pollutantCodes": pollutant_codes,
                "dataTypes": data_types
            }
        }

        logger.info(
            "query_report_data",
            city_codes=city_codes,
            start_time=start_time,
            end_time=end_time,
            pollutant_codes=pollutant_codes,
            data_types=data_types
        )

        return self._make_request(endpoint, payload, method="POST")

    def query_city_day_old_standard(
        self,
        city_codes: List[str],
        start_time: str,
        end_time: str,
        plan_type: int = 0,
        time_type: int = 8,
        area_type: int = 2,
        pollutant_codes: Optional[List[str]] = None,
        revise_type: int = 0,
        data_source: int = 1,
        sand_type: int = 0,
        skip_count: int = 0,
        max_result_count: int = 40
    ) -> Dict[str, Any]:
        """
        查询城市日数据（旧标准：十三五/十四五）

        综合统计报表接口，支持十三五和十四五两种数据类型。

        Args:
            city_codes: 城市代码列表
            start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
            end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"
            plan_type: 规划类型（0=十四五, 135=十三五）
            time_type: 时间类型（8=任意时间, 3=周报, 4=月报, 5=季报, 7=年报）
            area_type: 区域类型（2=城市, 1=区县, 0=站点）
            pollutant_codes: 污染物代码列表（如 ["so2", "no2", "pm2.5"]）
            revise_type: 修订类型（0=不扣沙）
            data_source: 数据源类型（1=审核实况, 0=原始实况）
            sand_type: 扣沙类型（0=不扣沙）
            skip_count: 分页跳过数
            max_result_count: 每页结果数

        Returns:
            API 响应数据
        """
        endpoint = "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangeListFilterAsync"

        # 默认污染物代码（如果未指定）
        if pollutant_codes is None:
            pollutant_codes = ["so2", "no2", "pm2_5", "pm10", "co", "o3"]

        # 根据网页端请求格式构造 payload
        payload = {
            "skipCount": skip_count,
            "maxResultCount": max_result_count,
            "TimeType": time_type,
            "AreaType": area_type,
            "PollutantCode": pollutant_codes,
            "ReviseType": revise_type,
            "TimePoint": [start_time, end_time],
            "dataSource": data_source,
            "planType": plan_type,
            "sandType": sand_type,
            "codes": city_codes
        }

        logger.info(
            "query_city_day_old_standard",
            city_codes=city_codes,
            start_time=start_time,
            end_time=end_time,
            plan_type=plan_type,
            time_type=time_type,
            area_type=area_type,
            pollutant_codes=pollutant_codes
        )

        return self._make_request(endpoint, payload, method="POST")


# 全局单例
_api_client_instance: Optional[GDSuncereAPIClient] = None


def get_gd_suncere_api_client() -> GDSuncereAPIClient:
    """获取全局 API 客户端实例"""
    global _api_client_instance
    if _api_client_instance is None:
        _api_client_instance = GDSuncereAPIClient()
    return _api_client_instance
