"""
Get Fire Hotspots Tool

LLM可调用的火点数据查询工具

功能：
- 查询指定区域和时间范围内的火点数据
- 用于识别生物质燃烧污染源
- 支持按置信度过滤
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.db.repositories.satellite_repo import SatelliteRepository

logger = structlog.get_logger()


class GetFireHotspotsTool(LLMTool):
    """
    火点数据查询工具

    给LLM提供查询火点数据的能力
    用于分析生物质燃烧是否为污染源
    """

    def __init__(self):
        function_schema = {
            "name": "get_fire_hotspots",
            "description": "查询指定区域和时间范围内的火点数据，用于识别生物质燃烧污染源。数据来源：NASA FIRMS卫星监测（VIIRS 375m分辨率）",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "object",
                        "properties": {
                            "min_lat": {
                                "type": "number",
                                "description": "最小纬度"
                            },
                            "max_lat": {
                                "type": "number",
                                "description": "最大纬度"
                            },
                            "min_lon": {
                                "type": "number",
                                "description": "最小经度"
                            },
                            "max_lon": {
                                "type": "number",
                                "description": "最大经度"
                            }
                        },
                        "required": ["min_lat", "max_lat", "min_lon", "max_lon"],
                        "description": "查询区域范围（矩形边界）"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间（ISO8601格式，如'2025-10-20T00:00:00'）"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间（ISO8601格式，如'2025-10-20T23:59:59'）"
                    },
                    "min_confidence": {
                        "type": "integer",
                        "description": "最小置信度阈值（0-100），默认70。建议：低=50，中=70，高=90",
                        "default": 70,
                        "minimum": 0,
                        "maximum": 100
                    }
                },
                "required": ["region", "start_time", "end_time"]
            }
        }

        super().__init__(
            name="get_fire_hotspots",
            description="Get fire hotspot data from NASA FIRMS",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        self.repo = SatelliteRepository()

    async def execute(
        self,
        region: Dict[str, float],
        start_time: str,
        end_time: str,
        min_confidence: int = 70,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行火点数据查询

        Args:
            region: 查询区域 {min_lat, max_lat, min_lon, max_lon}
            start_time: 开始时间（ISO8601格式）
            end_time: 结束时间（ISO8601格式）
            min_confidence: 最小置信度

        Returns:
            Dict: 火点数据，包含：
                - success: 是否成功
                - count: 火点数量
                - hotspots: 火点列表
                - statistics: 统计信息
                - metadata: 查询元数据
        """
        try:
            # 验证输入参数
            self._validate_inputs(region, start_time, end_time, min_confidence)

            # 解析时间
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))

            logger.info(
                "fire_hotspots_query_started",
                region=region,
                start_time=start_time,
                end_time=end_time,
                min_confidence=min_confidence
            )

            # 查询火点数据
            hotspots = await self.repo.get_fire_hotspots(
                min_lat=region['min_lat'],
                max_lat=region['max_lat'],
                min_lon=region['min_lon'],
                max_lon=region['max_lon'],
                start_time=start_dt,
                end_time=end_dt,
                min_confidence=min_confidence
            )

            # 格式化结果
            result = self._format_fire_hotspots(
                hotspots=hotspots,
                region=region,
                start_time=start_time,
                end_time=end_time,
                min_confidence=min_confidence
            )

            logger.info(
                "fire_hotspots_query_successful",
                count=len(hotspots),
                region=region,
                time_range=(start_time, end_time)
            )

            return result

        except Exception as e:
            logger.error(
                "fire_hotspots_query_failed",
                region=region,
                start_time=start_time,
                end_time=end_time,
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": str(e),
                "count": 0,
                "hotspots": [],
                "metadata": {
                    "query_region": region,
                    "time_range": [start_time, end_time],
                    "confidence_threshold": min_confidence
                }
            }

    def _validate_inputs(
        self,
        region: Dict[str, float],
        start_time: str,
        end_time: str,
        min_confidence: int
    ):
        """
        验证输入参数

        Args:
            region: 区域范围
            start_time: 开始时间
            end_time: 结束时间
            min_confidence: 最小置信度

        Raises:
            ValueError: 参数验证失败
        """
        # 验证区域范围
        if not all(k in region for k in ['min_lat', 'max_lat', 'min_lon', 'max_lon']):
            raise ValueError("Region must contain min_lat, max_lat, min_lon, max_lon")

        if region['min_lat'] >= region['max_lat']:
            raise ValueError("min_lat must be less than max_lat")

        if region['min_lon'] >= region['max_lon']:
            raise ValueError("min_lon must be less than max_lon")

        # 验证纬度范围
        if not (-90 <= region['min_lat'] <= 90 and -90 <= region['max_lat'] <= 90):
            raise ValueError("Latitude must be between -90 and 90")

        # 验证经度范围
        if not (-180 <= region['min_lon'] <= 180 and -180 <= region['max_lon'] <= 180):
            raise ValueError("Longitude must be between -180 and 180")

        # 验证置信度
        if not (0 <= min_confidence <= 100):
            raise ValueError("Confidence must be between 0 and 100")

        # 验证时间格式
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))

            if start_dt >= end_dt:
                raise ValueError("start_time must be before end_time")

        except ValueError as e:
            raise ValueError(f"Invalid time format: {e}")

    def _format_fire_hotspots(
        self,
        hotspots: List,
        region: Dict[str, float],
        start_time: str,
        end_time: str,
        min_confidence: int
    ) -> Dict[str, Any]:
        """
        格式化火点数据

        Args:
            hotspots: 火点数据列表
            region: 查询区域
            start_time: 开始时间
            end_time: 结束时间
            min_confidence: 最小置信度

        Returns:
            Dict: 格式化后的火点数据
        """
        # 计算统计信息
        total_frp = sum(h.frp for h in hotspots if h.frp is not None)
        avg_confidence = (
            sum(h.confidence for h in hotspots if h.confidence is not None) / len(hotspots)
            if hotspots else 0
        )

        # 格式化火点列表
        formatted_hotspots = [
            {
                "lat": h.lat,
                "lon": h.lon,
                "frp": h.frp,
                "confidence": h.confidence,
                "brightness": h.brightness,
                "acquisition_time": h.acq_datetime.isoformat(),
                "satellite": h.satellite,
                "day_night": h.daynight
            }
            for h in hotspots
        ]

        return {
            "success": True,
            "count": len(hotspots),
            "hotspots": formatted_hotspots,
            "statistics": {
                "total_count": len(hotspots),
                "total_frp_mw": round(total_frp, 2),
                "avg_confidence": round(avg_confidence, 1),
                "day_fires": sum(1 for h in hotspots if h.daynight == 'D'),
                "night_fires": sum(1 for h in hotspots if h.daynight == 'N')
            },
            "metadata": {
                "query_region": region,
                "time_range": [start_time, end_time],
                "confidence_threshold": min_confidence,
                "data_source": "NASA FIRMS (VIIRS 375m)",
                "queried_at": datetime.now().isoformat()
            }
        }


# 导出
__all__ = ["GetFireHotspotsTool"]
