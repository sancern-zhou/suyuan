"""
测试图表策略选择器 (ChartStrategySelector)

验证内容：
1. 策略选择逻辑（4级优先级）
2. 场景匹配算法
3. 复杂意图识别
4. 策略配置生成
"""

import pytest

from app.tools.visualization.chart_strategy import (
    ChartStrategySelector,
    StrategyType
)


class TestStrategySelection:
    """测试策略选择"""

    def setup_method(self):
        """初始化测试"""
        self.selector = ChartStrategySelector()

    def test_template_strategy_no_intent(self):
        """测试无用户意图时选择模板策略"""
        strategy = self.selector.select_strategy(
            data_id="vocs:v1:test",
            schema="vocs"
        )

        assert strategy == "template"

    def test_template_strategy_with_matching_intent(self):
        """测试用户意图匹配时选择模板策略"""
        strategy = self.selector.select_strategy(
            data_id="vocs:v1:test",
            schema="vocs",
            user_intent="我想看VOCs的组分占比"
        )

        assert strategy == "template"

    def test_template_strategy_for_pmf(self):
        """测试PMF数据选择模板策略"""
        strategy = self.selector.select_strategy(
            data_id="pmf:v1:test",
            schema="pmf_result",
            user_intent="显示污染源贡献"
        )

        assert strategy == "template"

    def test_intelligent_recommend_with_timeseries(self):
        """测试包含时序数据时的智能推荐"""
        strategy = self.selector.select_strategy(
            data_id="air_quality:v1:test",
            schema="air_quality",
            data_summary={
                "statistics": {
                    "has_time_series": True,
                    "record_count": 1000
                }
            }
        )

        # 可能是template（如果意图匹配）或intelligent_recommend
        assert strategy in ["template", "intelligent_recommend"]

    def test_llm_custom_with_complex_intent(self):
        """测试复杂意图时选择LLM自定义"""
        strategy = self.selector.select_strategy(
            data_id="air_quality:v1:test",
            schema="air_quality",
            user_intent="我想看PM2.5和O3的时序变化，同时对比不同站点，并分析它们的相关性"
        )

        assert strategy == "llm_custom"

    def test_llm_custom_with_prefer_custom(self):
        """测试用户偏好自定义时选择LLM"""
        strategy = self.selector.select_strategy(
            data_id="vocs:v1:test",
            schema="vocs",
            prefer_custom=True
        )

        assert strategy == "llm_custom"

    def test_fallback_for_unknown_schema(self):
        """测试未知schema时使用fallback"""
        strategy = self.selector.select_strategy(
            data_id="unknown:v1:test",
            schema="unknown_type"
        )

        assert strategy == "fallback"


class TestScenarioMatching:
    """测试场景匹配"""

    def setup_method(self):
        """初始化测试"""
        self.selector = ChartStrategySelector()

    def test_match_composition_scenario(self):
        """测试匹配组分占比场景"""
        result = self.selector._match_scenario(
            "我想看VOCs的组分占比",
            "组分占比"
        )
        assert result is True

    def test_match_trend_scenario(self):
        """测试匹配趋势场景"""
        result = self.selector._match_scenario(
            "显示PM2.5浓度变化趋势",
            "浓度趋势"
        )
        assert result is True

    def test_match_comparison_scenario(self):
        """测试匹配对比场景"""
        result = self.selector._match_scenario(
            "对比不同站点的污染物浓度",
            "污染物对比"
        )
        assert result is True

    def test_match_wind_rose_scenario(self):
        """测试匹配风向玫瑰场景"""
        result = self.selector._match_scenario(
            "生成风向玫瑰图",
            "风向玫瑰"
        )
        assert result is True

    def test_match_source_contribution_scenario(self):
        """测试匹配源贡献场景"""
        result = self.selector._match_scenario(
            "分析污染源贡献",
            "源贡献占比"
        )
        assert result is True

    def test_no_match_different_scenario(self):
        """测试不匹配的场景"""
        result = self.selector._match_scenario(
            "显示PM2.5浓度",
            "风向玫瑰"
        )
        assert result is False

    def test_case_insensitive_matching(self):
        """测试大小写不敏感匹配"""
        result = self.selector._match_scenario(
            "我想看VOCS的占比",
            "组分占比"
        )
        assert result is True


class TestComplexIntentDetection:
    """测试复杂意图识别"""

    def setup_method(self):
        """初始化测试"""
        self.selector = ChartStrategySelector()

    def test_detect_linkage_intent(self):
        """测试检测联动意图"""
        result = self.selector._is_complex_intent(
            "我想看多个图表联动显示"
        )
        assert result is True

    def test_detect_overlay_intent(self):
        """测试检测叠加意图"""
        result = self.selector._is_complex_intent(
            "将PM2.5和O3叠加在一张图上"
        )
        assert result is True

    def test_detect_multi_chart_intent(self):
        """测试检测多图表意图"""
        result = self.selector._is_complex_intent(
            "同时显示多图对比"
        )
        assert result is True

    def test_detect_correlation_intent(self):
        """测试检测相关性意图"""
        result = self.selector._is_complex_intent(
            "分析PM2.5和气象因素的相关性"
        )
        assert result is True

    def test_detect_multidimensional_intent(self):
        """测试检测多维度意图"""
        result = self.selector._is_complex_intent(
            "多维度分析污染物变化"
        )
        assert result is True

    def test_simple_intent_not_complex(self):
        """测试简单意图不被识别为复杂"""
        result = self.selector._is_complex_intent(
            "显示PM2.5浓度"
        )
        assert result is False

    def test_none_intent(self):
        """测试None意图"""
        result = self.selector._is_complex_intent(None)
        assert result is False


