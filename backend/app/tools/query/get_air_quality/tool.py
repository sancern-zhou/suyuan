"""
Get Air Quality Tool

LLM可调用的空气质量查询工具

功能：
- 通过 Dify 工作流查询全国各城市空气质量数据
- 支持小时、日、月、年粒度查询
- 支持历史时间范围查询
- 支持Context-Aware V2架构（保存data_id供下游使用）
"""
from typing import Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.external_apis.dify_client import DifyClient
from app.utils.data_standardizer import get_data_standardizer

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetAirQualityTool(LLMTool):
    """
    空气质量查询工具

    给LLM提供查询空气质量数据的能力
    通过 Dify 工作流实时调用数据查询接口
    """

    def __init__(self):
        function_schema = {
            "name": "get_air_quality",
            "description": """
查询指定城市的空气质量数据（支持自然语言查询）。

【重要说明】
本工具查询城市级空气质量数据。如需查询**具体站点的空气质量数据**（如某监测站的PM2.5、NO2等监测值），请调用 `query_guangdong_air_quality` 工具。

支持查询：
- 小时、日、月、年粒度数据
- 历史任意时间范围的AQI、PM2.5、PM10、O3、NO2、SO2、CO等污染物数据
- 全国各城市空气质量数据

支持自然语言查询，示例：
- "查询广州昨日小时空气质量"
- "查询深圳今日空气质量"
- "查询惠州2025-08-09的空气质量"
- "查询北京本月的空气质量日报"

请使用自然语言描述您的查询需求，系统会自动理解并返回相应数据。

**Context-Aware V2**: 成功获取数据后，会自动保存data_id供下游工具使用。
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "自然语言查询问题，需包含：城市名称、时间范围、数据粒度（可选）。示例：'查询广州昨日小时空气质量'"
                    }
                },
                "required": ["question"]
            }
        }

        super().__init__(
            name="get_air_quality",
            description="Get air quality data via Dify workflow (Context-Aware V2)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.0.0",
            requires_context=True
        )

        self.client = DifyClient()

    async def execute(
        self,
        context: "ExecutionContext",
        question: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行空气质量查询（使用自然语言查询）

        Args:
            context: 执行上下文（Context-Aware V2）
            question: 自然语言查询问题，如"查询广州昨日小时空气质量"

        Returns:
            Dict: 统一数据格式的空气质量数据，包含：
                - success: 是否成功
                - data: UnifiedDataRecord列表
                - data_id: 数据存储ID（供下游使用）
                - metadata: 数据元信息
                - summary: 摘要信息
        """
        try:
            logger.info(
                "air_quality_query_started",
                question=question
            )

            # 调用 Dify API（使用 blocking 模式避免数据重复）
            response = await self.client.chat_messages(
                query=question,
                response_mode="blocking"
            )

            # 使用Dify数据适配器解析响应
            from app.schemas.dify_data_adapter import parse_dify_air_quality_data
            unified_data = parse_dify_air_quality_data(response)

            logger.info(
                "air_quality_query_successful",
                question=question,
                conversation_id=response.get("conversation_id"),
                record_count=len(unified_data.data)
            )

            # 【UDF v2.0】使用全局数据标准化器标准化数据
            # 核心原则：保留measurements嵌套结构，只标准化内部字段名
            # 修复：无论success标志如何，只要有数据就进行标准化
            standardized_records = []
            data_standardizer = None

            if unified_data.data and len(unified_data.data) > 0:
                # 获取数据标准化器
                data_standardizer = get_data_standardizer()

                # 标准化measurements内部字段，保留嵌套结构
                for record in unified_data.data:
                    # 标准化measurements中的字段名
                    standardized_measurements = {}
                    for key, value in record.measurements.items():
                        # 使用data_standardizer映射字段名
                        standard_key = data_standardizer._get_standard_field_name(key)
                        final_key = standard_key if standard_key else key
                        # 规范化值（去除空值标记、转换数值）
                        normalized_value = data_standardizer._normalize_value(value)
                        if normalized_value is not None:
                            standardized_measurements[final_key] = normalized_value

                    # 构建标准化后的记录（保留UnifiedDataRecord结构）
                    standardized_record = {
                        "timestamp": record.timestamp.strftime("%Y-%m-%d %H:%M:%S") if hasattr(record.timestamp, 'strftime') else str(record.timestamp),
                        "station_name": record.station_name,
                        "lat": record.lat,
                        "lon": record.lon,
                        "measurements": standardized_measurements,  # 已标准化但保留嵌套
                        "metadata": record.metadata or {}
                    }
                    standardized_records.append(standardized_record)

                logger.info(
                    "air_quality_data_standardized",
                    question=question,
                    original_count=len(unified_data.data),
                    standardized_count=len(standardized_records),
                    sample_measurements=standardized_records[0]["measurements"] if standardized_records else {}
                )

                # 生成数据样本（第一条记录，用于LLM快速了解数据结构）
                sample_record = None
                if standardized_records:
                    first = standardized_records[0]
                    sample_record = {
                        "station_name": first.get("station_name"),
                        "timestamp": first.get("timestamp"),
                        "measurements": first.get("measurements", {}),
                        "lat": first.get("lat"),
                        "lon": first.get("lon")
                    }

            # Context-Aware V2: 保存数据到执行上下文
            # 修复：即使success=False，只要数据存在就保存（处理Dify截断JSON的情况）
            if unified_data.data and len(unified_data.data) > 0:
                try:
                    data_ref = context.save_data(
                        data=standardized_records,
                        schema="air_quality_unified",
                        metadata={
                            "question": question,
                            "record_count": len(standardized_records),
                            "station_name": unified_data.metadata.station_name if unified_data.metadata else None,
                            "schema_version": "v2.0",  # UDF v2.0 标记
                            "field_mapping_applied": True,
                            "field_mapping_info": data_standardizer.get_field_mapping_info() if data_standardizer else {}
                        }
                    )
                    data_id = data_ref["data_id"]
                    file_path = data_ref["file_path"]
                    logger.info(
                        "air_quality_data_saved",
                        data_id=data_id,
                        file_path=file_path,
                        record_count=len(unified_data.data),
                        success_flag=unified_data.success
                    )

                    # UDF v2.0: 更新metadata中的data_id为正确的格式
                    result = unified_data.dict()
                    result["data"] = standardized_records  # 返回标准化数据
                    result["data_id"] = data_id

                    # 更新metadata中的data_id
                    if isinstance(result.get("metadata"), dict):
                        result["metadata"]["data_id"] = data_id
                        # 确保schema_version为v2.0
                        result["metadata"]["schema_version"] = "v2.0"
                        # 添加数据样本
                        result["metadata"]["sample_record"] = sample_record
                    else:
                        # 如果metadata不是字典，创建新的metadata
                        result["metadata"] = {
                            "data_id": data_id,
                            "schema_version": "v2.0",
                            "source": "dify_api",
                            "sample_record": sample_record
                        }

                    # 修改 summary 包含 data_id 和 file_path
                    if result.get("summary"):
                        result["summary"] = f"{result['summary']}，已保存为 {data_id}，文件路径: {file_path}。"

                    # 添加 file_path 到返回结果（供后续工具使用）
                    result["file_path"] = file_path

                    return result
                except Exception as save_error:
                    logger.warning(
                        "air_quality_data_save_failed",
                        error=str(save_error)
                    )

            return unified_data.dict()

        except Exception as e:
            logger.error(
                "air_quality_query_failed",
                question=question,
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
                    data_id=f"air_quality_error:{id(e)}",
                    data_type=DataType.AIR_QUALITY,
                    source="dify_api"
                ),
                summary=f"[ERROR] 空气质量查询失败: {str(e)[:50]}"
            ).dict()
