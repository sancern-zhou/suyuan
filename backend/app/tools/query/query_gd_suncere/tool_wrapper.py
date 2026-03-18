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

    async def execute(
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

        # 调用现有的查询函数（同步函数，直接调用）
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

    async def execute(
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

        # 调用现有的查询函数（同步函数，直接调用）
        result = execute_query_gd_suncere_regional_comparison(
            target_city=target_city,
            nearby_cities=nearby_cities,
            start_time=start_time,
            end_time=end_time,
            context=context
        )

        return result


class QueryGDSuncereCityDayTool(LLMTool):
    """
    广东省城市日数据查询工具

    用于查询广东省城市级别的日空气质量数据
    """

    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_city_day",
            "description": """
查询广东省城市日空气质量数据。

【核心功能】
- 查询广东省城市的日级别空气质量数据
- 支持多城市并发查询
- 城市/站点名称自动映射到编码
- 适合查询日报、月报、季报、年报数据

【使用场景】
- 城市空气质量日变化分析
- 多城市日均数据对比
- 长时间序列趋势分析
- 日报数据查询

【输入参数】
- cities: 城市名称列表（如 ["广州", "深圳", "佛山"]）
- start_date: 开始日期，格式 "YYYY-MM-DD"
- end_date: 结束日期，格式 "YYYY-MM-DD"
- data_type: 数据类型（可选，默认1）
  - 0: 原始实况
  - 1: 审核实况（默认）
  - 2: 原始标况
  - 3: 审核标况

【重要】
- 工具会自动将城市名称转换为编码
- 返回 UDF v2.0 标准格式数据
- 日数据包含PM2.5、PM10、SO2、NO2、O3、CO等污染物的日均值

示例：
cities=["广州", "深圳", "佛山"]
start_date="2026-02-01"
end_date="2026-02-28"
data_type=1  # 查询审核实况数据（默认）

【返回数据】
- data_id: 数据引用ID（UDF v2.0格式）
- 包含多城市的日级别污染物数据
- 可直接传递给可视化工具生成趋势图
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表，如 ['广州', '深圳', '佛山']"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 'YYYY-MM-DD'"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 'YYYY-MM-DD'"
                    },
                    "data_type": {
                        "type": "integer",
                        "description": "数据类型：0原始实况，1审核实况（默认），2原始标况，3审核标况",
                        "enum": [0, 1, 2, 3]
                    }
                },
                "required": ["cities", "start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_gd_suncere_city_day",
            description="Query Guangdong city daily air quality data - Suncere API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: ExecutionContext,
        cities: List[str],
        start_date: str,
        end_date: str,
        data_type: int = 1,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行城市日数据查询

        Args:
            context: 执行上下文
            cities: 城市名称列表
            start_date: 开始日期
            end_date: 结束日期
            data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认0

        Returns:
            UDF v2.0格式的查询结果
        """
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_city_day

        logger.info(
            "query_gd_suncere_city_day_tool_start",
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用现有的查询函数（同步函数，直接调用）
        result = execute_query_gd_suncere_city_day(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            context=context,
            data_type=data_type
        )

        return result


class QueryGDSuncereReportTool(LLMTool):
    """
    广东省综合统计报表查询工具

    用于查询广东省综合统计报表数据（周报、月报、季报、年报、任意时间）
    """

    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_report",
            "description": """
查询广东省综合统计报表数据。

【核心功能】
- 查询广东省综合统计报表数据（周报、月报、季报、年报、任意时间）
- 支持多城市并发查询
- 支持站点/区县/城市三种区域类型
- 支持污染物字段过滤
- 自动判断数据源类型

【使用场景】
- 城市空气质量周报、月报、季报、年报查询
- 任意时间段综合统计分析
- 多城市综合指数对比
- 污染物浓度统计汇总

【输入参数】
- cities: 城市名称列表（如 ["广州", "深圳", "佛山"]）
- start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
- end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"
- time_type: 报表类型（可选，默认8）
  * 3=周报, 4=月报, 5=季报, 7=年报, 8=任意时间
- area_type: 区域类型（可选，默认2）
  * 0=站点, 1=区县, 2=城市
- pollutant_codes: 污染物代码列表（可选），如 ["PM2.5", "SO2"]

【重要】
- 工具会自动将城市名称转换为编码
- 工具会自动根据结束时间判断数据源类型
- 返回 UDF v2.0 标准格式数据
- 综合报表包含综合指数、污染物浓度、达标天数等统计指标

示例：
cities=["广州", "深圳", "佛山"]
start_time="2026-02-01 00:00:00"
end_time="2026-02-28 23:59:59"
time_type=8  # 任意时间报表

【返回数据】
- data_id: 数据引用ID（UDF v2.0格式）
- 包含多城市的综合统计数据
- 包含综合指数、各污染物浓度、达标天数等指标
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
                    },
                    "time_type": {
                        "type": "integer",
                        "description": "报表类型：3=周报, 4=月报, 5=季报, 7=年报, 8=任意时间（默认8）",
                        "enum": [3, 4, 5, 7, 8]
                    },
                    "area_type": {
                        "type": "integer",
                        "description": "区域类型：0=站点, 1=区县, 2=城市（默认2）",
                        "enum": [0, 1, 2]
                    },
                    "pollutant_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "污染物代码列表（可选），如 ['PM2.5', 'SO2', 'NO2']"
                    }
                },
                "required": ["cities", "start_time", "end_time"]
            }
        }

        super().__init__(
            name="query_gd_suncere_report",
            description="Query Guangdong comprehensive statistical report data - Suncere API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: ExecutionContext,
        cities: List[str],
        start_time: str,
        end_time: str,
        time_type: int = 8,
        area_type: int = 2,
        pollutant_codes: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行综合统计报表查询

        Args:
            context: 执行上下文
            cities: 城市名称列表
            start_time: 开始时间
            end_time: 结束时间
            time_type: 报表类型
            area_type: 区域类型
            pollutant_codes: 污染物代码列表

        Returns:
            UDF v2.0格式的查询结果
        """
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_report

        logger.info(
            "query_gd_suncere_report_tool_start",
            cities=cities,
            start_time=start_time,
            end_time=end_time,
            time_type=time_type,
            area_type=area_type,
            pollutant_codes=pollutant_codes,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用现有的查询函数（同步函数，直接调用）
        result = execute_query_gd_suncere_report(
            cities=cities,
            start_time=start_time,
            end_time=end_time,
            time_type=time_type,
            area_type=area_type,
            pollutant_codes=pollutant_codes,
            context=context
        )

        return result


class QueryGDSuncereReportCompareTool(LLMTool):
    """
    广东省对比分析报表查询工具

    用于查询广东省对比分析报表数据（月报、任意时间对比）
    """

    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_report_compare",
            "description": """
查询广东省对比分析报表数据。

【核心功能】
- 查询广东省对比分析报表数据（月报、任意时间对比）
- 支持多城市并发查询
- 支持站点/区县/城市三种区域类型
- 支持污染物字段过滤
- 返回当前时间段与对比时间段的数据对比

【使用场景】
- 同期对比分析（今年vs去年）
- 环比对比分析（本月vs上月）
- 季节性对比分析
- 污染物变化趋势分析

【输入参数】
- cities: 城市名称列表（如 ["广州", "深圳", "佛山"]）
- time_point: 当前时间范围，格式 ["YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM:SS"]
- contrast_time: 对比时间范围，格式 ["YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM:SS"]
- time_type: 报表类型（可选，默认8）
  * 4=月报, 8=任意时间
- area_type: 区域类型（可选，默认2）
  * 0=站点, 1=区县, 2=城市
- pollutant_codes: 污染物代码列表（可选）

【重要】
- 工具会自动将城市名称转换为编码
- 工具会自动根据时间判断数据源类型
- 返回数据包含当前值、对比值、增幅等对比指标
- 返回 UDF v2.0 标准格式数据

示例：
cities=["广州", "深圳", "佛山"]
time_point=["2026-02-01 00:00:00", "2026-02-28 23:59:59"]
contrast_time=["2025-02-01 00:00:00", "2025-02-28 23:59:59"]

【返回数据】
- data_id: 数据引用ID（UDF v2.0格式）
- 包含当前时间段和对比时间段的数据
- 包含对比值、增幅、排名变化等对比指标
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表，如 ['广州', '深圳', '佛山']"
                    },
                    "time_point": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "当前时间范围，格式 ['YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM:SS']"
                    },
                    "contrast_time": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "对比时间范围，格式 ['YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM:SS']"
                    },
                    "time_type": {
                        "type": "integer",
                        "description": "报表类型：4=月报, 8=任意时间（默认8）",
                        "enum": [4, 8]
                    },
                    "area_type": {
                        "type": "integer",
                        "description": "区域类型：0=站点, 1=区县, 2=城市（默认2）",
                        "enum": [0, 1, 2]
                    },
                    "pollutant_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "污染物代码列表（可选），如 ['PM2.5', 'SO2', 'NO2']"
                    }
                },
                "required": ["cities", "time_point", "contrast_time"]
            }
        }

        super().__init__(
            name="query_gd_suncere_report_compare",
            description="Query Guangdong comparative analysis report data - Suncere API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: ExecutionContext,
        cities: List[str],
        time_point: List[str],
        contrast_time: List[str],
        time_type: int = 8,
        area_type: int = 2,
        pollutant_codes: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行对比分析报表查询

        Args:
            context: 执行上下文
            cities: 城市名称列表
            time_point: 当前时间范围
            contrast_time: 对比时间范围
            time_type: 报表类型
            area_type: 区域类型
            pollutant_codes: 污染物代码列表

        Returns:
            UDF v2.0格式的查询结果
        """
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_report_compare

        logger.info(
            "query_gd_suncere_report_compare_tool_start",
            cities=cities,
            time_point=time_point,
            contrast_time=contrast_time,
            time_type=time_type,
            area_type=area_type,
            pollutant_codes=pollutant_codes,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用现有的查询函数（同步函数，直接调用）
        result = execute_query_gd_suncere_report_compare(
            cities=cities,
            time_point=time_point,
            contrast_time=contrast_time,
            time_type=time_type,
            area_type=area_type,
            pollutant_codes=pollutant_codes,
            context=context
        )

        return result


class QueryStandardComparisonTool(LLMTool):
    """
    新旧标准对比查询工具

    用于查询任意时间段内新旧空气质量标准的统计指标对比
    """

    def __init__(self):
        function_schema = {
            "name": "query_standard_comparison",
            "description": """
查询任意时间段内新旧空气质量标准的统计指标对比。

【核心功能】
- 并发查询日报数据和统计数据
- 返回新旧标准综合指数、超标天数、达标率对比
- 返回统计浓度值（SO2, NO2, PM10, CO, PM2_5, NO, NOx, O3_8h）

【新旧标准差异】
- PM2.5断点：IAQI=50时35→30μg/m³，IAQI=100时75→60μg/m³
- PM10断点：IAQI=100时150→120μg/m³
- 新标准综合指数：PM2.5权重3，O3权重2，NO2权重2，其他权重1

【输入参数】
- cities: 城市列表
- start_date: 开始日期 (YYYY-MM-DD)
- end_date: 结束日期 (YYYY-MM-DD)

【返回数据】
统计摘要包含：
- 旧标准统计（从接口）：compositeIndex, overDays, overRate, rank, validDays, pM2_5_Rank
- 新标准统计（计算）：新综合指数、新超标天数、新达标率
- 对比数据：综合指数变化、超标天数变化
- 统计浓度值：各污染物平均浓度
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表，如 ['广州', '深圳', '佛山']"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 'YYYY-MM-DD'"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 'YYYY-MM-DD'"
                    }
                },
                "required": ["cities", "start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_standard_comparison",
            description="Query air quality standard comparison",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: ExecutionContext,
        cities: List[str],
        start_date: str,
        end_date: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行新旧标准对比查询

        Args:
            context: 执行上下文
            cities: 城市名称列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            新旧标准对比结果
        """
        from app.tools.query.query_gd_suncere.tool import execute_query_standard_comparison

        logger.info(
            "query_standard_comparison_tool_start",
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用核心实现函数
        result = execute_query_standard_comparison(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            context=context
        )

        return result


class QueryGDSuncereCityDayNewStandardTool(LLMTool):
    """
    广东省城市日数据查询工具（新标准 HJ 633-2024）

    查询广东省城市级别的日空气质量数据，并自动更新为新标准字段。
    """

    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_city_day_new",
            "description": """
查询广东省城市日空气质量数据（新标准 HJ 633-2024）。

【核心功能】
- 查询广东省城市的日级别空气质量数据
- 自动更新为新标准（HJ 633-2024）字段
- 支持多城市并发查询
- 城市/站点名称自动映射到编码

【新标准变化】
- PM2.5 日平均(IAQI=100): 75 → 60 μg/m³
- PM10 日平均(IAQI=100): 150 → 120 μg/m³

【更新字段】
- measurements.PM2_5_IAQI → 新标准值
- measurements.PM10_IAQI → 新标准值
- measurements.AQI → 新标准值
- record.air_quality_level → 新标准等级
- record.primary_pollutant → 新标准首要污染物

【使用场景】
- 需要新标准数据的空气质量分析
- 新旧标准对比研究
- 符合最新规范的日报数据查询

【输入参数】
- cities: 城市名称列表（如 ["广州", "深圳", "佛山"]）
- start_date: 开始日期，格式 "YYYY-MM-DD"
- end_date: 结束日期，格式 "YYYY-MM-DD"
- data_type: 数据类型（可选，默认1）
  - 0: 原始实况
  - 1: 审核实况（默认）
  - 2: 原始标况
  - 3: 审核标况

【重要】
- 工具会自动将城市名称转换为编码
- 返回 UDF v2.0 标准格式数据
- IAQI/AQI 按新标准计算，向上进位取整数
- 日数据包含PM2.5、PM10、SO2、NO2、O3、CO等污染物的日均值

示例：
cities=["广州", "深圳", "佛山"]
start_date="2026-02-01"
end_date="2026-02-28"
data_type=1  # 查询审核实况数据（默认）

【返回数据】
- data_id: 数据引用ID（UDF v2.0格式）
- 包含多城市的日级别污染物数据
- 所有IAQI/AQI字段均为新标准值
- 可直接传递给可视化工具生成趋势图
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表，如 ['广州', '深圳', '佛山']"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 'YYYY-MM-DD'"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 'YYYY-MM-DD'"
                    },
                    "data_type": {
                        "type": "integer",
                        "description": "数据类型：0原始实况，1审核实况（默认），2原始标况，3审核标况",
                        "enum": [0, 1, 2, 3]
                    }
                },
                "required": ["cities", "start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_gd_suncere_city_day_new",
            description="Query Guangdong city daily air quality data (New Standard HJ 633-2024) - Suncere API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: ExecutionContext,
        cities: List[str],
        start_date: str,
        end_date: str,
        data_type: int = 1,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行城市日数据查询（新标准）

        Args:
            context: 执行上下文
            cities: 城市名称列表
            start_date: 开始日期
            end_date: 结束日期
            data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认0

        Returns:
            UDF v2.0 格式的查询结果
        """
        from app.tools.query.query_gd_suncere.tool_city_day_new import execute_query_city_day_new_standard

        logger.info(
            "query_gd_suncere_city_day_new_tool_start",
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用核心实现函数
        result = execute_query_city_day_new_standard(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            context=context,
            data_type=data_type
        )

        return result
