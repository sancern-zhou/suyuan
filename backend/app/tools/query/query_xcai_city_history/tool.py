"""
XcAiDb城市历史数据查询工具

查询全国城市历史空气质量数据（SQL Server XcAiDb数据库）

支持查询：
- 小时数据：CityAQIPublishHistory表（2017-01-01 至今）
- 日数据：CityDayAQIPublishHistory表（2021-06-25 至今）
- 多城市查询
- 自定义时间范围

返回格式：UDF v2.0标准（包含data_id供下游工具使用）
"""
from typing import Dict, Any, List, TYPE_CHECKING
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.data_standardizer import get_data_standardizer

if TYPE_CHECKING:
    from app.agent.context.execution_context import ExecutionContext

from .sql_client import get_sql_server_client

logger = structlog.get_logger()


class QueryXcAiCityHistoryTool(LLMTool):
    """
    XcAiDb城市历史数据查询工具

    通过SQL Server查询全国城市历史空气质量数据
    """

    def __init__(self):
        function_schema = {
            "name": "query_xcai_city_history",
            "description": """
查询全国城市历史空气质量数据（SQL Server XcAiDb数据库）。

**数据表说明**：
- hour（小时数据）：CityAQIPublishHistory表，时间范围 2017-01-01 至今，字段包括 PM2_5, PM10, O3, NO2, SO2, CO, AQI, PrimaryPollutant, Quality
- day（日数据）：CityDayAQIPublishHistory表，时间范围 2021-06-25 至今，字段包括 PM2_5_24h, PM10_24h, O3_8h_24h, NO2_24h, SO2_24h, CO_24h, AQI, PrimaryPollutant, Quality

**使用示例**：
- 查询广州2025年3月的小时数据：data_type="hour", cities=["广州市"], start_time="2025-03-01 00:00:00", end_time="2025-03-31 23:00:00"
- 查询深圳近7天的日数据：data_type="day", cities=["深圳市"], start_time="2025-03-22 00:00:00", end_time="2025-03-29 00:00:00"
- 查询北京2024年全年日数据：data_type="day", cities=["北京市"], start_time="2024-01-01 00:00:00", end_time="2024-12-31 00:00:00"

**注意事项**：
- 时间格式必须严格：小时数据用 "YYYY-MM-DD HH:MM:SS"，日数据用 "YYYY-MM-DD 00:00:00"
- 城市名称支持中文（如"广州市"、"深圳市"）
- 返回的data_id可用于下游分析工具获取完整数据
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表，如：['广州市', '深圳市', '北京市']"
                    },
                    "data_type": {
                        "type": "string",
                        "enum": ["hour", "day"],
                        "description": "数据类型：hour=查询小时数据表（CityAQIPublishHistory），day=查询日数据表（CityDayAQIPublishHistory）"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间（必须），格式：YYYY-MM-DD HH:MM:SS（小时数据）或 YYYY-MM-DD 00:00:00（日数据）"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间（必须），格式：YYYY-MM-DD HH:MM:SS（小时数据）或 YYYY-MM-DD 00:00:00（日数据）"
                    }
                },
                "required": ["cities", "data_type", "start_time", "end_time"]
            }
        }

        super().__init__(
            name="query_xcai_city_history",
            description="Query city history air quality data from XcAiDb SQL Server (UDF v2.0)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

        self.sql_client = get_sql_server_client()

    async def execute(
        self,
        context: "ExecutionContext",
        cities: List[str],
        data_type: str,
        start_time: str,
        end_time: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行查询

        Args:
            context: 执行上下文
            cities: 城市名称列表
            data_type: 数据类型（hour/day）
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            UDF v2.0格式的查询结果
        """
        logger.info(
            "query_xcai_city_history_start",
            cities=cities,
            data_type=data_type,
            start_time=start_time,
            end_time=end_time
        )

        try:
            # Step 1: 确定查询表名
            table_map = {
                "hour": "CityAQIPublishHistory",
                "day": "CityDayAQIPublishHistory"
            }
            table_name = table_map.get(data_type)
            if not table_name:
                raise ValueError(f"不支持的数据类型: {data_type}")

            # Step 2: 执行SQL查询
            raw_records = self.sql_client.query(
                cities=cities,
                start_time=start_time,
                end_time=end_time,
                table=table_name
            )

            if not raw_records:
                logger.warning(
                    "query_xcai_city_history_no_data",
                    cities=cities,
                    data_type=data_type,
                    time_range=f"{start_time} to {end_time}"
                )
                return {
                    "status": "empty",
                    "success": True,
                    "data": [],
                    "metadata": {
                        "tool_name": "query_xcai_city_history",
                        "cities": cities,
                        "data_type": data_type,
                        "table": table_name,
                        "time_range": f"{start_time} to {end_time}",
                        "message": "查询成功但无数据返回"
                    },
                    "summary": f"未找到 {', '.join(cities)} 在指定时间段的{data_type}数据"
                }

            logger.info(
                "query_xcai_city_history_data_received",
                raw_count=len(raw_records)
            )

            # Step 3: 字段标准化（使用 data_standardizer）
            standardizer = get_data_standardizer()
            standardized_records = standardizer.standardize(raw_records)

            logger.info(
                "query_xcai_city_history_data_standardized",
                raw_count=len(raw_records),
                standardized_count=len(standardized_records)
            )

            # Step 4: 保存数据（返回 data_id）
            data_id = context.data_manager.save_data(
                data=standardized_records,
                schema="air_quality_unified",
                metadata={
                    "source": "xcai_sql_server",
                    "table": table_name,
                    "cities": cities,
                    "time_range": f"{start_time} to {end_time}",
                    "data_type": data_type,
                    "schema_version": "v2.0",
                    "field_mapping_applied": True,
                    "field_mapping_info": standardizer.get_field_mapping_info() if standardizer else {}
                }
            )

            logger.info(
                "query_xcai_city_history_data_saved",
                data_id=data_id,
                record_count=len(standardized_records)
            )

            # Step 5: 返回结果（前24条供预览）
            preview_count = min(24, len(standardized_records))
            return {
                "status": "success",
                "success": True,
                "data": standardized_records[:preview_count],
                "metadata": {
                    "tool_name": "query_xcai_city_history",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": preview_count,
                    "cities": cities,
                    "data_type": data_type,
                    "table": table_name,
                    "time_range": f"{start_time} to {end_time}",
                    "schema_version": "v2.0",
                    "source": "xcai_sql_server",
                    "field_mapping_applied": True
                },
                "summary": f"成功查询 {', '.join(cities)} 的{data_type}数据共 {len(standardized_records)} 条，已保存为 {data_id}"
            }

        except Exception as e:
            logger.error(
                "query_xcai_city_history_failed",
                error=str(e),
                error_type=type(e).__name__,
                cities=cities,
                data_type=data_type
            )
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "data": None,
                "metadata": {
                    "tool_name": "query_xcai_city_history",
                    "cities": cities,
                    "data_type": data_type,
                    "time_range": f"{start_time} to {end_time}"
                },
                "summary": f"XcAiDb城市历史数据查询失败: {str(e)}"
            }
