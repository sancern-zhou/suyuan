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
            "description": (
                "查询广东省城市级小时空气质量数据，适合时序、过程追溯、区域传输和多城市小时对比。"
                "城市名自动映射编码；根据结束时间自动判断数据源；include_weather默认true。"
                "站点级小时数据用query_gd_suncere_station_hour_new。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，格式 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，格式 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "include_weather": {
                        "type": "boolean",
                        "description": "是否包含气象字段，默认true"
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
        include_weather: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行城市小时数据查询

        Args:
            context: 执行上下文
            cities: 城市名称列表
            start_time: 开始时间
            end_time: 结束时间
            include_weather: 是否包含气象字段

        Returns:
            UDF v2.0格式的查询结果
        """
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_hour

        logger.info(
            "query_gd_suncere_city_hour_tool_start",
            cities=cities,
            start_time=start_time,
            end_time=end_time,
            include_weather=include_weather,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用现有的查询函数（同步函数，直接调用）
        result = execute_query_gd_suncere_station_hour(
            cities=cities,
            start_time=start_time,
            end_time=end_time,
            context=context,
            include_weather=include_weather
        )

        return result


class QueryGDSuncereStationHourTool(LLMTool):
    """
    广东省站点小时数据查询工具

    用于查询广东省站点级别的小时空气质量数据
    LLM 只传城市名，工具内部自动展开为站点代码
    """

    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_station_hour_new",
            "description": (
                "查询广东省站点级小时空气质量数据，基于HJ 633-2026计算IAQI/AQI/首要污染物。"
                "用户提到具体站点或需要站点级小时数据时使用；城市聚合小时数据用query_gd_suncere_city_hour。"
                "cities和stations至少提供一个；station_type仅cities时生效；include_weather默认true。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "station_type": {
                        "type": "string",
                        "description": "站点类型，仅cities时生效，默认国控"
                    },
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市列表，可自动展开站点"
                    },
                    "stations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "站点名称列表，使用时不需要station_type"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，格式 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，格式 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "include_weather": {
                        "type": "boolean",
                        "description": "是否包含气象字段，默认true"
                    }
                },
                "required": ["start_time", "end_time"]
            }
        }

        super().__init__(
            name="query_gd_suncere_station_hour_new",
            description="Query Guangdong station hourly air quality data (HJ 633-2026 new standard) - Suncere API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: ExecutionContext,
        start_time: str,
        end_time: str,
        station_type: Optional[str] = None,
        cities: Optional[List[str]] = None,
        stations: Optional[List[str]] = None,
        include_weather: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行站点小时数据查询

        Args:
            context: 执行上下文
            start_time: 开始时间
            end_time: 结束时间
            station_type: 站点类型（可选，仅在使用cities时有效，默认国控）
            cities: 城市名称列表（与stations至少提供一个）
            stations: 站点名称列表（与cities至少提供一个）
            include_weather: 是否包含气象字段

        Returns:
            UDF v2.0格式的查询结果
        """
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_hour_real

        # 验证cities或stations至少提供一个
        if not cities and not stations:
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "summary": "必须提供cities或stations参数。为避免数据量过大，不支持全省查询。请指定具体城市或站点。",
                "metadata": {
                    "error": "Missing cities or stations parameter",
                    "suggestion": "请提供需要查询的城市或站点"
                }
            }

        # 智能推断 station_type
        # 规则1: 如果使用 stations 参数，不需要 station_type（站点名称已确定类型）
        # 规则2: 如果只使用 cities 参数且没有 station_type，默认使用"国控"
        if stations and not cities:
            # 场景1: 只提供站点名称，不需要 station_type
            if station_type:
                logger.warning(
                    "query_gd_suncere_station_hour_ignored_station_type",
                    reason="使用stations参数时，station_type将被忽略",
                    stations=stations,
                    provided_station_type=station_type
                )
            # 不传递 station_type
            effective_station_type = None
        elif cities and not stations:
            # 场景2: 只提供城市名称，使用默认的"国控"或用户指定的 station_type
            effective_station_type = station_type or "国控"
        else:
            # 场景3: 同时提供 cities 和 stations，使用用户指定的 station_type（如果有）
            effective_station_type = station_type

        logger.info(
            "query_gd_suncere_station_hour_tool_start",
            cities=cities,
            stations=stations,
            station_type=station_type,
            effective_station_type=effective_station_type,
            start_time=start_time,
            end_time=end_time,
            include_weather=include_weather,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        result = execute_query_gd_suncere_station_hour_real(
            start_time=start_time,
            end_time=end_time,
            context=context,
            cities=cities,
            stations=stations,
            station_type=effective_station_type,
            include_weather=include_weather
        )

        return result


class QueryGDSuncereStationDayTool(LLMTool):
    """
    广东省站点日数据查询工具

    用于查询广东省站点级别的日空气质量数据
    """

    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_station_day_new",
            "description": (
                "查询广东省站点级日空气质量数据，基于HJ 633-2026计算IAQI/AQI/首要污染物。"
                "用户提到具体站点或需要站点级日均数据时使用；城市聚合日数据用query_gd_suncere_city_day_new。"
                "cities和stations至少提供一个；station_type仅cities时生效。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "station_type": {
                        "type": "string",
                        "description": "站点类型，仅cities时生效，默认国控"
                    },
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市列表，可自动展开站点"
                    },
                    "stations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "站点名称列表，使用时不需要station_type"
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
                "required": ["start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_gd_suncere_station_day_new",
            description="Query Guangdong station daily air quality data (HJ 633-2026 new standard) - Suncere API",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: ExecutionContext,
        start_date: str,
        end_date: str,
        station_type: Optional[str] = None,
        cities: Optional[List[str]] = None,
        stations: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行站点日数据查询

        Args:
            context: 执行上下文
            start_date: 开始日期
            end_date: 结束日期
            station_type: 站点类型（可选，仅在使用cities时有效，默认国控）
            cities: 城市名称列表（与stations至少提供一个）
            stations: 站点名称列表（与cities至少提供一个）

        Returns:
            UDF v2.0格式的查询结果
        """
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_day

        # 验证cities或stations至少提供一个
        if not cities and not stations:
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "summary": "必须提供cities或stations参数。为避免数据量过大，不支持全省查询。请指定具体城市或站点。",
                "metadata": {
                    "error": "Missing cities or stations parameter",
                    "suggestion": "请提供需要查询的城市或站点"
                }
            }

        # 智能推断 station_type
        # 规则1: 如果使用 stations 参数，不需要 station_type（站点名称已确定类型）
        # 规则2: 如果只使用 cities 参数且没有 station_type，默认使用"国控"
        if stations and not cities:
            # 场景1: 只提供站点名称，不需要 station_type
            if station_type:
                logger.warning(
                    "query_gd_suncere_station_day_ignored_station_type",
                    reason="使用stations参数时，station_type将被忽略",
                    stations=stations,
                    provided_station_type=station_type
                )
            # 不传递 station_type
            effective_station_type = None
        elif cities and not stations:
            # 场景2: 只提供城市名称，使用默认的"国控"或用户指定的 station_type
            effective_station_type = station_type or "国控"
        else:
            # 场景3: 同时提供 cities 和 stations，使用用户指定的 station_type（如果有）
            effective_station_type = station_type

        logger.info(
            "query_gd_suncere_station_day_tool_start",
            cities=cities,
            stations=stations,
            station_type=station_type,
            effective_station_type=effective_station_type,
            start_date=start_date,
            end_date=end_date,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        result = execute_query_gd_suncere_station_day(
            start_date=start_date,
            end_date=end_date,
            context=context,
            cities=cities,
            stations=stations,
            station_type=effective_station_type
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
            "description": (
                "查询广东省目标城市与周边城市小时数据，用于区域传输、本地生成与外部输送对比。"
                "城市名自动映射编码；根据结束时间自动判断数据源。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_city": {
                        "type": "string",
                        "description": "目标城市名称"
                    },
                    "nearby_cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "周边城市名称列表"
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
            "description": (
                "查询广东省城市级日空气质量数据，适合日变化、多城市日均对比和长时间序列分析。"
                "城市名自动映射编码；data_type默认审核实况1；enable_sand_deduction默认true。"
                "需要新标准日数据优先用query_gd_suncere_city_day_new。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表"
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
                    },
                    "enable_sand_deduction": {
                        "type": "boolean",
                        "description": "是否启用扣沙处理，默认true"
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
            data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认1
            **kwargs: 工具参数
                - enable_sand_deduction: 是否启用扣沙处理（默认true）

        Returns:
            UDF v2.0格式的查询结果
        """
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_city_day

        # 提取可选参数
        enable_sand_deduction = kwargs.get("enable_sand_deduction", True)  # 默认true

        logger.info(
            "query_gd_suncere_city_day_tool_start",
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type,
            enable_sand_deduction=enable_sand_deduction,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用现有的查询函数（同步函数，直接调用）
        result = execute_query_gd_suncere_city_day(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            context=context,
            data_type=data_type,
            enable_sand_deduction=enable_sand_deduction
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
            "description": (
                "【第一优先级】查询同一时间段的新旧空气质量标准统计对比。"
                "返回新旧标准综合指数、超标天数、达标率和统计浓度差异；不要手算。"
                "result可直接用于报告；data_id仅保存日报明细。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 'YYYY-MM-DD'"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 'YYYY-MM-DD'"
                    },
                    "enable_sand_deduction": {
                        "type": "boolean",
                        "description": "是否启用扣沙处理，默认true"
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
            **kwargs: 工具参数
                - enable_sand_deduction: 是否启用扣沙处理（默认true）

        Returns:
            新旧标准对比结果
        """
        from app.tools.query.query_gd_suncere.tool import execute_query_standard_comparison

        # 提取可选参数
        enable_sand_deduction = kwargs.get("enable_sand_deduction", True)  # 默认true

        logger.info(
            "query_standard_comparison_tool_start",
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            enable_sand_deduction=enable_sand_deduction,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用核心实现函数
        result = await execute_query_standard_comparison(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            context=context,
            enable_sand_deduction=enable_sand_deduction
        )

        return result


class QueryGDSuncereCityDayNewStandardTool(LLMTool):
    """
    广东省城市日数据查询工具（新标准 HJ 633-2026）

    查询广东省城市级别的日空气质量数据，并自动更新为新标准字段。
    """

    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_city_day_new",
            "description": (
                "查询广东省城市级日空气质量数据，并按HJ 633-2026新标准计算IAQI/AQI/首要污染物。"
                "需要新标准日报或新旧标准分析时优先使用；城市名自动映射编码。"
                "data_type默认审核实况1；enable_sand_deduction默认true。统计报表优先用query_new_standard_report。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表"
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
                    },
                    "enable_sand_deduction": {
                        "type": "boolean",
                        "description": "是否启用扣沙处理，默认true"
                    }
                },
                "required": ["cities", "start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_gd_suncere_city_day_new",
            description="Query Guangdong city daily air quality data (New Standard HJ 633-2026) - Suncere API",
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
            data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认1
            **kwargs: 工具参数
                - enable_sand_deduction: 是否启用扣沙处理（默认true）

        Returns:
            UDF v2.0 格式的查询结果
        """
        from app.tools.query.query_gd_suncere.tool_city_day_new import execute_query_city_day_new_standard

        # 提取可选参数
        enable_sand_deduction = kwargs.get("enable_sand_deduction", True)  # 默认true
        from app.tools.query.query_gd_suncere.tool_city_day_new import execute_query_city_day_new_standard

        logger.info(
            "query_gd_suncere_city_day_new_tool_start",
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type,
            enable_sand_deduction=enable_sand_deduction,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用核心实现函数（async）
        result = await execute_query_city_day_new_standard(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            context=context,
            data_type=data_type,
            enable_sand_deduction=enable_sand_deduction
        )

        return result


class QueryGDSuncereCityDayOldStandardTool(LLMTool):
    """
    广东省城市日数据查询工具（旧标准：十三五/十四五）

    查询广东省城市日空气质量数据，支持十三五和十四五两种标准。
    """

    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_city_day_old_standard",
            "description": """
查询广东省城市日空气质量数据（旧标准：十三五/十四五）。

【核心功能】
- 查询广东省城市的日级别空气质量统计数据
- 支持十三五（planType=135）和十四五（planType=0）两种标准
- 返回综合统计报表数据

【规划类型】
- planType=0: 十四五标准（默认）
- planType=135: 十三五标准

【数据源】
- data_source=1: 审核实况（默认）
- data_source=0: 原始实况

【使用场景】
- 历史数据对比分析（十三五 vs 十四五）
- 旧标准数据查询
- 统计报表生成

【输入参数】
- cities: 城市名称列表（如 ["广州", "深圳", "佛山"]）
- start_date: 开始日期，格式 "YYYY-MM-DD"
- end_date: 结束日期，格式 "YYYY-MM-DD"
- plan_type: 规划类型（0=十四五默认, 135=十三五）
- data_source: 数据源（1=审核实况默认, 0=原始实况）

【重要】
- 返回综合统计数据，非原始日数据
- 返回 UDF v2.0 标准格式数据
- 可直接传递给可视化工具
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
                    "plan_type": {
                        "type": "integer",
                        "description": "规划类型：0=十四五（默认），135=十三五",
                        "enum": [0, 135]
                    },
                    "data_source": {
                        "type": "integer",
                        "description": "数据源：1=审核实况（默认），0=原始实况",
                        "enum": [0, 1]
                    }
                },
                "required": ["cities", "start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_gd_suncere_city_day_old_standard",
            description="Query Guangdong city daily air quality data (Old Standard: 13th/14th Five-Year Plan)",
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
        plan_type: int = 0,
        data_source: int = 1,
        **kwargs
    ) -> Dict[str, Any]:
        """执行查询"""
        from app.tools.query.query_gd_suncere.tool_city_day_old_standard import execute_query_city_day_old_standard

        logger.info(
            "query_gd_suncere_city_day_old_standard_tool_start",
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            plan_type=plan_type,
            data_source=data_source,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        result = await execute_query_city_day_old_standard(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            context=context,
            plan_type=plan_type,
            data_source=data_source
        )

        return result


class QueryGDSuncereOldStandardReportTool(LLMTool):
    """
    旧标准统计报表查询工具（HJ 633-2013）

    查询基于旧标准的空气质量统计报表，返回旧标准综合指数、超标天数、首要污染物等统计指标。
    """

    def __init__(self):
        function_schema = {
            "name": "query_old_standard_report",
            "description": (
                "【第一优先级】查询HJ 633-2013旧标准空气质量统计报表。"
                "用于综合指数、超标天数、达标率、六参数统计浓度、首要污染物等统计结果；不要手算。"
                "result返回统计汇总，可直接用于分析和报告；data_id仅保存日报明细。"
                "默认旧综合指数算法为所有污染物权重1，可选使用新综合指数算法。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 'YYYY-MM-DD'"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 'YYYY-MM-DD'"
                    },
                    "enable_sand_deduction": {
                        "type": "boolean",
                        "description": "是否启用扣沙处理，默认true"
                    },
                    "use_new_composite_algorithm": {
                        "type": "boolean",
                        "description": "是否使用新综合指数算法，默认false"
                    }
                },
                "required": ["cities", "start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_old_standard_report",
            description="Query old standard (HJ 633-2013) air quality statistical report - Suncere API",
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
        """执行旧标准统计报表查询"""
        from app.tools.query.query_gd_suncere.tool_city_day_old_standard_report import execute_query_old_standard_report

        # 提取可选参数
        enable_sand_deduction = kwargs.get("enable_sand_deduction", True)  # 默认true
        use_new_composite_algorithm = kwargs.get("use_new_composite_algorithm", False)  # 默认false（使用旧算法）

        logger.info(
            "query_old_standard_report_tool_start",
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            enable_sand_deduction=enable_sand_deduction,
            use_new_composite_algorithm=use_new_composite_algorithm,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        # 调用核心实现函数（async）
        result = await execute_query_old_standard_report(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            enable_sand_deduction=enable_sand_deduction,
            use_new_composite_algorithm=use_new_composite_algorithm,
            context=context
        )

        return result
