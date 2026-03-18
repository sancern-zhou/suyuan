"""
气象专家模式优化集成示例

展示如何在WeatherExecutor中集成:
1. SmartVisualizationRecommender (智能可视化推荐)
2. DataQualityValidator (统一数据质量验证)
3. 并行执行优化
"""

from typing import Dict, Any, List
import asyncio
import structlog

from app.agent.experts.expert_executor import ExpertExecutor
from app.agent.core.smart_visualization_recommender import SmartVisualizationRecommender
from app.utils.data_quality_validator import get_data_quality_validator, DataQualityLevel

logger = structlog.get_logger()


class OptimizedWeatherExecutor(ExpertExecutor):
    """
    优化后的气象专家执行器

    新增功能:
    1. 智能可视化推荐
    2. 统一数据质量验证
    3. 并行工具执行
    """

    def __init__(self):
        super().__init__("weather")
        self.viz_recommender = SmartVisualizationRecommender()
        self.quality_validator = get_data_quality_validator()

    async def execute_with_optimization(
        self,
        context: Any,
        task: Any
    ) -> Dict[str, Any]:
        """
        带优化的执行流程

        优化点:
        1. 数据质量预检查
        2. 智能可视化推荐
        3. 并行工具执行
        """
        logger.info(
            "optimized_weather_execution_start",
            task_id=task.task_id
        )

        # ========================================
        # Step 1: 执行数据获取工具（基础层）
        # ========================================
        base_tools = [
            plan for plan in task.tool_plan
            if plan.tool in ["get_weather_data", "get_universal_meteorology"]
        ]

        base_results = []
        if base_tools:
            logger.info("executing_base_tools", count=len(base_tools))
            # 基础工具可并行执行
            base_tasks = [
                self._execute_tool_with_validation(plan, context)
                for plan in base_tools
            ]
            base_results = await asyncio.gather(*base_tasks, return_exceptions=True)

        # ========================================
        # Step 2: 数据质量验证 ⭐ 新增
        # ========================================
        primary_data = None
        for result in base_results:
            if isinstance(result, dict) and result.get("success"):
                primary_data = result
                break

        if not primary_data:
            logger.warning("no_valid_base_data")
            return self._build_error_result("基础数据获取失败")

        # 质量验证
        quality_report = self.quality_validator.validate_data(
            data=primary_data.get("data"),
            schema_type="weather",
            required_fields=["timestamp", "temperature_2m"]
        )

        logger.info(
            "data_quality_validated",
            is_valid=quality_report.is_valid,
            quality_level=quality_report.quality_level.value,
            record_count=quality_report.record_count
        )

        # 如果数据质量不合格,提前返回
        if not quality_report.is_valid:
            return self._build_quality_warning_result(quality_report)

        # ========================================
        # Step 3: 智能可视化推荐 ⭐ 新增
        # ========================================
        viz_recommendations = self.viz_recommender.recommend_visualizations(
            data_preview=primary_data.get("data"),
            schema_type="weather",
            user_intent=task.task_description
        )

        logger.info(
            "visualization_recommendations",
            count=len(viz_recommendations),
            high_priority=sum(1 for r in viz_recommendations if r["priority"] == "high")
        )

        # 动态更新工具计划（添加推荐的可视化工具）
        enhanced_tool_plan = self._merge_viz_recommendations(
            original_plan=task.tool_plan,
            recommendations=viz_recommendations
        )

        # ========================================
        # Step 4: 执行高级分析和可视化工具 ⭐ 并行优化
        # ========================================
        advanced_tools = [
            plan for plan in enhanced_tool_plan
            if plan.tool not in ["get_weather_data", "get_universal_meteorology"]
        ]

        if advanced_tools:
            logger.info(
                "executing_advanced_tools_parallel",
                count=len(advanced_tools)
            )

            # 构建执行层级（拓扑排序）
            execution_layers = self._build_execution_layers(advanced_tools)

            advanced_results = []
            for layer_idx, layer in enumerate(execution_layers):
                logger.info(
                    "executing_layer",
                    layer_idx=layer_idx,
                    tool_count=len(layer),
                    tools=[t.tool for t in layer]
                )

                # 每一层的工具可以并行执行
                layer_tasks = [
                    self._execute_tool_with_validation(plan, context)
                    for plan in layer
                ]

                layer_results = await asyncio.gather(*layer_tasks, return_exceptions=True)
                advanced_results.extend(layer_results)

        # ========================================
        # Step 5: 汇总结果
        # ========================================
        all_results = base_results + advanced_results

        return self._build_final_result(
            results=all_results,
            quality_report=quality_report,
            viz_recommendations=viz_recommendations
        )

    async def _execute_tool_with_validation(
        self,
        plan: Any,
        context: Any
    ) -> Dict[str, Any]:
        """
        带数据验证的工具执行

        在工具执行后自动验证数据质量
        """
        try:
            # 执行工具
            tool = self.tools.get(plan.tool)
            if not tool:
                logger.warning("tool_not_found", tool=plan.tool)
                return {"success": False, "error": "tool_not_found"}

            result = await tool.execute(context, **plan.params)

            # 执行后数据验证（只验证数据工具的结果）
            if plan.tool.startswith("get_") and result.get("success"):
                quality_report = self.quality_validator.validate_data(
                    data=result.get("data"),
                    schema_type=plan.tool
                )

                # 附加质量报告到结果
                result["quality_report"] = quality_report.to_dict()

                # 如果质量不合格,标记警告
                if quality_report.quality_level == DataQualityLevel.POOR:
                    logger.warning(
                        "tool_result_low_quality",
                        tool=plan.tool,
                        quality_level=quality_report.quality_level.value,
                        issues=quality_report.issues
                    )

            return result

        except Exception as e:
            logger.error(
                "tool_execution_failed",
                tool=plan.tool,
                error=str(e),
                exc_info=True
            )
            return {"success": False, "error": str(e)}

    def _merge_viz_recommendations(
        self,
        original_plan: List,
        recommendations: List[Dict]
    ) -> List:
        """
        合并可视化推荐到原始计划

        避免重复,优先级高的推荐优先
        """
        # 提取原始计划中的工具名
        existing_tools = {plan.tool for plan in original_plan}

        # 添加推荐的可视化工具（避免重复）
        enhanced = list(original_plan)
        for rec in recommendations:
            if rec["tool"] not in existing_tools:
                # 转换为ToolCallPlan格式
                from app.agent.core.expert_plan_generator import ToolCallPlan
                enhanced.append(ToolCallPlan(
                    tool=rec["tool"],
                    params={"chart_type": rec.get("chart_type", "auto")},
                    purpose=rec.get("reason", ""),
                    depends_on=rec.get("depends_on", [0])
                ))

        return enhanced

    def _build_execution_layers(
        self,
        tools: List
    ) -> List[List]:
        """
        构建执行层级（拓扑排序）

        无依赖关系的工具在同一层,可并行执行
        """
        layers = []
        executed_indices = set()

        while len(executed_indices) < len(tools):
            current_layer = []

            for i, tool in enumerate(tools):
                if i in executed_indices:
                    continue

                # 检查依赖是否都已执行
                if all(dep in executed_indices for dep in tool.depends_on):
                    current_layer.append(tool)

            if not current_layer:
                # 避免死循环（存在循环依赖）
                logger.error("circular_dependency_detected")
                break

            layers.append(current_layer)
            executed_indices.update([tools.index(t) for t in current_layer])

        return layers

    def _build_error_result(self, message: str) -> Dict[str, Any]:
        """构建错误结果"""
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "summary": f"❌ {message}"
        }

    def _build_quality_warning_result(
        self,
        quality_report: Any
    ) -> Dict[str, Any]:
        """构建质量警告结果"""
        return {
            "status": "partial",
            "success": True,
            "data": None,
            "quality_report": quality_report.to_dict(),
            "summary": (
                f"⚠️ 数据质量不合格\n"
                f"质量等级: {quality_report.quality_level.value}\n"
                f"问题: {', '.join(quality_report.issues)}\n"
                f"建议: {', '.join(quality_report.recommendations)}"
            )
        }

    def _build_final_result(
        self,
        results: List[Dict],
        quality_report: Any,
        viz_recommendations: List[Dict]
    ) -> Dict[str, Any]:
        """构建最终结果"""
        # 统计成功的工具
        successful_tools = [r for r in results if isinstance(r, dict) and r.get("success")]

        return {
            "status": "success",
            "success": True,
            "data": successful_tools,
            "metadata": {
                "total_tools": len(results),
                "successful_tools": len(successful_tools),
                "quality_report": quality_report.to_dict(),
                "viz_recommendations": [
                    {
                        "chart_type": r.get("chart_type"),
                        "reason": r.get("reason"),
                        "priority": r.get("priority")
                    }
                    for r in viz_recommendations
                ]
            },
            "summary": (
                f"✅ 气象分析完成\n"
                f"数据质量: {quality_report.quality_level.value}\n"
                f"成功工具: {len(successful_tools)}/{len(results)}\n"
                f"可视化推荐: {len(viz_recommendations)}个"
            )
        }
