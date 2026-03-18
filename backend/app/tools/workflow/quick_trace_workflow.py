"""
快速溯源工作流 (QuickTraceWorkflow)

专门用于污染高值告警场景的快速溯源分析。

工具链：
1. get_current_weather - 当天实时气象数据
2. get_weather_data - 历史气象数据(前3天)
3. get_weather_forecast - 未来15天预报
4. _get_air_quality_from_db - 从数据库获取空气质量(周边8市历史+未来7天预报)
5. meteorological_trajectory_analysis - 后向轨迹分析(可跳过)
6. get_weather_situation_map - 中央气象台天气形势图AI解读(通义千问VL)

总耗时: 3-5分钟 (轨迹分析超时则2-3分钟)

参数：
- city: 城市名称（如 "济宁市"）
- alert_time: 告警时间（如 "2026-02-02 12:00:00"）
- pollutant: 污染物类型（如 "PM2.5"）
- alert_value: 告警浓度值

返回：
标准UDF v2.0格式，包含：
- summary_text: Markdown格式的溯源分析报告
- visuals: 可视化图表列表（轨迹图、天气形势图等）
- has_trajectory: 是否包含轨迹分析结果
- warning_message: 警告信息（如轨迹分析超时）
"""

from typing import Dict, Any, Optional
from datetime import datetime
import structlog

from .workflow_tool import WorkflowTool, WorkflowStatus

logger = structlog.get_logger()


class QuickTraceWorkflow(WorkflowTool):
    """
    快速溯源工作流

    封装QuickTraceExecutor为ReAct工具，用于污染高值告警场景的快速溯源分析。
    """

    name = "quick_trace_workflow"
    description = """快速溯源工作流 - 污染高值告警快速溯源分析

专门用于污染高值告警场景的快速溯源分析，自动执行完整的分析流程：

1. 气象条件分析：获取历史气象（前3天）、实时天气、未来预报（15天）
2. 区域传输分析：查询周边8城市空气质量数据
3. 后向轨迹分析：72小时后向轨迹分析（可选，超时自动跳过）
4. 天气形势解读：中央气象台天气形势图AI解读
5. 综合报告生成：自动生成Markdown格式的溯源分析报告

适用场景：
- 污染高值告警响应
- 快速污染溯源分析
- 应急决策支持

参数：
- city: 城市名称（如 "济宁市"）
- alert_time: 告警时间（如 "2026-02-02 12:00:00"）
- pollutant: 污染物类型（如 "PM2.5"）
- alert_value: 告警浓度值（数值）

返回：完整的溯源分析报告（Markdown格式）+ 可视化图表
"""
    version = "1.0.0"
    category = "quick_trace"
    requires_context = False

    def __init__(self):
        """初始化快速溯源工作流"""
        super().__init__()
        self._executor = None

    def _get_executor(self):
        """
        延迟加载QuickTraceExecutor

        Returns:
            QuickTraceExecutor实例
        """
        if self._executor is None:
            from app.agent.executors.quick_trace_executor import QuickTraceExecutor
            self._executor = QuickTraceExecutor()
            logger.info("quick_trace_executor_loaded")
        return self._executor

    async def execute(
        self,
        city: str,
        alert_time: str,
        pollutant: str,
        alert_value: float
    ) -> Dict[str, Any]:
        """
        执行快速溯源分析

        Args:
            city: 城市名称（如 "济宁市"）
            alert_time: 告警时间（如 "2026-02-02 12:00:00"）
            pollutant: 污染物类型（如 "PM2.5"）
            alert_value: 告警浓度值

        Returns:
            标准UDF v2.0格式
        """
        self._start_timer()

        try:
            self._record_step("quick_trace_start", "running", {
                "city": city,
                "alert_time": alert_time,
                "pollutant": pollutant,
                "alert_value": alert_value
            })

            # 获取执行器并执行
            executor = self._get_executor()
            result = await executor.execute(
                city=city,
                alert_time=alert_time,
                pollutant=pollutant,
                alert_value=alert_value
            )

            # 记录执行步骤
            self._record_step("quick_trace_complete", "success", {
                "has_trajectory": result.get("has_trajectory", False),
                "has_visuals": len(result.get("visuals", [])) > 0,
                "has_warning": result.get("warning_message") is not None
            })

            # 构建标准UDF v2.0格式
            summary_text = result.get("summary_text", "")
            has_summary = bool(summary_text and not summary_text.startswith("❌"))

            return self._build_udf_v2_result(
                status="success" if has_summary else "failed",
                success=has_summary,
                data={
                    "summary_text": summary_text,
                    "has_trajectory": result.get("has_trajectory", False),
                    "warning_message": result.get("warning_message")
                },
                visuals=result.get("visuals", []),
                summary=f"快速溯源完成，耗时 {self._get_elapsed_ms()}ms"
            )

        except Exception as e:
            logger.error(
                "quick_trace_workflow_failed",
                city=city,
                error=str(e),
                exc_info=True
            )

            self._record_step("quick_trace_failed", "failed", {
                "error": str(e)
            })

            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={
                    "summary_text": f"快速溯源失败: {str(e)}",
                    "has_trajectory": False,
                    "warning_message": str(e)
                },
                summary=f"快速溯源失败: {str(e)}"
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
                    "city": {
                        "type": "string",
                        "description": "城市名称，如 '济宁市'"
                    },
                    "alert_time": {
                        "type": "string",
                        "description": "告警时间，格式为 'YYYY-MM-DD HH:MM:SS'，如 '2026-02-02 12:00:00'"
                    },
                    "pollutant": {
                        "type": "string",
                        "description": "污染物类型，如 'PM2.5'、'PM10'、'O3'、'VOCs'等",
                        "enum": ["PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "VOCs"]
                    },
                    "alert_value": {
                        "type": "number",
                        "description": "告警浓度值，数值类型，如 150.5"
                    }
                },
                "required": ["city", "alert_time", "pollutant", "alert_value"]
            }
        }
