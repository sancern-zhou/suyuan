"""
广东省 Suncere API 查询工具注册模块

将现有的查询函数包装为 LLMTool，供 Agent 调用
"""
from typing import Dict, Any, List, Optional
import structlog
from datetime import datetime

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext


logger = structlog.get_logger()


class QueryGDSuncereCityHourTool(LLMTool):
    """
    广东省城市小时数据查询工具

    用于查询广东省城市级别的小时空气质量数据
    """

    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_city_hour",
            "description": """
查询广东省城市小时空气质量数据。

【核心功能】
- 查询广东省城市的小时级别空气质量数据
- 支持多城市并发查询
- 城市/站点名称自动映射到编码
- 根据查询时间自动判断数据源（原始实况/审核实况）

【使用场景】
- 城市空气质量时序分析
- 区域传输分析
- 多城市对比分析
- 污染过程追溯

【输入参数】
- cities: 城市名称列表（如 ["广州", "深圳", "佛山"]）
- start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
- end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"

【重要】
- 工具会自动将城市名称转换为编码
- 工具会自动根据结束时间判断数据源类型
- 返回 UDF v2.0 标准格式数据

示例：
cities=["广州", "深圳", "佛山"]
start_time="2026-02-01 00:00:00"
end_time="2026-02-01 23:59:59"

【返回数据】
- data_id: 数据引用ID（UDF v2.0格式）
- 包含多城市的小时级别污染物数据
- 可直接传递给可视化工具生成时序图
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表，如 ['广州', '深圳', '佛山']"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，格式 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，格式 'YYYY-MM-DD HH:MM:SS'"
                    }
                },
                "required": ["cities", "start_time", "end_time"]
            }
        }

        super().__init__(
            name="query_gd_suncere_city_hour",
            description="Query Guangdong city hourly air quality data - Suncere API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    def execute(
        self,
        context: ExecutionContext,
        cities: List[str],
        start_time: str,
        end_time: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行城市小时数据查询

        Args:
            context: 执行上下文
            cities: 城市名称列表
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            UDF v2.0格式的查询结果
        """
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_hour

        logger.info(
            "query_gd_suncere_city_hour_tool_start",
            cities=cities,
            start_time=start_time,
            end_time=end_time,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用现有的查询函数
        result = execute_query_gd_suncere_station_hour(
            cities=cities,
            start_time=start_time,
            end_time=end_time,
            context=context
        )

        return result


class QueryGDSuncereRegionalComparisonTool(LLMTool):
    """
    广东省区域对比数据查询工具

    用于查询目标城市与周边城市的对比数据
    """

    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_regional_comparison",
            "description": """
查询广东省区域对比空气质量数据。

【核心功能】
- 查询目标城市与周边城市的小时数据
- 用于区域传输分析
- 自动判断数据源类型
- 返回统一格式数据

【使用场景】
- 区域传输分析（本地生成 vs 外部输送）
- 目标城市与周边城市对比
- 污染来源溯源分析

【输入参数】
- target_city: 目标城市名称（如 "广州"）
- nearby_cities: 周边城市名称列表（如 ["佛山", "深圳", "东莞"]）
- start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
- end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"

【重要】
- 工具会自动将城市名称转换为编码
- 工具会自动根据结束时间判断数据源类型
- 返回 UDF v2.0 标准格式数据

示例：
target_city="广州"
nearby_cities=["佛山", "深圳", "东莞", "清远"]
start_time="2026-02-01 00:00:00"
end_time="2026-02-01 23:59:59"

【返回数据】
- data_id: 数据引用ID（UDF v2.0格式）
- 包含目标城市和周边城市的小时数据
- 可直接用于区域传输分析
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_city": {
                        "type": "string",
                        "description": "目标城市名称，如 '广州'"
                    },
                    "nearby_cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "周边城市名称列表，如 ['佛山', '深圳', '东莞']"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，格式 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，格式 'YYYY-MM-DD HH:MM:SS'"
                    }
                },
                "required": ["target_city", "nearby_cities", "start_time", "end_time"]
            }
        }

        super().__init__(
            name="query_gd_suncere_regional_comparison",
            description="Query Guangdong regional comparison air quality data - Suncere API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    def execute(
        self,
        context: ExecutionContext,
        target_city: str,
        nearby_cities: List[str],
        start_time: str,
        end_time: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行区域对比数据查询

        Args:
            context: 执行上下文
            target_city: 目标城市名称
            nearby_cities: 周边城市名称列表
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            UDF v2.0格式的查询结果
        """
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_regional_comparison

        logger.info(
            "query_gd_suncere_regional_comparison_tool_start",
            target_city=target_city,
            nearby_cities=nearby_cities,
            start_time=start_time,
            end_time=end_time,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用现有的查询函数
        result = execute_query_gd_suncere_regional_comparison(
            target_city=target_city,
            nearby_cities=nearby_cities,
            start_time=start_time,
            end_time=end_time,
            context=context
        )

        return result
