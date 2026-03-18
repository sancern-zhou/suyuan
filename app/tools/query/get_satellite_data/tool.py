"""
卫星数据查询工具

获取 Sentinel-5P TROPOMI 和 MODIS 卫星遥感数据
支持多种大气污染物和气溶胶参数监测
"""

import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext
from app.external_apis.satellite_data_hub import SatelliteDataHub

logger = structlog.get_logger()


class GetSatelliteDataTool(LLMTool):
    """卫星数据查询工具"""

    def __init__(self):
        super().__init__(
            name="get_satellite_data",
            description="获取卫星遥感数据 (Sentinel-5P TROPOMI, MODIS)",
            category=ToolCategory.QUERY,
            requires_context=False
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        """获取工具参数定义"""
        return {
            "type": "object",
            "properties": {
                "data_type": {
                    "type": "string",
                    "description": """数据类型，必须使用以下标准值之一:
- s5p_no2: Sentinel-5P NO2柱浓度 (机动车/工业排放监测)
- s5p_so2: Sentinel-5P SO2柱浓度 (火山/工业排放)
- s5p_co: Sentinel-5P CO柱浓度 (生物质燃烧/交通排放)
- s5p_hcho: Sentinel-5P HCHO柱浓度 (VOCs排放)
- s5p_o3: Sentinel-5P O3柱浓度 (臭氧污染)
- s5p_aer_ai: Sentinel-5P气溶胶指数 (沙尘/烟雾)
- modis_aod: MODIS气溶胶光学厚度 (细颗粒物)""",
                    "enum": [
                        "s5p_no2",
                        "s5p_so2",
                        "s5p_co",
                        "s5p_hcho",
                        "s5p_o3",
                        "s5p_aer_ai",
                        "modis_aod"
                    ],
                    "default": "s5p_no2"
                },
                "bbox": {
                    "type": "array",
                    "description": "边界框坐标 [min_lat, min_lon, max_lat, max_lon]，例如珠三角: [22.0, 113.0, 24.0, 114.5]",
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期 (YYYY-MM-DD)，例如: 2025-11-20"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期 (YYYY-MM-DD)，例如: 2025-11-27"
                },
                "cloud_threshold": {
                    "type": "number",
                    "description": "云覆盖阈值 (0-1, 仅对S5P有效)，默认0.3，值越小过滤越严格",
                    "default": 0.3
                },
                "satellites": {
                    "type": "array",
                    "description": "MODIS卫星列表 ['terra', 'aqua']，仅modis_aod时使用",
                    "items": {"type": "string"},
                    "default": ["terra", "aqua"]
                }
            },
            "required": ["data_type", "bbox", "start_date", "end_date"]
        }

    def get_function_schema(self) -> Dict[str, Any]:
        """获取OpenAI Function Calling格式的函数定义"""
        return {
            "name": self.name,
            "description": self.description + """

注意事项:
1. data_type必须使用标准值 (s5p_no2, modis_aod等)
2. bbox格式: [min_lat, min_lon, max_lat, max_lon]
3. 日期格式: YYYY-MM-DD
4. 云覆盖阈值仅对Sentinel-5P数据有效
5. 需要先安装并认证Google Earth Engine""",
            "parameters": self.parameters
        }

    examples = [
        {
            "data_type": "s5p_no2",
            "bbox": [39.9, 116.4, 40.0, 116.5],
            "start_date": "2024-11-01",
            "end_date": "2024-11-07",
            "description": "获取北京地区NO2柱浓度数据"
        },
        {
            "data_type": "modis_aod",
            "bbox": [22.5, 113.8, 23.5, 114.5],
            "start_date": "2024-11-01",
            "end_date": "2024-11-07",
            "satellites": ["terra", "aqua"],
            "description": "获取珠三角地区MODIS AOD数据"
        }
    ]

    async def execute(
        self,
        context: ExecutionContext,
        data_type: str,
        bbox: List[float],
        start_date: str,
        end_date: str,
        cloud_threshold: float = 0.3,
        satellites: Optional[List[str]] = None,
        output_format: str = "summary"
    ) -> Dict[str, Any]:
        """
        执行卫星数据查询

        Args:
            context: 执行上下文
            data_type: 数据类型
            bbox: 边界框 [min_lat, min_lon, max_lat, max_lon]
            start_date: 开始日期
            end_date: 结束日期
            cloud_threshold: 云覆盖阈值
            satellites: 卫星列表 (MODIS)
            output_format: 输出格式

        Returns:
            UDF v2.0格式的卫星数据
        """
        try:
            logger.info(
                "satellite_data_query_started",
                data_type=data_type,
                bbox=bbox,
                start_date=start_date,
                end_date=end_date
            )

            # 验证数据类型
            valid_types = ["s5p_no2", "s5p_so2", "s5p_co", "s5p_hcho", "s5p_o3", "s5p_aer_ai", "modis_aod"]
            if data_type not in valid_types:
                raise ValueError(
                    f"无效的data_type: {data_type}。"
                    f"必须使用以下值之一: {', '.join(valid_types)}"
                )

            # 验证边界框
            if len(bbox) != 4:
                raise ValueError("边界框必须是4个数值: [min_lat, min_lon, max_lat, max_lon]")

            min_lat, min_lon, max_lat, max_lon = bbox

            if min_lat >= max_lat:
                raise ValueError("min_lat 必须小于 max_lat")
            if min_lon >= max_lon:
                raise ValueError("min_lon 必须小于 max_lon")

            # 验证日期范围
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

            if start_dt >= end_dt:
                raise ValueError("start_date 必须早于 end_date")

            # 检查时间范围（限制最大3个月）
            if (end_dt - start_dt).days > 90:
                logger.warning(
                    "large_time_range",
                    days=(end_dt - start_dt).days,
                    hint="建议使用3个月以内的时间范围"
                )

            # 初始化卫星数据中心
            # 自动设置项目ID
            satellite_hub = SatelliteDataHub(project_id='gen-lang-client-0761286422')

            # 构建查询参数
            query_params = {
                "data_type": data_type,
                "bbox": bbox,
                "start_date": start_date,
                "end_date": end_date
            }

            # 添加可选参数
            if data_type.startswith("s5p_") and cloud_threshold is not None:
                query_params["cloud_fraction_threshold"] = cloud_threshold

            if data_type == "modis_aod" and satellites:
                query_params["satellites"] = satellites

            # 获取卫星数据
            satellite_data = await satellite_hub.fetch_satellite_data(**query_params)

            if not satellite_data.get("success"):
                raise Exception(f"获取卫星数据失败: {satellite_data.get('error')}")

            # 标准化数据格式
            standardized_data = await self._standardize_satellite_data(
                satellite_data,
                data_type=data_type,
                bbox=bbox
            )

            # 保存数据到上下文（可选）
            if output_format == "full":
                data_id = await self._save_data_to_context(
                    context,
                    standardized_data,
                    schema="satellite_data_unified"
                )
                standardized_data["data_id"] = data_id

            logger.info(
                "satellite_data_query_completed",
                data_type=data_type,
                image_count=satellite_data.get("image_count"),
                success=True
            )

            return standardized_data

        except Exception as e:
            logger.error(
                "satellite_data_query_failed",
                data_type=data_type,
                error=str(e),
                exc_info=True
            )
            raise

    async def _standardize_satellite_data(
        self,
        raw_data: Dict[str, Any],
        data_type: str,
        bbox: List[float]
    ) -> Dict[str, Any]:
        """
        标准化卫星数据到UDF v2.0格式

        Args:
            raw_data: 原始卫星数据
            data_type: 数据类型
            bbox: 边界框

        Returns:
            UDF v2.0格式数据
        """
        # 构建UDF v2.0格式
        result = {
            "status": "success",
            "success": True,
            "data": [{
                "parameter": raw_data.get("parameter"),
                "value": raw_data.get("statistics", {}),
                "unit": raw_data.get("unit"),
                "spatial_resolution": raw_data.get("spatial_resolution"),
                "temporal_range": raw_data.get("temporal_range"),
                "bbox": bbox,
                "image_count": raw_data.get("image_count"),
                "valid_image_count": raw_data.get("valid_image_count", 0),
                "source": raw_data.get("data_source")
            }],
            "metadata": {
                "schema_version": "v2.0",
                "field_mapping_applied": True,
                "field_mapping_info": {
                    "source_fields": ["parameter", "value", "unit"],
                    "target_fields": ["parameter", "value", "unit"],
                    "mapped_count": 3
                },
                "generator": "get_satellite_data",
                "scenario": f"satellite_{data_type}",
                "record_count": 1,
                "generator_version": "1.0.0"
            },
            "summary": f"成功获取{raw_data.get('data_source')} {raw_data.get('parameter')}数据"
        }

        # 添加数据源特定信息
        if data_type.startswith("s5p_"):
            result["metadata"]["satellite"] = "Sentinel-5P TROPOMI"
        elif data_type == "modis_aod":
            result["metadata"]["satellite"] = raw_data.get("satellites", ["terra", "aqua"])

        # 添加云覆盖信息（仅S5P）
        if "cloud_threshold" in raw_data:
            result["metadata"]["cloud_threshold"] = raw_data["cloud_threshold"]

        return result

    async def _save_data_to_context(
        self,
        context: ExecutionContext,
        data: Dict[str, Any],
        schema: str
    ) -> str:
        """
        保存数据到上下文

        Args:
            context: 执行上下文
            data: 数据
            schema: 数据模式

        Returns:
            数据ID
        """
        try:
            if context.requires_context:
                data_id = context.save_data(
                    data=data["data"],
                    schema=schema
                )
                return data_id
            else:
                logger.info("context_not_available", skip_save=True)
                return "no_context"
        except Exception as e:
            logger.warning("save_data_failed", error=str(e))
            return "save_failed"

    async def validate_bbox(self, bbox: List[float]) -> bool:
        """
        验证边界框坐标

        Args:
            bbox: 边界框 [min_lat, min_lon, max_lat, max_lon]

        Returns:
            是否有效
        """
        try:
            if len(bbox) != 4:
                return False

            min_lat, min_lon, max_lat, max_lon = bbox

            # 检查纬度范围
            if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
                return False

            # 检查经度范围
            if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
                return False

            # 检查逻辑关系
            if min_lat >= max_lat or min_lon >= max_lon:
                return False

            return True
        except Exception:
            return False

    def get_data_type_info(self, data_type: str) -> Dict[str, Any]:
        """
        获取数据类型信息

        Args:
            data_type: 数据类型

        Returns:
            数据类型详细信息
        """
        info_map = {
            "s5p_no2": {
                "name": "Sentinel-5P NO2柱浓度",
                "parameter": "NO2",
                "description": "对流层NO2柱浓度，反映机动车和工业排放",
                "applications": ["交通污染", "工业排放", "城市空气质量"]
            },
            "s5p_so2": {
                "name": "Sentinel-5P SO2柱浓度",
                "parameter": "SO2",
                "description": "SO2柱浓度，指示火山活动和工业排放",
                "applications": ["火山监测", "燃煤污染", "工业排放"]
            },
            "s5p_co": {
                "name": "Sentinel-5P CO柱浓度",
                "parameter": "CO",
                "description": "CO柱浓度，指示生物质燃烧和不完全燃烧",
                "applications": ["生物质燃烧", "交通排放", "秸秆焚烧"]
            },
            "s5p_hcho": {
                "name": "Sentinel-5P HCHO柱浓度",
                "parameter": "HCHO",
                "description": "甲醛柱浓度，VOCs排放指示物",
                "applications": ["VOCs排放", "光化学污染", "生物排放"]
            },
            "s5p_o3": {
                "name": "Sentinel-5P O3柱浓度",
                "parameter": "O3",
                "description": "臭氧柱浓度，指示光化学污染",
                "applications": ["臭氧污染", "光化学烟雾", "区域传输"]
            },
            "s5p_aer_ai": {
                "name": "Sentinel-5P气溶胶指数",
                "parameter": "Aerosol Index",
                "description": "气溶胶指数，监测沙尘和烟雾",
                "applications": ["沙尘监测", "烟雾检测", "污染层识别"]
            },
            "modis_aod": {
                "name": "MODIS气溶胶光学厚度",
                "parameter": "AOD",
                "description": "550nm气溶胶光学厚度，指示细颗粒物污染",
                "applications": ["PM2.5监测", "沙尘传输", "污染强度评估"]
            }
        }

        return info_map.get(data_type, {})