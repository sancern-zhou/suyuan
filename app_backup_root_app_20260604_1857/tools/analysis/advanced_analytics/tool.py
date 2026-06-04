"""
高级分析算法工具 - 异常检测、趋势预测、统计分析

核心功能：
1. 异常检测 - 识别数据中的异常点
2. 趋势预测 - 基于历史数据预测未来趋势
3. 统计分析 - 提供更深度的洞察

适用场景：
- 空气质量异常值检测
- 污染物浓度趋势分析
- 气象要素影响评估

参考：docs/可视化增强方案.md 阶段3任务
"""

from typing import Dict, Any, Optional, List, Tuple
import math
import statistics
from datetime import datetime, timedelta

from abc import ABC, abstractmethod

logger = __import__('structlog').get_logger()


class AdvancedAnalytics:
    """
    高级分析算法工具 - 提供异常检测、趋势预测等功能

    基于统计学和机器学习算法对数据进行分析
    """

    def execute(
        self,
        context: Any,
        analysis_type: str,
        data: Any,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行高级分析

        Args:
            context: 执行上下文
            analysis_type: 分析类型（anomaly_detection, trend_prediction, statistical_analysis）
            data: 要分析的数据
            config: 分析配置
                {
                    "field": "PM2.5",  # 要分析的字段
                    "time_field": "timePoint",  # 时间字段
                    "method": "z_score|iqr|isolation_forest",  # 检测方法
                    "threshold": 2.5,  # 异常阈值
                    "prediction_periods": 7  # 预测未来7个周期
                }

        Returns:
            {
                "status": "success",
                "success": true,
                "data": {
                    "analysis_results": {...},
                    "insights": [...],
                    "visualization_suggestions": [...]
                },
                "summary": "检测到5个异常值，预测趋势上升"
            }
        """
        logger.info(
            "advanced_analytics_start",
            analysis_type=analysis_type,
            has_data=data is not None
        )

        if not config:
            config = {}

        try:
            if analysis_type == "anomaly_detection":
                result = self._detect_anomalies(data, config)
            elif analysis_type == "trend_prediction":
                result = self._predict_trends(data, config)
            elif analysis_type == "statistical_analysis":
                result = self._analyze_statistics(data, config)
            else:
                raise ValueError(f"不支持的分析类型: {analysis_type}")

            return result

        except Exception as e:
            logger.error("advanced_analytics_error", analysis_type=analysis_type, error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "metadata": {
                    "tool_name": "advanced_analytics",
                    "analysis_type": analysis_type
                }
            }

    def _detect_anomalies(
        self,
        data: Any,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """异常检测"""
        field = config.get("field", "value")
        method = config.get("method", "z_score")
        threshold = config.get("threshold", 2.5)

        # 提取数值
        records = self._extract_records_from_data(data)
        values = [
            record.get(field) for record in records
            if isinstance(record.get(field), (int, float))
        ]

        if not values:
            raise ValueError(f"字段'{field}'中没有找到数值数据")

        anomalies = []
        method_results = {}

        if method == "z_score":
            # Z-Score方法：基于标准差
            mean_val = statistics.mean(values)
            stdev_val = statistics.stdev(values) if len(values) > 1 else 0

            if stdev_val == 0:
                method_results["error"] = "数据标准差为0，无法进行异常检测"
            else:
                for i, record in enumerate(records):
                    val = record.get(field)
                    if isinstance(val, (int, float)):
                        z_score = abs((val - mean_val) / stdev_val)
                        if z_score > threshold:
                            anomalies.append({
                                "index": i,
                                "record": record,
                                "value": val,
                                "z_score": z_score,
                                "severity": "high" if z_score > 3 else "medium"
                            })

                method_results = {
                    "mean": mean_val,
                    "std": stdev_val,
                    "threshold": threshold,
                    "anomaly_count": len(anomalies)
                }

        elif method == "iqr":
            # IQR方法：基于四分位数
            sorted_values = sorted(values)
            q1 = statistics.quantiles(sorted_values, n=4)[0]
            q3 = statistics.quantiles(sorted_values, n=4)[2]
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr

            for i, record in enumerate(records):
                val = record.get(field)
                if isinstance(val, (int, float)) and (val < lower_bound or val > upper_bound):
                    anomalies.append({
                        "index": i,
                        "record": record,
                        "value": val,
                        "bounds": [lower_bound, upper_bound],
                        "severity": "high" if val < q1 - 3*iqr or val > q3 + 3*iqr else "medium"
                    })

            method_results = {
                "q1": q1,
                "q3": q3,
                "iqr": iqr,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "anomaly_count": len(anomalies)
            }

        # 生成洞察和建议
        insights = self._generate_anomaly_insights(anomalies, len(values))

        return {
            "status": "success",
            "success": True,
            "data": {
                "analysis_type": "anomaly_detection",
                "method": method,
                "field": field,
                "results": method_results,
                "anomalies": anomalies,
                "insights": insights,
                "visualization_suggestions": [
                    {
                        "type": "timeseries",
                        "config": {
                            "title": f"{field}异常值检测",
                            "highlight_anomalies": True
                        }
                    },
                    {
                        "type": "boxplot",
                        "config": {
                            "title": f"{field}分布箱线图"
                        }
                    }
                ]
            },
            "metadata": {
                "tool_name": "advanced_analytics",
                "analysis_type": "anomaly_detection",
                "method": method
            },
            "summary": f"使用{method}方法检测到{len(anomalies)}个异常值（总数据点：{len(values)}）"
        }

    def _predict_trends(
        self,
        data: Any,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """趋势预测"""
        field = config.get("field", "value")
        time_field = config.get("time_field", "timePoint")
        method = config.get("method", "linear_regression")
        periods = config.get("prediction_periods", 7)

        # 提取时序数据
        records = self._extract_records_from_data(data)
        time_series = self._extract_time_series(records, time_field, field)

        if len(time_series) < 2:
            raise ValueError("时序数据点不足，无法进行预测")

        # 执行预测
        predictions = []
        trend_info = {}

        if method == "linear_regression":
            # 线性回归预测
            x_values = list(range(len(time_series)))
            y_values = [point[1] for point in time_series]

            # 计算回归系数
            n = len(x_values)
            sum_x = sum(x_values)
            sum_y = sum(y_values)
            sum_xy = sum(x * y for x, y in zip(x_values, y_values))
            sum_x2 = sum(x * x for x in x_values)

            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
            intercept = (sum_y - slope * sum_x) / n

            # 生成预测
            last_time = time_series[-1][0]
            for i in range(1, periods + 1):
                pred_x = len(time_series) + i - 1
                pred_y = slope * pred_x + intercept
                predictions.append({
                    "period": i,
                    "value": round(pred_y, 2)
                })

            trend_info = {
                "slope": slope,
                "intercept": intercept,
                "trend_direction": "上升" if slope > 0 else "下降" if slope < 0 else "平稳",
                "trend_strength": abs(slope),
                "r_squared": self._calculate_r_squared(y_values, [slope * x + intercept for x in x_values])
            }

        elif method == "moving_average":
            # 移动平均预测
            window_size = config.get("window_size", 3)
            last_values = [point[1] for point in time_series[-window_size:]]
            avg_value = statistics.mean(last_values)

            for i in range(1, periods + 1):
                predictions.append({
                    "period": i,
                    "value": round(avg_value, 2)
                })

            trend_info = {
                "moving_average": avg_value,
                "window_size": window_size,
                "trend_direction": "平稳",
                "trend_strength": 0
            }

        elif method == "exponential_smoothing":
            # 指数平滑预测
            alpha = config.get("alpha", 0.3)
            smoothed_values = [time_series[0][1]]

            for i in range(1, len(time_series)):
                prev_smoothed = smoothed_values[-1]
                current_value = time_series[i][1]
                new_smoothed = alpha * current_value + (1 - alpha) * prev_smoothed
                smoothed_values.append(new_smoothed)

            last_smoothed = smoothed_values[-1]
            for i in range(1, periods + 1):
                predictions.append({
                    "period": i,
                    "value": round(last_smoothed, 2)
                })

            trend_info = {
                "alpha": alpha,
                "last_smoothed": last_smoothed,
                "trend_direction": "平稳",
                "trend_strength": 0
            }

        # 生成洞察和建议
        insights = self._generate_trend_insights(trend_info, predictions, len(time_series))

        return {
            "status": "success",
            "success": True,
            "data": {
                "analysis_type": "trend_prediction",
                "method": method,
                "field": field,
                "time_field": time_field,
                "historical_points": len(time_series),
                "trend_info": trend_info,
                "predictions": predictions,
                "insights": insights,
                "visualization_suggestions": [
                    {
                        "type": "timeseries",
                        "config": {
                            "title": f"{field}趋势分析与预测",
                            "show_prediction": True,
                            "prediction_periods": periods
                        }
                    }
                ]
            },
            "metadata": {
                "tool_name": "advanced_analytics",
                "analysis_type": "trend_prediction",
                "method": method
            },
            "summary": f"使用{method}方法预测未来{periods}个周期，趋势{trend_info.get('trend_direction', '未知')}"
        }

    def _analyze_statistics(
        self,
        data: Any,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """统计分析"""
        field = config.get("field", "value")

        # 提取数值
        records = self._extract_records_from_data(data)
        values = [
            record.get(field) for record in records
            if isinstance(record.get(field), (int, float))
        ]

        if not values:
            raise ValueError(f"字段'{field}'中没有找到数值数据")

        # 计算统计量
        stats = {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "mode": self._safe_mode(values),
            "min": min(values),
            "max": max(values),
            "range": max(values) - min(values),
            "variance": statistics.variance(values) if len(values) > 1 else 0,
            "stdev": statistics.stdev(values) if len(values) > 1 else 0,
        }

        # 计算分位数
        sorted_values = sorted(values)
        if len(values) >= 2:
            stats["q1"] = statistics.quantiles(sorted_values, n=4)[0]
            stats["q3"] = statistics.quantiles(sorted_values, n=4)[2]
            stats["iqr"] = stats["q3"] - stats["q1"]
        else:
            # 单个数据点时，无法计算分位数
            stats["q1"] = sorted_values[0]
            stats["q3"] = sorted_values[0]
            stats["iqr"] = 0

        # 计算偏度和峰度（简化）
        mean_val = stats["mean"]
        stdev_val = stats["stdev"] if stats["stdev"] > 0 else 1

        skewness = sum((x - mean_val) ** 3 for x in values) / (len(values) * stdev_val ** 3) if len(values) > 2 else 0
        kurtosis = sum((x - mean_val) ** 4 for x in values) / (len(values) * stdev_val ** 4) if len(values) > 3 else 0

        stats["skewness"] = skewness
        stats["kurtosis"] = kurtosis

        # 生成洞察
        insights = self._generate_statistical_insights(stats)

        return {
            "status": "success",
            "success": True,
            "data": {
                "analysis_type": "statistical_analysis",
                "field": field,
                "statistics": stats,
                "insights": insights,
                "distribution_shape": self._classify_distribution(stats),
                "visualization_suggestions": [
                    {
                        "type": "histogram",
                        "config": {
                            "title": f"{field}分布直方图"
                        }
                    },
                    {
                        "type": "boxplot",
                        "config": {
                            "title": f"{field}箱线图"
                        }
                    }
                ]
            },
            "metadata": {
                "tool_name": "advanced_analytics",
                "analysis_type": "statistical_analysis",
                "field": field
            },
            "summary": f"完成{field}的统计分析，数据分布呈{self._classify_distribution(stats)}"
        }

    def _extract_records_from_data(self, data: Any) -> List[Dict[str, Any]]:
        """提取记录"""
        if isinstance(data, dict):
            if "data" in data:
                return data["data"]
            elif isinstance(data, list):
                return data
            else:
                return [data]
        elif isinstance(data, list):
            return data
        else:
            return [data]

    def _extract_time_series(
        self,
        records: List[Dict[str, Any]],
        time_field: str,
        value_field: str
    ) -> List[Tuple[Any, float]]:
        """提取时序数据"""
        time_series = []
        for record in records:
            time_val = record.get(time_field)
            value = record.get(value_field)
            if time_val is not None and isinstance(value, (int, float)):
                time_series.append((time_val, value))

        # 按时间排序
        time_series.sort(key=lambda x: x[0])
        return time_series

    def _safe_mode(self, values: List[float]) -> Any:
        """安全计算众数"""
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        try:
            return statistics.mode(values)
        except statistics.StatisticsError:
            # 如果没有唯一众数，返回最频繁的值
            from collections import Counter
            counter = Counter(values)
            return counter.most_common(1)[0][0] if counter else None

    def _calculate_r_squared(self, actual: List[float], predicted: List[float]) -> float:
        """计算R²"""
        if len(actual) != len(predicted) or len(actual) < 2:
            return 0

        mean_actual = sum(actual) / len(actual)
        ss_tot = sum((y - mean_actual) ** 2 for y in actual)
        ss_res = sum((actual[i] - predicted[i]) ** 2 for i in range(len(actual)))

        return 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    def _generate_anomaly_insights(self, anomalies: List[Dict], total_count: int) -> List[str]:
        """生成异常检测洞察"""
        insights = []

        if not anomalies:
            insights.append("未检测到异常值，数据质量良好")
            return insights

        anomaly_rate = len(anomalies) / total_count * 100
        insights.append(f"检测到{len(anomalies)}个异常值，占总数据的{anomaly_rate:.1f}%")

        if anomaly_rate > 5:
            insights.append("异常值比例较高，建议检查数据源或测量设备")
        elif anomaly_rate > 1:
            insights.append("存在少量异常值，建议进一步调查原因")

        # 分析异常值严重程度
        high_severity = sum(1 for a in anomalies if a.get("severity") == "high")
        if high_severity > 0:
            insights.append(f"其中{high_severity}个为高严重度异常值，需要重点关注")

        return insights

    def _generate_trend_insights(
        self,
        trend_info: Dict,
        predictions: List[Dict],
        historical_points: int
    ) -> List[str]:
        """生成趋势预测洞察"""
        insights = []

        direction = trend_info.get("trend_direction", "未知")
        strength = trend_info.get("trend_strength", 0)

        insights.append(f"历史数据显示{direction}趋势")

        if strength > 0:
            if direction == "上升":
                insights.append(f"趋势强度为{strength:.3f}，呈上升态势")
            elif direction == "下降":
                insights.append(f"趋势强度为{strength:.3f}，呈下降态势")

        if predictions:
            avg_pred = statistics.mean([p["value"] for p in predictions])
            insights.append(f"预测未来平均值为{avg_pred:.2f}")

        if "r_squared" in trend_info:
            r2 = trend_info["r_squared"]
            if r2 > 0.7:
                insights.append(f"模型拟合度较高（R²={r2:.3f}），预测可信度好")
            elif r2 > 0.3:
                insights.append(f"模型拟合度中等（R²={r2:.3f}），预测结果需谨慎参考")
            else:
                insights.append(f"模型拟合度较低（R²={r2:.3f}），建议使用其他方法")

        return insights

    def _generate_statistical_insights(self, stats: Dict) -> List[str]:
        """生成统计分析洞察"""
        insights = []

        mean = stats["mean"]
        median = stats["median"]
        mode = stats["mode"]

        # 中心趋势
        if abs(mean - median) / mean < 0.1 if mean != 0 else abs(mean - median) < 1:
            insights.append("均值与中位数接近，数据分布较为对称")
        elif mean > median:
            insights.append("均值大于中位数，数据呈右偏分布")
        else:
            insights.append("均值小于中位数，数据呈左偏分布")

        # 变异性
        cv = stats["stdev"] / stats["mean"] if stats["mean"] != 0 else 0
        if cv < 0.1:
            insights.append("数据变异性很小，数值较为集中")
        elif cv > 0.5:
            insights.append("数据变异性较大，数值分散")
        else:
            insights.append("数据变异性适中")

        # 分布形状
        skewness = stats.get("skewness", 0)
        if abs(skewness) < 0.5:
            insights.append("数据分布接近正态分布")
        elif skewness > 0.5:
            insights.append("数据分布右偏，存在长尾")
        else:
            insights.append("数据分布左偏，存在长尾")

        return insights

    def _classify_distribution(self, stats: Dict) -> str:
        """分类分布形状"""
        skewness = stats.get("skewness", 0)
        kurtosis = stats.get("kurtosis", 0)

        if abs(skewness) < 0.5 and abs(kurtosis - 3) < 1:
            return "正态分布"
        elif skewness > 0.5:
            return "右偏分布"
        elif skewness < -0.5:
            return "左偏分布"
        elif kurtosis > 4:
            return "尖峰分布"
        elif kurtosis < 2:
            return "平峰分布"
        else:
            return "接近正态分布"


# ============================================
# 便捷函数
# ============================================

async def detect_anomalies(
    data: Any,
    field: str,
    method: str = "z_score",
    threshold: float = 2.5
) -> Dict[str, Any]:
    """快速异常检测"""
    config = {
        "field": field,
        "method": method,
        "threshold": threshold
    }

    class MockContext:
        def __init__(self):
            self.requires_context = False

    context = MockContext()
    analytics = AdvancedAnalytics()
    return analytics.execute(context, "anomaly_detection", data, config)


async def predict_trends(
    data: Any,
    field: str,
    time_field: str = "timePoint",
    method: str = "linear_regression",
    periods: int = 7
) -> Dict[str, Any]:
    """快速趋势预测"""
    config = {
        "field": field,
        "time_field": time_field,
        "method": method,
        "prediction_periods": periods
    }

    class MockContext:
        def __init__(self):
            self.requires_context = False

    context = MockContext()
    analytics = AdvancedAnalytics()
    return analytics.execute(context, "trend_prediction", data, config)


async def analyze_statistics(
    data: Any,
    field: str
) -> Dict[str, Any]:
    """快速统计分析"""
    config = {"field": field}

    class MockContext:
        def __init__(self):
            self.requires_context = False

    context = MockContext()
    analytics = AdvancedAnalytics()
    return analytics.execute(context, "statistical_analysis", data, config)


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":
    import asyncio

    async def example():
        """示例：异常检测和趋势分析"""
        # 模拟数据
        data = [
            {"timePoint": f"2025-01-{i:02d}", "PM2.5": 30 + i * 2 + (10 if i == 10 else 0)}
            for i in range(1, 21)
        ]

        # 异常检测
        print("=== 异常检测 ===")
        result1 = await detect_anomalies(data, "PM2.5", method="z_score", threshold=2)
        print(f"检测结果: {result1['summary']}")
        print(f"洞察: {result1['data']['insights']}")

        # 趋势预测
        print("\n=== 趋势预测 ===")
        result2 = await predict_trends(data, "PM2.5", periods=5)
        print(f"预测结果: {result2['summary']}")
        print(f"趋势: {result2['data']['trend_info']['trend_direction']}")

        # 统计分析
        print("\n=== 统计分析 ===")
        result3 = await analyze_statistics(data, "PM2.5")
        print(f"分析结果: {result3['summary']}")
        stats = result3['data']['statistics']
        print(f"均值: {stats['mean']:.2f}, 标准差: {stats['stdev']:.2f}")

    asyncio.run(example())
