"""
测试高级分析算法工具 (AdvancedAnalytics)

验证内容：
1. 异常检测 (Z-Score, IQR方法)
2. 趋势预测 (线性回归, 移动平均, 指数平滑)
3. 统计分析
4. 数据质量评估
"""

import pytest
from typing import Dict, Any

from app.tools.analysis.advanced_analytics.tool import (
    AdvancedAnalytics,
    detect_anomalies,
    predict_trends,
    analyze_statistics
)


class TestAnomalyDetection:
    """测试异常检测"""

    def setup_method(self):
        self.analytics = AdvancedAnalytics()

    def test_z_score_detection_with_anomalies(self):
        """测试Z-Score异常检测（有异常值）"""
        data = [
            {"value": 10}, {"value": 11}, {"value": 12}, {"value": 11},
            {"value": 10}, {"value": 50}  # 异常值
        ]

        result = self.analytics._detect_anomalies(data, {
            "field": "value",
            "method": "z_score",
            "threshold": 2
        })

        assert result["data"]["analysis_type"] == "anomaly_detection"
        assert result["data"]["method"] == "z_score"
        assert len(result["data"]["anomalies"]) > 0
        assert "insights" in result["data"]

    def test_z_score_detection_no_anomalies(self):
        """测试Z-Score异常检测（无异常值）"""
        data = [
            {"value": 10}, {"value": 11}, {"value": 12}, {"value": 11}, {"value": 10}
        ]

        result = self.analytics._detect_anomalies(data, {
            "field": "value",
            "method": "z_score",
            "threshold": 1
        })

        # 可能检测到一些异常，但应该少于高阈值的情况
        assert "anomalies" in result["data"]

    def test_iqr_detection_with_anomalies(self):
        """测试IQR异常检测"""
        data = [
            {"value": 10}, {"value": 11}, {"value": 12}, {"value": 11},
            {"value": 10}, {"value": 50}
        ]

        result = self.analytics._detect_anomalies(data, {
            "field": "value",
            "method": "iqr"
        })

        assert result["data"]["analysis_type"] == "anomaly_detection"
        assert result["data"]["method"] == "iqr"
        assert "results" in result["data"]
        assert "anomalies" in result["data"]

    def test_iqr_detection_no_anomalies(self):
        """测试IQR异常检测（无异常值）"""
        data = [
            {"value": 10}, {"value": 11}, {"value": 12}, {"value": 11}, {"value": 10}
        ]

        result = self.analytics._detect_anomalies(data, {
            "field": "value",
            "method": "iqr"
        })

        assert "results" in result["data"]

    def test_anomaly_detection_missing_field(self):
        """测试异常检测（字段不存在）"""
        data = [
            {"value1": 10}, {"value1": 11}
        ]

        with pytest.raises(ValueError, match="字段.*中没有找到数值数据"):
            self.analytics._detect_anomalies(data, {
                "field": "nonexistent_field",
                "method": "z_score"
            })

    def test_anomaly_detection_empty_data(self):
        """测试异常检测（空数据）"""
        data = []

        with pytest.raises(ValueError):
            self.analytics._detect_anomalies(data, {
                "field": "value",
                "method": "z_score"
            })

    def test_generate_anomaly_insights_with_anomalies(self):
        """测试生成异常检测洞察（有异常）"""
        anomalies = [
            {"value": 50, "severity": "high"},
            {"value": 45, "severity": "medium"}
        ]
        total_count = 10

        insights = self.analytics._generate_anomaly_insights(anomalies, total_count)

        assert len(insights) > 0
        assert "异常值" in insights[0]

    def test_generate_anomaly_insights_without_anomalies(self):
        """测试生成异常检测洞察（无异常）"""
        anomalies = []
        total_count = 10

        insights = self.analytics._generate_anomaly_insights(anomalies, total_count)

        assert len(insights) > 0
        assert "未检测到异常值" in insights[0]


