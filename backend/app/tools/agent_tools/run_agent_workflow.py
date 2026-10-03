"""Run a bounded, dependency-aware workflow of cooperating Agents."""

from __future__ import annotations

import asyncio
import time
import json
from typing import Any, Dict, Mapping, Optional

import structlog

from app.agent.workflow.resource_handoff import result_resource_declarations
from app.agent.workflow.target_mode_contract import build_target_mode_contract, target_mode_values
from app.agent.workflow.coordinator import WorkflowCoordinator, WorkflowNodeSpec
from app.agent.workflow.registry import active_workflow_registry
from app.tools.base.tool_interface import LLMTool, ToolCategory


logger = structlog.get_logger(__name__)

# 报告 DAG 专家节点集合：这些模式必须提供 task_contract 并受交付物粒度校验
EXPERT_NODE_MODES = frozenset({"expert_meteorology", "expert_analysis"})
MAX_EXPERT_NODE_DELIVERABLES = 3
# 报告父 Agent 只允许取数与领域专家节点，禁止子节点越权成稿或再次编排。
REPORT_NODE_ALLOWED_MODES = frozenset({
    "query_monitoring",
    "query_forecast",
    "expert_meteorology",
    "expert_analysis",
})

_DEFAULT_EXPERT_NODE_LIMITS = {
    "expert_meteorology": {"max_iterations": 15, "timeout_seconds": 300},
    "expert_analysis": {"max_iterations": 20, "timeout_seconds": 360},
    "expert": {"max_iterations": 30, "timeout_seconds": 480},
    # 固定问数流程由运行时约束为最多四轮。
    "query_monitoring": {"max_iterations": 4, "timeout_seconds": 420},
    "query_forecast": {"max_iterations": 4, "timeout_seconds": 420},
}


WORKFLOW_DAG_EXAMPLE = (
    '{"workflow": {"workflow_id": "air-quality-report", "nodes": ['
    '{"task_id": "air-data", "target_mode": "query_monitoring", "goal": "查询指定区域和时间范围的空气质量监测数据"}, '
    '{"task_id": "weather-data", "target_mode": "query_forecast", "goal": "获取同期地面气象观测与预报数据"}, '
    '{"task_id": "cause-analysis", "target_mode": "expert_analysis", '
    '"goal": "基于上游数据完成污染成因研判，输出结论、证据和缺口", '
    '"dependencies": ["air-data", "weather-data"]}]}, "max_concurrency": 4}'
)

