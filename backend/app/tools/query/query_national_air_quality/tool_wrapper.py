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
            "description": """
查询全国各省份空气质量统计数据（六参数均值、AQI达标率、综合指数）。

【核心功能】
- 查询全国31个省份的空气质量统计数据
- 返回各省份的SO2、NO2、CO、O3_8h、PM10、PM2.5均值
- 返回综合指数（SumIndex）
- 返回AQI达标率（AQIStandardRate）

【数据来源】
- 参考项目：GDQFWS_SYS（广东省环境监测中心预报预警系统）
- 数据库：SQL Server（10.10.10.135）
- 数据表：Air_CityAQIHistory_Day_Pub（城市发布日均数据源）

【使用场景】
- 全国省份空气质量排名
- 区域空气质量对比分析
- 省份间六参数浓度比较
- 省份达标率统计
- 综合指数趋势分析

【输入参数】
- start_date: 开始日期，格式 "YYYY-MM-DD"
- end_date: 结束日期，格式 "YYYY-MM-DD"
- ns_type: 数据类型（可选），默认"NS"（非实时），可选"NSDay"（非实时日均值）

【返回数据】
每个省份包含以下字段：
- AreaCode: 省份代码（如 440000 表示广东省）
- AreaName: 省份名称（如 "广东省"）
- SO2: SO2均值(μg/m³)
- NO2: NO2均值(μg/m³)
- CO: CO均值(mg/m³)
- O3_8h: O3_8h均值(μg/m³)
- PM10: PM10均值(μg/m³)
- PM2_5: PM2.5均值(μg/m³)
- SumIndex: 综合指数
- AQIStandardRate: AQI达标率(%)

【示例】
start_date="2024-03-01"
end_date="2024-03-31"
ns_type="NS"

【数据说明】
- 共31个省份（不含港澳台）
- 数据按省份代码排序
- -99 表示数据缺失
            """.strip(),
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
                        "description": "数据类型，默认'NS'（非实时），可选'NSDay'（非实时日均值）",
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
            "description": """
查询全国各城市空气质量统计数据（六参数均值、AQI达标率、综合指数）。

【核心功能】
- 查询全国城市（含地级市）的空气质量统计数据
- 返回各城市的SO2、NO2、CO、O3_8h、PM10、PM2.5均值
- 返回综合指数（SumIndex）
- 返回AQI达标率（AQIStandardRate）
- 支持按省份筛选

【数据来源】
- 参考项目：GDQFWS_SYS（广东省环境监测中心预报预警系统）
- 数据库：SQL Server（10.10.10.135）
- 数据表：Air_CityAQIHistory_Day_Pub（城市发布日均数据源）

【使用场景】
- 城市空气质量排名
- 城市间空气质量对比分析
- 省内城市对比分析
- 城市达标率统计
- 城市综合指数分析

【输入参数】
- start_date: 开始日期，格式 "YYYY-MM-DD"
- end_date: 结束日期，格式 "YYYY-MM-DD"
- province_code: 省份代码（可选），如 "440000" 表示广东省，不填则查询全国所有城市
- ns_type: 数据类型（可选），默认"NS"（非实时）

【返回数据】
每个城市包含以下字段：
- AreaCode: 城市代码（如 440100 表示广州市）
- AreaName: 城市名称（如 "广州市"）
- SO2、NO2、CO、O3_8h、PM10、PM2_5均值
- SumIndex: 综合指数
- AQIStandardRate: AQI达标率(%)

【示例】
# 查询全国所有城市
start_date="2024-03-01"
end_date="2024-03-31"

# 查询广东省内城市
start_date="2024-03-01"
end_date="2024-03-31"
province_code="440000"
            """.strip(),
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
                        "description": "省份代码（可选），如 '440000' 表示广东省，不填则查询全国所有城市"
                    },
                    "ns_type": {
                        "type": "string",
                        "description": "数据类型，默认'NS'（非实时）",
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
