"""Run a bounded, dependency-aware workflow of cooperating Agents."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Mapping, Optional

import structlog

from app.agent.workflow.resource_handoff import result_resource_declarations
from app.agent.workflow.target_mode_contract import build_target_mode_contract, target_mode_values
from app.agent.workflow.coordinator import WorkflowCoordinator, WorkflowNodeSpec
from app.agent.workflow.templates import build_report_analysis_manifest, build_report_analysis_workflow
from app.agent.workflow.registry import active_workflow_registry
from app.tools.base.tool_interface import LLMTool, ToolCategory


logger = structlog.get_logger(__name__)


REPORT_TEMPLATE_EXAMPLE = (
    '{"workflow_template": "report_analysis_v1", "max_concurrency": 4, "template_options": {'
    '"workflow_id": "air-quality-report", '
    '"source_tasks": ['
    '{"task_id": "air-data", "target_mode": "query", "goal": "查询指定区域和时间范围的空气质量数据"}, '
    '{"task_id": "weather-data", "target_mode": "expert", "goal": "分析同期气象条件及其影响"}], '
    '"synthesis_task": {"task_id": "synthesis", "target_mode": "expert", '
    '"goal": "基于上游结果完成交叉分析，输出报告提纲、结论、证据和缺口"}}}'
)

WORKFLOW_SCHEMA_DESCRIPTION = (
    "提交一个有向无环 Agent 工作流（DAG）：节点可并行执行，只有依赖节点成功后才会执行下游节点；"
    "适合多源数据分析、交叉验证和分阶段报告任务。"
    "报告任务使用 workflow_template='report_analysis_v1'，并在 template_options 中提供 "
    "source_tasks（无依赖的 query/expert 节点，并行执行）、synthesis_task（有依赖的 expert 节点，等待全部上游成功并输出报告就绪简报）。"
    "报告 DAG 禁止 report 子节点；父报告 Agent 是唯一成稿者。模板只向父 Agent 返回状态、节点错误和精简的 report_analysis，"
    "完整快照在服务端留存，避免父 Agent 对子节点结果做重复全量复核。每个节点必须有唯一 task_id、target_mode、goal，"
    "goal 写清时间范围、区域、指标口径和预期输出；多源任务把无依赖查询拆成独立 source 节点以并行执行，"
    "有依赖关系的节点用 dependencies 表达，不靠文字约定顺序。"
    "expert 节点必须提供 task_contract（protocol_version=workflow.v1、task_type=expert_analysis、question、"
    "decision_context、scope、required_evidence、deliverables）和 result_schema（要求 status、findings、evidence、"
    "uncertainties、data_gaps，finding 通过 evidence id 回溯证据）；节点可用 max_attempts 设置重试次数（1-3）。"
    f"示例：{REPORT_TEMPLATE_EXAMPLE}\n\n"
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
                                "完整 DAG 定义：{workflow_id, version, nodes:[{task_id, target_mode, goal, context, "
                                "dependencies, task_contract, result_schema, max_attempts}]}。与 workflow_template 二选一。"
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
                                        },
                                        "required": ["task_id", "target_mode", "goal"],
                                    },
                                },
                            },
                            "required": ["workflow_id", "nodes"],
                        },
                        "workflow_template": {
                            "type": "string",
                            "enum": ["report_analysis_v1"],
                            "description": "可选标准模板；选择 report_analysis_v1 时使用 template_options 构建报告 DAG。",
                        },
                        "template_options": {
                            "type": "object",
                            "description": (
                                "report_analysis_v1 的模板参数：{source_tasks:[...], synthesis_task:{...]}；"
                                "不接受 delivery_tasks，结构与示例见工具说明。"
                            ),
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
                    "required": [],
                },
            },
            version="1.0.0",
        )

    async def execute(
        self,
        context: Optional[Any] = None,
        workflow: Optional[Mapping[str, Any]] = None,
        workflow_template: Optional[str] = None,
        template_options: Optional[Mapping[str, Any]] = None,
        max_concurrency: int = 4,
        snapshot: Optional[Mapping[str, Any]] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        is_report_template = workflow_template == "report_analysis_v1"
        if not isinstance(workflow, Mapping):
            if workflow_template != "report_analysis_v1" or not isinstance(template_options, Mapping):
                return self._failure("请提供 workflow 定义，或使用 report_analysis_v1 模板及 template_options")
            try:
                workflow = build_report_analysis_workflow(
                    workflow_id=str(template_options.get("workflow_id") or "report-workflow"),
                    source_tasks=template_options.get("source_tasks") or [],
                    synthesis_task=template_options.get("synthesis_task") or {},
                    delivery_tasks=template_options.get("delivery_tasks") or [],
                )
            except (TypeError, ValueError) as exc:
                return self._failure(f"报告工作流模板参数无效：{exc}")
        try:
            definition = dict(workflow)
            nodes = [dict(node) for node in definition.get("nodes") or []]
            for node in nodes:
                if not node.get("target_mode") or not node.get("goal"):
                    return self._failure(f"节点 {node.get('task_id') or '<unknown>'} 缺少 target_mode 或 goal")
            definition["nodes"] = nodes
            sub_agent_tool = self._build_sub_agent_tool()

            async def execute_node(node: WorkflowNodeSpec, dependency_results: Mapping[str, Any], attempt: int):
                payload = node.payload
                upstream = ""
                if dependency_results:
                    upstream_handles = [
                        handle
                        for task_id, result in dependency_results.items()
                        for handle in collect_result_handles(task_id, result)
                    ]
                    upstream = format_upstream_handles(dependency_results)
                    upstream += (
                        "\n上游节点结构化结果（只使用其中已提供的证据，不要臆造缺失信息）：\n"
                        + json.dumps(dependency_results, ensure_ascii=False, default=str)
                    )
                else:
                    upstream_handles = []
                context_text = str(payload.get("context") or "") + upstream
                return await sub_agent_tool.execute(
                    context=context,
                    target_mode=payload["target_mode"],
                    goal=payload["goal"],
                    context_str=context_text,
                    task_id=f"{definition['workflow_id']}:{node.task_id}",
                    parent_task_id=str(definition["workflow_id"]),
                    task_contract=payload.get("task_contract"),
                    result_schema=payload.get("result_schema"),
                    # A coordinator node always emits a lineage manifest.  The
                    # template can opt into strict result-envelope checking.
                    repair_attempts=max(0, min(node.max_attempts - 1, 2)),
                    _force_isolated_session=True,
                    _upstream_handles=upstream_handles,
                )

            coordinator = WorkflowCoordinator(
                definition,
                executor=execute_node,
                max_concurrency=max(1, min(int(max_concurrency or 4), 8)),
                snapshot=snapshot,
                persist=lambda current: self._persist_parent_snapshot(context, current),
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
            report_analysis = build_report_analysis_manifest(snapshot) if is_report_template else None
            resources = result_resource_declarations(
                str(snapshot["workflow_id"]),
                snapshot["node_results"],
            )
            if is_report_template:
                result_data = {
                    "workflow_id": snapshot["workflow_id"],
                    "status": snapshot["status"],
                    "node_errors": snapshot["node_errors"],
                    "report_analysis": report_analysis,
                }
            else:
                result_data = {
                    "workflow_id": snapshot["workflow_id"],
                    "status": snapshot["status"],
                    "node_results": snapshot["node_results"],
                    "node_errors": snapshot["node_errors"],
                    "node_lineage": snapshot["node_lineage"],
                    "report_analysis": report_analysis,
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