class TestGetStrategyConfig:
    """测试获取策略配置"""

    def setup_method(self):
        """初始化测试"""
        self.selector = ChartStrategySelector()

    def test_template_config(self):
        """测试模板策略配置"""
        config = self.selector.get_strategy_config(
            strategy="template",
            schema="vocs"
        )

        assert config["executor"] == "generate_chart"
        assert config["params"]["use_template"] is True
        assert config["timeout"] == 5
        assert config["params"]["template"] is not None

    def test_intelligent_recommend_config(self):
        """测试智能推荐策略配置"""
        config = self.selector.get_strategy_config(
            strategy="intelligent_recommend",
            schema="air_quality"
        )

        assert config["executor"] == "smart_chart_generator"
        assert config["params"]["auto_recommend"] is True
        assert config["timeout"] == 10

    def test_llm_custom_config(self):
        """测试LLM自定义策略配置"""
        config = self.selector.get_strategy_config(
            strategy="llm_custom",
            schema="vocs"
        )

        assert config["executor"] == "intelligent_visualization_planner"
        assert config["params"]["use_llm"] is True
        assert config["timeout"] == 30

    def test_fallback_config(self):
        """测试fallback策略配置"""
        config = self.selector.get_strategy_config(
            strategy="fallback",
            schema="unknown"
        )

        assert config["executor"] == "generate_chart"
        assert config["params"]["chart_type"] == "bar"
        assert config["params"]["simple_mode"] is True
        assert config["timeout"] == 5


class TestExplainDecision:
    """测试决策解释"""

    def setup_method(self):
        """初始化测试"""
        self.selector = ChartStrategySelector()

    def test_explain_template_decision(self):
        """测试解释模板策略决策"""
        explanation = self.selector.explain_decision(
            strategy="template",
            schema="vocs"
        )

        assert "模板" in explanation
        assert "vocs" in explanation

    def test_explain_intelligent_recommend_decision(self):
        """测试解释智能推荐策略决策"""
        explanation = self.selector.explain_decision(
            strategy="intelligent_recommend",
            schema="air_quality"
        )

        assert "智能推荐" in explanation or "推荐" in explanation
        assert "air_quality" in explanation

    def test_explain_llm_custom_decision(self):
        """测试解释LLM自定义策略决策"""
        explanation = self.selector.explain_decision(
            strategy="llm_custom",
            schema="vocs",
            user_intent="复杂分析"
        )

        assert "AI" in explanation or "大模型" in explanation or "LLM" in explanation

    def test_explain_fallback_decision(self):
        """测试解释fallback策略决策"""
        explanation = self.selector.explain_decision(
            strategy="fallback",
            schema="unknown"
        )

        assert "默认" in explanation or "fallback" in explanation


class TestIntegrationScenarios:
    """测试集成场景"""

    def setup_method(self):
        """初始化测试"""
        self.selector = ChartStrategySelector()

    def test_vocs_pie_chart_scenario(self):
        """测试VOCs饼图场景"""
        strategy = self.selector.select_strategy(
            data_id="vocs:v1:test",
            schema="vocs",
            user_intent="显示VOCs组分占比"
        )

        assert strategy == "template"

        config = self.selector.get_strategy_config(strategy, "vocs", "显示VOCs组分占比")
        assert config["executor"] == "generate_chart"

    def test_air_quality_timeseries_scenario(self):
        """测试空气质量时序图场景"""
        strategy = self.selector.select_strategy(
            data_id="air_quality:v1:test",
            schema="air_quality",
            user_intent="显示PM2.5时序变化"
        )

        # 应该匹配到模板
        assert strategy == "template"

    def test_guangdong_stations_comparison(self):
        """测试广东站点对比场景"""
        strategy = self.selector.select_strategy(
            data_id="guangdong:v1:test",
            schema="guangdong_stations",
            user_intent="对比各站点污染物浓度"
        )

        assert strategy == "template"

    def test_pmf_result_visualization(self):
        """测试PMF结果可视化场景"""
        strategy = self.selector.select_strategy(
            data_id="pmf:v1:test",
            schema="pmf_result",
            user_intent="展示源解析结果"
        )

        assert strategy == "template"

    def test_complex_multi_chart_scenario(self):
        """测试复杂多图表场景"""
        strategy = self.selector.select_strategy(
            data_id="air_quality:v1:test",
            schema="air_quality",
            user_intent="生成污染物和气象要素的多图表联动分析",
            data_summary={
                "statistics": {
                    "has_time_series": True,
                    "has_multiple_categories": True
                }
            }
        )

        # 应该识别为复杂意图，选择LLM
        assert strategy == "llm_custom"


class TestEdgeCases:
    """测试边界情况"""

    def setup_method(self):
        """初始化测试"""
        self.selector = ChartStrategySelector()

    def test_empty_user_intent(self):
        """测试空用户意图"""
        strategy = self.selector.select_strategy(
            data_id="vocs:v1:test",
            schema="vocs",
            user_intent=""
        )

        # 空意图应该被当作无意图
        assert strategy == "template"

    def test_none_data_summary(self):
        """测试None数据摘要"""
        strategy = self.selector.select_strategy(
            data_id="vocs:v1:test",
            schema="vocs",
            data_summary=None
        )

        # 没有数据摘要时应该使用模板
        assert strategy == "template"

    def test_unknown_schema_fallback(self):
        """测试未知schema降级"""
        strategy = self.selector.select_strategy(
            data_id="unknown:v1:test",
            schema="completely_unknown_type"
        )

        # 应该降级到fallback
        assert strategy == "fallback"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