class TestTrendPrediction:
    """测试趋势预测"""

    def setup_method(self):
        self.analytics = AdvancedAnalytics()

    def test_linear_regression_prediction(self):
        """测试线性回归预测"""
        data = [
            {"timePoint": f"2025-01-{i:02d}", "value": i * 2 + 10}
            for i in range(1, 11)
        ]

        result = self.analytics._predict_trends(data, {
            "field": "value",
            "time_field": "timePoint",
            "method": "linear_regression",
            "prediction_periods": 3
        })

        assert result["data"]["analysis_type"] == "trend_prediction"
        assert result["data"]["method"] == "linear_regression"
        assert len(result["data"]["predictions"]) == 3
        assert "trend_info" in result["data"]
        assert "slope" in result["data"]["trend_info"]

    def test_moving_average_prediction(self):
        """测试移动平均预测"""
        data = [
            {"timePoint": f"2025-01-{i:02d}", "value": 10 + i}
            for i in range(1, 11)
        ]

        result = self.analytics._predict_trends(data, {
            "field": "value",
            "time_field": "timePoint",
            "method": "moving_average",
            "prediction_periods": 3,
            "window_size": 3
        })

        assert result["data"]["method"] == "moving_average"
        assert len(result["data"]["predictions"]) == 3

    def test_exponential_smoothing_prediction(self):
        """测试指数平滑预测"""
        data = [
            {"timePoint": f"2025-01-{i:02d}", "value": 10 + i}
            for i in range(1, 11)
        ]

        result = self.analytics._predict_trends(data, {
            "field": "value",
            "time_field": "timePoint",
            "method": "exponential_smoothing",
            "prediction_periods": 3,
            "alpha": 0.3
        })

        assert result["data"]["method"] == "exponential_smoothing"
        assert "alpha" in result["data"]["trend_info"]

    def test_prediction_insufficient_data(self):
        """测试预测（数据不足）"""
        data = [{"timePoint": "2025-01-01", "value": 10}]

        with pytest.raises(ValueError, match="时序数据点不足"):
            self.analytics._predict_trends(data, {
                "field": "value",
                "time_field": "timePoint",
                "method": "linear_regression"
            })

    def test_generate_trend_insights(self):
        """测试生成趋势洞察"""
        trend_info = {
            "trend_direction": "上升",
            "trend_strength": 0.5,
            "r_squared": 0.8
        }
        predictions = [
            {"period": 1, "value": 20},
            {"period": 2, "value": 22}
        ]
        historical_points = 10

        insights = self.analytics._generate_trend_insights(
            trend_info, predictions, historical_points
        )

        assert len(insights) > 0
        assert "历史数据显示上升趋势" in insights[0]


class TestStatisticalAnalysis:
    """测试统计分析"""

    def setup_method(self):
        self.analytics = AdvancedAnalytics()

    def test_basic_statistics(self):
        """测试基本统计"""
        data = [
            {"value": 10}, {"value": 20}, {"value": 30}, {"value": 40}, {"value": 50}
        ]

        result = self.analytics._analyze_statistics(data, {
            "field": "value"
        })

        assert result["data"]["analysis_type"] == "statistical_analysis"
        assert "statistics" in result["data"]
        stats = result["data"]["statistics"]
        assert stats["count"] == 5
        assert stats["mean"] == 30
        assert stats["min"] == 10
        assert stats["max"] == 50
        assert "distribution_shape" in result["data"]

    def test_statistics_with_mode(self):
        """测试包含众数的统计"""
        data = [
            {"value": 10}, {"value": 20}, {"value": 20}, {"value": 30}
        ]

        result = self.analytics._analyze_statistics(data, {
            "field": "value"
        })

        stats = result["data"]["statistics"]
        assert stats["mode"] == 20

    def test_statistics_single_value(self):
        """测试单一值统计"""
        data = [{"value": 25}]

        result = self.analytics._analyze_statistics(data, {
            "field": "value"
        })

        stats = result["data"]["statistics"]
        assert stats["count"] == 1
        assert stats["mean"] == 25
        assert stats["stdev"] == 0

    def test_generate_statistical_insights(self):
        """测试生成统计洞察"""
        stats = {
            "mean": 30,
            "median": 30,
            "mode": 30,
            "stdev": 5,
            "skewness": 0.2,
            "kurtosis": 3
        }

        insights = self.analytics._generate_statistical_insights(stats)

        assert len(insights) > 0

    def test_classify_distribution(self):
        """测试分布形状分类"""
        # 正态分布
        stats_normal = {"skewness": 0.1, "kurtosis": 3}
        shape = self.analytics._classify_distribution(stats_normal)
        assert "正态" in shape

        # 右偏分布
        stats_right = {"skewness": 0.8, "kurtosis": 3}
        shape = self.analytics._classify_distribution(stats_right)
        assert "右偏" in shape

        # 左偏分布
        stats_left = {"skewness": -0.8, "kurtosis": 3}
        shape = self.analytics._classify_distribution(stats_left)
        assert "左偏" in shape


