"""
测试图表质量评估器 (ChartEvaluator)

验证内容：
1. 6维度评分系统
2. 不同图表类型的评估
3. 改进建议生成
4. 边界情况处理
"""

import pytest
from typing import Dict, Any

from app.tools.visualization.chart_evaluator import ChartEvaluator, evaluate_chart


class TestBasicEvaluation:
    """测试基础评估功能"""

    def setup_method(self):
        """初始化测试"""
        self.evaluator = ChartEvaluator()

    def test_evaluate_returns_all_required_fields(self):
        """测试评估结果包含所有必需字段"""
        chart_spec = {
            "id": "test",
            "type": "bar",
            "title": "Test Chart",
            "data": {"type": "bar", "data": {"x": ["A"], "y": [10]}},
            "meta": {"unit": "count"}
        }

        result = self.evaluator.evaluate(chart_spec)

        assert "overall_score" in result
        assert "dimension_scores" in result
        assert "suggestions" in result
        assert "grade" in result

    def test_evaluate_all_dimensions(self):
        """测试所有6个维度都被评估"""
        chart_spec = {
            "id": "test",
            "type": "bar",
            "title": "Test",
            "data": {"type": "bar", "data": {"x": ["A", "B"], "y": [10, 20]}},
            "meta": {"unit": "count"}
        }

        result = self.evaluator.evaluate(chart_spec)

        dimensions = result["dimension_scores"]
        assert "data_integrity" in dimensions
        assert "visual_clarity" in dimensions
        assert "appropriateness" in dimensions
        assert "readability" in dimensions
        assert "aesthetics" in dimensions
        assert "insight" in dimensions

    def test_overall_score_in_range(self):
        """测试总分在0-100范围内"""
        chart_spec = {
            "id": "test",
            "type": "bar",
            "title": "Test",
            "data": {"type": "bar", "data": {"x": ["A"], "y": [10]}},
            "meta": {}
        }

        result = self.evaluator.evaluate(chart_spec)

        assert 0 <= result["overall_score"] <= 100

    def test_grade_assignment(self):
        """测试等级分配"""
        # Grade A: 90+
        assert self.evaluator._get_grade(95) == "A"
        # Grade B: 80-89
        assert self.evaluator._get_grade(85) == "B"
        # Grade C: 70-79
        assert self.evaluator._get_grade(75) == "C"
        # Grade D: 60-69
        assert self.evaluator._get_grade(65) == "D"
        # Grade F: <60
        assert self.evaluator._get_grade(50) == "F"


class TestDataIntegrity:
    """测试数据完整性评估"""

    def setup_method(self):
        self.evaluator = ChartEvaluator()

    def test_low_record_count_penalty(self):
        """测试记录数量过少的扣分"""
        data_summary = {
            "statistics": {"record_count": 1},
            "field_info": {}
        }

        score, suggestions = self.evaluator._evaluate_data_integrity(
            {}, data_summary, None
        )

        assert score < 100
        assert any("数量过少" in s for s in suggestions)

    def test_high_missing_rate_penalty(self):
        """测试高缺失率的扣分"""
        data_summary = {
            "statistics": {"record_count": 10},
            "field_info": {
                "field1": {
                    "missing_count": 4,
                    "sample_values": [1, 2, 3, 4, 5, 6]  # 4缺失 + 6有效 = 40%缺失率
                }
            }
        }

        score, suggestions = self.evaluator._evaluate_data_integrity(
            {}, data_summary, None
        )

        assert score < 100
        assert any("缺失" in s for s in suggestions)

    def test_no_data_summary_returns_full_score(self):
        """测试无数据摘要时返回满分"""
        score, suggestions = self.evaluator._evaluate_data_integrity(
            {}, None, None
        )

        assert score == 100.0
        assert len(suggestions) == 0


