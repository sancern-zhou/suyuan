"""
模板报告数据获取器 - 复用现有工具，通过ReAct Agent工具注册表
场景2核心组件
"""
from typing import Dict, Any, List
import structlog
import asyncio
from collections import defaultdict

from app.schemas.report_generation import ToolCall
from app.services.tool_executor import ToolExecutor
from app.agent.context.execution_context import ExecutionContext

logger = structlog.get_logger()


class TemplateDataFetcher:
    """模板报告数据获取器 - 复用工具层实现 UDF v2.0 + data_id 契约"""

    def __init__(self, tool_executor: ToolExecutor, context: ExecutionContext):
        """
        初始化数据获取器

        Args:
            tool_executor: 工具执行器（通过ReAct Agent工具注册表）
            context: 执行上下文（用于数据存储和data_id生成）
        """
        self.tool_executor = tool_executor
        self.context = context

    async def fetch_all(
        self,
        requirements: List[Dict[str, Any]],
        time_range: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        根据报告数据点需求，批量获取数据（使用工具层 + UDF v2.0）

        Args:
            requirements: 数据需求列表
            time_range: 目标时间范围

        Returns:
            Dict[str, Any]: 获取的数据（格式：{section_id: {data_points: {...}, data_id}})
        """
        logger.info(f"Fetching data for {len(requirements)} requirements via tools")

        results = {}

        # 按查询类型分组，优化工具调用
        grouped_queries = self._group_requirements(requirements)

        # 并行执行不同类型的查询（保持结果顺序与分组顺序一致）
        query_results = await asyncio.gather(
            *[self._execute_query_via_tools(qt, g, time_range) for qt, g in grouped_queries.items()],
            return_exceptions=True
        )

        for (query_type, group), query_result in zip(grouped_queries.items(), query_results):
            if isinstance(query_result, Exception):
                logger.error(f"Query failed for {query_type}: {query_result}")
                continue

            for req in group:
                section_id = req["section_id"]
                extracted = self._extract_data_from_tools(query_result, req)
                results[section_id] = extracted

        logger.info(f"Data fetching completed, {len(results)} sections processed")
        return results

    def _group_requirements(
        self,
        requirements: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        将数据点按查询类型分组，优化API调用

        Args:
            requirements: 数据需求列表

        Returns:
            Dict[str, List[Dict[str, Any]]]: 分组后的需求
        """
        groups = defaultdict(list)

        for req in requirements:
            query_type = req.get("query_type", "general")
            groups[query_type].append(req)

        return dict(groups)

    async def _execute_query_via_tools(
        self,
        query_type: str,
        requirements: List[Dict[str, Any]],
        time_range: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        通过工具层执行查询 - 返回UDF v2.0格式数据（无Mock）

        Args:
            query_type: 查询类型
            requirements: 该类型的需求列表
            time_range: 时间范围

        Returns:
            Dict[str, Any]: 标准化查询结果（含data_id）
        """
        # 构建自然语言查询
        question = self._build_query(query_type, requirements, time_range)

        logger.info(f"Executing query via tools: {question[:100]}...")

        # 映射查询类型到工具调用
        tool_call = self._map_query_type_to_tool(query_type, question, time_range)

        # 通过ToolExecutor执行工具（自动处理Context-Aware V2）
        # 注意：如果工具执行失败，这里会抛出异常，由fetch_all捕获
        result = await self.tool_executor.execute_via_context(
            context=self.context,
            tool_call=tool_call
        )

        logger.info(
            "tool_query_completed",
            query_type=query_type,
            data_id=getattr(result, "data_id", None),
            success=getattr(result, "success", None)
        )
        return result

    def _map_query_type_to_tool(
        self,
        query_type: str,
        question: str,
        time_range: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        将查询类型映射为工具调用

        Args:
            query_type: 查询类型
            question: 自然语言查询
            time_range: 时间范围

        Returns:
            Dict[str, Any]: 工具调用参数
        """
        if query_type == "province_overview":
            # 省级概览：使用get_air_quality工具
            return ToolCall(
                name="get_air_quality",
                params={"question": question}
            ).dict()

        elif query_type == "city_ranking":
            # 城市排名
            return ToolCall(
                name="get_air_quality",
                params={"question": question}
            ).dict()

        elif query_type == "city_detail_table":
            # 城市详细数据表
            return ToolCall(
                name="get_air_quality",
                params={"question": question}
            ).dict()

        elif query_type == "district_ranking":
            # 区县排名
            return ToolCall(
                name="get_air_quality",
                params={"question": question}
            ).dict()

        elif query_type == "monthly_comparison":
            # 单月数据
            return ToolCall(
                name="get_air_quality",
                params={"question": question}
            ).dict()

        else:
            # 通用查询
            return ToolCall(
                name="get_air_quality",
                params={"question": question}
            ).dict()

    def _build_query(
        self,
        query_type: str,
        requirements: List[Dict[str, Any]],
        time_range: Dict[str, str]
    ) -> str:
        """
        构造自然语言查询

        Args:
            query_type: 查询类型
            requirements: 需求列表
            time_range: 时间范围

        Returns:
            str: 自然语言查询
        """
        start = time_range.get("start", "")
        end = time_range.get("end", "")
        display = f"{start}至{end}" if start and end else "指定时间范围"

        if query_type == "province_overview":
            # 省级概览：达标率、污染物均值、同比
            return f"查询广东省{display}空气质量概况，包括AQI达标率、PM2.5浓度、O3浓度及同比变化"

        elif query_type == "city_ranking":
            # 城市排名
            return f"查询广东省{display}空气质量排名，包括综合指数、PM2.5、O3排名前5和后5的城市"

        elif query_type == "district_ranking":
            # 区县排名
            return f"查询广东省{display}区县空气质量排名前20和后20"

        elif query_type == "city_detail_table":
            # 城市详细数据表
            return f"查询广东省21个地市{display}空气质量详细数据，包括AQI达标率、PM2.5、O3、综合指数及同比"

        elif query_type == "monthly_comparison":
            # 单月数据（如6月）
            month = requirements[0].get("month") if requirements else None
            if month:
                return f"查询广东省2025年{month}月空气质量数据及同比变化"
            return f"查询广东省{display}单月空气质量数据及同比变化"

        else:
            # 通用查询
            return f"查询广东省{display}空气质量统计数据"

    def _extract_data_from_tools(
        self,
        query_result: Dict[str, Any],
        requirement: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        从工具层返回的UDF v2.0数据中提取数据
        根据需求类型返回不同格式：
        - 章节需求(data_points): → {data_points: {name: value}, data_id, ...}
        - 表格/排名需求(table/ranking): → {data: [...], data_id, ...}

        Args:
            query_result: 工具层返回的UDF v2.0格式数据
            requirement: 数据需求（包含section_id等）

        Returns:
            Dict[str, Any]: 提取的数据（结构根据需求类型变化）
        """
        section_id = requirement["section_id"]
        query_type = requirement.get("query_type", "general")

        # 识别需求类型
        has_data_points = "data_points" in requirement and requirement.get("data_points")
        has_table = "table" in requirement
        has_ranking = "ranking" in requirement

        # 工具层返回解析
        data = None
        data_id = None
        metadata = {}

        if hasattr(query_result, "dict"):
            qr = query_result.dict()
            data = qr.get("data")
            data_id = qr.get("data_id")
            metadata = qr.get("metadata") or {}
        elif isinstance(query_result, dict):
            data = query_result.get("data")
            data_id = query_result.get("data_id")
            metadata = query_result.get("metadata") or {}

        # 无数据情况
        if data is None:
            logger.warning(f"no_data_from_tools section={section_id} data_id={data_id}")
            if has_data_points:
                data_points = requirement.get("data_points", [])
                return {
                    "section_id": section_id,
                    "query_type": query_type,
                    "data_points": {p.get("name", ""): "N/A" for p in data_points},
                    "data_id": data_id,
                    "metadata": metadata
                }
            else:
                return {
                    "section_id": section_id,
                    "query_type": query_type,
                    "data": [],
                    "data_id": data_id,
                    "metadata": metadata
                }

        # 提取UFD v2.0数据
        if isinstance(data, dict) and "data" in data:
            standardized_data = data.get("data") or []
            metadata = data.get("metadata") or metadata
            data_id = data.get("data_id") or data_id
        else:
            standardized_data = data

        # 章节需求：提取特定数据点
        if has_data_points:
            data_points = requirement.get("data_points", [])
            logger.info(f"Extracting section data: section={section_id}, data_id={data_id}, points={len(data_points)}")

            extracted_datapoints = self._extract_datapoints_from_standardized_data(
                standardized_data, data_points
            )

            return {
                "section_id": section_id,
                "query_type": query_type,
                "data_points": extracted_datapoints,
                "data_id": data_id,
                "metadata": metadata
            }

        # 表格/排名需求：返回完整列表数据
        else:
            logger.info(f"Extracting table/ranking data: section={section_id}, data_id={data_id}, records={len(standardized_data) if standardized_data else 0}")

            return {
                "section_id": section_id,
                "query_type": query_type,
                "data": standardized_data,  # 完整标准化数据列表
                "data_id": data_id,
                "metadata": metadata
            }

    def _extract_datapoints_from_standardized_data(
        self,
        standardized_data: List[Dict[str, Any]],
        data_points: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        从标准化数据中提取特定数据点

        优先级策略：
        1. 如果是列表数据（多条记录），取第一条或聚合
        2. 如果是字典数据（单条记录），直接匹配字段
        3. 智能匹配字段名（对齐真实返回）

        Args:
            standardized_data: 标准化后的数据列表（UDF v2.0 format）
            data_points: 要提取的数据点定义列表

        Returns:
            Dict[str, Any]: {数据点名称: 值, ...}
        """
        extracted = {}

        # 归一为列表
        if standardized_data is None:
            logger.warning("No standardized data available")
            return {point.get("name", ""): "N/A" for point in data_points}

        if isinstance(standardized_data, dict):
            standardized_data = [standardized_data]

        if not standardized_data:
            return {point.get("name", ""): "N/A" for point in data_points}

        sample_item = standardized_data[0] if isinstance(standardized_data, list) else standardized_data

        # 如果是多条记录，提取第一条（可后续扩展聚合）
        if isinstance(standardized_data, list) and len(standardized_data) > 1:
            logger.info(f"Multiple data records ({len(standardized_data)}), using first record")

        # 支持两种深度结构：
        # 1. {timestamp, station_name, measurements: {...}} - 空气质量数据
        # 2. {aqi_rate: 93.2, pm25_avg: 24, ...} - 直接标准化数据
        if isinstance(sample_item, dict) and "measurements" in sample_item:
            source_data = sample_item.get("measurements", {})
        else:
            source_data = sample_item if isinstance(sample_item, dict) else {}

        for point in data_points:
            point_name = point["name"]
            value = self._smart_match_value_from_standardized(source_data, point_name)
            extracted[point_name] = value

        return extracted

    def _smart_match_value_from_standardized(
        self,
        data: Dict[str, Any],
        point_name: str
    ) -> Any:
        """
        从标准化数据中智能匹配字段值

        标准化数据中的字段名（示例）：
        - aqi_rate, aqi_yoy, pm25_avg, pm25_yoy, o3_avg, o3_yoy, composite
        - 都是英文小写+下划线标准格式

        Args:
            data: 标准化数据字典
            point_name: 数据点显示名称（如"AQI达标率"）

        Returns:
            Any: 匹配到的值
        """
        # 显示名称到标准化字段名的映射
        display_to_std = {
            "AQI达标率": ["aqi_rate"],
            "AQI同比": ["aqi_yoy"],
            "PM2.5浓度": ["pm25_avg", "pm25"],
            "PM2.5同比": ["pm25_yoy"],
            "PM10浓度": ["pm10_avg", "pm10"],
            "O3浓度": ["o3_avg", "o3"],
            "O3同比": ["o3_yoy"],
            "综合指数": ["composite", "composite_index"],
            "优良天数": ["good_days"],
            "污染天数": ["polluted_days"],
        }

        # 优先级1: 精确映射匹配
        if point_name in display_to_std:
            for std_field in display_to_std[point_name]:
                if std_field in data:
                    return data[std_field]

        # 优先级2: 模糊匹配关键词
        for key, value in data.items():
            if not isinstance(value, (int, float)):
                continue

            # 检查字段名是否包含关键词
            key_lower = key.lower()

            if "pm25" in point_name.lower() or "pm2.5" in point_name.lower():
                if "pm25" in key_lower:
                    return value
            elif "o3" in point_name.lower():
                if "o3" in key_lower:
                    return value
            elif "aqi" in point_name.lower() and "rate" in point_name.lower():
                if "aqi" in key_lower and "rate" in key_lower:
                    return value
            elif "composite" in point_name.lower() or "综合指数" in point_name:
                if "composite" in key_lower:
                    return value

        # 优先级3: 返回第一个数值字段（辅助生成）
        for value in data.values():
            if isinstance(value, (int, float)):
                return value

        # 终极: 返回N/A
        logger.warning(f"无法匹配数据点 '{point_name}' in {list(data.keys())}")
        return "N/A"

    def _extract_data(
        self,
        query_result: Dict[str, Any],
        requirement: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        从查询结果中提取特定数据点 - 已废弃，由 _extract_data_from_tools 替代

        Args:
            query_result: 查询结果
            requirement: 数据需求

        Returns:
            Dict[str, Any]: 提取的数据
        """
        # TODO: 实现数据提取逻辑
        # 根据requirement从query_result中提取相应的数据

        section_id = requirement["section_id"]
        query_type = requirement.get("query_type", "general")

        # 临时实现
        return {
            "section_id": section_id,
            "query_type": query_type,
            "data": query_result
        }