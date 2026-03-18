"""
智能可视化推荐器 (SmartVisualizationRecommender)

基于数据特征和用户意图,智能推荐最佳可视化方案
"""

from typing import Dict, List, Any, Optional
import structlog

logger = structlog.get_logger()


class SmartVisualizationRecommender:
    """智能可视化推荐器 - 气象专家专用"""

    # 数据特征检测规则
    DATA_FEATURE_RULES = {
        "wind_data": {
            "required_fields": ["wind_speed", "wind_direction"],
            "recommended_charts": ["wind_rose"],
            "priority": "high",
            "description": "风向风速数据 → 风向玫瑰图"
        },
        "profile_data": {
            "required_fields": ["altitude", "height"],
            "recommended_charts": ["profile"],
            "priority": "high",
            "description": "边界层数据 → 廓线图"
        },
        "trajectory_data": {
            "required_fields": ["trajectory_id", "lat", "lon"],
            "recommended_charts": ["map", "line3d"],
            "priority": "high",
            "description": "轨迹数据 → 地图可视化"
        },
        "timeseries_data": {
            "required_fields": ["timestamp", "temperature_2m"],
            "recommended_charts": ["timeseries", "line"],
            "priority": "medium",
            "description": "时序数据 → 时序图"
        },
        "multi_location": {
            "detection": "station_count > 1",
            "recommended_charts": ["map", "heatmap"],
            "priority": "medium",
            "description": "多站点数据 → 空间分布图"
        }
    }

    def __init__(self):
        logger.info("smart_visualization_recommender_initialized")

    def recommend_visualizations(
        self,
        data_preview: Dict[str, Any],
        schema_type: str,
        user_intent: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        智能推荐可视化方案

        Args:
            data_preview: 数据预览（前几条记录）
            schema_type: 数据schema类型
            user_intent: 用户意图（可选）

        Returns:
            推荐的可视化工具列表
        """
        recommendations = []

        # Step 1: 基于数据特征检测
        detected_features = self._detect_data_features(data_preview)

        logger.info(
            "data_features_detected",
            schema_type=schema_type,
            features=detected_features
        )

        # Step 2: 应用推荐规则
        for feature_name, feature_info in detected_features.items():
            rule = self.DATA_FEATURE_RULES.get(feature_name)
            if rule:
                for chart_type in rule["recommended_charts"]:
                    recommendations.append({
                        "tool": "generate_chart",
                        "chart_type": chart_type,
                        "reason": rule["description"],
                        "priority": rule["priority"],
                        "depends_on": [0]  # 依赖数据获取工具
                    })

        # Step 3: 添加默认智能图表生成器(兜底)
        recommendations.append({
            "tool": "smart_chart_generator",
            "chart_type": "auto",
            "reason": "默认智能可视化（兜底）",
            "priority": "low",
            "depends_on": [0]
        })

        # Step 4: 去重和排序
        unique_recommendations = self._deduplicate_and_sort(recommendations)

        logger.info(
            "visualization_recommendations",
            total_count=len(unique_recommendations),
            high_priority=sum(1 for r in unique_recommendations if r["priority"] == "high")
        )

        return unique_recommendations

    def _detect_data_features(self, data_preview: Dict[str, Any]) -> Dict[str, bool]:
        """
        检测数据特征

        Args:
            data_preview: 数据预览

        Returns:
            检测到的数据特征字典
        """
        detected = {}

        if not data_preview or not isinstance(data_preview, dict):
            return detected

        # 获取第一条记录（用于字段检测）
        first_record = None
        if "data" in data_preview and isinstance(data_preview["data"], list) and data_preview["data"]:
            first_record = data_preview["data"][0]
        elif isinstance(data_preview, list) and data_preview:
            first_record = data_preview[0]

        if not first_record or not isinstance(first_record, dict):
            return detected

        # 检查measurements字段
        measurements = first_record.get("measurements", {})
        all_fields = set(first_record.keys()).union(set(measurements.keys()))

        # 应用检测规则
        for feature_name, rule in self.DATA_FEATURE_RULES.items():
            if "required_fields" in rule:
                # 字段存在性检测
                required = rule["required_fields"]
                if all(field in all_fields for field in required):
                    detected[feature_name] = True
            elif "detection" in rule:
                # 自定义检测逻辑
                # TODO: 实现自定义检测（如station_count > 1）
                pass

        return detected

    def _deduplicate_and_sort(self, recommendations: List[Dict]) -> List[Dict]:
        """去重和排序"""
        # 去重：同一chart_type只保留优先级最高的
        unique_map = {}
        for rec in recommendations:
            key = (rec["tool"], rec.get("chart_type", "auto"))
            if key not in unique_map or self._priority_value(rec["priority"]) > self._priority_value(unique_map[key]["priority"]):
                unique_map[key] = rec

        # 排序：按优先级排序
        sorted_recs = sorted(
            unique_map.values(),
            key=lambda x: self._priority_value(x["priority"]),
            reverse=True
        )

        return sorted_recs

    def _priority_value(self, priority: str) -> int:
        """优先级转数值"""
        return {"high": 3, "medium": 2, "low": 1}.get(priority, 0)
