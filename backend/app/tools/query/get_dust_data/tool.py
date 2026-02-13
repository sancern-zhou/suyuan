"""
Get Dust Data Tool

LLM查询工具 - 查询沙尘预报数据，用于判断污染是否受沙尘传输影响
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.db.repositories.dust_repo import DustRepository

logger = structlog.get_logger()


class GetDustDataTool(LLMTool):
    """
    沙尘数据查询工具

    功能：
    - 查询指定区域和时间范围内的沙尘预报数据
    - 识别沙尘传输事件
    - 分析沙尘对空气质量的潜在影响

    数据来源: CAMS (Copernicus Atmosphere Monitoring Service)
    分辨率: 0.4° × 0.4° (约40km)
    预报范围: 5天（120小时）
    """

    def __init__(self):
        # Function Calling Schema
        function_schema = {
            "name": "get_dust_data",
            "description": (
                "查询指定区域和时间范围内的沙尘气溶胶预报数据，用于判断空气污染是否受沙尘传输影响。"
                "返回沙尘AOD（气溶胶光学厚度）、PM10浓度预报、沙尘事件信息等。"
                "适用于分析北方沙尘暴、戈壁沙尘传输等自然源污染事件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "object",
                        "description": "查询区域的边界框（经纬度范围）",
                        "properties": {
                            "min_lat": {
                                "type": "number",
                                "description": "最小纬度（南边界），中国范围: 15-55°N"
                            },
                            "max_lat": {
                                "type": "number",
                                "description": "最大纬度（北边界），中国范围: 15-55°N"
                            },
                            "min_lon": {
                                "type": "number",
                                "description": "最小经度（西边界），中国范围: 70-140°E"
                            },
                            "max_lon": {
                                "type": "number",
                                "description": "最大经度（东边界），中国范围: 70-140°E"
                            }
                        },
                        "required": ["min_lat", "max_lat", "min_lon", "max_lon"]
                    },
                    "start_time": {
                        "type": "string",
                        "description": "查询开始时间（ISO8601格式，如 2025-10-20T00:00:00）"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "查询结束时间（ISO8601格式，如 2025-10-20T23:59:59）"
                    },
                    "min_dust_aod": {
                        "type": "number",
                        "description": "最小沙尘AOD阈值，默认0.2。高于此值视为有沙尘影响。参考：0.2=轻微影响, 0.5=中度影响, 1.0=严重影响",
                        "default": 0.2
                    }
                },
                "required": ["region", "start_time", "end_time"]
            }
        }

        super().__init__(
            name="get_dust_data",
            description="Query dust aerosol forecast data to identify dust transport events",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        self.repo = DustRepository()

    async def execute(
        self,
        region: Dict[str, float],
        start_time: str,
        end_time: str,
        min_dust_aod: float = 0.2
    ) -> Dict[str, Any]:
        """
        执行沙尘数据查询

        Args:
            region: 查询区域 {min_lat, max_lat, min_lon, max_lon}
            start_time: 开始时间（ISO8601格式）
            end_time: 结束时间（ISO8601格式）
            min_dust_aod: 最小沙尘AOD阈值（默认0.2）

        Returns:
            Dict: 沙尘预报数据和统计信息
        """
        try:
            logger.info(
                "get_dust_data_start",
                region=region,
                time_range=[start_time, end_time],
                min_dust_aod=min_dust_aod
            )

            # 1. 参数验证和转换
            validation_result = self._validate_params(region, start_time, end_time)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": validation_result["error"],
                    "error_type": "validation_error"
                }

            start_dt = validation_result["start_dt"]
            end_dt = validation_result["end_dt"]

            # 2. 查询沙尘预报数据
            dust_forecasts = await self.repo.get_dust_forecasts(
                min_lat=region["min_lat"],
                max_lat=region["max_lat"],
                min_lon=region["min_lon"],
                max_lon=region["max_lon"],
                start_time=start_dt,
                end_time=end_dt,
                min_dust_aod=min_dust_aod
            )

            logger.info(
                "dust_forecasts_queried",
                count=len(dust_forecasts)
            )

            # 3. 查询最大AOD值（用于判断沙尘强度）
            max_aod = await self.repo.get_max_dust_aod_in_region(
                min_lat=region["min_lat"],
                max_lat=region["max_lat"],
                min_lon=region["min_lon"],
                max_lon=region["max_lon"],
                start_time=start_dt,
                end_time=end_dt
            )

            # 4. 格式化返回数据
            result = self._format_results(
                dust_forecasts,
                max_aod,
                region,
                start_dt,
                end_dt,
                min_dust_aod
            )

            logger.info(
                "get_dust_data_complete",
                count=result["count"],
                max_aod=result["statistics"]["max_dust_aod"],
                has_dust_impact=result["statistics"]["has_dust_impact"]
            )

            return result

        except Exception as e:
            logger.error(
                "get_dust_data_failed",
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": f"沙尘数据查询失败: {str(e)}",
                "error_type": "internal_error"
            }

    def _validate_params(
        self,
        region: Dict[str, float],
        start_time: str,
        end_time: str
    ) -> Dict[str, Any]:
        """
        验证输入参数

        Returns:
            Dict: {valid: bool, error: str, start_dt: datetime, end_dt: datetime}
        """
        try:
            # 检查region必需字段
            required_fields = ["min_lat", "max_lat", "min_lon", "max_lon"]
            for field in required_fields:
                if field not in region:
                    return {
                        "valid": False,
                        "error": f"缺少必需字段: region.{field}"
                    }

            # 检查经纬度范围
            if region["min_lat"] >= region["max_lat"]:
                return {
                    "valid": False,
                    "error": "min_lat必须小于max_lat"
                }

            if region["min_lon"] >= region["max_lon"]:
                return {
                    "valid": False,
                    "error": "min_lon必须小于max_lon"
                }

            # 检查中国范围（宽松检查）
            if not (-90 <= region["min_lat"] <= 90 and -90 <= region["max_lat"] <= 90):
                return {
                    "valid": False,
                    "error": "纬度范围必须在 -90 到 90 之间"
                }

            if not (-180 <= region["min_lon"] <= 180 and -180 <= region["max_lon"] <= 180):
                return {
                    "valid": False,
                    "error": "经度范围必须在 -180 到 180 之间"
                }

            # 时间转换
            try:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            except ValueError as e:
                return {
                    "valid": False,
                    "error": f"时间格式错误: {str(e)}. 请使用ISO8601格式（如 2025-10-20T00:00:00）"
                }

            # 检查时间顺序
            if start_dt >= end_dt:
                return {
                    "valid": False,
                    "error": "start_time必须早于end_time"
                }

            return {
                "valid": True,
                "start_dt": start_dt,
                "end_dt": end_dt
            }

        except Exception as e:
            return {
                "valid": False,
                "error": f"参数验证失败: {str(e)}"
            }

    def _format_results(
        self,
        dust_forecasts: List,
        max_aod: Optional[float],
        region: Dict[str, float],
        start_time: datetime,
        end_time: datetime,
        min_dust_aod: float
    ) -> Dict[str, Any]:
        """
        格式化查询结果

        Returns:
            Dict: 格式化的沙尘预报数据
        """
        # 转换为字典列表
        forecasts_data = []
        total_pm10 = 0.0
        pm10_count = 0
        aod_values = []

        for forecast in dust_forecasts:
            forecast_dict = {
                "lat": forecast.lat,
                "lon": forecast.lon,
                "forecast_time": forecast.forecast_time.isoformat(),
                "valid_time": forecast.valid_time.isoformat(),
                "leadtime_hour": forecast.leadtime_hour,
                "dust_aod_550nm": forecast.dust_aod_550nm,
                "pm10_concentration": forecast.pm10_concentration,
                "data_source": forecast.data_source
            }

            forecasts_data.append(forecast_dict)

            # 统计
            if forecast.dust_aod_550nm is not None:
                aod_values.append(forecast.dust_aod_550nm)

            if forecast.pm10_concentration is not None:
                total_pm10 += forecast.pm10_concentration
                pm10_count += 1

        # 计算统计指标
        avg_aod = sum(aod_values) / len(aod_values) if aod_values else 0.0
        avg_pm10 = total_pm10 / pm10_count if pm10_count > 0 else 0.0

        # 判断沙尘影响等级
        dust_impact_level = self._classify_dust_impact(max_aod or 0.0)

        # 构建返回结果
        result = {
            "success": True,
            "count": len(forecasts_data),
            "forecasts": forecasts_data,
            "statistics": {
                "total_count": len(forecasts_data),
                "max_dust_aod": max_aod,
                "avg_dust_aod": round(avg_aod, 3),
                "avg_pm10_concentration": round(avg_pm10, 1) if avg_pm10 > 0 else None,
                "has_dust_impact": (max_aod or 0.0) >= min_dust_aod,
                "dust_impact_level": dust_impact_level,
                "grid_points_affected": len(set((f["lat"], f["lon"]) for f in forecasts_data))
            },
            "metadata": {
                "query_region": region,
                "time_range": [start_time.isoformat(), end_time.isoformat()],
                "min_dust_aod_threshold": min_dust_aod,
                "data_source": "CAMS (Copernicus Atmosphere Monitoring Service)",
                "spatial_resolution": "0.4° × 0.4° (~40km)",
                "forecast_range": "5 days (120 hours)",
                "queried_at": datetime.now().isoformat()
            }
        }

        return result

    def _classify_dust_impact(self, max_aod: float) -> str:
        """
        根据最大AOD值判断沙尘影响等级

        参考标准（经验值）：
        - < 0.2: 无显著影响
        - 0.2 - 0.5: 轻微影响
        - 0.5 - 1.0: 中度影响
        - 1.0 - 2.0: 严重影响
        - >= 2.0: 极严重影响

        Args:
            max_aod: 最大沙尘AOD值

        Returns:
            str: 影响等级
        """
        if max_aod < 0.2:
            return "无显著影响"
        elif max_aod < 0.5:
            return "轻微影响"
        elif max_aod < 1.0:
            return "中度影响"
        elif max_aod < 2.0:
            return "严重影响"
        else:
            return "极严重影响"


# 导出
__all__ = ["GetDustDataTool"]