class TestVisualClarity:
    """测试视觉清晰度评估"""

    def setup_method(self):
        self.evaluator = ChartEvaluator()

    def test_too_many_categories_in_bar_chart(self):
        """测试柱状图类别过多"""
        chart_spec = {
            "type": "bar",
            "data": {
                "type": "bar",
                "data": {
                    "x": [f"Cat{i}" for i in range(25)],
                    "y": [10] * 25
                }
            }
        }

        score, suggestions = self.evaluator._evaluate_visual_clarity(
            chart_spec, None
        )

        assert score < 100
        assert any("类别数量过多" in s for s in suggestions)

    def test_too_many_categories_in_pie_chart(self):
        """测试饼图类别过多"""
        chart_spec = {
            "type": "pie",
            "data": {
                "type": "pie",
                "data": [{"name": f"Cat{i}", "value": 10} for i in range(12)]
            }
        }

        score, suggestions = self.evaluator._evaluate_visual_clarity(
            chart_spec, None
        )

        assert score < 100
        assert any("饼图类别过多" in s for s in suggestions)

    def test_too_few_points_in_timeseries(self):
        """测试时序图数据点过少"""
        chart_spec = {
            "type": "timeseries",
            "data": {
                "type": "timeseries",
                "data": {
                    "x": ["2025-01-01", "2025-01-02"],
                    "series": [{"name": "A", "data": [10, 20]}]
                }
            }
        }

        score, suggestions = self.evaluator._evaluate_visual_clarity(
            chart_spec, None
        )

        assert score < 100
        assert any("数据点过少" in s for s in suggestions)


class TestAppropriateness:
    """测试适配性评估"""

    def setup_method(self):
        self.evaluator = ChartEvaluator()

    def test_timeseries_without_temporal_data(self):
        """测试时序图但无时间数据"""
        chart_spec = {"type": "timeseries"}
        data_summary = {
            "statistics": {
                "has_time_series": False,
                "numeric_fields": ["value"],
                "categorical_fields": ["category"]
            }
        }

        score, suggestions = self.evaluator._evaluate_appropriateness(
            chart_spec, data_summary
        )

        assert score < 100
        assert any("无时间字段" in s for s in suggestions)

    def test_pie_without_categories(self):
        """测试饼图但无类别数据"""
        chart_spec = {"type": "pie"}
        data_summary = {
            "statistics": {
                "has_time_series": False,
                "numeric_fields": [],
                "categorical_fields": []
            }
        }

        score, suggestions = self.evaluator._evaluate_appropriateness(
            chart_spec, data_summary
        )

        assert score < 100
        assert any("需要类别字段" in s or "需要数值字段" in s for s in suggestions)

    def test_scatter_without_enough_numeric_fields(self):
        """测试散点图但数值字段不足"""
        chart_spec = {"type": "scatter"}
        data_summary = {
            "statistics": {
                "has_time_series": False,
                "numeric_fields": ["value"],  # 只有1个数值字段
                "categorical_fields": []
            }
        }

        score, suggestions = self.evaluator._evaluate_appropriateness(
            chart_spec, data_summary
        )

        assert score < 100
        assert any("至少2个数值字段" in s for s in suggestions)

    def test_appropriate_chart_gets_full_score(self):
        """测试适配的图表获得满分"""
        chart_spec = {"type": "timeseries"}
        data_summary = {
            "statistics": {
                "has_time_series": True,
                "numeric_fields": ["value"],
                "categorical_fields": []
            }
        }

        score, suggestions = self.evaluator._evaluate_appropriateness(
            chart_spec, data_summary
        )

        assert score == 100.0


class TestReadability:
    """测试可读性评估"""

    def setup_method(self):
        self.evaluator = ChartEvaluator()

    def test_missing_title_penalty(self):
        """测试缺少标题的扣分"""
        chart_spec = {
            "id": "test",
            "type": "bar",
            "data": {},
            "meta": {"unit": "count"}
        }

        score, suggestions = self.evaluator._evaluate_readability(chart_spec)

        assert score < 100
        assert any("缺少图表标题" in s for s in suggestions)

    def test_title_too_long_penalty(self):
        """测试标题过长的扣分"""
        chart_spec = {
            "id": "test",
            "type": "bar",
            "title": "A" * 60,  # 超过50字符
            "data": {},
            "meta": {"unit": "count"}
        }

        score, suggestions = self.evaluator._evaluate_readability(chart_spec)

        assert score < 100
        assert any("标题过长" in s for s in suggestions)

    def test_missing_unit_penalty(self):
        """测试缺少单位的扣分"""
        chart_spec = {
            "id": "test",
            "type": "bar",
            "title": "Test",
            "data": {},
            "meta": {}  # 无unit字段
        }

        score, suggestions = self.evaluator._evaluate_readability(chart_spec)

        assert score < 100
        assert any("缺少数据单位" in s for s in suggestions)

    def test_complete_metadata_gets_high_score(self):
        """测试完整元数据获得高分"""
        chart_spec = {
            "id": "test_chart",
            "type": "bar",
            "title": "Test Chart",
            "data": {},
            "meta": {"unit": "count", "source": "test"}
        }

        score, suggestions = self.evaluator._evaluate_readability(chart_spec)

        assert score >= 95


