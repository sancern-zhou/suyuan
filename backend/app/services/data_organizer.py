"""
数据整理器 - 整理API返回的统计结果
场景2核心组件
"""
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger()

class DataOrganizer:
    """数据整理器 - 格式化数据点、组装表格数据结构"""

    async def organize(
        self,
        raw_data: Dict[str, Any],
        data_points: List[Dict[str, Any]],
        tables: List[Dict[str, Any]],
        rankings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        整理原始数据为报告格式

        Args:
            raw_data: 原始数据
            data_points: 数据点列表
            tables: 表格列表
            rankings: 排名列表

        Returns:
            Dict[str, Any]: 整理后的数据
        """
        logger.info("Organizing raw data for report")

        organized_data = {
            "sections": [],
            "tables": [],
            "rankings": [],
            "summary": ""
        }

        # 整理章节数据
        for section in data_points:
            section_id = section.get("id")
            section_data = raw_data.get(section_id, {})

            organized_section = {
                "id": section_id,
                "title": section.get("title"),
                "type": section.get("type", "text_with_data"),
                "data": self._format_section_data(section_data, section)
            }
            organized_data["sections"].append(organized_section)

        # 整理表格数据
        for table in tables:
            table_id = table.get("id")
            table_data = raw_data.get(table_id, {})

            organized_table = {
                "id": table_id,
                "title": table.get("title"),
                "columns": table.get("columns", []),
                "rows": self._format_table_data(table_data, table)
            }
            organized_data["tables"].append(organized_table)

        # 整理排名数据
        for ranking in rankings:
            ranking_id = ranking.get("id")
            ranking_data = raw_data.get(ranking_id, {})

            organized_ranking = {
                "id": ranking_id,
                "description": ranking.get("description"),
                "metric": ranking.get("metric"),
                "order": ranking.get("order"),
                "items": self._format_ranking_data(ranking_data, ranking)
            }
            organized_data["rankings"].append(organized_ranking)

        # 生成摘要
        organized_data["summary"] = self._generate_summary(organized_data)

        logger.info(f"Data organization completed: {len(organized_data['sections'])} sections, "
                   f"{len(organized_data['tables'])} tables, {len(organized_data['rankings'])} rankings")

        return organized_data

    def _format_section_data(
        self,
        section_data: Dict[str, Any],
        section_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        格式化章节数据 - 接收上游提取好的值，只做格式化

        Args:
            section_data: 上游数据（来自TemplateDataFetcher），
                          格式：{section_id, data_points: {...}, data_id, metadata}
            section_config: 章节配置（来自ReportParser，包含data_points定义）

        Returns:
            List[Dict[str, Any]]: 格式化后的数据点
        """
        formatted_points = []

        # 上游data来源（来自TemplateDataFetcher._extract_data_from_tools）：
        # {
        #     "section_id": "section_0",
        #     "data_points": {"AQI达标率": 93.2, "PM2.5浓度": 24},
        #     "data_id": "air_quality_unified_123",
        #     "query_type": "...",
        #     "metadata": {...}
        # }

        # 从上游获取已经提取好的数据点
        upstream_data_points = section_data.get("data_points", {})

        # 按section_config中定义的顺序格式化
        if "data_points" in section_config:
            for point in section_config["data_points"]:
                point_name = point.get("name")
                if point_name is not None:
                    # 直接使用上游提取的结果
                    value = upstream_data_points.get(point_name, "N/A")

                    # 必须包含的格式
                    formatted_point = {
                        "name": point_name,
                        "value": value,
                        "unit": point.get("unit", ""),
                        "comparison": point.get("comparison", self._extract_comparison_from_raw(upstream_data_points, point_name))
                    }
                    formatted_points.append(formatted_point)

        return formatted_points

    def _extract_comparison_from_raw(self, data: Dict[str, Any], point_name: str) -> str:
        """
        从上游数据中智能提取同比/环比信息

        Args:
            data: 上游数据（来自TemplateDataFetcher，包含data_points和metadata）
            point_name: 数据点名称（如"PM2.5浓度"、"AQI达标率"）

        Returns:
            str: 同比/环比描述（如"同比下降2.5%"），如果没有则返回空字符串

        策略：
            1. 如果point_name本身包含"同比/环比"，直接查找通用yoy字段
            2. 如果是普通指标，尝试查找对应的同比字段（精确匹配 + 模糊匹配）
            3. 兜底：返回空字符串
        """
        if not isinstance(data, dict) or not data:
            return ""

        # 策略1：如果数据点名称本身包含"同比"或"环比"
        if "同比" in point_name or "环比" in point_name:
            for key, value in data.items():
                if "yoy" in key.lower() or "同比" in key:
                    if isinstance(value, (int, float)):
                        trend = "上升" if value > 0 else "下降"
                        return f"同比{trend}{abs(value)}%"
            return ""

        # 策略2：为普通指标查找对应的同比字段
        # 构建可能的同比字段名（如"PM2.5浓度" -> "PM2.5同比"）
        base_name = point_name.replace("浓度", "").replace("平均", "").replace("指数", "").replace("达标率", "").strip()
        
        # 精确匹配
        possible_yoy_names = [
            f"{base_name}同比",
            f"{base_name}_yoy",
            f"{base_name}_year_over_year"
        ]
        
        for yoy_name in possible_yoy_names:
            if yoy_name in data:
                value = data[yoy_name]
                if isinstance(value, (int, float)):
                    trend = "上升" if value > 0 else "下降"
                    return f"同比{trend}{abs(value)}%"

        # 策略3：模糊匹配（兜底）
        base_name_lower = base_name.lower()
        for key, value in data.items():
            key_lower = key.lower()
            # 同时包含指标名称和"yoy/同比"关键词
            if (base_name_lower in key_lower) and ("yoy" in key_lower or "同比" in key_lower):
                if isinstance(value, (int, float)):
                    trend = "上升" if value > 0 else "下降"
                    return f"同比{trend}{abs(value)}%"

        return ""

    def _format_table_data(
        self,
        table_data: Dict[str, Any],
        table_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        格式化表格数据 - 接收上游提取好的表格数据，只做格式化

        Args:
            table_data: 上游数据（来自TemplateDataFetcher），格式：
                        {
                            "section_id": "table_id",
                            "data": [...],  # 标准化后的表格数据
                            "data_id": "...",
                            "metadata": {...}
                        }
            table_config: 表格配置（包含columns定义）

        Returns:
            List[Dict[str, Any]]: 格式化后的表格行
        """
        rows = []

        # 从上游提取标准化数据
        upstream_data = table_data.get("data", [])

        # 如果没有数据，返回空
        if not upstream_data:
            return rows

        # 确保是列表格式
        if not isinstance(upstream_data, list):
            return rows

        # 按表格配置的columns提取对应字段
        columns = table_config.get("columns", [])

        for row in upstream_data:
            if isinstance(row, dict):
                formatted_row = {
                    col: row.get(col, "")
                    for col in columns
                }
                rows.append(formatted_row)

        return rows

    def _format_ranking_data(
        self,
        ranking_data: Dict[str, Any],
        ranking_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        格式化排名数据 - 接收上游提取好的排名数据，只做格式化

        Args:
            ranking_data: 上游数据（来自TemplateDataFetcher），格式：
                          {
                              "section_id": "ranking_id",
                              "data": [...],  # 排名列表数据
                              "data_id": "...",
                              "metadata": {...}
                          }
            ranking_config: 排名配置（包含description、metric、order、top_n等）

        Returns:
            List[Dict[str, Any]]: 格式化后的排名项目
        """
        items = []

        # 从上游提取排名数据 - 统一为列表格式处理
        upstream_data = ranking_data.get("data", [])

        if not upstream_data:
            return items

        # 如果上游数据是dict，尝试提取best_5/worst_5
        if isinstance(upstream_data, dict):
            if "best_5" in upstream_data:
                upstream_data = upstream_data["best_5"]
            elif "worst_5" in upstream_data:
                upstream_data = upstream_data["worst_5"]
            else:  # 如果是单个对象，包装为列表
                upstream_data = [upstream_data]

        if not isinstance(upstream_data, list):
            return items

        # 获取排名配置信息
        top_n = ranking_config.get("top_n", len(upstream_data))
        order = ranking_config.get("order", "desc")
        metric = ranking_config.get("metric", "")

        # 处理每一条排名数据
        rank = 1
        for item in upstream_data[:top_n]:
            if isinstance(item, dict):
                # 提取名称和指标值（优先使用标准化的字段名）
                name = item.get("station_name") or item.get("city") or item.get("name") or str(item)
                metric_value = item.get(metric) if metric else item.get("metric_value", "")

                items.append({
                    "rank": rank,
                    "name": name,
                    "metric_value": metric_value
                })
            else:
                # 如果是简单值，直接使用
                items.append({
                    "rank": rank,
                    "name": str(item),
                    "metric_value": ""
                })
            rank += 1

        return items

    def _generate_summary(self, organized_data: Dict[str, Any]) -> str:
        """
        生成数据整理摘要

        Args:
            organized_data: 整理后的数据

        Returns:
            str: 摘要信息
        """
        sections_count = len(organized_data["sections"])
        tables_count = len(organized_data["tables"])
        rankings_count = len(organized_data["rankings"])

        summary = f"数据整理完成：{sections_count}个章节、{tables_count}个表格、{rankings_count}个排名"

        return summary
