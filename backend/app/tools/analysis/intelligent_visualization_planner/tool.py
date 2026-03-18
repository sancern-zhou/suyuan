"""
智能可视化规划器 - LLM驱动的可视化方案生成

核心功能：
1. 理解用户的自然语言可视化需求
2. 生成完整的可视化方案
3. 支持多图表组合方案

参考：docs/可视化增强方案.md 阶段3任务3.1
"""

from typing import Dict, Any, Optional, List
import json
import structlog

from abc import ABC, abstractmethod

logger = structlog.get_logger()


class IntelligentVisualizationPlanner:
    """
    智能可视化规划工具 - LLM驱动的可视化方案生成

    根据用户的自然语言需求，自动生成完整的可视化方案
    """

    async def execute(
        self,
        context: Any,
        user_intent: str,
        data_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        根据用户意图生成可视化方案

        Args:
            context: 执行上下文
            user_intent: 用户的自然语言需求
            data_id: 可选的数据引用ID

        Returns:
            {
                "status": "success",
                "success": true,
                "data": {
                    "visualization_plan": {...},
                    "estimated_charts": 2,
                    "complexity": "medium"
                },
                "summary": "生成了2个图表的可视化方案"
            }
        """
        logger.info(
            "intelligent_visualization_planner_start",
            user_intent=user_intent,
            has_data_id=data_id is not None
        )

        try:
            # Step 1: 如果有data_id，先分析数据特征
            data_profile = None
            if data_id:
                from app.tools.visualization.data_summarizer import DataSummarizer
                summarizer = DataSummarizer()

                # 从context获取数据
                raw_data = await self._get_data_from_context(context, data_id)
                if raw_data:
                    data_profile = summarizer.summarize(raw_data, schema=kwargs.get("schema"))
                    logger.info("data_profile_extracted", profile_keys=list(data_profile.keys()))

            # Step 2: 使用LLM理解用户意图并生成方案
            plan = await self._generate_visualization_plan(
                user_intent=user_intent,
                data_profile=data_profile,
                context=context
            )

            # Step 3: 验证方案可行性
            validated_plan = self._validate_plan(plan, context)

            # Step 4: 返回方案
            result = {
                "status": "success",
                "success": True,
                "data": {
                    "visualization_plan": validated_plan,
                    "estimated_charts": len(validated_plan.get("charts", [])),
                    "complexity": self._assess_complexity(validated_plan)
                },
                "metadata": {
                    "tool_name": "intelligent_visualization_planner",
                    "user_intent": user_intent,
                    "has_data_profile": data_profile is not None
                },
                "summary": f"生成了{len(validated_plan.get('charts', []))}个图表的可视化方案"
            }

            logger.info(
                "intelligent_visualization_planner_complete",
                chart_count=result["data"]["estimated_charts"],
                complexity=result["data"]["complexity"]
            )

            return result

        except Exception as e:
            logger.error("intelligent_visualization_planner_error", error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "metadata": {
                    "tool_name": "intelligent_visualization_planner"
                }
            }

    async def _get_data_from_context(
        self,
        context: Any,
        data_id: str
    ) -> Optional[Any]:
        """从context获取数据"""
        try:
            if context.requires_context:
                return context.get_data(data_id)
            else:
                logger.warning("context_does_not_support_data_retrieval")
                return None
        except Exception as e:
            logger.error("failed_to_get_data_from_context", data_id=data_id, error=str(e))
            return None

    async def _generate_visualization_plan(
        self,
        user_intent: str,
        data_profile: Optional[Dict[str, Any]],
        context: Any
    ) -> Dict[str, Any]:
        """使用LLM生成可视化方案"""
        prompt = self._build_planning_prompt(user_intent, data_profile)

        logger.info("llm_generation_start", prompt_length=len(prompt))

        # 调用LLM
        try:
            from app.external_apis.dify_client import DifyClient
            dify_client = DifyClient()

            response = await dify_client.chat(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )

            # 解析响应
            content = response.get("content", "{}")
            if isinstance(content, str):
                plan = json.loads(content)
            else:
                plan = content

            logger.info("llm_generation_success", plan_keys=list(plan.keys()))
            return plan

        except Exception as e:
            logger.error("llm_generation_failed", error=str(e))
            # 降级到简单方案
            return self._generate_fallback_plan(user_intent)

    def _build_planning_prompt(
        self,
        user_intent: str,
        data_profile: Optional[Dict[str, Any]]
    ) -> str:
        """构建LLM提示词"""
        prompt = f"""你是一个专业的数据可视化规划师。请根据用户需求生成可视化方案。

用户需求：
{user_intent}

"""

        if data_profile:
            stats = data_profile.get("statistics", {})
            prompt += f"""
数据特征：
- 记录数：{stats.get('record_count', 'Unknown')}
- 字段数：{len(data_profile.get('field_info', {}))}
- 时间字段：{len([f for f, info in data_profile.get('field_info', {}).items() if info.get('type') == 'temporal'])}
- 分类字段：{len([f for f, info in data_profile.get('field_info', {}).items() if info.get('type') == 'nominal'])}
- 数值字段：{len([f for f, info in data_profile.get('field_info', {}).items() if info.get('type') == 'quantitative'])}
- 包含时序数据：{'是' if stats.get('has_time_series') else '否'}
- 包含多分类：{'是' if stats.get('has_multiple_categories') else '否'}
"""

        prompt += """
请生成一个JSON格式的可视化方案，包含：
1. charts: 图表列表，每个图表包含type、config等
2. layout: 布局方式（single, grid, overlay等）
3. reasoning: 选择该方案的理由

可用的图表类型：
- timeseries: 时序图（用于展示趋势）
- bar: 柱状图（用于对比）
- pie: 饼图（用于占比）
- scatter: 散点图（用于相关性）
- heatmap: 热力图（用于时空分布）
- line: 折线图（用于趋势）
- wind_rose: 风向玫瑰图（用于气象数据）

示例输出格式：
{
    "charts": [
        {
            "type": "timeseries",
            "config": {
                "x_field": "timestamp",
                "y_fields": ["PM2.5", "O3"],
                "title": "污染物浓度时序变化"
            }
        }
    ],
    "layout": "single",
    "reasoning": "用户想看时序趋势，使用时序图最合适"
}
"""
        return prompt

    def _generate_fallback_plan(self, user_intent: str) -> Dict[str, Any]:
        """生成降级方案（基于关键词）"""
        user_intent_lower = user_intent.lower()

        # 简单的关键词匹配
        if any(keyword in user_intent_lower for keyword in ["趋势", "变化", "时序", "时间"]):
            return {
                "charts": [{
                    "type": "timeseries",
                    "config": {
                        "title": "时序变化图"
                    }
                }],
                "layout": "single",
                "reasoning": "根据关键词匹配，推荐时序图"
            }
        elif any(keyword in user_intent_lower for keyword in ["对比", "比较", "排名"]):
            return {
                "charts": [{
                    "type": "bar",
                    "config": {
                        "title": "对比分析图"
                    }
                }],
                "layout": "single",
                "reasoning": "根据关键词匹配，推荐柱状图"
            }
        elif any(keyword in user_intent_lower for keyword in ["占比", "比例", "分布"]):
            return {
                "charts": [{
                    "type": "pie",
                    "config": {
                        "title": "占比分析图"
                    }
                }],
                "layout": "single",
                "reasoning": "根据关键词匹配，推荐饼图"
            }
        else:
            return {
                "charts": [{
                    "type": "bar",
                    "config": {
                        "title": "数据分析图"
                    }
                }],
                "layout": "single",
                "reasoning": "默认推荐柱状图"
            }

    def _validate_plan(
        self,
        plan: Dict[str, Any],
        context: Any
    ) -> Dict[str, Any]:
        """验证方案可行性"""
        # 基本的方案验证
        validated_plan = plan.copy()

        if "charts" not in validated_plan:
            validated_plan["charts"] = []

        # 过滤不支持的图表类型
        supported_types = [
            "bar", "line", "point", "area", "pie",
            "timeseries", "scatter", "heatmap",
            "wind_rose", "profile"
        ]

        validated_plan["charts"] = [
            chart for chart in validated_plan["charts"]
            if chart.get("type") in supported_types
        ]

        # 确保有layout
        if "layout" not in validated_plan:
            validated_plan["layout"] = "single"

        return validated_plan

    def _assess_complexity(self, plan: Dict[str, Any]) -> str:
        """评估方案复杂度"""
        chart_count = len(plan.get("charts", []))
        layout = plan.get("layout", "single")

        if chart_count >= 3 or layout == "grid":
            return "high"
        elif chart_count >= 2 or layout == "overlay":
            return "medium"
        else:
            return "low"


# ============================================
# 便捷函数
# ============================================

async def plan_visualization(
    context: Any,
    user_intent: str,
    data_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    快速生成可视化方案

    Args:
        context: 执行上下文
        user_intent: 用户自然语言需求
        data_id: 数据引用ID（可选）

    Returns:
        可视化方案
    """
    planner = IntelligentVisualizationPlanner()
    return await planner.execute(context, user_intent, data_id, **kwargs)


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":
    import asyncio

    async def example():
        """示例：用户想看各站点PM2.5时序变化"""
        user_intent = "我想看各站点PM2.5的时序变化趋势"

        # 模拟context
        class MockContext:
            def __init__(self):
                self.requires_context = False

        context = MockContext()

        result = await plan_visualization(
            context=context,
            user_intent=user_intent,
            data_id=None
        )

        print("=== 可视化方案生成结果 ===")
        print(f"状态: {result['status']}")
        print(f"图表数量: {result['data']['estimated_charts']}")
        print(f"复杂度: {result['data']['complexity']}")
        print(f"方案: {json.dumps(result['data']['visualization_plan'], indent=2, ensure_ascii=False)}")

    asyncio.run(example())
