"""
测试智能可视化规划器 (IntelligentVisualizationPlanner)

验证内容：
1. 自然语言理解与方案生成
2. 基于数据特征的分析
3. 方案验证
4. 降级处理
"""

import pytest
from typing import Dict, Any

from app.tools.analysis.intelligent_visualization_planner.tool import (
    IntelligentVisualizationPlanner,
    plan_visualization
)


class TestIntelligentVisualizationPlanner:
    """测试智能可视化规划器"""

    def setup_method(self):
        """初始化测试"""
        self.planner = IntelligentVisualizationPlanner()

    def test_planner_initialization(self):
        """测试规划器初始化"""
        assert self.planner is not None

    def test_generate_fallback_plan_with_timeseries_keywords(self):
        """测试基于时序关键词的降级方案"""
        user_intent = "我想看各站点PM2.5的时序变化"

        result = self.planner._generate_fallback_plan(user_intent)

        assert "charts" in result
        assert len(result["charts"]) > 0
        assert result["charts"][0]["type"] == "timeseries"
        assert "reasoning" in result

    def test_generate_fallback_plan_with_bar_keywords(self):
        """测试基于柱状图关键词的降级方案"""
        user_intent = "我想对比不同站点的浓度"

        result = self.planner._generate_fallback_plan(user_intent)

        assert result["charts"][0]["type"] == "bar"

    def test_generate_fallback_plan_with_pie_keywords(self):
        """测试基于饼图关键词的降级方案"""
        user_intent = "我想看各污染物的占比分布"

        result = self.planner._generate_fallback_plan(user_intent)

        assert result["charts"][0]["type"] == "pie"

    def test_generate_fallback_plan_default(self):
        """测试默认降级方案"""
        user_intent = "我想看数据分析"

        result = self.planner._generate_fallback_plan(user_intent)

        assert "charts" in result
        assert "layout" in result

    def test_validate_plan_basic(self):
        """测试基本方案验证"""
        plan = {
            "charts": [
                {"type": "bar"},
                {"type": "line"}
            ],
            "layout": "grid"
        }

        validated = self.planner._validate_plan(plan, None)

        assert "charts" in validated
        assert "layout" in validated
        assert len(validated["charts"]) == 2

    def test_validate_plan_filter_unsupported_types(self):
        """测试过滤不支持的图表类型"""
        plan = {
            "charts": [
                {"type": "bar"},
                {"type": "unsupported_type"},
                {"type": "line"}
            ],
            "layout": "single"
        }

        validated = self.planner._validate_plan(plan, None)

        # 应该过滤掉不支持的类型
        chart_types = [c["type"] for c in validated["charts"]]
        assert "bar" in chart_types
        assert "line" in chart_types
        assert "unsupported_type" not in chart_types

    def test_validate_plan_no_charts(self):
        """测试空方案验证"""
        plan = {
            "layout": "single"
        }

        validated = self.planner._validate_plan(plan, None)

        assert "charts" in validated
        assert validated["charts"] == []

    def test_assess_complexity_low(self):
        """测试低复杂度评估"""
        plan = {
            "charts": [{"type": "bar"}],
            "layout": "single"
        }

        complexity = self.planner._assess_complexity(plan)

        assert complexity == "low"

    def test_assess_complexity_medium(self):
        """测试中等复杂度评估"""
        plan = {
            "charts": [{"type": "bar"}, {"type": "line"}],
            "layout": "single"
        }

        complexity = self.planner._assess_complexity(plan)

        assert complexity == "medium"

    def test_assess_complexity_high(self):
        """测试高复杂度评估"""
        plan = {
            "charts": [{"type": "bar"}, {"type": "line"}, {"type": "pie"}],
            "layout": "grid"
        }

        complexity = self.planner._assess_complexity(plan)

        assert complexity == "high"

    def test_assess_complexity_high_with_grid(self):
        """测试高复杂度评估（网格布局）"""
        plan = {
            "charts": [{"type": "bar"}],
            "layout": "grid"
        }

        complexity = self.planner._assess_complexity(plan)

        assert complexity == "high"

    def test_build_planning_prompt_without_data_profile(self):
        """测试构建提示词（无数据特征）"""
        user_intent = "我想看PM2.5的变化"
        data_profile = None

        prompt = self.planner._build_planning_prompt(user_intent, data_profile)

        assert "用户需求：" in prompt
        assert user_intent in prompt
        assert "数据特征：" not in prompt

    def test_build_planning_prompt_with_data_profile(self):
        """测试构建提示词（有数据特征）"""
        user_intent = "我想看PM2.5的变化"
        data_profile = {
            "statistics": {
                "record_count": 100,
                "has_time_series": True
            },
            "field_info": {
                "PM2.5": {"type": "quantitative"},
                "station_name": {"type": "nominal"}
            }
        }

        prompt = self.planner._build_planning_prompt(user_intent, data_profile)

        assert "用户需求：" in prompt
        assert "数据特征：" in prompt
        assert "记录数：100" in prompt
        assert "包含时序数据：是" in prompt


class TestConvenienceFunction:
    """测试便捷函数"""

    def test_plan_visualization_function(self):
        """测试plan_visualization便捷函数"""
        import asyncio

        async def run_test():
            class MockContext:
                def __init__(self):
                    self.requires_context = False

            context = MockContext()
            user_intent = "我想看PM2.5时序变化"

            result = await plan_visualization(
                context=context,
                user_intent=user_intent,
                data_id=None
            )

            assert "status" in result
            assert "success" in result
            return True

        # 运行异步测试
        result = asyncio.run(run_test())
        assert result is True


class TestEdgeCases:
    """测试边界情况"""

    def setup_method(self):
        self.planner = IntelligentVisualizationPlanner()

    def test_empty_user_intent(self):
        """测试空用户意图"""
        result = self.planner._generate_fallback_plan("")

        assert "charts" in result

    def test_very_long_user_intent(self):
        """测试超长用户意图"""
        long_intent = "我想看" * 100
        result = self.planner._generate_fallback_plan(long_intent)

        assert "charts" in result

    def test_mixed_keywords_intent(self):
        """测试混合关键词意图"""
        # 包含多个关键词
        result = self.planner._generate_fallback_plan("我想看时序变化和占比分布")

        assert "charts" in result
        # 应该匹配第一个关键词
        assert result["charts"][0]["type"] in ["timeseries", "bar", "pie"]

    def test_special_characters_in_intent(self):
        """测试包含特殊字符的意图"""
        result = self.planner._generate_fallback_plan("我想看PM2.5@#$%的变化")

        assert "charts" in result

    def test_chinese_mixed_with_english(self):
        """测试中英文混合意图"""
        result = self.planner._generate_fallback_plan("I want to see 时序变化")

        assert "charts" in result
        assert "reasoning" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
