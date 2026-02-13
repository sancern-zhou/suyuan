"""
专家路由器 V3 (ExpertRouterV3)

核心职责：
1. 接收主Agent的结构化任务
2. 调度专家执行器（支持并行）
3. 收集结果返回给主Agent

架构特点：
- 主Agent生成工具计划，专家只执行
- 支持并行执行无依赖的专家
- 统一的结果格式
"""

from typing import Dict, Any, List, Optional
import structlog
import asyncio

from app.agent.core.structured_query_parser import StructuredQuery, StructuredQueryParser
from app.agent.core.expert_plan_generator import ExpertPlanGenerator, ExpertTask
from app.tools.query.get_nearby_stations.tool import GetNearbyStationsTool
from .expert_executor import ExpertResult
from .weather_executor import WeatherExecutor
from .component_executor import ComponentExecutor
from .viz_executor import VizExecutor
from .report_executor import ReportExecutor
from .template_report_executor import TemplateReportExecutor

logger = structlog.get_logger()


class PipelineResult:
    """流水线执行结果"""

    def __init__(self):
        self.status: str = "pending"
        self.query: str = ""
        self.parsed_query: Optional[StructuredQuery] = None
        self.selected_experts: List[str] = []
        self.expert_results: Dict[str, ExpertResult] = {}
        self.final_answer: str = ""
        self.conclusions: List[str] = []
        self.recommendations: List[str] = []
        self.data_ids: List[str] = []
        self.visuals: List[Dict[str, Any]] = []  # 聚合所有专家的visuals传递给前端
        self.confidence: float = 0.0
        self.errors: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "parsed_query": self.parsed_query.dict() if self.parsed_query else None,
            "selected_experts": self.selected_experts,
            "expert_results": {
                k: v.dict() for k, v in self.expert_results.items()
            },
            "final_answer": self.final_answer,
            "conclusions": self.conclusions,
            "recommendations": self.recommendations,
            "data_ids": self.data_ids,
            "visuals": self.visuals,  # 添加visuals字段
            "confidence": self.confidence,
            "errors": self.errors
        }


