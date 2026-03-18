"""
数据摘要工具 (DataSummarizer)

核心功能：
1. 自动分析数据特征（字段类型、统计信息、时序特征等）
2. 生成数据摘要供策略选择器使用
3. 支持环境监测、溯源分析等多种数据类型

设计参考：
- Microsoft LIDA的Data Summarization模块
- Apache Superset的数据探索功能
- Observable Plot的自动类型推断

输出格式：
{
    "field_info": {
        "field_name": {
            "type": "quantitative|nominal|temporal",
            "distinct_count": int,
            "missing_count": int,
            "statistics": {...}  # 仅数值字段
        }
    },
    "statistics": {
        "record_count": int,
        "has_time_series": bool,
        "has_multiple_categories": bool,
        "numeric_fields": [...],
        "categorical_fields": [...],
        "temporal_fields": [...]
    },
    "recommendations": {
        "suitable_chart_types": [...],
        "primary_dimensions": [...],
        "primary_measures": [...]
    }
}
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import structlog

logger = structlog.get_logger()


class DataSummarizer:
    """
    数据摘要工具

    自动分析数据特征并生成摘要，用于：
    1. 策略选择器决策
    2. 图表推荐
    3. 数据质量评估
    """

    # 时间字段常见命名模式
    TIME_FIELD_PATTERNS = [
        "time", "date", "timestamp", "datetime",
        "timepoint", "time_point", "datatime",
        "时间", "日期", "时刻"
    ]

    # 类别字段常见命名模式
    CATEGORY_FIELD_PATTERNS = [
        "name", "type", "category", "class", "station",
        "source", "species", "location", "site",
        "名称", "类型", "类别", "站点", "物种"
    ]

    def summarize(
        self,
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        schema: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成数据摘要

        Args:
            data: 输入数据（记录列表或UDF格式）
            schema: 数据类型（可选，帮助类型推断）

        Returns:
            数据摘要字典
        """
        logger.info(
            "data_summarization_start",
            data_type=type(data).__name__,
            schema=schema
        )

        # Step 1: 提取记录列表
        records = self._extract_records(data)

        if not records:
            return {
                "error": "数据为空",
                "record_count": 0
            }

        # Step 2: 分析字段信息
        field_info = self._analyze_fields(records)

        # Step 3: 生成统计信息
        statistics = self._generate_statistics(records, field_info)

        # Step 4: 生成推荐信息
        recommendations = self._generate_recommendations(field_info, statistics, schema)

        summary = {
            "field_info": field_info,
            "statistics": statistics,
            "recommendations": recommendations
        }

        logger.info(
            "data_summarization_complete",
            record_count=statistics["record_count"],
            field_count=len(field_info),
            has_time_series=statistics.get("has_time_series", False)
        )

        return summary

    def _extract_records(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> List[Dict[str, Any]]:
        """提取数据记录列表"""
        if isinstance(data, list):
            # 已经是记录列表
            return data
        elif isinstance(data, dict):
            if "data" in data:
                # UDF v1.0格式
                return data["data"]
            elif "records" in data:
                return data["records"]
            else:
                # 单条记录
                return [data]
        else:
            logger.warning("unexpected_data_format", data_type=type(data).__name__)
            return []

    def _analyze_fields(self, records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        分析所有字段的类型和特征

        Returns:
            字段信息字典
        """
        if not records:
            return {}

        # 收集所有字段
        all_fields = set()
        for record in records:
            all_fields.update(record.keys())

        field_info = {}

        for field_name in all_fields:
            # 收集该字段的所有值
            values = []
            missing_count = 0

            for record in records:
                value = record.get(field_name)
                if value is None or value == "" or value == "-":
                    missing_count += 1
                else:
                    values.append(value)

            # 推断字段类型
            field_type = self._infer_field_type(field_name, values)

            # 计算不同值数量
            distinct_count = len(set(str(v) for v in values))

            field_info[field_name] = {
                "type": field_type,
                "distinct_count": distinct_count,
                "missing_count": missing_count,
                "sample_values": values[:5] if values else []
            }

            # 如果是数值字段，计算统计信息
            if field_type == "quantitative":
                numeric_values = []
                for v in values:
                    try:
                        numeric_values.append(float(v))
                    except (ValueError, TypeError):
                        pass

                if numeric_values:
                    field_info[field_name]["statistics"] = {
                        "min": min(numeric_values),
                        "max": max(numeric_values),
                        "mean": sum(numeric_values) / len(numeric_values),
                        "count": len(numeric_values)
                    }

        return field_info

    def _infer_field_type(self, field_name: str, values: List[Any]) -> str:
        """
        推断字段类型

        Returns:
            "quantitative" | "nominal" | "temporal"
        """
        if not values:
            return "nominal"

        # 检查是否为时间字段
        if self._is_temporal_field(field_name, values):
            return "temporal"

        # 检查是否为数值字段
        numeric_count = 0
        for value in values[:min(100, len(values))]:  # 采样前100个
            try:
                float(value)
                numeric_count += 1
            except (ValueError, TypeError):
                pass

        # 如果80%以上是数值，判定为数值字段
        if numeric_count / len(values[:min(100, len(values))]) >= 0.8:
            return "quantitative"

        # 否则判定为类别字段
        return "nominal"

    def _is_temporal_field(self, field_name: str, values: List[Any]) -> bool:
        """判断是否为时间字段"""
        # 1. 检查字段名模式
        field_name_lower = field_name.lower()
        if any(pattern in field_name_lower for pattern in self.TIME_FIELD_PATTERNS):
            return True

        # 2. 检查值的格式（采样前10个）
        sample_values = values[:min(10, len(values))]
        temporal_count = 0

        for value in sample_values:
            if isinstance(value, datetime):
                temporal_count += 1
            elif isinstance(value, str):
                # 尝试解析常见时间格式
                time_formats = [
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M",
                    "%Y-%m-%d",
                    "%Y/%m/%d %H:%M:%S",
                    "%Y/%m/%d"
                ]
                for fmt in time_formats:
                    try:
                        datetime.strptime(value, fmt)
                        temporal_count += 1
                        break
                    except ValueError:
                        continue

        # 如果50%以上能解析为时间，判定为时间字段
        return temporal_count / len(sample_values) > 0.5 if sample_values else False

    def _generate_statistics(
        self,
        records: List[Dict[str, Any]],
        field_info: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """生成整体统计信息"""
        # 分类字段
        numeric_fields = []
        categorical_fields = []
        temporal_fields = []

        for field_name, info in field_info.items():
            if info["type"] == "quantitative":
                numeric_fields.append(field_name)
            elif info["type"] == "nominal":
                categorical_fields.append(field_name)
            elif info["type"] == "temporal":
                temporal_fields.append(field_name)

        # 检查是否有时序数据
        has_time_series = len(temporal_fields) > 0

        # 检查是否有多分类
        has_multiple_categories = any(
            info["distinct_count"] > 1
            for info in field_info.values()
            if info["type"] == "nominal"
        )

        return {
            "record_count": len(records),
            "field_count": len(field_info),
            "has_time_series": has_time_series,
            "has_multiple_categories": has_multiple_categories,
            "numeric_fields": numeric_fields,
            "categorical_fields": categorical_fields,
            "temporal_fields": temporal_fields
        }

    def _generate_recommendations(
        self,
        field_info: Dict[str, Dict[str, Any]],
        statistics: Dict[str, Any],
        schema: Optional[str]
    ) -> Dict[str, Any]:
        """
        生成图表推荐

        基于数据特征推荐合适的图表类型
        """
        suitable_chart_types = []
        primary_dimensions = []
        primary_measures = []

        # 推荐维度和度量
        for field_name, info in field_info.items():
            if info["type"] == "nominal" and info["distinct_count"] > 1:
                primary_dimensions.append(field_name)
            elif info["type"] == "quantitative":
                primary_measures.append(field_name)

        # 基于数据特征推荐图表类型
        if statistics["has_time_series"]:
            suitable_chart_types.append("timeseries")
            suitable_chart_types.append("line")

        if statistics["has_multiple_categories"]:
            suitable_chart_types.append("bar")
            if len(primary_dimensions) > 0:
                suitable_chart_types.append("pie")

        if len(statistics["numeric_fields"]) >= 2:
            suitable_chart_types.append("scatter")

        # 如果没有推荐，默认柱状图
        if not suitable_chart_types:
            suitable_chart_types = ["bar"]

        return {
            "suitable_chart_types": suitable_chart_types,
            "primary_dimensions": primary_dimensions[:3],  # 取前3个
            "primary_measures": primary_measures[:3]
        }


# ============================================
# 便捷函数
# ============================================

def summarize_data(
    data: Union[List[Dict[str, Any]], Dict[str, Any]],
    schema: Optional[str] = None
) -> Dict[str, Any]:
    """
    快速生成数据摘要

    Args:
        data: 输入数据
        schema: 数据类型（可选）

    Returns:
        数据摘要
    """
    summarizer = DataSummarizer()
    return summarizer.summarize(data, schema)


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":
    # 示例1：空气质量数据
    print("=== 示例1：空气质量数据 ===")
    air_quality_data = [
        {"timePoint": "2025-01-01 00:00", "PM2.5": 35.2, "O3": 45.8, "station_name": "广州"},
        {"timePoint": "2025-01-01 01:00", "PM2.5": 38.5, "O3": 42.1, "station_name": "广州"},
        {"timePoint": "2025-01-01 00:00", "PM2.5": 28.5, "O3": 52.3, "station_name": "深圳"},
        {"timePoint": "2025-01-01 01:00", "PM2.5": 30.2, "O3": 48.9, "station_name": "深圳"}
    ]

    summary1 = summarize_data(air_quality_data, "air_quality")
    print(f"记录数: {summary1['statistics']['record_count']}")
    print(f"时序数据: {summary1['statistics']['has_time_series']}")
    print(f"推荐图表: {summary1['recommendations']['suitable_chart_types']}")
    print(f"数值字段: {summary1['statistics']['numeric_fields']}")

    # 示例2：VOCs数据
    print("\n=== 示例2：VOCs数据 ===")
    vocs_data = [
        {"species_name": "乙烯", "concentration": 12.5, "category": "烷烃"},
        {"species_name": "丙烯", "concentration": 8.3, "category": "烯烃"},
        {"species_name": "甲苯", "concentration": 15.7, "category": "芳香烃"}
    ]

    summary2 = summarize_data(vocs_data, "vocs")
    print(f"记录数: {summary2['statistics']['record_count']}")
    print(f"类别字段: {summary2['statistics']['categorical_fields']}")
    print(f"推荐图表: {summary2['recommendations']['suitable_chart_types']}")
