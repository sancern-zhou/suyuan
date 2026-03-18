"""
标准分析工作流 (StandardAnalysisWorkflow)

完整的污染溯源分析流程，基于ExpertRouterV3多专家系统。

专家系统：
- WeatherExpertAgent: 气象数据分析（天气、轨迹、风向、上风向分析）
- ComponentExpertAgent: 污染物组分分析（VOCs、PM2.5、PM10、PMF、OBM、OFP源解析）
- VizExpertAgent: 数据可视化（图表生成、可视化分析，15种图表类型）
- ReportExpertAgent: 综合报告生成（分析总结、结论建议）

精度模式：
- fast: 快速筛查模式（~18秒）
- standard: 标准分析模式（~3分钟）
- full: 完整分析模式（~7-10分钟）

参数：
- user_query: 用户自然语言查询
- precision: 分析精度模式（fast/standard/full，默认standard）
- session_id: 会话ID（可选，用于连续对话）

返回：
标准UDF v2.0格式，包含：
- final_answer: 最终分析答案
- conclusions: 分析结论列表
- recommendations: 建议措施列表
- visuals: 可视化图表列表
- selected_experts: 参与分析的专家列表
"""

from typing import Dict, Any, List, Optional
import structlog

from .workflow_tool import WorkflowTool

logger = structlog.get_logger()


class StandardAnalysisWorkflow(WorkflowTool):
    """
    标准分析工作流

    封装ExpertRouterV3为ReAct工具，实现完整的污染溯源分析。
    """

    name = "standard_analysis_workflow"
    description = """标准分析工作流 - 完整的污染溯源分析

基于多专家系统的完整污染溯源分析，自动选择并调度相关专家：

专家类型：
- 气象专家：气象数据分析、轨迹分析、风向分析、上风向分析
- 组分专家：VOCs/PM2.5/PM10组分分析、PMF源解析、OBM/OFP分析
- 可视化专家：15种图表类型生成（饼图、柱状图、折线图、时序图、风向玫瑰图等）
- 报告专家：综合报告生成、分析总结、结论建议

分析模式：
- fast: 快速筛查模式（~18秒）- 基础数据查询和简单分析
- standard: 标准分析模式（~3分钟）- 完整专家协作分析
- full: 完整分析模式（~7-10分钟）- 深度分析+完整可视化

适用场景：
- 完整的污染溯源分析
- 多维度综合评估
- 专业分析报告生成

参数：
- user_query: 用户自然语言查询（如 "分析广州天河站2025-08-09的O3污染"）
- precision: 分析精度模式（fast/standard/full，默认standard）
- session_id: 会话ID（可选，用于连续对话）

返回：完整的分析报告 + 结论建议 + 可视化图表
"""
    version = "1.0.0"
    category = "standard_analysis"
    requires_context = False

    def __init__(self, memory_manager=None, event_callback=None):
        """
        初始化标准分析工作流

        Args:
            memory_manager: 记忆管理器（用于创建ExecutionContext）
            event_callback: 事件回调函数（用于实时发送专家执行事件）
        """
        super().__init__()
        self._memory_manager = memory_manager
        self._event_callback = event_callback
        self._expert_router = None

    def _get_expert_router(self):
        """
        延迟加载ExpertRouterV3

        Returns:
            ExpertRouterV3实例
        """
        if self._expert_router is None:
            from app.agent.experts.expert_router_v3 import ExpertRouterV3
            self._expert_router = ExpertRouterV3(
                memory_manager=self._memory_manager,
                event_callback=self._event_callback
            )
            logger.info("expert_router_v3_loaded")
        return self._expert_router

    async def execute(
        self,
        user_query: str,
        precision: str = 'standard',
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行标准分析

        Args:
            user_query: 用户自然语言查询
            precision: 分析精度模式（fast/standard/full）
            session_id: 会话ID（可选）

        Returns:
            标准UDF v2.0格式
        """
        self._start_timer()

        try:
            self._record_step("standard_analysis_start", "running", {
                "query": user_query[:100],
                "precision": precision,
                "session_id": session_id
            })

            # 获取专家路由器并执行
            router = self._get_expert_router()
            pipeline_result = await router.execute_pipeline(
                user_query=user_query,
                precision=precision,
                session_id=session_id
            )

            # 记录执行步骤
            self._record_step("standard_analysis_complete", "success", {
                "status": pipeline_result.status,
                "selected_experts": pipeline_result.selected_experts,
                "confidence": pipeline_result.confidence,
                "visuals_count": len(pipeline_result.visuals)
            })

            # 构建数据
            data = {
                "final_answer": pipeline_result.final_answer,
                "conclusions": pipeline_result.conclusions,
                "recommendations": pipeline_result.recommendations,
                "selected_experts": pipeline_result.selected_experts,
                "confidence": pipeline_result.confidence
            }

            return self._build_udf_v2_result(
                status=pipeline_result.status,
                success=pipeline_result.status in ["success", "partial"],
                data=data,
                visuals=pipeline_result.visuals,
                summary=f"标准分析完成，{len(pipeline_result.selected_experts)}个专家参与，置信度{pipeline_result.confidence:.2f}"
            )

        except Exception as e:
            logger.error(
                "standard_analysis_workflow_failed",
                query=user_query[:100],
                error=str(e),
                exc_info=True
            )

            self._record_step("standard_analysis_failed", "failed", {
                "error": str(e)
            })

            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={
                    "final_answer": f"标准分析失败: {str(e)}",
                    "conclusions": [],
                    "recommendations": [],
                    "selected_experts": [],
                    "confidence": 0.0
                },
                summary=f"标准分析失败: {str(e)}"
            )

    def get_function_schema(self) -> Dict[str, Any]:
        """
        生成OpenAI Function Schema

        Returns:
            OpenAI Function Schema格式
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "user_query": {
                        "type": "string",
                        "description": "用户自然语言查询，描述要分析的污染问题，如 '分析广州天河站2025-08-09的O3污染'"
                    },
                    "precision": {
                        "type": "string",
                        "description": "分析精度模式",
                        "enum": ["fast", "standard", "full"],
                        "default": "standard"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话ID，用于连续对话（可选）"
                    }
                },
                "required": ["user_query"]
            }
        }
