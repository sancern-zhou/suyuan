"""
图表生成策略选择器

核心功能：
1. 智能选择图表生成策略（模板/推荐/LLM/Fallback）
2. 基于用户意图、数据特征和catalog进行决策
3. 提供策略执行配置

优先级：
1. 精确匹配模板（速度快、质量稳定）
2. 智能推荐（基于数据特征）
3. LLM自定义生成（灵活但慢）
4. Fallback（兜底）

参考：
- Apache Superset的图表推荐逻辑
- LIDA的多阶段生成策略
"""

from typing import Dict, Any, Optional, Literal, Union, List
import structlog

from app.tools.visualization.chart_data_catalog import (
    get_catalog_entry,
    get_recommended_templates,
    validate_data_fields
)
from app.tools.visualization.data_summarizer import DataSummarizer

logger = structlog.get_logger()

StrategyType = Literal["template", "intelligent_recommend", "llm_custom", "fallback"]


class ChartStrategySelector:
    """
    图表生成策略选择器

    决策流程：
    1. 检查是否有精确匹配的模板
    2. 基于数据特征判断是否可以智能推荐
    3. 判断是否需要LLM自定义
    4. 兜底使用fallback策略
    """

    def __init__(self):
        """初始化策略选择器"""
        self.summarizer = DataSummarizer()

    def select_strategy_with_data(
        self,
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        data_id: str,
        schema: str,
        user_intent: Optional[str] = None,
        prefer_custom: bool = False
    ) -> tuple[StrategyType, Dict[str, Any]]:
        """
        基于实际数据选择策略（自动生成数据摘要）

        Args:
            data: 实际数据
            data_id: 数据ID
            schema: 数据类型
            user_intent: 用户意图
            prefer_custom: 是否偏好自定义

        Returns:
            (策略类型, 数据摘要)
        """
        # 生成数据摘要
        data_summary = self.summarizer.summarize(data, schema)

        # 选择策略
        strategy = self.select_strategy(
            data_id=data_id,
            schema=schema,
            user_intent=user_intent,
            prefer_custom=prefer_custom,
            data_summary=data_summary
        )

        return strategy, data_summary

    def select_strategy(
        self,
        data_id: str,
        schema: str,
        user_intent: Optional[str] = None,
        prefer_custom: bool = False,
        data_summary: Optional[Dict[str, Any]] = None
    ) -> StrategyType:
        """
        选择图表生成策略

        Args:
            data_id: 数据ID
            schema: 数据类型
            user_intent: 用户意图（自然语言）
            prefer_custom: 用户是否偏好自定义
            data_summary: 数据摘要（来自DataSummarizer）

        Returns:
            策略类型
        """
        logger.info(
            "strategy_selection_start",
            schema=schema,
            has_user_intent=user_intent is not None,
            prefer_custom=prefer_custom
        )

        # 策略1：优先检查LLM自定义（用户明确需要或场景复杂）
        if prefer_custom or self._is_complex_intent(user_intent):
            logger.info(
                "strategy_selected",
                strategy="llm_custom",
                reason="用户需要自定义或场景复杂"
            )
            return "llm_custom"

        # 策略2：精确匹配模板
        template_strategy = self._try_template_strategy(schema, user_intent)
        if template_strategy:
            logger.info(
                "strategy_selected",
                strategy="template",
                reason=template_strategy["reason"]
            )
            return "template"

        # 策略3：智能推荐（基于数据特征）
        if data_summary:
            recommend_strategy = self._try_recommend_strategy(schema, data_summary, user_intent)
            if recommend_strategy:
                logger.info(
                    "strategy_selected",
                    strategy="intelligent_recommend",
                    reason=recommend_strategy["reason"]
                )
                return "intelligent_recommend"

        # 策略4：Fallback（兜底）
        logger.warning(
            "strategy_selected",
            strategy="fallback",
            reason="无合适策略，使用fallback"
        )
        return "fallback"

    def _try_template_strategy(
        self,
        schema: str,
        user_intent: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        尝试模板策略

        Returns:
            如果适用模板策略，返回决策信息；否则返回None
        """
        # 检查catalog中是否有该类型
        entry = get_catalog_entry(schema)
        if not entry:
            return None

        # 如果没有用户意图，直接使用优先级最高的模板
        if not user_intent:
            return {
                "reason": "无用户意图，使用默认模板",
                "template": entry.recommended_templates[0]
            }

        # 如果用户意图与模板场景匹配，使用模板
        for template in entry.recommended_templates:
            if self._match_scenario(user_intent, template.scenario):
                return {
                    "reason": f"用户意图匹配模板场景: {template.scenario}",
                    "template": template
                }

        return None

    def _try_recommend_strategy(
        self,
        schema: str,
        data_summary: Dict[str, Any],
        user_intent: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        尝试智能推荐策略

        基于数据特征判断是否可以智能推荐
        """
        # 基于数据特征判断
        statistics = data_summary.get("statistics", {})

        # 如果数据特征明确，可以推荐
        if statistics.get("has_time_series"):
            return {
                "reason": "数据包含时序信息，使用智能推荐"
            }

        if statistics.get("has_multiple_categories"):
            return {
                "reason": "数据包含多个分类，使用智能推荐"
            }

        # 如果有足够的数值字段，可以推荐
        numeric_field_count = len(statistics.get("numeric_fields", []))
        if numeric_field_count >= 2:
            return {
                "reason": f"数据包含{numeric_field_count}个数值字段，可以进行多维分析"
            }

        return None

    def _match_scenario(self, user_intent: str, scenario: str) -> bool:
        """
        判断用户意图是否匹配场景

        使用关键词匹配算法
        """
        # 关键词映射（中文场景）
        keywords_map = {
            "组分占比": ["占比", "比例", "分布", "饼图", "组成", "构成"],
            "浓度趋势": ["趋势", "变化", "时序", "时间", "走势", "演变"],
            "污染物时序": ["污染物", "时序", "变化", "趋势", "时间序列"],
            "污染物对比": ["对比", "比较", "柱状图", "排名", "差异"],
            "物种对比": ["对比", "比较", "物种", "排名", "物种排名"],
            "风向玫瑰": ["风向", "风", "玫瑰", "风速", "风向频率"],
            "源贡献占比": ["源", "贡献", "占比", "来源", "污染源"],
            "源贡献对比": ["源", "贡献", "对比", "来源对比"],
            "源贡献时序": ["源", "贡献", "时序", "来源变化"],
            "时空分布": ["时空", "分布", "热力图", "热力", "空间分布"],
            "站点对比": ["站点", "对比", "比较", "站点比较"],
            "多站点时序": ["多站点", "站点", "时序", "变化", "站点变化"],
            "站点浓度占比": ["站点", "占比", "比例", "分布"],
            "时空热力图": ["时空", "热力图", "热力", "分布"],
            "气象要素时序": ["气象", "温度", "湿度", "风速", "时序"],
            "边界层廓线": ["边界层", "廓线", "垂直", "高度"],
            "物种OFP排名": ["OFP", "物种", "排名", "贡献"],
            "类别OFP占比": ["OFP", "类别", "占比"],
            "沙尘轨迹": ["沙尘", "轨迹", "传输", "路径"],
            "火点分布": ["火点", "分布", "FIRMS"],
        }

        # 获取场景对应的关键词
        keywords = keywords_map.get(scenario, [scenario.lower()])

        # 转换为小写进行匹配
        user_intent_lower = user_intent.lower()

        # 检查是否有任何关键词匹配
        return any(kw in user_intent_lower for kw in keywords)

    def _is_complex_intent(self, user_intent: Optional[str]) -> bool:
        """
        判断是否为复杂意图（需要LLM处理）

        复杂意图特征：
        1. 包含多图表组合
        2. 需要数据联动
        3. 复杂的数据处理逻辑
        4. 多维度分析
        """
        if not user_intent:
            return False

        # 包含复杂关键词
        complex_keywords = [
            "联动", "叠加", "多图", "组合", "对比分析",
            "相关性", "影响", "溯源", "综合", "多维度",
            "交叉", "关联", "因果", "同时显示", "结合"
        ]

        return any(kw in user_intent for kw in complex_keywords)

    def get_strategy_config(
        self,
        strategy: StrategyType,
        schema: str,
        user_intent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取策略的执行配置

        Returns:
            {
                "executor": "工具名称",
                "params": {...},
                "timeout": 秒数
            }
        """
        if strategy == "template":
            # 使用模板生成
            templates = get_recommended_templates(schema, user_intent)
            return {
                "executor": "generate_chart",
                "params": {
                    "use_template": True,
                    "template": templates[0] if templates else None
                },
                "timeout": 5
            }

        elif strategy == "intelligent_recommend":
            # 使用智能推荐
            return {
                "executor": "smart_chart_generator",
                "params": {
                    "auto_recommend": True
                },
                "timeout": 10
            }

        elif strategy == "llm_custom":
            # 使用LLM自定义
            return {
                "executor": "intelligent_visualization_planner",
                "params": {
                    "use_llm": True
                },
                "timeout": 30
            }

        else:  # fallback
            # 使用基础图表
            return {
                "executor": "generate_chart",
                "params": {
                    "chart_type": "bar",  # 默认柱状图
                    "simple_mode": True
                },
                "timeout": 5
            }

    def explain_decision(
        self,
        strategy: StrategyType,
        schema: str,
        user_intent: Optional[str] = None
    ) -> str:
        """
        解释策略选择决策

        用于调试和用户理解
        """
        explanations = {
            "template": f"使用预定义模板生成 {schema} 类型的图表，速度快且质量稳定",
            "intelligent_recommend": f"基于 {schema} 数据特征智能推荐最合适的图表类型",
            "llm_custom": "使用AI大模型理解您的需求，生成定制化的可视化方案",
            "fallback": "使用默认图表类型（柱状图），确保基本可用性"
        }

        explanation = explanations.get(strategy, "未知策略")

        if user_intent:
            explanation += f"（用户意图：{user_intent}）"

        return explanation


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":
    selector = ChartStrategySelector()

    # 测试场景1：VOCs数据，无用户意图
    print("=== 场景1：VOCs数据，无用户意图 ===")
    strategy1 = selector.select_strategy(
        data_id="vocs:v1:test",
        schema="vocs"
    )
    print(f"选择策略: {strategy1}")
    print(f"解释: {selector.explain_decision(strategy1, 'vocs')}\n")

    # 测试场景2：VOCs数据，明确要看占比
    print("=== 场景2：VOCs数据，明确要看占比 ===")
    strategy2 = selector.select_strategy(
        data_id="vocs:v1:test",
        schema="vocs",
        user_intent="我想看VOCs的组分占比"
    )
    print(f"选择策略: {strategy2}")
    print(f"解释: {selector.explain_decision(strategy2, 'vocs', '我想看VOCs的组分占比')}\n")

    # 测试场景3：复杂需求（多图表组合）
    print("=== 场景3：复杂需求（多图表组合） ===")
    strategy3 = selector.select_strategy(
        data_id="air_quality:v1:test",
        schema="air_quality",
        user_intent="我想看PM2.5和O3的时序变化，同时对比不同站点，并分析它们的相关性"
    )
    print(f"选择策略: {strategy3}")
    print(f"解释: {selector.explain_decision(strategy3, 'air_quality', '复杂多维分析')}\n")

    # 测试场景4：获取策略配置
    print("=== 场景4：获取策略配置 ===")
    config = selector.get_strategy_config(strategy1, "vocs")
    print(f"执行器: {config['executor']}")
    print(f"超时: {config['timeout']}秒")
    print(f"参数: {config['params']}")
