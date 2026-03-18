"""
深度溯源工作流 (DeepTraceWorkflow)

基于PMF源解析和OBM/OBP分析的深度污染溯源分析。

工具链：
1. 获取组分数据（VOCs或PM2.5组分数据）
2. PMF源解析（识别污染源贡献率）
3. OBM/OFP分析（仅VOCs，分析臭氧生成潜势）
4. 可视化分析（源贡献饼图、源谱特征图等）

适用场景：
- 深度污染源解析
- PMF源解析分析
- 臭氧生成机理分析
- 源谱特征分析

参数：
- city: 城市名称
- pollutant: 污染物类型（VOCs/PM2.5）
- start_time: 分析开始时间
- end_time: 分析结束时间
- context: ExecutionContext（必需）

返回：
标准UDF v2.0格式，包含：
- pmf_result: PMF源解析结果
- obm_result: OBM/OFP分析结果（仅VOCs）
- visuals: 可视化图表列表
"""

from typing import Dict, Any, List, Optional
import structlog

from .workflow_tool import WorkflowTool

logger = structlog.get_logger()


class DeepTraceWorkflow(WorkflowTool):
    """
    深度溯源工作流

    基于PMF源解析和OBM/OBP分析的深度污染溯源分析。
    """

    name = "deep_trace_workflow"
    description = """深度溯源工作流 - PMF源解析和OBM/OBP分析

基于PMF源解析和OBM/OBP分析的深度污染溯源分析，识别污染源贡献率和生成机理：

分析流程：
1. 获取组分数据：从数据库获取VOCs或PM2.5组分数据
2. PMF源解析：执行PMF模型，识别主要污染源及其贡献率
3. OBM/OFP分析（仅VOCs）：计算臭氧生成潜势和关键活性组分
4. 可视化分析：生成源贡献饼图、源谱特征图等

适用场景：
- 深度污染源解析
- PMF源解析分析
- 臭氧生成机理分析
- 源谱特征分析
- 前体物分析

参数：
- city: 城市名称（如 "广州市"）
- pollutant: 污染物类型（VOCs或PM2.5）
- start_time: 分析开始时间（格式：YYYY-MM-DD HH:MM:SS）
- end_time: 分析结束时间（格式：YYYY-MM-DD HH:MM:SS）

返回：PMF源解析结果 + OBM/OFP分析结果 + 可视化图表
"""
    version = "1.0.0"
    category = "deep_trace"
    requires_context = True  # 需要ExecutionContext

    def __init__(self):
        """初始化深度溯源工作流"""
        super().__init__()

    async def execute(
        self,
        context,
        city: str,
        pollutant: str,
        start_time: str,
        end_time: str
    ) -> Dict[str, Any]:
        """
        执行深度溯源分析

        Args:
            context: ExecutionContext实例（必需）
            city: 城市名称
            pollutant: 污染物类型（VOCs/PM2.5）
            start_time: 分析开始时间
            end_time: 分析结束时间

        Returns:
            标准UDF v2.0格式
        """
        self._start_timer()

        try:
            from app.agent.tool_adapter import call_llm_tool
            import asyncio

            self._record_step("deep_trace_start", "running", {
                "city": city,
                "pollutant": pollutant,
                "start_time": start_time,
                "end_time": end_time
            })

            # 1. 获取组分数据
            self._record_step("fetch_component_data", "running")
            data_tool = "get_vocs_data" if pollutant.lower() in ["vocs", "voc"] else "get_pm25_ionic"
            data_result = await call_llm_tool(
                data_tool,
                context=context,
                city=city,
                start_time=start_time,
                end_time=end_time
            )

            if not data_result.get("success"):
                raise Exception(f"获取{pollutant}数据失败: {data_result.get('summary')}")

            data_id = data_result.get("data_id")
            self._record_step("fetch_component_data", "success", {
                "data_id": data_id,
                "record_count": data_result.get("metadata", {}).get("record_count", 0)
            })

            # 2. PMF源解析
            self._record_step("pmf_analysis", "running")
            pmf_tool = "calculate_vocs_pmf" if pollutant.lower() in ["vocs", "voc"] else "calculate_pm_pmf"
            pmf_result = await call_llm_tool(
                pmf_tool,
                context=context,
                data_id=data_id,
                city=city
            )

            self._record_step("pmf_analysis", "success" if pmf_result.get("success") else "failed", {
                "success": pmf_result.get("success", False),
                "visuals_count": len(pmf_result.get("visuals", []))
            })

            # 3. OBM/OFP分析（仅VOCs）
            obm_result = None
            if pollutant.lower() in ["vocs", "voc"]:
                self._record_step("obm_ofp_analysis", "running")
                obm_result = await call_llm_tool(
                    "calculate_obm_ofp",
                    context=context,
                    data_id=data_id
                )

                self._record_step("obm_ofp_analysis", "success" if obm_result.get("success") else "failed", {
                    "success": obm_result.get("success", False),
                    "visuals_count": len(obm_result.get("visuals", []))
                })

            # 4. 聚合可视化
            all_visuals = []
            if pmf_result.get("visuals"):
                all_visuals.extend(pmf_result["visuals"])
            if obm_result and obm_result.get("visuals"):
                all_visuals.extend(obm_result["visuals"])

            self._record_step("deep_trace_complete", "success", {
                "pmf_success": pmf_result.get("success", False),
                "obm_success": obm_result.get("success", False) if obm_result else None,
                "total_visuals": len(all_visuals)
            })

            # 构建数据
            data = {
                "pmf_result": pmf_result.get("data"),
                "obm_result": obm_result.get("data") if obm_result else None,
                "source_data_id": data_id
            }

            return self._build_udf_v2_result(
                status="success",
                success=True,
                data=data,
                visuals=all_visuals,
                summary=f"深度溯源完成，PMF分析{'成功' if pmf_result.get('success') else '失败'}"
            )

        except Exception as e:
            logger.error(
                "deep_trace_workflow_failed",
                city=city,
                pollutant=pollutant,
                error=str(e),
                exc_info=True
            )

            self._record_step("deep_trace_failed", "failed", {
                "error": str(e)
            })

            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={
                    "pmf_result": None,
                    "obm_result": None,
                    "error": str(e)
                },
                summary=f"深度溯源失败: {str(e)}"
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
                        "description": "城市名称，如 '广州市'"
                    },
                    "pollutant": {
                        "type": "string",
                        "description": "污染物类型",
                        "enum": ["VOCs", "PM2.5", "PM10"]
                    },
                    "start_time": {
                        "type": "string",
                        "description": "分析开始时间，格式：YYYY-MM-DD HH:MM:SS，如 '2025-08-01 00:00:00'"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "分析结束时间，格式：YYYY-MM-DD HH:MM:SS，如 '2025-08-31 23:59:59'"
                    }
                },
                "required": ["city", "pollutant", "start_time", "end_time"]
            }
        }
