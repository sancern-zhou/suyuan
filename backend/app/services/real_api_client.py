"""
真实API客户端 - 集成外部数据源
"""
import aiohttp
import asyncio
import os
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger()


class RealAPIClient:
    """真实API客户端 - 连接180.184.91.74数据源"""

    def __init__(self):
        self.base_urls = {
            "monitoring": os.getenv("MONITORING_DATA_API_URL", "http://180.184.91.74:9091"),
            "vocs": os.getenv("VOCS_DATA_API_URL", "http://180.184.91.74:9092"),
            "particulate": os.getenv("PARTICULATE_DATA_API_URL", "http://180.184.91.74:9093"),
            "station": os.getenv("STATION_API_BASE_URL", "http://180.184.91.74:9095"),
        }
        self.timeout = aiohttp.ClientTimeout(total=30)

    async def query_air_quality(
        self,
        question: str,
        time_range: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        查询空气质量数据

        Args:
            question: 自然语言查询问题
            time_range: 时间范围

        Returns:
            Dict[str, Any]: 查询结果
        """
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # 构建请求参数
                params = {
                    "question": question,
                    "start_date": time_range.get("start", ""),
                    "end_date": time_range.get("end", ""),
                }

                # 调用监测数据API
                async with session.get(
                    f"{self.base_urls['monitoring']}/query",
                    params=params
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result
                    else:
                        logger.error(f"API request failed with status {response.status}")
                        return {"status": "error", "message": f"HTTP {response.status}"}

        except asyncio.TimeoutError:
            logger.error("API request timeout")
            return {"status": "error", "message": "Request timeout"}
        except Exception as e:
            logger.error(f"API request error: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def query_province_overview(
        self,
        time_range: Dict[str, str]
    ) -> Dict[str, Any]:
        """查询省级概览数据"""
        question = f"查询广东省{time_range.get('start', '')}至{time_range.get('end', '')}空气质量概况，包括AQI达标率、PM2.5浓度、O3浓度及同比变化"
        return await self.query_air_quality(question, time_range)

    async def query_city_ranking(
        self,
        time_range: Dict[str, str]
    ) -> Dict[str, Any]:
        """查询城市排名数据"""
        question = f"查询广东省{time_range.get('start', '')}至{time_range.get('end', '')}空气质量排名，包括综合指数、PM2.5、O3排名前5和后5的城市"
        return await self.query_air_quality(question, time_range)

    async def query_city_detail_table(
        self,
        time_range: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """查询城市详细数据表"""
        question = f"查询广东省21个地市{time_range.get('start', '')}至{time_range.get('end', '')}空气质量详细数据，包括AQI达标率、PM2.5、O3、综合指数及同比"
        result = await self.query_air_quality(question, time_range)

        # 如果返回的是列表，直接返回；否则尝试解析
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and "data" in result:
            return result["data"]
        else:
            return []

    async def query_district_ranking(
        self,
        time_range: Dict[str, str]
    ) -> Dict[str, Any]:
        """查询区县排名数据"""
        question = f"查询广东省{time_range.get('start', '')}至{time_range.get('end', '')}区县空气质量排名前20和后20"
        return await self.query_air_quality(question, time_range)

    async def query_monthly_comparison(
        self,
        month: int,
        time_range: Dict[str, str]
    ) -> Dict[str, Any]:
        """查询单月对比数据"""
        question = f"查询广东省2025年{month}月空气质量数据及同比变化"
        return await self.query_air_quality(question, time_range)


# 全局API客户端实例
api_client = RealAPIClient()
