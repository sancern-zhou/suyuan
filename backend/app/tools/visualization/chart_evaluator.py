"""
图表质量评估器 (ChartEvaluator)

核心功能：
1. 6维度评分系统评估图表质量
2. 生成改进建议
3. 支持多种图表类型

评估维度：
1. Data Integrity (数据完整性): 数据质量和完整性
2. Visual Clarity (视觉清晰度): 图表视觉效果
3. Appropriateness (适配性): 图表类型与数据的匹配度
4. Readability (可读性): 标签、图例、坐标轴等可读性
5. Aesthetics (美观性): 布局、配色、尺寸等美观度
6. Insight (洞察力): 传达信息和洞察的能力

设计参考：
- Microsoft LIDA的评估模块
- Vega-Lite的最佳实践
- Data-to-Viz的图表选择指南
"""

from typing import Dict, Any, List, Optional, Union
import structlog

logger = structlog.get_logger()


class ChartEvaluator:
    """
    图表质量评估器

    评估生成的图表质量并提供改进建议
    """

    # 评估维度权重（总和为1.0）
    DIMENSION_WEIGHTS = {
        "data_integrity": 0.20,      # 数据完整性 20%
        "visual_clarity": 0.15,      # 视觉清晰度 15%
        "appropriateness": 0.25,     # 适配性 25%（最重要）
        "readability": 0.15,         # 可读性 15%
        "aesthetics": 0.10,          # 美观性 10%
        "insight": 0.15              # 洞察力 15%
    }

    # 图表类型适配性规则
    CHART_TYPE_RULES = {
        "timeseries": {
            "preferred_data": ["temporal", "quantitative"],
            "min_points": 3,
            "max_categories": 10
        },
        "line": {
            "preferred_data": ["temporal", "quantitative"],
            "min_points": 2,
            "max_categories": 8
        },
        "bar": {
            "preferred_data": ["nominal", "quantitative"],
            "min_points": 1,
            "max_categories": 20
        },
        "pie": {
            "preferred_data": ["nominal", "quantitative"],
            "min_points": 2,
            "max_categories": 8,
            "warning_categories": 6  # 超过6个类别会降低可读性
        },
        "scatter": {
            "preferred_data": ["quantitative", "quantitative"],
            "min_points": 5,
            "max_points": 1000
        }
    }

    def evaluate(
        self,
        chart_spec: Dict[str, Any],
        data_summary: Optional[Dict[str, Any]] = None,
        data: Optional[Union[List[Dict], Dict]] = None
    ) -> Dict[str, Any]:
        """
        评估图表质量

        Args:
            chart_spec: 图表配置（v3.0格式）
            data_summary: 数据摘要（来自DataSummarizer）
            data: 原始数据（可选）

        Returns:
            评估结果：{
                "overall_score": float,  # 总分 (0-100)
                "dimension_scores": {    # 各维度得分
                    "data_integrity": float,
                    "visual_clarity": float,
                    "appropriateness": float,
                    "readability": float,
                    "aesthetics": float,
                    "insight": float
                },
                "suggestions": [...]     # 改进建议
            }
        """
        logger.info(
            "chart_evaluation_start",
            chart_type=chart_spec.get("type"),
            has_data_summary=data_summary is not None
        )

        # 评估各个维度
        scores = {}
        suggestions = []

        # 1. 数据完整性
        score, sugg = self._evaluate_data_integrity(chart_spec, data_summary, data)
        scores["data_integrity"] = score
        suggestions.extend(sugg)

        # 2. 视觉清晰度
        score, sugg = self._evaluate_visual_clarity(chart_spec, data_summary)
        scores["visual_clarity"] = score
        suggestions.extend(sugg)

        # 3. 适配性
        score, sugg = self._evaluate_appropriateness(chart_spec, data_summary)
        scores["appropriateness"] = score
        suggestions.extend(sugg)

        # 4. 可读性
        score, sugg = self._evaluate_readability(chart_spec)
        scores["readability"] = score
        suggestions.extend(sugg)

        # 5. 美观性
        score, sugg = self._evaluate_aesthetics(chart_spec, data_summary)
        scores["aesthetics"] = score
        suggestions.extend(sugg)

        # 6. 洞察力
        score, sugg = self._evaluate_insight(chart_spec, data_summary)
        scores["insight"] = score
        suggestions.extend(sugg)

        # 计算加权总分
        overall_score = sum(
            scores[dim] * self.DIMENSION_WEIGHTS[dim]
            for dim in scores
        )

        result = {
            "overall_score": round(overall_score, 2),
            "dimension_scores": {k: round(v, 2) for k, v in scores.items()},
            "suggestions": suggestions,
            "grade": self._get_grade(overall_score)
        }

        logger.info(
            "chart_evaluation_complete",
            overall_score=result["overall_score"],
            grade=result["grade"],
            suggestion_count=len(suggestions)
        )

        return result

    def _evaluate_data_integrity(
        self,
        chart_spec: Dict[str, Any],
        data_summary: Optional[Dict[str, Any]],
        data: Optional[Any]
    ) -> tuple[float, List[str]]:
        """评估数据完整性 (0-100)"""
        score = 100.0
        suggestions = []

        if not data_summary:
            return score, suggestions

        statistics = data_summary.get("statistics", {})
        field_info = data_summary.get("field_info", {})

        # 检查记录数量
        record_count = statistics.get("record_count", 0)
        if record_count < 2:
            score -= 30
            suggestions.append("数据记录数量过少（<2条），建议补充数据")
        elif record_count < 5:
            score -= 15
            suggestions.append("数据记录数量较少（<5条），可能影响可视化效果")

        # 检查缺失值
        total_missing = 0
        total_values = 0
        for field, info in field_info.items():
            missing = info.get("missing_count", 0)
            total_missing += missing
            total_values += missing + len(info.get("sample_values", []))

        if total_values > 0:
            missing_rate = total_missing / total_values
            if missing_rate > 0.3:
                score -= 25
                suggestions.append(f"数据缺失率过高（{missing_rate*100:.1f}%），建议清洗数据")
            elif missing_rate > 0.1:
                score -= 10
                suggestions.append(f"数据存在缺失值（{missing_rate*100:.1f}%）")

        # 检查字段数量
        field_count = statistics.get("field_count", 0)
        if field_count == 0:
            score -= 50
            suggestions.append("数据无有效字段")

        return max(0, score), suggestions

    def _evaluate_visual_clarity(
        self,
        chart_spec: Dict[str, Any],
        data_summary: Optional[Dict[str, Any]]
    ) -> tuple[float, List[str]]:
        """评估视觉清晰度 (0-100)"""
        score = 100.0
        suggestions = []

        chart_type = chart_spec.get("type")
        chart_data = chart_spec.get("data", {})

        # 检查数据密度
        if chart_type in ["bar", "pie"]:
            # 对于分类图表，检查类别数量
            if isinstance(chart_data, dict):
                if "data" in chart_data:
                    actual_data = chart_data["data"]
                    if isinstance(actual_data, list):
                        category_count = len(actual_data)
                    elif isinstance(actual_data, dict) and "x" in actual_data:
                        category_count = len(actual_data["x"])
                    else:
                        category_count = 0

                    if category_count > 20:
                        score -= 30
                        suggestions.append(f"类别数量过多（{category_count}个），建议只显示Top 10-15")
                    elif category_count > 10 and chart_type == "pie":
                        score -= 20
                        suggestions.append(f"饼图类别过多（{category_count}个），建议少于8个")

        # 检查时序图数据点
        if chart_type in ["timeseries", "line"]:
            if isinstance(chart_data, dict) and "data" in chart_data:
                actual_data = chart_data["data"]
                if isinstance(actual_data, dict) and "x" in actual_data:
                    point_count = len(actual_data["x"])
                    if point_count < 3:
                        score -= 20
                        suggestions.append("时序数据点过少（<3个），难以展示趋势")
                    elif point_count > 200:
                        score -= 10
                        suggestions.append("时序数据点过多（>200个），建议聚合或采样")

        return max(0, score), suggestions

    def _evaluate_appropriateness(
        self,
        chart_spec: Dict[str, Any],
        data_summary: Optional[Dict[str, Any]]
    ) -> tuple[float, List[str]]:
        """评估适配性 (0-100)"""
        score = 100.0
        suggestions = []

        chart_type = chart_spec.get("type")

        if not data_summary:
            return score, suggestions

        statistics = data_summary.get("statistics", {})
        has_time_series = statistics.get("has_time_series", False)
        numeric_field_count = len(statistics.get("numeric_fields", []))
        categorical_field_count = len(statistics.get("categorical_fields", []))

        # 检查图表类型是否适合数据特征
        if chart_type in ["timeseries", "line"]:
            if not has_time_series:
                score -= 40
                suggestions.append("使用时序图但数据无时间字段，建议改用柱状图或散点图")

        elif chart_type == "pie":
            if categorical_field_count == 0:
                score -= 30
                suggestions.append("饼图需要类别字段，当前数据无类别")
            if numeric_field_count == 0:
                score -= 30
                suggestions.append("饼图需要数值字段用于展示占比")

        elif chart_type == "bar":
            if categorical_field_count == 0 and numeric_field_count == 0:
                score -= 40
                suggestions.append("柱状图需要至少一个类别或数值字段")

        elif chart_type == "scatter":
            if numeric_field_count < 2:
                score -= 40
                suggestions.append("散点图需要至少2个数值字段")

        # 检查是否有更合适的图表类型
        if has_time_series and chart_type not in ["timeseries", "line"]:
            suggestions.append("数据包含时间信息，使用时序图或折线图可能更合适")

        if numeric_field_count >= 2 and chart_type != "scatter" and not has_time_series:
            suggestions.append("数据包含多个数值字段，散点图可以展示字段间关系")

        return max(0, score), suggestions

    def _evaluate_readability(
        self,
        chart_spec: Dict[str, Any]
    ) -> tuple[float, List[str]]:
        """评估可读性 (0-100)"""
        score = 100.0
        suggestions = []

        # 检查标题
        title = chart_spec.get("title")
        if not title:
            score -= 20
            suggestions.append("缺少图表标题，建议添加标题说明图表内容")
        elif len(title) > 50:
            score -= 5
            suggestions.append("标题过长（>50字符），建议简化")

        # 检查元数据
        meta = chart_spec.get("meta", {})
        if not meta.get("unit"):
            score -= 10
            suggestions.append("缺少数据单位信息")

        # 检查ID
        if not chart_spec.get("id"):
            score -= 5
            suggestions.append("缺少图表ID")

        return max(0, score), suggestions

    def _evaluate_aesthetics(
        self,
        chart_spec: Dict[str, Any],
        data_summary: Optional[Dict[str, Any]]
    ) -> tuple[float, List[str]]:
        """评估美观性 (0-100)"""
        score = 100.0
        suggestions = []

        chart_type = chart_spec.get("type")

        # 检查图表类型是否常用
        if chart_type not in ["bar", "line", "pie", "timeseries", "scatter"]:
            score -= 10
            suggestions.append(f"图表类型'{chart_type}'较少见，建议使用常见类型")

        # 检查数据格式一致性
        chart_data = chart_spec.get("data", {})
        if not isinstance(chart_data, dict):
            score -= 20
            suggestions.append("图表数据格式不规范")
        elif "type" not in chart_data:
            score -= 10
            suggestions.append("图表数据缺少type字段")

        return max(0, score), suggestions

    def _evaluate_insight(
        self,
        chart_spec: Dict[str, Any],
        data_summary: Optional[Dict[str, Any]]
    ) -> tuple[float, List[str]]:
        """评估洞察力 (0-100)"""
        score = 100.0
        suggestions = []

        chart_type = chart_spec.get("type")

        if not data_summary:
            return score, suggestions

        statistics = data_summary.get("statistics", {})
        record_count = statistics.get("record_count", 0)

        # 检查数据量是否足以产生洞察
        if record_count < 3:
            score -= 30
            suggestions.append("数据量过少，难以产生有价值的洞察")

        # 检查是否展示了数据的关键特征
        has_time_series = statistics.get("has_time_series", False)
        has_multiple_categories = statistics.get("has_multiple_categories", False)
        numeric_field_count = len(statistics.get("numeric_fields", []))

        # 时序数据应该展示趋势
        if has_time_series and chart_type not in ["timeseries", "line"]:
            score -= 20
            suggestions.append("时序数据应使用时序图或折线图展示趋势变化")

        # 多分类数据应该便于对比
        if has_multiple_categories and chart_type not in ["bar", "pie"]:
            score -= 15
            suggestions.append("多分类数据应使用柱状图或饼图便于对比")

        # 多维数值数据应该展示关系
        if numeric_field_count >= 2 and chart_type not in ["scatter", "timeseries"]:
            score -= 10
            suggestions.append("多维数值数据可使用散点图展示字段间关系")

        return max(0, score), suggestions

    def _get_grade(self, score: float) -> str:
        """根据分数获取等级"""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"