class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_detect_anomalies_function(self):
        """测试detect_anomalies便捷函数"""
        import asyncio

        async def run_test():
            data = [
                {"value": 10}, {"value": 11}, {"value": 50}
            ]

            result = await detect_anomalies(data, "value", method="z_score", threshold=2)
            assert "status" in result
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_predict_trends_function(self):
        """测试predict_trends便捷函数"""
        import asyncio

        async def run_test():
            data = [
                {"timePoint": f"2025-01-{i:02d}", "value": i * 2}
                for i in range(1, 6)
            ]

            result = await predict_trends(
                data, "value", "timePoint",
                method="linear_regression", periods=3
            )
            assert "status" in result
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_analyze_statistics_function(self):
        """测试analyze_statistics便捷函数"""
        import asyncio

        async def run_test():
            data = [{"value": i} for i in range(1, 11)]

            result = await analyze_statistics(data, "value")
            assert "status" in result
            assert "statistics" in result["data"]
            return True

        result = asyncio.run(run_test())
        assert result is True


class TestEdgeCases:
    """测试边界情况"""

    def setup_method(self):
        self.analytics = AdvancedAnalytics()

    def test_execute_unsupported_analysis_type(self):
        """测试不支持的分析类型"""
        data = [{"value": 10}]

        result = self.analytics.execute(None, "unsupported_type", data, {})
        # 方法会返回失败响应而不是抛出异常
        assert result["success"] is False
        assert "不支持的分析类型" in result.get("error", "")

    def test_extract_time_series_with_missing_data(self):
        """测试提取时序数据（含缺失数据）"""
        records = [
            {"timePoint": "2025-01-01", "value": 10},
            {"timePoint": "2025-01-02"},  # 缺失value
            {"timePoint": "2025-01-03", "value": 30}
        ]

        time_series = self.analytics._extract_time_series(records, "timePoint", "value")

        # 应该过滤掉缺失数据的记录
        assert len(time_series) == 2
        assert time_series[0] == ("2025-01-01", 10)
        assert time_series[1] == ("2025-01-03", 30)

    def test_safe_mode_no_unique_mode(self):
        """测试安全计算众数（无唯一众数）"""
        values = [10, 20, 20, 30, 30]
        mode = self.analytics._safe_mode(values)

        # 应该返回最频繁的值
        assert mode in [20, 30]

    def test_calculate_r_squared(self):
        """测试R²计算"""
        actual = [10, 20, 30, 40, 50]
        predicted = [12, 22, 28, 38, 48]

        r2 = self.analytics._calculate_r_squared(actual, predicted)

        assert 0 <= r2 <= 1

    def test_calculate_r_squared_insufficient_data(self):
        """测试R²计算（数据不足）"""
        actual = [10]
        predicted = [12]

        r2 = self.analytics._calculate_r_squared(actual, predicted)

        assert r2 == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
