"""
全国省份空气质量数据查询工具

从参考项目 GDQFWS_SYS 获取全国各省份的六参数均值、AQI达标率和综合指数
"""
import requests
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger()


class NationalAirQualityQueryTool:
    """
    全国省份空气质量数据查询工具

    功能：
    1. 从数据库获取有效的API Token
    2. 调用参考项目的接口获取全国省份数据
    3. 支持省份和城市两种查询级别
    4. 自动处理数据格式转换
    """

    # 参考项目配置
    BASE_URL = "http://113.108.142.147:20032"

    # Token 环境变量名称
    TOKEN_ENV_VAR = "GDQFWS_API_TOKEN"

    def __init__(self):
        pass

    def get_token(self) -> str:
        """
        从环境变量获取API Token

        Returns:
            API Token字符串

        Raises:
            Exception: 如果环境变量未设置
        """
        token = os.getenv(self.TOKEN_ENV_VAR)
        if not token:
            raise Exception(
                f"环境变量 {self.TOKEN_ENV_VAR} 未设置。"
                f"请设置: export {self.TOKEN_ENV_VAR}='your_token_here'"
            )

        return token

    def query_province_data(
        self,
        start_date: str,
        end_date: str,
        ns_type: str = "NS"
    ) -> List[Dict[str, Any]]:
        """
        查询全国省份空气质量数据

        Args:
            start_date: 开始日期，格式 YYYY-MM-DD
            end_date: 结束日期，格式 YYYY-MM-DD
            ns_type: 数据类型，NS=非实时，NSDay=非实时日均值

        Returns:
            省份空气质量数据列表，每个元素包含：
            - AreaCode: 省份代码
            - AreaName: 省份名称
            - SO2: SO2均值(μg/m³)
            - NO2: NO2均值(μg/m³)
            - CO: CO均值(mg/m³)
            - O3_8h: O3_8h均值(μg/m³)
            - PM10: PM10均值(μg/m³)
            - PM2_5: PM2.5均值(μg/m³)
            - SumIndex: 综合指数
            - AQIStandardRate: AQI达标率(%)
        """
        token = self.get_token()
        if not token:
            raise Exception("无法获取API Token")

        url = f"{self.BASE_URL}/api/GDDataApi/GetCityAirQualityData"

        params = {
            "token": token,
            "startTime": start_date,
            "endTime": end_date,
            "areaType": 2,  # 2=省份
            "nsType": ns_type
        }

        logger.info(
            "querying_province_data",
            start_date=start_date,
            end_date=end_date,
            url=url
        )

        try:
            response = requests.get(url, params=params, timeout=30)
            result = response.json()

            if result.get("Status") or result.get("status"):
                data = result.get("Data") or result.get("data")
                if data:
                    data_list = json.loads(data) if isinstance(data, str) else data
                    logger.info("province_data_retrieved", count=len(data_list))
                    return data_list

            error_msg = result.get("Message", result.get("message", "Unknown error"))
            logger.error("api_request_failed", error=error_msg)
            raise Exception(f"接口请求失败: {error_msg}")

        except requests.exceptions.Timeout:
            logger.error("api_request_timeout")
            raise Exception("API请求超时")
        except Exception as e:
            logger.error("query_province_data_failed", error=str(e))
            raise

    def query_city_data(
        self,
        start_date: str,
        end_date: str,
        province_code: Optional[str] = None,
        ns_type: str = "NS"
    ) -> List[Dict[str, Any]]:
        """
        查询全国城市空气质量数据

        Args:
            start_date: 开始日期，格式 YYYY-MM-DD
            end_date: 结束日期，格式 YYYY-MM-DD
            province_code: 省份代码（可选，用于筛选特定省份的城市）
            ns_type: 数据类型

        Returns:
            城市空气质量数据列表
        """
        token = self.get_token()
        if not token:
            raise Exception("无法获取API Token")

        url = f"{self.BASE_URL}/api/GDDataApi/GetCityAirQualityData"

        params = {
            "token": token,
            "startTime": start_date,
            "endTime": end_date,
            "areaType": 1,  # 1=城市
            "nsType": ns_type
        }

        logger.info(
            "querying_city_data",
            start_date=start_date,
            end_date=end_date,
            province_code=province_code
        )

        try:
            response = requests.get(url, params=params, timeout=30)
            result = response.json()

            if result.get("Status") or result.get("status"):
                data = result.get("Data") or result.get("data")
                if data:
                    data_list = json.loads(data) if isinstance(data, str) else data

                    # 如果指定了省份代码，进行筛选
                    if province_code:
                        data_list = [
                            item for item in data_list
                            if str(item.get('AreaCode', ''))[:2] == str(province_code)[:2]
                        ]

                    logger.info("city_data_retrieved", count=len(data_list))
                    return data_list

            error_msg = result.get("Message", result.get("message", "Unknown error"))
            logger.error("api_request_failed", error=error_msg)
            raise Exception(f"接口请求失败: {error_msg}")

        except Exception as e:
            logger.error("query_city_data_failed", error=str(e))
            raise


# 全局单例
_query_tool_instance: Optional[NationalAirQualityQueryTool] = None


def get_national_air_quality_tool() -> NationalAirQualityQueryTool:
    """获取全局工具实例"""
    global _query_tool_instance
    if _query_tool_instance is None:
        _query_tool_instance = NationalAirQualityQueryTool()
    return _query_tool_instance


# 便捷函数
def query_province_air_quality(
    start_date: str,
    end_date: str,
    ns_type: str = "NS"
) -> List[Dict[str, Any]]:
    """
    查询全国省份空气质量数据（便捷函数）

    Args:
        start_date: 开始日期，格式 YYYY-MM-DD
        end_date: 结束日期，格式 YYYY-MM-DD
        ns_type: 数据类型

    Returns:
        省份空气质量数据列表

    Example:
        >>> data = query_province_air_quality("2024-01-01", "2024-01-31")
        >>> for item in data:
        ...     print(f"{item['AreaName']}: PM2.5={item['PM2_5']}, 综合指数={item['SumIndex']}")
    """
    tool = get_national_air_quality_tool()
    return tool.query_province_data(start_date, end_date, ns_type)


def query_city_air_quality(
    start_date: str,
    end_date: str,
    province_code: Optional[str] = None,
    ns_type: str = "NS"
) -> List[Dict[str, Any]]:
    """
    查询城市空气质量数据（便捷函数）

    Args:
        start_date: 开始日期，格式 YYYY-MM-DD
        end_date: 结束日期，格式 YYYY-MM-DD
        province_code: 省份代码（可选）
        ns_type: 数据类型

    Returns:
        城市空气质量数据列表

    Example:
        >>> data = query_city_air_quality("2024-01-01", "2024-01-31", province_code="440000")
        >>> for item in data:
        ...     print(f"{item['AreaName']}: PM2.5={item['PM2_5']}")
    """
    tool = get_national_air_quality_tool()
    return tool.query_city_data(start_date, end_date, province_code, ns_type)
