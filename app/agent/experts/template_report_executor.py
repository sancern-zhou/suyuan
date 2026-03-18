"""
模板报告生成专家（方案B Agent化）

设计：引导式 Agent 模式
- 阶段1：LLM 分析模板，生成数据需求和工具查询计划
- 阶段2：执行工具计划（调用现有查询工具，输出 UDF v2.0 + data_id）
- 阶段3：LLM 基于模板 + 数据生成完整报告
"""
from typing import Dict, Any, List, Optional
import uuid
import asyncio
import structlog

from .expert_executor import ExpertExecutor, ExpertResult, ExpertAnalysis, ExecutionSummary
from .template_report_prompts import (
    build_template_analysis_prompt,
    build_report_generation_prompt,
)
from app.agent.core.expert_plan_generator import ExpertTask
from app.agent.context.execution_context import ExecutionContext
from app.agent.context.data_context_manager import DataContextManager
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.services.llm_service import llm_service

logger = structlog.get_logger()


class TemplateReportExecutor(ExpertExecutor):
    """模板报告生成专家（方案B Agent化实现）"""

    def __init__(self):
        super().__init__("template_report")

    # ===== 抽象方法占位实现（本专家不使用基类的摘要逻辑） =====
    def _get_summary_prompt(self) -> str:
        """模板报告专家不使用基类的总结 Prompt，返回空串占位。"""
        return ""

    def _extract_summary_stats(self, tool_results: List[Dict]) -> Dict[str, Any]:
        """
        模板报告专家不做额外的摘要统计，返回空字典占位。
        """
        return {}

    def _load_tools(self) -> Dict[str, Any]:
        """
        加载可用的查询工具
        说明：
        - 实际可调用的工具由 ReAct Agent 全局注册表提供（见 tool_adapter）
        - 这里返回的字典仅用于声明"本专家会用到哪些工具名"，不强依赖具体类
        - 工具优先级：get_jining_regular_stations > get_guangdong_regular_stations > get_air_quality
        - 其中：
          - get_jining_regular_stations / get_guangdong_regular_stations / get_component_data 走自然语言 UQP 查询
          - get_weather_data 为结构化参数工具（data_type/start_time/end_time/lat/lon）
        """
        # 仅声明工具名，具体实现由 tool_registry 提供
        return {
            "get_jining_regular_stations": object(),  # 济宁市专用工具，优先使用
            "get_guangdong_regular_stations": object(),  # 广东省专用工具，次优先使用
            "get_air_quality": object(),  # 全国城市查询，最后使用（非济宁/广东地区）
            "get_component_data": object(),
            "get_weather_data": object(),
        }

    async def execute(
        self,
        task: ExpertTask,
        expert_results: Optional[Dict[str, ExpertResult]] = None
    ) -> ExpertResult:
        """
        执行模板报告生成
        task.context 需包含：
        - template_content: 历史报告内容（Markdown 文本）
        - target_time_range: 目标时间范围
        """
        template_content = (task.context or {}).get("template_content", "")
        target_time_range = (task.context or {}).get("target_time_range", {})

        result = ExpertResult(
            status="pending",
            expert_type=self.expert_type,
            task_id=task.task_id,
        )

        try:
            # 阶段1：LLM 分析模板，生成数据需求
            data_requirements = await self._analyze_template(template_content, target_time_range)

            # 阶段2：执行工具计划，收集数据
            collected_data = await self._execute_requirements(data_requirements, target_time_range)

            # 阶段3：LLM 生成最终报告
            report_md = await self._generate_report(template_content, collected_data, target_time_range)

            # 组装结果
            result.analysis = ExpertAnalysis(
                summary="模板报告生成完成",
                key_findings=[],
                data_quality="good",
                confidence=0.8,
                section_content=report_md
            )
            result.tool_results = [{
                "tool": "template_report_generation",
                "status": "success",
                "result": {
                    "report_content": report_md,
                    "data_requirements": data_requirements,
                    "collected_data": collected_data
                }
            }]
            result.execution_summary = ExecutionSummary(
                tools_executed=len(collected_data),
                tools_succeeded=len(collected_data),
                tools_failed=0
            )
            result.data_ids = [
                item.get("data_id") for item in collected_data if item.get("data_id")
            ]
            result.status = "success"

        except Exception as e:
            logger.error(
                "template_report_executor_failed",
                error=str(e),
                exc_info=True
            )
            result.status = "failed"
            result.errors.append({"type": "template_report_error", "message": str(e)})

        return result

    async def _analyze_template(
        self,
        template_content: str,
        target_time_range: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """调用 LLM 生成数据需求/工具计划"""
        prompt = build_template_analysis_prompt(template_content, target_time_range)
        data = await llm_service.call_llm_with_json_response(
            prompt=prompt,
            max_retries=2
        )
        requirements = data.get("data_requirements", []) if isinstance(data, dict) else []
        logger.info("template_analysis_done", requirement_count=len(requirements))
        
        # 详细记录每个需求的结构（用于调试）
        for idx, req in enumerate(requirements):
            logger.info(
                f"requirement_{idx}_detail",
                section=req.get("section"),
                tool=req.get("tool"),
                question=req.get("question", ""),
                query_type=req.get("query_type")
            )
        
        return requirements

    async def _execute_requirements(
        self,
        requirements: List[Dict[str, Any]],
        target_time_range: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        执行工具查询，返回标准化数据
        """
        if not requirements:
            return []

        # 为本次执行创建 ExecutionContext
        session_id = f"template_report_{uuid.uuid4().hex[:8]}"
        memory_manager = getattr(self, "_memory_manager", None) or HybridMemoryManager(session_id=session_id, iteration=0)
        data_manager = getattr(self, "_data_manager", None) or DataContextManager(memory_manager)
        exec_context = ExecutionContext(session_id=session_id, iteration=0, data_manager=data_manager)

        # 并发执行所有查询，限制最多5个并发（根据UQP接口性能调整）
        MAX_CONCURRENT_QUERIES = 5
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_QUERIES)

        async def execute_single_requirement(req: Dict[str, Any]) -> Dict[str, Any]:
            """执行单个查询需求（带并发限制，完全由LLM选择的工具执行）"""
            async with semaphore:  # 限制并发数
                tool_name = req.get("tool") or "get_guangdong_regular_stations"
                question = req.get("question", "")
                params = req.get("params") or {}

                tool = self.tools.get(tool_name)
                if not tool:
                    logger.warning("tool_not_found_for_requirement", tool=tool_name)
                    return {
                        "section": req.get("section"),
                        "tool": tool_name,
                        "question": question,
                        "error": f"工具 {tool_name} 未找到",
                        "data": None,
                        "data_id": None,
                        "metadata": {}
                    }

                try:
                    # 针对不同工具采用不同的参数模式
                    if tool_name == "get_weather_data":
                        # 气象数据工具：使用结构化参数，而不是自然语言 question
                        start_date = target_time_range.get("start")
                        end_date = target_time_range.get("end")

                        if not start_date or not end_date:
                            error_msg = "气象查询缺少时间范围（start/end）"
                            logger.warning(
                                "weather_requirement_missing_time_range",
                                requirement=req,
                                target_time_range=target_time_range
                            )
                            return {
                                "section": req.get("section"),
                                "tool": tool_name,
                                "question": question,
                                "error": error_msg,
                                "data": None,
                                "data_id": None,
                                "metadata": {}
                            }

                        # 将日期转为 ISO8601 时间，覆盖/补充 LLM 给出的 params
                        start_time = f"{start_date}T00:00:00"
                        end_time = f"{end_date}T23:59:59"

                        # 默认使用 ERA5，再分析数据，选取广东省中部附近经纬度作为代表点
                        # 示例坐标参考 TOOL_DESCRIPTIONS: (23.13, 113.26)
                        lat = params.get("lat", 23.13)
                        lon = params.get("lon", 113.26)
                        data_type = params.get("data_type", "era5")

                        logger.info(
                            "executing_weather_tool_with_params",
                            tool=tool_name,
                            data_type=data_type,
                            start_time=start_time,
                            end_time=end_time,
                            lat=lat,
                            lon=lon
                        )

                        tool_result = await tool(
                            context=exec_context,
                            data_type=data_type,
                            start_time=start_time,
                            end_time=end_time,
                            lat=lat,
                            lon=lon,
                        )
                    else:
                        # 其余工具：继续使用自然语言 question → UQP 的模式
                        logger.info(
                            "executing_tool_with_question",
                            tool=tool_name,
                            question=question
                        )
                        tool_result = await tool(context=exec_context, question=question)

                    # 标准化提取
                    data_id = None
                    metadata = {}
                    data = None
                    if hasattr(tool_result, "dict"):
                        tr = tool_result.dict()
                        data = tr.get("data")
                        data_id = tr.get("data_id")
                        metadata = tr.get("metadata") or {}
                    elif isinstance(tool_result, dict):
                        data = tool_result.get("data")
                        data_id = tool_result.get("data_id")
                        metadata = tool_result.get("metadata") or {}

                    return {
                        "section": req.get("section"),
                        "tool": tool_name,
                        "question": question,
                        "data": data,
                        "data_id": data_id,
                        "metadata": metadata,
                        "query_type": req.get("query_type")
                    }
                except Exception as e:
                    logger.error("tool_execution_failed", tool=tool_name, error=str(e))
                    return {
                        "section": req.get("section"),
                        "tool": tool_name,
                        "question": question,
                        "error": str(e),
                        "data": None,
                        "data_id": None,
                        "metadata": {}
                    }

        # 并发执行所有查询（限制最多3个并发）
        logger.info(
            "executing_requirements_concurrently",
            total_requirements=len(requirements),
            max_concurrent=MAX_CONCURRENT_QUERIES
        )
        tasks = [execute_single_requirement(req) for req in requirements]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "requirement_execution_exception",
                    requirement_index=i,
                    error=str(result)
                )
                final_results.append({
                    "section": requirements[i].get("section"),
                    "tool": requirements[i].get("tool"),
                    "question": requirements[i].get("question", ""),
                    "error": str(result),
                    "data": None,
                    "data_id": None,
                    "metadata": {}
                })
            else:
                final_results.append(result)

        return final_results

    async def _generate_report(
        self,
        template_content: str,
        collected_data: List[Dict[str, Any]],
        target_time_range: Dict[str, Any]
    ) -> str:
        """调用 LLM 生成最终报告。

        注意：
        - 这里使用流式接口 chat_stream，以避免长时间生成导致的 ReadTimeout；
        - 当前仅在服务端聚合完整文本返回，后续如需前端逐字流式展示，
          可以在此处增加回调，将增量片段通过 SSE 向前端转发。
        """
        prompt = build_report_generation_prompt(
            template_content=template_content,
            collected_data=collected_data,
            time_range=target_time_range
        )
        # 使用流式接口，在 Qwen 侧以 stream 模式返回，避免长时间无响应
        report = await llm_service.chat_stream(
            [{"role": "user", "content": prompt}],
            timeout=600.0,
        )
        clean = llm_service.clean_thinking_tags(report)

        # 【修复】移除Markdown代码块包裹（LLM可能返回 ```markdown ... ```）
        clean = clean.strip()
        if clean.startswith("```markdown"):
            # 移除开头的 ```markdown
            clean = clean[len("```markdown"):].lstrip()
        elif clean.startswith("```"):
            # 移除开头的 ```
            clean = clean[3:].lstrip()

        if clean.endswith("```"):
            # 移除结尾的 ```
            clean = clean[:-3].rstrip()

        return clean.strip()

