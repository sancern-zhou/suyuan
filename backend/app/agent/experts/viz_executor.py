"""
可视化专家执行器 (VizExecutor)

负责执行可视化相关工具并生成图表
"""

from typing import Dict, Any, List
import structlog

from .expert_executor import ExpertExecutor, ExpertResult
from app.agent.core.expert_plan_generator import ExpertTask, ExpertPlanGenerator

logger = structlog.get_logger()


class VizExecutor(ExpertExecutor):
    """可视化专家执行器"""

    def __init__(self):
        super().__init__("viz")
        # 初始化计划生成器（用于重新生成工具计划）
        self.plan_generator = ExpertPlanGenerator()

    async def execute(self, task: ExpertTask, execution_context=None) -> ExpertResult:
        """
        执行可视化专家任务（重写以支持skip_viz_data_ids过滤）

        Args:
            task: 专家任务（包含skip_viz_data_ids）
            execution_context: ExecutionContext对象（可选）

        Returns:
            ExpertResult: 执行结果
        """
        # 【新增】如果任务有skip_viz_data_ids，需要过滤upstream_data_ids
        if hasattr(task, 'skip_viz_data_ids') and task.skip_viz_data_ids:
            skip_viz_data_ids = task.skip_viz_data_ids
            original_upstream_count = len(task.upstream_data_ids)

            # 过滤掉需要跳过可视化的data_id
            filtered_upstream_data_ids = [
                did for did in task.upstream_data_ids
                if did not in skip_viz_data_ids
            ]

            if len(filtered_upstream_data_ids) != len(task.upstream_data_ids):
                logger.info(
                    "viz_executor_filtering_upstream_data_ids",
                    original_count=original_upstream_count,
                    filtered_count=len(filtered_upstream_data_ids),
                    skipped_count=original_upstream_count - len(filtered_upstream_data_ids),
                    skipped_data_ids=[did for did in task.skip_viz_data_ids if did in task.upstream_data_ids]
                )

                # 重新生成工具计划（使用过滤后的upstream_data_ids）
                if execution_context is None:
                    # task.context可能是ExecutionContext对象或字典
                    from app.agent.context import ExecutionContext
                    if isinstance(task.context, ExecutionContext):
                        # 已经是ExecutionContext对象，直接使用
                        execution_context = task.context
                    elif isinstance(task.context, dict):
                        # 是字典，创建ExecutionContext
                        context_dict = task.context.copy()
                        context_dict["session_id"] = context_dict.get("session_id", f"expert_viz_{task.task_id}")
                        execution_context = self._create_execution_context(context_dict)
                    else:
                        # 其他情况，创建新的ExecutionContext
                        execution_context = self._create_execution_context({"session_id": f"expert_viz_{task.task_id}"})

                # 获取上游结果字典
                from app.agent.context import ExecutionContext
                if isinstance(execution_context, ExecutionContext):
                    # 从context获取上游结果
                    upstream_results = execution_context.get_data("upstream_results") if hasattr(execution_context, 'get_data') else {}
                else:
                    upstream_results = {}

                # 使用过滤后的upstream_data_ids重新生成工具计划
                from .expert_router_v3 import ExpertRouterV3
                # 创建临时路由器来获取上游结果字典格式
                # 由于无法直接获取，我们使用task.context中的信息

                # 直接修改task的upstream_data_ids
                task = task.copy(update={"upstream_data_ids": filtered_upstream_data_ids})

                logger.info(
                    "viz_task_upstream_data_ids_updated",
                    new_upstream_count=len(task.upstream_data_ids)
                )

        # 调用父类执行方法
        return await super().execute(task, execution_context)
    
    def _load_tools(self) -> Dict[str, Any]:
        """加载可视化专家可用的工具"""
        tools = {}
        
        # 必需工具
        try:
            from app.tools.visualization.generate_chart.tool import GenerateChartTool
            tools["generate_chart"] = GenerateChartTool()
        except ImportError as e:
            logger.warning("tool_import_failed", tool="generate_chart", error=str(e))
        
        try:
            from app.tools.analysis.smart_chart_generator.tool import SmartChartGenerator
            tools["smart_chart_generator"] = SmartChartGenerator()
        except ImportError as e:
            logger.warning("tool_import_failed", tool="smart_chart_generator", error=str(e))
        
        # 可选工具
        try:
            from app.tools.visualization.generate_map.tool import GenerateMapTool
            tools["generate_map"] = GenerateMapTool()
        except ImportError:
            pass
        
        return tools
    
    def _get_summary_prompt(self) -> str:
        """可视化专家总结提示词"""
        return """你是数据可视化专家。基于图表生成结果，评估可视化效果。

评估要点：
1. 图表类型是否适合数据特征
2. 数据展示是否清晰易懂
3. 是否需要补充其他类型的图表

图表类型建议：
- 时间序列数据 → 折线图
- 占比数据 → 饼图
- 对比数据 → 柱状图
- 空间分布 → 地图/热力图
- 风向数据 → 风玫瑰图"""
    
    def _extract_summary_stats(self, tool_results: List[Dict]) -> Dict[str, Any]:
        """从可视化工具结果中提取统计摘要"""

        stats = {
            "charts_generated": 0,
            "chart_types": [],
            "maps_generated": 0
        }

        for result in tool_results:
            if result.get("status") != "success":
                continue

            tool_name = result.get("tool", "")
            data = result.get("result", {})

            if tool_name in ["generate_chart", "smart_chart_generator"]:
                stats["charts_generated"] += 1

                if isinstance(data, dict):
                    # 从visuals中提取图表信息
                    visuals = data.get("visuals", [])
                    for v in visuals:
                        if isinstance(v, dict):
                            chart_type = v.get("type") or v.get("payload", {}).get("type")
                            if chart_type and chart_type not in stats["chart_types"]:
                                stats["chart_types"].append(chart_type)

                    # 或者直接从data中获取
                    chart_type = data.get("type") or data.get("chart_type")
                    if chart_type and chart_type not in stats["chart_types"]:
                        stats["chart_types"].append(chart_type)

            elif tool_name == "generate_map":
                stats["maps_generated"] += 1

        stats["total_visuals"] = stats["charts_generated"] + stats["maps_generated"]

        return stats

    async def _generate_summary(
        self,
        task_description: str,
        summary_stats: Dict[str, Any],
        tool_results: List[Dict],
        task: Any = None
    ):
        """
        可视化专家总结（无需LLM，直接返回元数据摘要）

        理由：
        1. 可视化专家仅负责生成图表，不需要复杂的化学机制分析
        2. 下游report专家依赖的是visuals元数据，而非LLM总结文本
        3. 节省API调用成本和延迟（~2-5秒）
        4. 当前LLM总结内容过于简单，无实质分析价值
        """
        from .expert_executor import ExpertAnalysis

        # 直接从统计摘要构建简洁的文本总结
        charts_count = summary_stats.get("charts_generated", 0)
        chart_types = summary_stats.get("chart_types", [])
        maps_count = summary_stats.get("maps_generated", 0)
        total_visuals = summary_stats.get("total_visuals", 0)

        # 构建自然语言摘要
        summary_parts = []
        if charts_count > 0:
            types_str = "、".join(chart_types) if chart_types else "未知类型"
            summary_parts.append(f"生成{charts_count}个图表（{types_str}）")
        if maps_count > 0:
            summary_parts.append(f"{maps_count}个地图")

        summary = "，".join(summary_parts) if summary_parts else "未生成可视化内容"

        # 构建关键发现（仅列举图表类型）
        key_findings = [f"{t}图表" for t in chart_types]
        if maps_count > 0:
            key_findings.append(f"{maps_count}个地图")

        logger.info(
            "viz_expert_summary_generated_without_llm",
            charts_count=charts_count,
            maps_count=maps_count,
            total_visuals=total_visuals,
            chart_types=chart_types,
            summary_length=len(summary)
        )

        return ExpertAnalysis(
            summary=summary,
            key_findings=key_findings,
            data_quality="good" if total_visuals > 0 else "poor",
            confidence=1.0,  # 元数据统计的置信度为100%
            section_content=""  # viz不生成独立章节
        )
