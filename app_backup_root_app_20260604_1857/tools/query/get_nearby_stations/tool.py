"""
Nearby Stations Query Tool

提供目标站点及周边站点信息，支持按需附带空气质量数据，便于开展传输分析。
适用范围：广东省站点数据。
"""
from typing import Dict, Any, List, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.services.external_apis import station_api, monitoring_api

logger = structlog.get_logger()


class GetNearbyStationsTool(LLMTool):
    """
    查询目标站点附近的监测站点列表，可选获取指定时间段的空气质量数据。
    """

    def __init__(self):
        function_schema = {
            "name": "get_nearby_stations",
            "description": (
                "查询指定监测站附近的站点信息（广东省）。"
                "可选获取目标站和周边站的空气质量数据以支持传输分析。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "station_name": {
                        "type": "string",
                        "description": "目标监测站名称（如“广雅中学”）"
                    },
                    "max_distance": {
                        "type": "number",
                        "description": "搜索半径（公里），默认20km",
                        "default": 20.0
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "返回的周边站点数量，默认5个",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 10
                    },
                    "fetch_air_quality": {
                        "type": "boolean",
                        "description": "是否获取空气质量对比数据（需提供时间范围）",
                        "default": False
                    },
                    "pollutants": {
                        "type": "array",
                        "description": "需要对比的污染物列表（如PM2.5、PM10、O3、NOX）",
                        "items": {"type": "string"},
                        "default": ["PM2.5", "PM10", "O3", "NOX"]
                    },
                    "start_time": {
                        "type": "string",
                        "description": "空气质量数据开始时间（YYYY-MM-DD HH:MM:SS）"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "空气质量数据结束时间（YYYY-MM-DD HH:MM:SS），默认与开始时间相同"
                    }
                },
                "required": ["station_name"]
            }
        }

        super().__init__(
            name="get_nearby_stations",
            description="Query nearby monitoring stations around a target station (Guangdong only)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

    async def execute(
        self,
        station_name: str,
        max_distance: float = 20.0,
        max_results: int = 5,
        fetch_air_quality: bool = False,
        pollutants: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        查询周边站点并按需附带空气质量数据（统一格式）。

        Returns:
            Dict: 统一数据格式的周边站点查询结果 (UnifiedData.dict())
        """
        from app.schemas.unified import (
            UnifiedData, DataType, DataStatus, DataMetadata, UnifiedDataRecord
        )

        pollutants = pollutants or ["PM2.5", "PM10", "O3", "NOX"]
        logger.info(
            "nearby_stations_request",
            station=station_name,
            distance=max_distance,
            limit=max_results,
            fetch_air_quality=fetch_air_quality
        )

        try:
            target_info = await station_api.get_station_by_name(station_name)
            nearby_list = await station_api.get_nearby_stations(
                station_name=station_name,
                max_distance=max_distance,
                max_results=max_results
            )

            if not isinstance(nearby_list, list):
                nearby_list = []

            air_quality_payload = {}
            if fetch_air_quality:
                if not start_time:
                    logger.warning(
                        "nearby_stations_missing_time_range",
                        station=station_name
                    )
                else:
                    end_time = end_time or start_time
                    air_quality_payload = await self._collect_air_quality_data(
                        stations=[target_info] + nearby_list if target_info else nearby_list,
                        pollutants=pollutants,
                        start_time=start_time,
                        end_time=end_time
                    )

            # 转换为UnifiedDataRecord格式
            records = []

            # 添加目标站点记录
            if target_info:
                # measurements 只保留数值型数据
                station_measurements = {
                    "distance_km": 0.0
                }

                # 站点元信息放在 metadata 中
                station_metadata = {
                    "station_type": "target",
                    "station_code": target_info.get("唯一编码"),
                    "district": target_info.get("区县"),
                    "city": target_info.get("城市"),
                    "province": target_info.get("省份"),
                    "address": target_info.get("详细地址")
                }

                records.append(UnifiedDataRecord(
                    timestamp=None,  # 站点信息不是时间序列数据
                    station_name=target_info.get("station_name", target_info.get("站点名称", station_name)),
                    lat=target_info.get("lat", target_info.get("纬度")),
                    lon=target_info.get("lon", target_info.get("经度")),
                    measurements=station_measurements,
                    metadata=station_metadata
                ))

            # 添加周边站点记录
            for station in nearby_list:
                # measurements 只保留数值型数据
                station_measurements = {
                    "distance_km": station.get("distance", station.get("距离", 0.0))
                }

                # 站点元信息放在 metadata 中
                station_metadata = {
                    "station_type": "nearby",
                    "station_code": station.get("station_code", station.get("唯一编码")),
                    "district": station.get("district", station.get("所属区县")),
                    "city": station.get("city", station.get("所属城市")),
                    "province": station.get("province", station.get("省份")),
                    "address": station.get("address", station.get("地址"))
                }

                records.append(UnifiedDataRecord(
                    timestamp=None,  # 站点信息不是时间序列数据
                    station_name=station.get("station_name", station.get("站点名称", station.get("name", "Unknown"))),
                    lat=station.get("lat", station.get("纬度")),
                    lon=station.get("lon", station.get("经度")),
                    measurements=station_measurements,
                    metadata=station_metadata
                ))

            # 构建元数据
            metadata = DataMetadata(
                data_id=f"nearby_stations:{station_name}:{max_distance}",
                data_type=DataType.CUSTOM,
                schema_version="v2.0",  # ✅ UDF v2.0 标记
                record_count=len(records),
                station_name=station_name,
                source="station_api",
                quality_score=0.9 if records else 0.0,
                # v2.0 新增字段
                scenario="nearby_stations_query",
                generator="get_nearby_stations",
                parameters={
                    "station_name": station_name,
                    "max_distance": max_distance,
                    "max_results": max_results,
                    "pollutants": pollutants if fetch_air_quality else [],
                    "start_time": start_time,
                    "end_time": end_time,
                    "fetch_air_quality": fetch_air_quality
                }
            )

            # 构建摘要
            summary = f"[OK] 找到 {len(nearby_list)} 个周边站点"
            if air_quality_payload:
                summary += f"，已附带空气质量对比数据"
            if target_info:
                summary += f"（{station_name}）"

            # 构建统一数据格式
            unified_data = UnifiedData(
                status=DataStatus.SUCCESS if records else DataStatus.EMPTY,
                success=len(records) > 0,
                data=records,
                metadata=metadata,
                summary=summary,
                legacy_fields={
                    "target_station": target_info,
                    "nearby_stations": nearby_list,
                    "air_quality": air_quality_payload,
                    "params": {
                        "station_name": station_name,
                        "max_distance": max_distance,
                        "max_results": max_results,
                        "pollutants": pollutants if fetch_air_quality else [],
                        "start_time": start_time,
                        "end_time": end_time,
                    }
                }
            )

            return unified_data.dict()

        except Exception as e:
            logger.error(
                "nearby_stations_query_failed",
                station=station_name,
                error=str(e),
                exc_info=True
            )
            # 返回统一错误格式
            from app.schemas.unified import UnifiedData, DataType, DataStatus, DataMetadata
            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error=str(e),
                data=[],
                metadata=DataMetadata(
                    data_id=f"nearby_stations_error:{id(e)}",
                    data_type=DataType.CUSTOM,
                    schema_version="v2.0",  # ✅ UDF v2.0 标记
                    source="station_api",
                    scenario="nearby_stations_query",
                    generator="get_nearby_stations"
                ),
                summary=f"[ERROR] 周边站点查询失败: {str(e)[:50]}"
            ).dict()

    async def _collect_air_quality_data(
        self,
        stations: List[Optional[Dict[str, Any]]],
        pollutants: List[str],
        start_time: str,
        end_time: str
    ) -> Dict[str, Any]:
        """
        采集目标及周边站点的空气质量数据。
        """
        results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

        if not stations:
            return results

        for station in stations:
            if not station:
                continue

            name = station.get("station_name") or station.get("name")
            if not name:
                continue

            station_records: Dict[str, List[Dict[str, Any]]] = {}
            for pollutant in pollutants:
                try:
                    data = await monitoring_api.get_station_pollutant_data(
                        station_name=name,
                        pollutant=pollutant,
                        start_time=start_time,
                        end_time=end_time
                    )
                    if data:
                        station_records[pollutant] = data
                except Exception as e:
                    logger.warning(
                        "air_quality_fetch_failed",
                        station=name,
                        pollutant=pollutant,
                        error=str(e)
                    )

            if station_records:
                results[name] = station_records

        return results

