"""
广东省气象局API客户端

提供气象数据查询功能，用于污染玫瑰图生成
"""
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()


class GDMetBureauAPIClient:
    """广东省气象局API客户端"""

    BASE_URL = "http://180.184.30.94"

    @classmethod
    def query_weather(
        cls,
        city_name: str,
        begin_time: str,
        end_time: str,
        district_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        查询气象数据

        Args:
            city_name: 城市名称（如"广州"）
            begin_time: 开始时间（格式："2025-01-01"）
            end_time: 结束时间（格式："2025-01-02"）
            district_name: 区县名称（可选，如"天河"）

        Returns:
            气象数据列表，每条记录包含：
            - timePoint: 时间
            - stationCode: 站点编码
            - windDirection: 风向（度）
            - windSpeed: 风速（m/s）
            - temperature: 气温（℃）
            - relativeHumidity: 相对湿度（%）
            - pressure: 气压（hPa）
            - precipitation1h: 1小时降水量（mm）
            - visibility: 能见度（m）
            - cityName: 城市名称
            - directName: 区县名称
        """
        url = f"{cls.BASE_URL}/api/AiDataService/ReportApplication/UserReportDataQuery/Query"

        params = {
            "beginTime": begin_time,
            "endTime": end_time,
            "cityName": city_name
        }

        if district_name:
            params["directName"] = district_name

        try:
            logger.info(
                "gd_met_bureau_query_start",
                url=url,
                params=params
            )

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            if not isinstance(data, list):
                logger.warning(
                    "gd_met_bureau_invalid_response_type",
                    expected_type="list",
                    actual_type=type(data).__name__
                )
                return []

            logger.info(
                "gd_met_bureau_query_success",
                record_count=len(data),
                time_range=f"{begin_time} ~ {end_time}",
                city=city_name,
                district=district_name or "全市"
            )

            return data

        except requests.exceptions.Timeout:
            logger.error(
                "gd_met_bureau_query_timeout",
                url=url,
                timeout=30
            )
            return []

        except requests.exceptions.RequestException as e:
            logger.error(
                "gd_met_bureau_query_failed",
                error=str(e),
                url=url
            )
            return []

        except Exception as e:
            logger.error(
                "gd_met_bureau_query_unexpected_error",
                error=str(e),
                exc_info=True
            )
            return []

    @classmethod
    def query_weather_by_station(
        cls,
        station_code: str,
        city_name: str,
        begin_time: str,
        end_time: str
    ) -> List[Dict[str, Any]]:
        """
        按站点编码查询气象数据

        注意：气象局API可能不支持精确的站点编码过滤，
        此方法先查询城市/区县数据，然后在结果中筛选站点编码

        Args:
            station_code: 站点编码
            city_name: 城市名称
            begin_time: 开始时间
            end_time: 结束时间

        Returns:
            该站点的气象数据列表
        """
        # 先查询全市数据
        all_data = cls.query_weather(
            city_name=city_name,
            begin_time=begin_time,
            end_time=end_time
        )

        # 筛选该站点的数据
        station_data = [
            record for record in all_data
            if record.get('stationCode') == station_code
        ]

        logger.info(
            "gd_met_bureau_station_filter",
            station_code=station_code,
            total_count=len(all_data),
            station_count=len(station_data)
        )

        return station_data