class TestAesthetics:
    """测试美观性评估"""

    def setup_method(self):
        self.evaluator = ChartEvaluator()

    def test_uncommon_chart_type_penalty(self):
        """测试不常见图表类型的扣分"""
        chart_spec = {
            "type": "radar",  # 不常见的图表类型
            "data": {"type": "radar"}
        }

        score, suggestions = self.evaluator._evaluate_aesthetics(
            chart_spec, None
        )

        assert score < 100
        assert any("较少见" in s for s in suggestions)

    def test_invalid_data_format_penalty(self):
        """测试数据格式不规范的扣分"""
        chart_spec = {
            "type": "bar",
            "data": "invalid"  # 不是字典
        }

        score, suggestions = self.evaluator._evaluate_aesthetics(
            chart_spec, None
        )

        assert score < 100
        assert any("格式不规范" in s for s in suggestions)

    def test_missing_type_in_data_penalty(self):
        """测试data缺少type字段的扣分"""
        chart_spec = {
            "type": "bar",
            "data": {"x": [1, 2, 3]}  # 缺少type字段
        }

        score, suggestions = self.evaluator._evaluate_aesthetics(
            chart_spec, None
        )

        assert score < 100
        assert any("缺少type字段" in s for s in suggestions)


class TestInsight:
    """测试洞察力评估"""

    def setup_method(self):
        self.evaluator = ChartEvaluator()

    def test_insufficient_data_penalty(self):
        """测试数据量不足的扣分"""
        chart_spec = {"type": "bar"}
        data_summary = {
            "statistics": {
                "record_count": 2,  # 数据量过少
                "has_time_series": False,
                "numeric_fields": []
            }
        }

        score, suggestions = self.evaluator._evaluate_insight(
            chart_spec, data_summary
        )

        assert score < 100
        assert any("数据量过少" in s for s in suggestions)

    def test_timeseries_data_with_wrong_chart_type(self):
        """测试时序数据使用错误图表类型"""
        chart_spec = {"type": "pie"}
        data_summary = {
            "statistics": {
                "record_count": 10,
                "has_time_series": True,
                "has_multiple_categories": False,
                "numeric_fields": ["value"]
            }
        }

        score, suggestions = self.evaluator._evaluate_insight(
            chart_spec, data_summary
        )

        assert score < 100
        assert any("时序" in s and "趋势" in s for s in suggestions)

    def test_optimal_chart_type_gets_full_score(self):
        """测试最优图表类型获得满分"""
        chart_spec = {"type": "timeseries"}
        data_summary = {
            "statistics": {
                "record_count": 20,
                "has_time_series": True,
                "has_multiple_categories": False,
                "numeric_fields": ["value"]
            }
        }

        score, suggestions = self.evaluator._evaluate_insight(
            chart_spec, data_summary
        )

        assert score == 100.0


class TestConvenienceFunction:
    """测试便捷函数"""

    def test_evaluate_chart_function(self):
        """测试evaluate_chart函数"""
        chart_spec = {
            "id": "test",
            "type": "bar",
            "title": "Test",
            "data": {"type": "bar", "data": {"x": ["A"], "y": [10]}},
            "meta": {"unit": "count"}
        }

        result = evaluate_chart(chart_spec)

        assert "overall_score" in result
        assert "dimension_scores" in result
        assert "suggestions" in result
        assert "grade" in result


class TestEdgeCases:
    """测试边界情况"""

    def setup_method(self):
        self.evaluator = ChartEvaluator()

    def test_empty_chart_spec(self):
        """测试空图表配置"""
        result = self.evaluator.evaluate({})

        assert "overall_score" in result
        assert result["overall_score"] >= 0

    def test_chart_without_data(self):
        """测试无数据的图表"""
        chart_spec = {
            "id": "test",
            "type": "bar",
            "title": "Test"
        }

        result = self.evaluator.evaluate(chart_spec)

        assert "overall_score" in result
        assert len(result["suggestions"]) > 0

    def test_evaluate_with_all_parameters(self):
        """测试使用所有参数评估"""
        chart_spec = {
            "id": "test",
            "type": "bar",
            "title": "Test",
            "data": {"type": "bar", "data": {"x": ["A"], "y": [10]}},
            "meta": {"unit": "count"}
        }

        data_summary = {
            "statistics": {
                "record_count": 1,
                "has_time_series": False,
                "numeric_fields": ["value"],
                "categorical_fields": []
            },
            "field_info": {}
        }

        data = [{"category": "A", "value": 10}]

        result = self.evaluator.evaluate(chart_spec, data_summary, data)

        assert "overall_score" in result
        assert "dimension_scores" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