WORKFLOW_SCHEMA_DESCRIPTION = (
    "提交一个有向无环 Agent 工作流（DAG）：节点可并行执行，只有依赖节点成功后才会执行下游节点；"
    "适合多源数据分析、交叉验证和分阶段报告任务。编排完全由你自主决定：按分析问题规划节点数量、"
    "每个节点的 target_mode 与 goal；无依赖的数据/分析节点并行执行，需要上游产物或结论的节点用 "
    "dependencies 表达，不靠文字约定顺序。每个节点必须有唯一 task_id、target_mode、goal，"
    "goal 写清时间范围、区域、指标口径和预期输出；把无依赖的取数拆成独立节点以并行执行。"
    "节点可用可选 phase 字段打用户可读的阶段名（如'取数与质检'/'气象分箱研判'/'整合成稿'），"
    "同阶段节点共用一个名字，面板按阶段分组展示故事线；用业务语言命名，不用编排术语。"
    "领域拆分建议：监测历史取数（小时/日历史、AQI 与六参数、站点目录、全国对比）拆 query_monitoring，"
    "气象实况/预报与空气质量预报数据拆 query_forecast，二者可并行；"
    "气象条件、输送通道、静稳/边界层形势拆 expert_meteorology；浓度特征、超标统计、"
    "组分解读、成因研判拆 expert_analysis；交叉归因由你自己整合（整合阶段禁止重新取数）。"
    "报告编排禁止综合问数（query）子节点：监测历史用 query_monitoring，气象与预报用 query_forecast；"
    "综合 expert 也不对报告 DAG 暴露。"
    "**问数节点轮次硬约束**：固定工作流由运行时控制为最多 4 轮且失败项最多补查一次；"
    "取数节点必须多表探查一次完成——同库数据用一条合法的 JOIN/UNION/CTE SQL 覆盖所需表和口径，"
    "或独立查询在同一轮并发发出（单轮多工具调用），禁止逐表串行试探；"
    "禁止多语句 SQL；缺失/口径质检最多用一个 python 脚本完成。"
    "**交付物粒度硬约束**：每个节点承载 2~3 项强耦合必交物（最多 5 项）；"
    "一个专家节点只能回答一个分析问题；计算结果、对应图表和证据摘要可以算同一问题的交付物。"
    "**同域多节点并行是默认模式**——同一领域的多个独立子分析拆成多个同 mode 节点"
    "（如 3 个 expert_analysis 分别做相关性/超标统计/时空对比，task_id 不同即可），"
    "不要把独立子分析合并进单一节点：并行节点总耗时 ≈ 最慢节点，合并则全部串行相加。"
    "**合并判据**：共享同一份输入文件不是合并理由（各分支可各自 load_data，重复读取是秒级成本）；"
    "只有必须共享同一份中间计算状态（同一样本集/同一对齐表）才能保持可比时才合并。"
    "样本一致性用任务书统一过滤口径解决；有依赖的子分析用 dependencies 表达（如归因节点依赖分段节点）。"
    "**⚠️ 图表随节点并行产出**：报告需要的分析图表（分箱图、相关性热力图、时序对比等）"
    "必须在对应子节点的 goal/task_contract 中明确要求，由子 Agent 在分析的同时一并生成；"
    "子节点交付的图表文件会在上游产物清单中回传，父 Agent 只做复用与排版，"
    "禁止在 DAG 完成后再由父 Agent 重新绘制分析图表——那是串行追加的整段时间。"
    "DAG 禁止 report 子节点；报告模式父 Agent 是唯一成稿者。"
    "工具返回每个节点的 result_envelope（status/summary/evidence/artifacts/data_gaps）与血缘清单，"
    "据此判断覆盖范围与缺口并整合结论，不要对子节点过程做重复全量复核。"
    "expert 族节点（expert/expert_meteorology/expert_analysis）必须提供 task_contract（protocol_version=workflow.v1、"
    "task_type=expert_analysis、question、decision_context、scope、required_evidence、deliverables）和 "
    "result_schema（要求 status、findings、evidence、uncertainties、data_gaps，finding 通过 evidence id 回溯证据）；"
    "节点可用 max_attempts 设置重试次数（默认 2：重试自动续用子会话、预算扩容 50% 并携带失败原因），"
    "用 max_iterations 限制子 Agent 推理轮次，"
    "用 timeout_seconds 设置节点硬超时；聚合、分箱、相关性等含图表的计算密集节点请放宽预算"
    "（建议 expert 节点 max_iterations≥25、timeout_seconds≥1200）。"
    "重试时预算自动放宽：迭代与超时各放大 50%（迭代封顶 120、超时封顶 1 小时），"
    "专家节点 task_contract.deliverables 最多 3 项；超过 3 项必须拆成多个并行节点。"
    "因此首试可给紧凑预算，把余量留给重试。"
    f"示例：{WORKFLOW_DAG_EXAMPLE}\n\n"
    f"{build_target_mode_contract()}"
)


def _result_envelope(result: Any) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    data = result.get("data")
    if isinstance(data, Mapping) and isinstance(data.get("result_envelope"), Mapping):
        return data["result_envelope"]
    if isinstance(result.get("result_envelope"), Mapping):
        return result["result_envelope"]
    if {"status", "outputs", "evidence", "artifacts"}.issubset(result):
        return result
    return {}