class ExpertRouterV3:
    """专家路由器 V3"""

    def __init__(self, event_callback=None, memory_manager=None):
        # 初始化核心组件
        self.query_parser = StructuredQueryParser()
        self.plan_generator = ExpertPlanGenerator()
        self.nearby_station_tool = GetNearbyStationsTool()
        self.event_callback = event_callback  # 事件回调函数
        self.memory_manager = memory_manager  # 记忆管理器（用于创建DataContextManager）

        # 初始化专家执行器
        self.executors: Dict[str, Any] = {
            "weather": WeatherExecutor(),
            "component": ComponentExecutor(),
            "viz": VizExecutor(),
            "report": ReportExecutor(),
            "template_report": TemplateReportExecutor()
        }

        # 为专家执行器设置memory_manager和data_manager
        self._setup_executor_context()

        logger.info(
            "expert_router_v3_initialized",
            executors=list(self.executors.keys()),
            has_callback=event_callback is not None,
            has_memory_manager=memory_manager is not None
        )
    
    def _setup_executor_context(self):
        """
        为专家执行器设置memory_manager和data_manager

        这样专家执行器就能创建ExecutionContext并正确传递给工具
        """
        if not self.memory_manager:
            logger.warning(
                "no_memory_manager_provided",
                message="Experts will not have context support"
            )
            return

        # 获取DataContextManager
        try:
            from app.agent.context.data_context_manager import DataContextManager

            data_manager = DataContextManager(self.memory_manager)

            # 为每个专家执行器设置上下文
            for expert_type, executor in self.executors.items():
                if hasattr(executor, '_memory_manager'):
                    executor._memory_manager = self.memory_manager
                else:
                    executor._memory_manager = self.memory_manager

                if hasattr(executor, '_data_manager'):
                    executor._data_manager = data_manager
                else:
                    executor._data_manager = data_manager

                logger.debug(
                    "executor_context_set",
                    expert_type=expert_type,
                    has_memory_manager=True,
                    has_data_manager=True
                )

            logger.info(
                "all_executors_context_configured",
                executor_count=len(self.executors)
            )

        except Exception as e:
            logger.error(
                "executor_context_setup_failed",
                error=str(e)
            )

    async def execute_pipeline(
        self,
        user_query: str,
        precision: str = 'standard'
    ) -> PipelineResult:
        """
        执行完整的专家流水线

        Args:
            user_query: 用户原始查询
            precision: EKMA分析精度模式 (fast/standard/full)
                - fast: 快速筛查模式 (~18秒)
                - standard: 标准分析模式 (~3分钟)
                - full: 完整分析模式 (~7-10分钟)

        Returns:
            PipelineResult: 完整的流水线结果
        """
        result = PipelineResult()
        result.query = user_query

        logger.info("pipeline_started", query=user_query[:100], precision=precision)

        # 发送pipeline开始事件
        if self.event_callback:
            self.event_callback({
                "type": "pipeline_started",
                "data": {
                    "query": user_query[:100],
                    "precision": precision
                }
            })

        try:
            # 1. 结构化解析
            parsed_query = await self.query_parser.parse(user_query)
            parsed_query = await self._maybe_enrich_query_with_station(parsed_query)

            # 注入precision选项
            parsed_query.precision = precision
            result.parsed_query = parsed_query

            logger.info(
                "query_parsed",
                location=parsed_query.location,
                confidence=parsed_query.parse_confidence,
                precision=precision
            )

            # 发送查询解析完成事件
            if self.event_callback:
                self.event_callback({
                    "type": "query_parsed",
                    "data": {
                        "location": parsed_query.location,
                        "confidence": parsed_query.parse_confidence
                    }
                })

            # 2. 选择专家
            result.selected_experts = self.plan_generator.determine_required_experts(parsed_query)

            logger.info(
                "experts_selected",
                experts=result.selected_experts
            )

            # 发送专家选择完成事件
            if self.event_callback:
                self.event_callback({
                    "type": "experts_selected",
                    "data": {
                        "selected_experts": result.selected_experts
                    }
                })

            # 3. 获取并行执行分组
            parallel_groups = self._build_parallel_groups(result.selected_experts)

            # 5. 按组执行（每组执行完发送阶段性事件）
            upstream_results: Dict[str, ExpertResult] = {}
            expert_tasks: Dict[str, ExpertTask] = {}  # 初始化为空，逐步添加各组任务

            for group_idx, group in enumerate(parallel_groups):
                logger.info("executing_expert_group", group=group, group_index=group_idx)

                # 【诊断】记录当前upstream_results状态
                logger.info(
                    "upstream_results_before_group",
                    group_index=group_idx,
                    group=group,
                    upstream_experts=list(upstream_results.keys()),
                    upstream_data_ids={
                        k: v.data_ids for k, v in upstream_results.items()
                    }
                )

                # 为当前组专家生成任务
                upstream_dict = {k: v.dict() for k, v in upstream_results.items()}
                logger.info(
                    "generating_tasks_for_group",
                    group_index=group_idx,
                    group=group,
                    upstream_count=len(upstream_dict)
                )
                group_tasks = self.plan_generator.generate(
                    parsed_query,
                    group,
                    upstream_dict
                )
                expert_tasks.update(group_tasks)  # 将当前组任务添加到总任务字典

                # 【诊断】记录当前组任务
                logger.info(
                    "group_tasks_generated",
                    group_index=group_idx,
                    group=group,
                    task_count=len(group_tasks),
                    task_experts=list(group_tasks.keys())
                )

                # 并行执行组内专家
                group_results = await self._execute_group(
                    group,
                    expert_tasks,
                    upstream_results
                )

                # 【诊断】记录组执行结果
                logger.info(
                    "group_execution_results",
                    group_index=group_idx,
                    group=group,
                    results={k: {"status": v.status, "data_ids": v.data_ids} for k, v in group_results.items()}
                )

                # 【新增】从上游专家执行结果中收集skip_viz_data_ids
                # 下一组如果是viz专家，需要使用这些skip_viz_data_ids来过滤
                all_upstream_skip_viz = []
                for expert_type, expert_result in upstream_results.items():
                    if expert_type == "viz":
                        continue
                    if hasattr(expert_result, 'skip_viz_data_ids'):
                        all_upstream_skip_viz.extend(expert_result.skip_viz_data_ids)

                # 【新增】如果下一组有viz专家，更新其任务的skip_viz_data_ids
                if group_idx + 1 < len(parallel_groups):
                    next_group = parallel_groups[group_idx + 1]
                    if "viz" in next_group and all_upstream_skip_viz:
                        # 更新expert_tasks中viz任务的skip_viz_data_ids
                        if "viz" in expert_tasks:
                            existing_skip_viz = set(expert_tasks["viz"].skip_viz_data_ids)
                            existing_skip_viz.update(all_upstream_skip_viz)
                            expert_tasks["viz"] = expert_tasks["viz"].copy(
                                update={"skip_viz_data_ids": list(existing_skip_viz)}
                            )
                            logger.info(
                                "viz_expert_skip_viz_data_ids_updated_from_execution",
                                skip_viz_data_ids=list(existing_skip_viz),
                                count=len(existing_skip_viz)
                            )

                # 合并结果
                for expert_type, expert_result in group_results.items():
                    result.expert_results[expert_type] = expert_result
                    upstream_results[expert_type] = expert_result

                    # 收集data_ids
                    result.data_ids.extend(expert_result.data_ids)

                # 【诊断】记录合并后的upstream_results
                logger.info(
                    "upstream_results_after_group",
                    group_index=group_idx,
                    group=group,
                    upstream_experts=list(upstream_results.keys()),
                    all_data_ids=[
                        data_id for expert_result in upstream_results.values()
                        for data_id in expert_result.data_ids
                    ]
                )

                # 发送阶段性汇总事件
                if self.event_callback:
                    # 构造阶段性expert_results
                    partial_expert_results = {
                        k: v.dict() for k, v in result.expert_results.items()
                    }

                    self.event_callback({
                        "type": "expert_result",
                        "data": {
                            "status": "in_progress",
                            "expert_results": partial_expert_results,
                            "completed_groups": group_idx + 1,
                            "total_groups": len(parallel_groups),
                            "completed_experts": list(result.expert_results.keys()),
                            "total_experts": result.selected_experts
                        }
                    })

            # 6. 生成最终答案
            result = self._finalize_result(result)

            logger.info(
                "pipeline_completed",
                status=result.status,
                experts_succeeded=sum(1 for r in result.expert_results.values() if r.status == "success"),
                confidence=result.confidence
            )

        except Exception as e:
            logger.error(
                "pipeline_failed",
                error=str(e),
                exc_info=True
            )
            result.status = "failed"
            result.errors.append({"type": "pipeline_error", "message": str(e)})

            # 发送失败事件
            if self.event_callback:
                self.event_callback({
                    "type": "pipeline_error",
                    "data": {
                        "error": str(e),
                        "partial_results": {
                            k: v.dict() for k, v in result.expert_results.items()
                        } if result.expert_results else {}
                    }
                })

        return result
    
    async def _execute_group(
        self,
        group: List[str],
        expert_tasks: Dict[str, ExpertTask],
        upstream_results: Dict[str, ExpertResult]
    ) -> Dict[str, ExpertResult]:
        """并行执行一组专家"""

        # 发送组开始事件
        if self.event_callback:
            self.event_callback({
                "type": "expert_group_started",
                "data": {
                    "group": group,
                    "expert_count": len(group)
                }
            })

        async def execute_single(expert_type: str) -> tuple:
            if expert_type not in expert_tasks:
                return expert_type, ExpertResult(
                    status="failed",
                    expert_type=expert_type,
                    errors=[{"message": "No task generated"}]
                )

            task = expert_tasks[expert_type]
            executor = self.executors.get(expert_type)

            if not executor:
                return expert_type, ExpertResult(
                    status="failed",
                    expert_type=expert_type,
                    errors=[{"message": f"Executor not found: {expert_type}"}]
                )

            # 发送单个专家开始事件
            if self.event_callback:
                self.event_callback({
                    "type": "expert_started",
                    "data": {
                        "expert_type": expert_type,
                        "task_id": task.task_id,
                        "tool_count": len(task.tool_plan)
                    }
                })

            try:
                # 创建ExecutionContext并传递给专家执行器
                execution_context = self._create_execution_context_for_expert(expert_type)

                # 报告专家需要其他专家的结果
                if expert_type == "report":
                    result = await executor.execute(task, upstream_results)
                else:
                    result = await executor.execute(task, execution_context)

                # 发送专家完成事件
                if self.event_callback:
                    self.event_callback({
                        "type": "expert_completed",
                        "data": {
                            "expert_type": expert_type,
                            "status": result.status,
                            "task_id": task.task_id,
                            "tool_count": len(result.tool_results) if result.tool_results else 0,
                            "data_ids": result.data_ids
                        }
                    })

                return expert_type, result

            except Exception as e:
                logger.error(
                    "expert_execution_error",
                    expert=expert_type,
                    error=str(e)
                )
                # 发送专家错误事件
                if self.event_callback:
                    self.event_callback({
                        "type": "expert_error",
                        "data": {
                            "expert_type": expert_type,
                            "error": str(e),
                            "task_id": task.task_id
                        }
                    })
                return expert_type, ExpertResult(
                    status="failed",
                    expert_type=expert_type,
                    task_id=task.task_id,
                    errors=[{"type": "execution_error", "message": str(e)}]
                )

        # 并行执行
        tasks = [execute_single(expert_type) for expert_type in group]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        group_results = {}
        for item in results:
            if isinstance(item, Exception):
                logger.error("group_execution_exception", error=str(item))
            else:
                expert_type, result = item
                group_results[expert_type] = result

        # 发送组完成事件
        if self.event_callback:
            self.event_callback({
                "type": "expert_group_completed",
                "data": {
                    "group": group,
                    "results": {k: v.status for k, v in group_results.items()}
                }
            })

        return group_results
    
    def _finalize_result(self, result: PipelineResult) -> PipelineResult:
        """生成最终结果"""

        # 统计成功/失败
        success_count = sum(1 for r in result.expert_results.values() if r.status == "success")
        partial_count = sum(1 for r in result.expert_results.values() if r.status == "partial")
        failed_count = sum(1 for r in result.expert_results.values() if r.status == "failed")

        # 确定整体状态
        if failed_count == len(result.expert_results):
            result.status = "failed"
        elif success_count == len(result.expert_results):
            result.status = "success"
        else:
            result.status = "partial"

        # 聚合所有专家的 visuals
        all_visuals = []
        seen_ids = set()
        for expert_type, expert_result in result.expert_results.items():
            if hasattr(expert_result, 'visuals') and expert_result.visuals:
                for visual in expert_result.visuals:
                    if not isinstance(visual, dict):
                        continue
                    visual_id = visual.get("id")
                    # 去重
                    if visual_id and visual_id in seen_ids:
                        continue
                    if visual_id:
                        seen_ids.add(visual_id)
                    # 添加来源专家信息
                    visual["expert"] = expert_type
                    all_visuals.append(visual)

        result.visuals = all_visuals
        logger.info(
            "all_visuals_aggregated",
            total=len(all_visuals),
            from_experts=list(result.expert_results.keys())
        )

        # 生成最终答案
        if "report" in result.expert_results and result.expert_results["report"].status == "success":
            # 使用报告专家的总结
            report_result = result.expert_results["report"]
            result.final_answer = report_result.analysis.summary
            result.confidence = report_result.analysis.confidence
            
            # 从报告中提取结论和建议
            if report_result.tool_results:
                report_content = report_result.tool_results[0].get("result", {})
                result.conclusions = report_content.get("conclusions", [])
                result.recommendations = report_content.get("recommendations", [])
        
        else:
            # 单专家或无报告专家，使用各专家的总结
            summaries = []
            findings = []
            total_confidence = 0.0
            count = 0
            
            for expert_type, expert_result in result.expert_results.items():
                if expert_result.status in ["success", "partial"]:
                    summaries.append(f"【{expert_type}】{expert_result.analysis.summary}")
                    findings.extend(expert_result.analysis.key_findings)
                    total_confidence += expert_result.analysis.confidence
                    count += 1
            
            result.final_answer = "\n".join(summaries) if summaries else "分析未完成"
            result.conclusions = findings[:5]  # 取前5个发现作为结论
            result.confidence = total_confidence / max(count, 1)
        
        return result
    
    async def execute_single_expert(
        self,
        user_query: str,
        expert_type: str
    ) -> ExpertResult:
        """
        执行单个专家（用于简单查询）
        
        Args:
            user_query: 用户查询
            expert_type: 专家类型
            
        Returns:
            ExpertResult: 专家执行结果
        """
        logger.info(
            "single_expert_execution",
            expert=expert_type,
            query=user_query[:100]
        )
        
        # 1. 解析查询
        parsed_query = await self.query_parser.parse(user_query)
        parsed_query = await self._maybe_enrich_query_with_station(parsed_query)
        
        # 2. 生成任务
        tasks = self.plan_generator.generate(parsed_query, [expert_type])
        
        if expert_type not in tasks:
            return ExpertResult(
                status="failed",
                expert_type=expert_type,
                errors=[{"message": "Failed to generate task"}]
            )
        
        # 3. 执行
        executor = self.executors.get(expert_type)
        if not executor:
            return ExpertResult(
                status="failed",
                expert_type=expert_type,
                errors=[{"message": f"Executor not found: {expert_type}"}]
            )
        
        return await executor.execute(tasks[expert_type])
    
    def get_executor_status(self) -> Dict[str, Any]:
        """获取所有执行器状态"""
        return {
            expert_type: {
                "available": executor is not None,
                "tools": list(executor.tools.keys()) if executor else []
            }
            for expert_type, executor in self.executors.items()
        }

    async def get_expert_status(self) -> Dict[str, Any]:
        """兼容旧接口的异步状态查询"""
        return self.get_executor_status()

    async def health_check(self) -> Dict[str, Any]:
        """返回简要的执行器健康状态"""
        status = self.get_executor_status()
        overall = "healthy" if all(meta["available"] for meta in status.values()) else "degraded"
        return {
            "overall_status": overall,
            "executors": status
        }

    def _build_parallel_groups(self, experts: List[str]) -> List[List[str]]:
        """根据专家列表生成可并行的执行分组"""
        groups: List[List[str]] = []
        first_group = [e for e in experts if e in ["weather", "component"]]
        if first_group:
            groups.append(first_group)
        if "viz" in experts:
            groups.append(["viz"])
        if "report" in experts:
            groups.append(["report"])
        return groups or [experts]

    def _create_execution_context_for_expert(self, expert_type: str):
        """
        为特定专家创建ExecutionContext

        Args:
            expert_type: 专家类型

        Returns:
            ExecutionContext对象或None
        """
        try:
            from app.agent.context.execution_context import ExecutionContext

            # 获取该专家的执行器
            executor = self.executors.get(expert_type)
            if not executor:
                logger.warning(
                    "executor_not_found_for_context",
                    expert_type=expert_type
                )
                return None

            # 检查是否有data_manager
            if not hasattr(executor, '_data_manager') or executor._data_manager is None:
                logger.warning(
                    "no_data_manager_for_expert",
                    expert_type=expert_type,
                    message="ExecutionContext creation skipped"
                )
                return None

            # 创建ExecutionContext
            execution_context = ExecutionContext(
                session_id=f"expert_{expert_type}_{id(executor)}",
                iteration=0,
                data_manager=executor._data_manager
            )

            logger.debug(
                "execution_context_created_for_expert",
                expert_type=expert_type,
                session_id=execution_context.session_id,
                has_data_manager=True
            )

            return execution_context

        except Exception as e:
            logger.error(
                "execution_context_creation_failed_for_expert",
                expert_type=expert_type,
                error=str(e),
                exc_info=True
            )
            return None

    async def _maybe_enrich_query_with_station(
        self,
        query: StructuredQuery
    ) -> StructuredQuery:
        """必要时调用get_nearby_stations补齐站点经纬度"""
        if not query.location:
            return query
        if (query.lat is not None and query.lon is not None) or "站" not in query.location:
            return query

        try:
            response = await self.nearby_station_tool.execute(
                station_name=query.location,
                max_distance=5.0,
                max_results=1,
                fetch_air_quality=False
            )
            records = response.get("data") or []
            target_record = None
            for record in records:
                metadata = record.get("metadata") or {}
                if metadata.get("station_type") == "target":
                    target_record = record
                    break
            if not target_record and records:
                target_record = records[0]

            if not target_record:
                return query

            metadata = target_record.get("metadata") or {}
            lat = target_record.get("lat") or metadata.get("lat")
            lon = target_record.get("lon") or metadata.get("lon")
            station_id = metadata.get("station_code")

            if lat is None or lon is None:
                return query

            updated = query.copy(update={
                "lat": lat,
                "lon": lon,
                "station_id": station_id or query.station_id
            })
            logger.info(
                "query_station_enriched",
                location=query.location,
                lat=lat,
                lon=lon,
                station_id=updated.station_id
            )
            return updated
        except Exception as exc:
            logger.warning(
                "nearby_station_lookup_failed",
                location=query.location,
                error=str(exc)
            )
            return query
