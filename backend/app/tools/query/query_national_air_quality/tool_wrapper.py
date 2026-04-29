"""
全国省份空气质量数据查询工具注册模块

从参考项目 GDQFWS_SYS 获取全国各省份的六参数均值、AQI达标率和综合指数
"""
from typing import Dict, Any, List, Optional
import structlog
from datetime import datetime

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext


logger = structlog.get_logger()


class QueryNationalProvinceAirQualityTool(LLMTool):
    """
    全国省份空气质量数据查询工具

    从参考项目 GDQFWS_SYS 获取全国各省份的六参数均值、AQI达标率和综合指数
    """

    def __init__(self):
        function_schema = {
            "name": "query_national_province_air_quality",
            "description": (
                "查询全国省份空气质量统计数据，返回六参数均值、综合指数SumIndex和AQI达标率。"
                "用于省份排名、区域对比和达标率统计；数据来源为全国发布数据，-99表示缺失。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 'YYYY-MM-DD'"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 'YYYY-MM-DD'"
                    },
                    "ns_type": {
                        "type": "string",
                        "description": "数据类型，默认NS",
                        "enum": ["NS", "NSDay", "OldNS"],
                        "default": "NS"
                    }
                },
                "required": ["start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_national_province_air_quality",
            description="Query national province air quality statistics - GDQFWS System",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False  # 不需要ExecutionContext
        )

    async def execute(
        self,
        start_date: str,
        end_date: str,
        ns_type: str = "NS",
        context: Optional[ExecutionContext] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行全国省份空气质量数据查询

        Args:
            context: 执行上下文（可选）
            start_date: 开始日期
            end_date: 结束日期
            ns_type: 数据类型

        Returns:
            查询结果字典
        """
        from app.tools.query.query_national_air_quality import get_national_air_quality_tool

        logger.info(
            "query_national_province_air_quality_start",
            start_date=start_date,
            end_date=end_date,
            ns_type=ns_type,
            session_id=getattr(context, 'session_id', 'unknown') if context else 'unknown'
        )

        try:
            # 获取工具实例
            tool = get_national_air_quality_tool()

            # 调用查询方法
            data = tool.query_province_data(
                start_date=start_date,
                end_date=end_date,
                ns_type=ns_type
            )

            logger.info(
                "query_national_province_air_quality_success",
                province_count=len(data)
            )

            # 返回标准格式结果
            return {
                "status": "success",
                "success": True,
                "data": data,
                "summary": f"成功获取{len(data)}个省份的空气质量统计数据"
            }

        except Exception as e:
            logger.error(
                "query_national_province_air_quality_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "summary": f"查询失败: {str(e)}"
            }


class QueryNationalCityAirQualityTool(LLMTool):
    """
    全国城市空气质量数据查询工具

    从参考项目 GDQFWS_SYS 获取全国各城市的六参数均值、AQI达标率和综合指数
    """

    def __init__(self):
        function_schema = {
            "name": "query_national_city_air_quality",
            "description": (
                "查询全国城市空气质量统计数据，返回六参数均值、综合指数SumIndex和AQI达标率。"
                "用于城市排名、城市对比和省内城市统计；可用province_code筛选，数据来源为全国发布数据。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 'YYYY-MM-DD'"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 'YYYY-MM-DD'"
                    },
                    "province_code": {
                        "type": "string",
                        "description": "省份代码；不填查询全国城市"
                    },
                    "ns_type": {
                        "type": "string",
                        "description": "数据类型，默认NS",
                        "enum": ["NS", "NSDay", "OldNS"],
                        "default": "NS"
                    }
                },
                "required": ["start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_national_city_air_quality",
            description="Query national city air quality statistics - GDQFWS System",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

    async def execute(
        self,
        start_date: str,
        end_date: str,
        province_code: Optional[str] = None,
        ns_type: str = "NS",
        context: Optional[ExecutionContext] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行全国城市空气质量数据查询

        Args:
            context: 执行上下文（可选）
            start_date: 开始日期
            end_date: 结束日期
            province_code: 省份代码（可选）
            ns_type: 数据类型

        Returns:
            查询结果字典
        """
        from app.tools.query.query_national_air_quality import get_national_air_quality_tool

        logger.info(
            "query_national_city_air_quality_start",
            start_date=start_date,
            end_date=end_date,
            province_code=province_code,
            ns_type=ns_type
        )

        try:
            # 获取工具实例
            tool = get_national_air_quality_tool()

            # 调用查询方法
            data = tool.query_city_data(
                start_date=start_date,
                end_date=end_date,
                province_code=province_code,
                ns_type=ns_type
            )

            logger.info(
                "query_national_city_air_quality_success",
                city_count=len(data)
            )

            return {
                "status": "success",
                "success": True,
                "data": data,
                "summary": f"成功获取{len(data)}个城市的空气质量统计数据"
            }

        except Exception as e:
            logger.error(
                "query_national_city_air_quality_failed",
                error=str(e)
            )
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "summary": f"查询失败: {str(e)}"
            }