def collect_result_handles(task_id: str, result: Any) -> list[Dict[str, Any]]:
    """Extract reusable file/artifact handles from one node result."""
    if not isinstance(result, Mapping):
        return []
    data = result.get("data") if isinstance(result.get("data"), Mapping) else {}
    handles: list[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_file(kind: str, value: Any, name: Any = None) -> None:
        if value is None:
            return
        text = str(value).strip()
        identity = ("file_path", text)
        if not text or identity in seen:
            return
        seen.add(identity)
        item: Dict[str, Any] = {
            "source_task_id": str(task_id),
            "handle_type": "file_path",
            "kind": kind,
            "file_path": text,
        }
        if name:
            item["label"] = str(name)
        handles.append(item)

    for ref in data.get("resource_refs") or []:
        if not isinstance(ref, Mapping):
            continue
        resource_id = str(ref.get("resource_id") or "").strip()
        source_session_id = str(ref.get("source_session_id") or "").strip()
        identity = (source_session_id, resource_id)
        if not resource_id or not source_session_id or identity in seen:
            continue
        seen.add(identity)
        handles.append({
            **dict(ref),
            "handle_type": "session_resource",
            "source_task_id": str(task_id),
        })
        ref_path = str(ref.get("file_path") or "").strip()
        if ref_path:
            seen.add(("file_path", ref_path))

    for path in data.get("file_paths") or []:
        add_file("file", path)
    for key in ("file_path", "report_file_path"):
        add_file("file", data.get(key))
    for artifact in _result_envelope(result).get("artifacts") or []:
        if isinstance(artifact, Mapping):
            resource_id = str(artifact.get("resource_id") or "").strip()
            source_session_id = str(artifact.get("source_session_id") or "").strip()
            if resource_id and source_session_id:
                identity = (source_session_id, resource_id)
                if identity not in seen:
                    seen.add(identity)
                    handles.append({
                        **dict(artifact),
                        "handle_type": "session_resource",
                        "source_task_id": str(task_id),
                    })
                continue
            add_file(
                str(artifact.get("kind") or "artifact"),
                artifact.get("path") or artifact.get("file_path"),
                artifact.get("name"),
            )
        else:
            add_file("artifact", artifact)
    return handles


def format_upstream_handles(dependency_results: Mapping[str, Any]) -> str:
    """Render the explicit upstream artifact/file handle block for a dependent node."""
    lines: list[str] = []
    for task_id, result in (dependency_results or {}).items():
        for handle in collect_result_handles(task_id, result):
            label = str(handle.get("label") or handle.get("name") or "").strip()
            name = f" ({label})" if label else ""
            if handle.get("handle_type") == "session_resource":
                details = f"resource: {handle.get('resource_id')}"
                if handle.get("file_path"):
                    details += f"; file_path: {handle['file_path']}"
            else:
                details = f"file_path: {handle.get('file_path')}"
            lines.append(f"- [{handle['source_task_id']}] {handle.get('kind') or 'artifact'}{name}: {details}")
    if not lines:
        return ""
    return (
        "## 上游节点产物（可直接复用，禁止对同一数据源重复查询）\n"
        "资源已由运行时登记并授权；结构化数据使用目标工具的 `file_path` 参数或 "
        "`execute_python` 的 `load_data(file_path)`，文档类文件使用 `read_file`。"
        "不要重新查询已覆盖的数据：\n"
        + "\n".join(lines)
        + "\n"
    )


def format_upstream_summaries(dependency_results: Mapping[str, Any]) -> str:
    """Pass conclusions and evidence references, never raw child tool traces."""
    summaries = []
    for task_id, result in (dependency_results or {}).items():
        envelope = _result_envelope(result)
        if not envelope:
            continue
        summaries.append({
            "source_task_id": str(task_id),
            "status": envelope.get("status"),
            "summary": str(envelope.get("summary") or "")[:2000],
            "evidence": [
                {key: item.get(key) for key in ("ref_id", "kind", "label", "source_task_id")
                 if item.get(key) is not None}
                for item in envelope.get("evidence") or []
                if isinstance(item, Mapping)
            ],
            "uncertainties": [str(item) for item in envelope.get("uncertainties") or []],
            "data_gaps": [str(item) for item in envelope.get("data_gaps") or []],
        })
    if not summaries:
        return ""
    return (
        "## 上游节点结论摘要\n"
        "上游资源和文件已通过工作流资源目录导入当前会话，可直接读取；"
        "以下仅是上游结论和证据索引。不要根据摘要重新查询同一数据源：\n"
        + json.dumps(summaries, ensure_ascii=False, default=str)
        + "\n"
    )

class RunAgentWorkflowTool(LLMTool):
    """Coordinator entry point for report/assistant orchestration."""

    def __init__(self) -> None:
        super().__init__(
            name="run_agent_workflow",
            description="按任务依赖图并行调度多个 Agent，并汇聚结构化结果。",
            category=ToolCategory.PLANNING,
            requires_context=True,
            function_schema={
                "name": "run_agent_workflow",
                "description": WORKFLOW_SCHEMA_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow": {
                            "type": "object",
                            "description": (
                                "完整 DAG 定义：{workflow_id?, version?, nodes:[{task_id, target_mode, goal, context, "
                                "dependencies, task_contract, result_schema, max_attempts, max_iterations, "
                                "timeout_seconds}]}. workflow_id 缺省时自动生成。"
                                "编排由你自主规划；无依赖节点并行，依赖用 dependencies 表达。"
                            ),
                            "properties": {
                                "workflow_id": {"type": "string"},
                                "version": {"type": "string"},
                                "nodes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "task_id": {"type": "string"},
                                            "target_mode": {
                                                "type": "string",
                                                "enum": target_mode_values(),
                                                "description": "目标 Agent 模式；能力与工具边界见工具说明。",
                                            },
                                            "goal": {"type": "string"},
                                            "context": {"type": "string"},
                                            "dependencies": {"type": "array", "items": {"type": "string"}},
                                            "task_contract": {"type": "object"},
                                            "result_schema": {"type": "object"},
                                            "max_attempts": {"type": "integer", "minimum": 1, "maximum": 3},
                                            "phase": {
                                                "type": "string",
                                                "description": "可选阶段名（用户可读的业务语言），同阶段节点共用一个名字",
                                            },
                                            "max_iterations": {
                                                "type": "integer",
                                                "minimum": 1,
                                                "maximum": 120,
                                                "description": "子 Agent 最大推理轮次；气象专家建议15，常规分析专家建议20。",
                                            },
                                            "timeout_seconds": {
                                                "type": "number",
                                                "minimum": 30,
                                                "maximum": 1800,
                                                "description": "节点硬超时秒数；到期后取消正在运行的子 Agent 和工具。",
                                            },
                                        },
                                        "required": ["task_id", "target_mode", "goal"],
                                    },
                                },
                            },
                            "required": ["nodes"],
                        },
                        "max_concurrency": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 8,
                            "description": "同时运行的节点数量，默认4。",
                        },
                        "snapshot": {
                            "type": "object",
                            "description": "可选的上次运行快照；传入后从中断位置恢复。",
                        },
                    },
                    "required": ["workflow"],
                },
            },
            version="1.0.0",
        )

    async def execute(
        self,
        context: Optional[Any] = None,
        workflow: Optional[Mapping[str, Any]] = None,
        max_concurrency: int = 4,
        snapshot: Optional[Mapping[str, Any]] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        if not isinstance(workflow, Mapping):
            return self._failure("请提供 workflow DAG 定义（workflow_id + nodes）")
        try:
            definition = dict(workflow)
            if not str(definition.get("workflow_id") or "").strip():
                definition["workflow_id"] = f"workflow-{int(time.time() * 1000)}"
            nodes = [dict(node) for node in definition.get("nodes") or []]
            for node in nodes:
                if not node.get("target_mode") or not node.get("goal"):
                    return self._failure(f"节点 {node.get('task_id') or '<unknown>'} 缺少 target_mode 或 goal")
                limits = _DEFAULT_EXPERT_NODE_LIMITS.get(str(node.get("target_mode")))
                if limits:
                    node.setdefault("max_iterations", limits["max_iterations"])
                    node.setdefault("timeout_seconds", limits["timeout_seconds"])
                granularity_error = self._validate_expert_node_granularity(node)
                if granularity_error:
                    return self._failure(granularity_error)
            # 报告编排只暴露领域取数与专家节点，禁止综合模式或产出型模式越权。
            runtime_mode = str(getattr(context, "runtime_mode", "") or "")
            if runtime_mode == "report":
                disallowed_nodes = [
                    str(node.get("task_id") or "<unknown>")
                    for node in nodes
                    if str(node.get("target_mode") or "") not in REPORT_NODE_ALLOWED_MODES
                ]
                if disallowed_nodes:
                    return self._failure(
                        "报告 DAG 子节点仅允许 query_monitoring / query_forecast / "
                        "expert_meteorology / expert_analysis；"
                        "监测历史用 query_monitoring，气象与预报用 query_forecast，"
                        "其他模式不得作为报告子节点。"
                        f"越界节点：{', '.join(disallowed_nodes)}"
                    )
            definition["nodes"] = nodes
            # 节点成果缓存：同 workflow 重提时复用命中节点（依赖闭包完整才复用）
            from app.agent.workflow.result_cache import (
                result_fingerprint,
                select_reusable_nodes,
                store_node_result,
            )
            from app.agent.workflow.journal import WorkflowJournal

            workflow_journal = WorkflowJournal()
            workflow_id_str = str(definition["workflow_id"])
            completed_results = select_reusable_nodes(workflow_id_str, nodes)
            if completed_results:
                logger.info(
                    "workflow_cache_nodes_reused",
                    workflow_id=workflow_id_str,
                    tasks=sorted(completed_results),
                )
            sub_agent_tool = self._build_sub_agent_tool()

            async def execute_node(
                node: WorkflowNodeSpec,
                dependency_results: Mapping[str, Any],
                attempt: int,
                retry_context: Optional[Mapping[str, Any]] = None,
            ):
                payload = node.payload
                upstream = ""
                if dependency_results:
                    upstream_handles = [
                        handle
                        for task_id, result in dependency_results.items()
                        for handle in collect_result_handles(task_id, result)
                    ]
                    upstream = format_upstream_summaries(dependency_results)
                else:
                    upstream_handles = []
                context_text = str(payload.get("context") or "") + upstream
                # 重试续用上次的子会话：失败原因与已交付进度写入上下文
                retry_session_id = None
                if retry_context:
                    retry_session_id = str(retry_context.get("session_id") or "") or None
                    previous_error = str(retry_context.get("error") or "")[:300]
                    if retry_session_id or previous_error:
                        context_text += (
                            "\n## 重试说明\n"
                            f"上一轮执行未通过结果校验：{previous_error or '未交付结构化结果'}。\n"
                            "该会话保留了上轮已完成的工作，请在其基础上修正并交付，不要从零重做。\n"
                        )
                    progress = retry_context.get("progress") or {}
                    delivered = progress.get("delivered_files") or []
                    if delivered:
                        context_text += (
                            "上一轮已交付文件（可直接复用，勿重复生成）：\n"
                            + "\n".join(f"- {path}" for path in delivered)
                            + "\n请核对剩余交付物并继续完成。\n"
                        )
                return await sub_agent_tool.execute(
                    context=context,
                    target_mode=payload["target_mode"],
                    goal=payload["goal"],
                    context_str=context_text,
                    task_id=f"{definition['workflow_id']}:{node.task_id}",
                    parent_task_id=str(definition["workflow_id"]),
                    task_contract=payload.get("task_contract"),
                    result_schema=payload.get("result_schema"),
                    max_iterations=node.max_iterations,
                    session_id=retry_session_id,
                    # 结构化修复轮独立于节点重试预算：修复在同会话内进行，
                    # 成本 ~1 分钟且保住全部已有工作，只要带 result_schema 就值得跑满 2 轮。
                    repair_attempts=2 if payload.get("result_schema") else max(0, min(node.max_attempts - 1, 2)),
                    _force_isolated_session=True,
                    _upstream_handles=upstream_handles,
                )

            coordinator = WorkflowCoordinator(
                definition,
                executor=execute_node,
                max_concurrency=max(1, min(int(max_concurrency or 4), 8)),
                snapshot=snapshot,
                persist=lambda current: self._persist_parent_snapshot(context, current),
                completed_results=completed_results,
                journal=workflow_journal,
            )
            await active_workflow_registry.register(
                str(definition["workflow_id"]),
                coordinator,
                session_id=getattr(context, "session_id", None) if context is not None else None,
            )
            try:
                snapshot = await coordinator.run()
            finally:
                await active_workflow_registry.unregister(
                    str(definition["workflow_id"]), coordinator
                )
            pending_persistence = list(getattr(context, "workflow_persistence_tasks", set())) if context is not None else []
            if pending_persistence:
                await asyncio.gather(*pending_persistence, return_exceptions=True)
            succeeded = snapshot["status"] == "succeeded"
            if succeeded:
                # 全部成功后才写缓存：部分失败的结果不污染缓存
                for cached_node in nodes:
                    cached_task_id = str(cached_node.get("task_id") or "")
                    cached_result = snapshot["node_results"].get(cached_task_id)
                    if isinstance(cached_result, Mapping):
                        store_node_result(
                            workflow_id_str,
                            cached_task_id,
                            str(cached_node.get("goal") or ""),
                            str(cached_node.get("target_mode") or ""),
                            cached_result,
                            dependency_hashes={
                                str(dependency): result_fingerprint(
                                    snapshot["node_results"][str(dependency)]
                                )
                                for dependency in (cached_node.get("dependencies") or [])
                                if str(dependency) in snapshot["node_results"]
                            },
                        )
            resources = result_resource_declarations(
                str(snapshot["workflow_id"]),
                snapshot["node_results"],
            )
            result_data = {
                "workflow_id": snapshot["workflow_id"],
                "status": snapshot["status"],
                "node_results": snapshot["node_results"],
                "node_errors": snapshot["node_errors"],
                "node_lineage": snapshot["node_lineage"],
                "snapshot": snapshot,
            }
            return {
                "status": "success" if succeeded else snapshot["status"],
                "success": succeeded,
                "result": "工作流已完成" if succeeded else "工作流未完成",
                "data": result_data,
                "metadata": {
                    "schema_version": "workflow.v1",
                    "generator": "run_agent_workflow",
                    "workflow_id": snapshot["workflow_id"],
                },
                "summary": "工作流执行完成" if succeeded else "工作流执行失败或被取消",
                "resources": resources,
            }
        except (TypeError, ValueError, KeyError) as exc:
            return self._failure(f"工作流定义无效：{exc}")
        except Exception as exc:
            return self._failure(f"工作流执行失败：{exc}")

    @staticmethod
    def _build_sub_agent_tool():
        from app.tools.agent_tools.call_sub_agent import CallSubAgentTool

        return CallSubAgentTool()

    @staticmethod
    def _validate_expert_node_granularity(node: Mapping[str, Any]) -> Optional[str]:
        """Enforce one-question-per-expert-node with a bounded deliverables list.

        提示词约束已被证实不足以阻止集中分配（实测单节点被塞 4-5 个分析问题，
        研判拖到 25+ 轮）：报告 DAG 内的专家节点必须携带 task_contract.deliverables
        （1~MAX_EXPERT_NODE_DELIVERABLES 项），缺失即整单拒绝并指导拆分。
        """
        mode = str(node.get("target_mode") or "")
        if mode not in EXPERT_NODE_MODES:
            return None
        task_id = str(node.get("task_id") or "<unknown>")
        contract = node.get("task_contract")
        if not isinstance(contract, Mapping):
            return (
                f"专家节点 {task_id} 缺少 task_contract：每个专家节点必须且只能回答一个分析问题，"
                f"请在 task_contract 中给出 protocol_version=workflow.v1、question 和 "
                f"deliverables（1~{MAX_EXPERT_NODE_DELIVERABLES} 项）；"
                f"若有多个独立分析问题，必须拆成多个并行 {mode} 节点。"
            )
        deliverables = contract.get("deliverables")
        if deliverables is None:
            return (
                f"专家节点 {task_id} 的 task_contract 缺少 deliverables："
                f"必须列出 1~{MAX_EXPERT_NODE_DELIVERABLES} 项交付物以界定该节点回答的单一分析问题；"
                "多个独立问题请拆成多个并行节点。"
            )
        if not isinstance(deliverables, list):
            return (
                f"节点 {task_id} 的 task_contract.deliverables 必须是数组；"
                "每个专家节点只允许描述一个分析问题。"
            )
        if len(deliverables) == 0:
            return (
                f"节点 {task_id} 的 task_contract.deliverables 为空："
                f"至少给出 1 项交付物；多个独立问题请拆成多个并行 {mode} 节点。"
            )
        if len(deliverables) > MAX_EXPERT_NODE_DELIVERABLES:
            return (
                f"节点 {task_id} 包含 {len(deliverables)} 项交付物，"
                f"超过专家节点上限 {MAX_EXPERT_NODE_DELIVERABLES}；请按独立分析问题拆成多个并行"
                f" {mode} 节点，并用 dependencies 表达真正的先后关系。"
            )
        return None

    @staticmethod
    def _persist_parent_snapshot(context: Optional[Any], snapshot: Mapping[str, Any]) -> None:
        """Keep the coordinator checkpoint with the parent conversation when available."""
        session_id = getattr(context, "session_id", None) if context is not None else None
        if not session_id:
            return
        workflow_id = str(snapshot.get("workflow_id") or "").strip()
        if not workflow_id:
            return
        mode = getattr(context, "runtime_mode", None) if context is not None else None
        persistence_lock = getattr(context, "workflow_persistence_lock", None)
        if persistence_lock is None:
            persistence_lock = asyncio.Lock()
            setattr(context, "workflow_persistence_lock", persistence_lock)

        async def save_async() -> None:
            async with persistence_lock:
                try:
                    # Route through the mode-aware resolver so report/expert sessions
                    # (DB-backed) and social sessions (file-backed) both persist to
                    # the store the read APIs actually consult.
                    from app.agent.session.session_resolver import (
                        load_session_for_mode,
                        save_session_metadata_for_mode,
                    )

                    session = await load_session_for_mode(
                        session_id,
                        mode=mode,
                        include_messages=False,
                    )
                    if session is None:
                        return
                    workflows = dict(session.metadata.get("workflow_coordinators") or {})
                    workflows[workflow_id] = dict(snapshot)
                    session.metadata["workflow_coordinators"] = workflows
                    await save_session_metadata_for_mode(
                        session,
                        mode=mode,
                        update_timestamp=True,
                    )
                    event_sink = getattr(context, "workflow_event_sink", None)
                    if callable(event_sink):
                        event_sink(dict(snapshot))
                except Exception as exc:
                    # Checkpointing must never turn a successfully running node into
                    # a failed node; the coordinator still returns the in-memory
                    # snapshot.
                    logger.warning(
                        "workflow_snapshot_persistence_failed",
                        session_id=session_id,
                        workflow_id=workflow_id,
                        error=str(exc),
                    )
                    return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(save_async())
        pending = getattr(context, "workflow_persistence_tasks", None)
        if pending is None:
            pending = set()
            setattr(context, "workflow_persistence_tasks", pending)
        pending.add(task)
        task.add_done_callback(pending.discard)

    @staticmethod
    def _failure(message: str) -> Dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "result": message,
            "data": {},
            "metadata": {"schema_version": "workflow.v1", "generator": "run_agent_workflow"},
            "summary": message,
        }
