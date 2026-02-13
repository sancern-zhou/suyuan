"""
地图生成工具（Generate Map Tool）

生成高德地图（AMap）配置，用于可视化站点和企业位置。
"""
from typing import Dict, Any, List, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.visualization import generate_map_payload

logger = structlog.get_logger()


class GenerateMapTool(LLMTool):
    """
    高德地图配置生成工具

    生成用于前端MapPanel组件的高德地图配置，展示：
    - 监测站点位置
    - 企业标记（带行业、距离等信息）
    - 上风向路径（可选）
    - 风向扇区（可选）
    """

    def __init__(self):
        function_schema = {
            "name": "generate_map",
            "description": """
生成高德地图配置，用于可视化站点和企业位置。

功能：
1. 在地图上标注监测站点
2. 在地图上标注企业位置（带行业、距离等信息）
3. 绘制上风向路径（可选）
4. 绘制风向扇区（可选）

返回数据：
- 地图中心点坐标
- 站点标记
- 企业标记列表
- 上风向路径（可选）
- 风向扇区（可选）
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "station": {
                        "type": "object",
                        "description": "站点信息，包含经纬度、名称等",
                        "properties": {
                            "station_name": {"type": "string", "description": "站点名称"},
                            "longitude": {"type": "number", "description": "经度"},
                            "latitude": {"type": "number", "description": "纬度"},
                            "lng": {"type": "number", "description": "经度（别名）"},
                            "lat": {"type": "number", "description": "纬度（别名）"},
                        }
                    },
                    "enterprises": {
                        "type": "array",
                        "description": "企业列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "企业名称"},
                                "longitude": {"type": "number", "description": "经度"},
                                "latitude": {"type": "number", "description": "纬度"},
                                "lng": {"type": "number", "description": "经度（别名）"},
                                "lat": {"type": "number", "description": "纬度（别名）"},
                                "industry": {"type": "string", "description": "行业"},
                                "distance": {"type": "number", "description": "距离（km）"},
                                "emissions": {"type": "object", "description": "排放信息"},
                            }
                        }
                    },
                    "upwind_paths": {
                        "type": "array",
                        "description": "上风向路径（可选）"
                    },
                    "sectors": {
                        "type": "array",
                        "description": "风向扇区（可选）"
                    }
                },
                "required": ["station", "enterprises"]
            }
        }

        super().__init__(
            name="generate_map",
            description="Generate AMap configuration for visualizing stations and enterprises",
            category=ToolCategory.VISUALIZATION,
            function_schema=function_schema,
            version="1.0.0"
        )

    async def execute(
        self,
        station: Dict[str, Any],
        enterprises: List[Dict[str, Any]],
        upwind_paths: Optional[List[Dict[str, Any]]] = None,
        sectors: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成高德地图配置

        Args:
            station: 站点信息（包含经纬度、名称）
            enterprises: 企业列表
            upwind_paths: 上风向路径（可选）
            sectors: 风向扇区（可选）

        Returns:
            {
                "success": True,
                "map_config": {
                    "map_center": {"lng": ..., "lat": ...},
                    "station": {...},
                    "enterprises": [...],
                    "upwind_paths": [...],  # 可选
                    "sectors": [...]  # 可选
                },
                "summary": "摘要信息"
            }
        """
        try:
            # 空值检查（防止参数绑定失败时传入None）
            if station is None:
                logger.warning("generate_map_station_is_none")
                return {
                    "success": False,
                    "error": "站点数据为空",
                    "summary": "❌ 地图配置生成失败：未提供站点数据（可能是上游工具未返回有效数据）"
                }
            
            if enterprises is None:
                logger.warning("generate_map_enterprises_is_none")
                return {
                    "success": False,
                    "error": "企业数据为空",
                    "summary": "❌ 地图配置生成失败：未提供企业数据（可能是上游工具未返回有效数据）"
                }

            logger.info(
                "generate_map_start",
                station_name=station.get("station_name", station.get("name")) if isinstance(station, dict) else str(station),
                enterprises_count=len(enterprises) if isinstance(enterprises, list) else 0
            )

            # 验证站点数据
            if not isinstance(station, dict):
                return {
                    "success": False,
                    "error": "站点数据格式无效",
                    "summary": "❌ 地图配置生成失败：站点数据格式错误"
                }

            # 验证企业数据
            if not isinstance(enterprises, list):
                return {
                    "success": False,
                    "error": "企业数据格式无效",
                    "summary": "❌ 地图配置生成失败：企业数据格式错误"
                }

            # 生成地图配置
            map_config = generate_map_payload(
                station=station,
                enterprises=enterprises,
                upwind_paths=upwind_paths,
                sectors=sectors
            )

            # 验证生成的配置
            if not isinstance(map_config, dict):
                return {
                    "success": False,
                    "error": "地图配置生成失败",
                    "summary": "❌ 地图配置生成失败：生成器返回格式错误"
                }

            logger.info(
                "map_config_generated",
                station_name=station.get("station_name", station.get("name")),
                enterprises_count=len(enterprises),
                has_upwind_paths=bool(upwind_paths),
                has_sectors=bool(sectors),
                map_center=map_config.get("map_center")
            )

            # 构建摘要
            summary_parts = [f"✅ 生成地图配置成功"]
            summary_parts.append(f"站点1个")
            summary_parts.append(f"企业{len(enterprises)}个")
            if upwind_paths:
                summary_parts.append("包含上风向路径")
            if sectors:
                summary_parts.append("包含风向扇区")

            # 【UDF v2.0 + Chart v3.1】统一返回visuals格式
            from app.schemas.unified import VisualBlock
            from datetime import datetime

            # 生成唯一ID
            map_id = f"map_{id(map_config)}"
            timestamp = datetime.now().isoformat()

            visual_block = VisualBlock(
                id=map_id,
                type="map",
                schema="chart_config",
                payload={
                    "id": map_id,
                    "type": "map",
                    "title": f"{station.get('station_name', station.get('name', '站点'))}周边企业分布图",
                    "data": map_config,
                    "meta": {
                        "schema_version": "3.1",
                        "generator": "generate_map",
                        "generator_version": "2.0.0",
                        "source_data_ids": [],
                        "original_data_ids": [],
                        "scenario": "station_enterprise_distribution",
                        "interaction_group": "map_interaction",
                        "data_flow": ["station_data", "enterprise_data", "map_config"],
                        "layout_hint": "map-full",
                        "timestamp": timestamp,
                        "created_at": timestamp
                    }
                },
                meta={
                    "schema_version": "v2.0",
                    "generator": "generate_map",
                    "generator_version": "2.0.0",
                    "source_data_ids": [],
                    "original_data_ids": [],
                    "scenario": "station_enterprise_distribution",
                    "interaction_group": "map_interaction",
                    "data_flow": ["station_data", "enterprise_data", "map_config"],
                    "layout_hint": "map-full",
                    "timestamp": timestamp,
                    "created_at": timestamp
                }
            )

            return {
                "status": "success",
                "success": True,
                "data": None,  # v2.0格式使用visuals字段
                "visuals": [visual_block.dict()],  # 统一visuals格式
                "metadata": {
                    "schema_version": "v2.0",
                    "source_data_ids": [],
                    "generator": "generate_map",
                    "record_count": 1
                },
                "summary": "，".join(summary_parts)
            }

        except Exception as e:
            logger.error(
                "generate_map_failed",
                error=str(e),
                exc_info=True
            )

            return {
                "success": False,
                "error": str(e),
                "summary": f"❌ 地图配置生成失败: {str(e)[:50]}"
            }