# ============================================
# 便捷函数
# ============================================

def evaluate_chart(
    chart_spec: Dict[str, Any],
    data_summary: Optional[Dict[str, Any]] = None,
    data: Optional[Any] = None
) -> Dict[str, Any]:
    """
    快速评估图表质量

    Args:
        chart_spec: 图表配置
        data_summary: 数据摘要（可选）
        data: 原始数据（可选）

    Returns:
        评估结果
    """
    evaluator = ChartEvaluator()
    return evaluator.evaluate(chart_spec, data_summary, data)


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":
    # 示例1：评估一个简单的柱状图
    print("=== 示例1：评估柱状图 ===")
    chart_spec_1 = {
        "id": "test_bar_chart",
        "type": "bar",
        "title": "各站点PM2.5平均浓度",
        "data": {
            "type": "bar",
            "data": {
                "x": ["广州", "深圳", "北京"],
                "y": [35.2, 28.5, 45.8]
            }
        },
        "meta": {
            "unit": "μg/m³",
            "data_source": "air_quality"
        }
    }

    data_summary_1 = {
        "statistics": {
            "record_count": 3,
            "has_time_series": False,
            "has_multiple_categories": True,
            "numeric_fields": ["PM2.5"],
            "categorical_fields": ["station_name"]
        },
        "field_info": {
            "station_name": {"type": "nominal", "distinct_count": 3, "missing_count": 0},
            "PM2.5": {"type": "quantitative", "distinct_count": 3, "missing_count": 0}
        }
    }

    result_1 = evaluate_chart(chart_spec_1, data_summary_1)
    print(f"总分: {result_1['overall_score']}/100 (等级: {result_1['grade']})")
    print(f"维度得分: {result_1['dimension_scores']}")
    print(f"建议数量: {len(result_1['suggestions'])}")
    if result_1['suggestions']:
        print("改进建议:")
        for i, sugg in enumerate(result_1['suggestions'], 1):
            print(f"  {i}. {sugg}")

    # 示例2：评估一个不太合适的饼图
    print("\n=== 示例2：评估饼图（类别过多）===")
    chart_spec_2 = {
        "id": "test_pie_chart",
        "type": "pie",
        "title": "VOCs物种浓度分布",
        "data": {
            "type": "pie",
            "data": [
                {"name": f"物种{i}", "value": 10.0 + i}
                for i in range(15)  # 15个类别，饼图过多
            ]
        },
        "meta": {"unit": "ppb"}
    }

    data_summary_2 = {
        "statistics": {
            "record_count": 15,
            "has_time_series": False,
            "has_multiple_categories": True,
            "numeric_fields": ["concentration"],
            "categorical_fields": ["species_name"]
        }
    }

    result_2 = evaluate_chart(chart_spec_2, data_summary_2)
    print(f"总分: {result_2['overall_score']}/100 (等级: {result_2['grade']})")
    print(f"建议数量: {len(result_2['suggestions'])}")
    if result_2['suggestions']:
        print("改进建议:")
        for i, sugg in enumerate(result_2['suggestions'], 1):
            print(f"  {i}. {sugg}")
