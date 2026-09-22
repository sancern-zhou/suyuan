"""Run a bounded, dependency-aware workflow of cooperating Agents."""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Dict, Mapping, Optional

from app.agent.workflow.coordinator import WorkflowCoordinator, WorkflowNodeSpec
from app.agent.workflow.templates import build_report_analysis_workflow, build_report_delivery_manifest
from app.agent.workflow.registry import active_workflow_registry
from app.tools.base.tool_interface import LLMTool, ToolCategory


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
                "description": (
                    "提交一个有向无环 Agent 工作流。节点可并行执行，只有依赖节点成功后才会执行下游节点。"
                    "适合多源数据分析、交叉验证和分阶段报告任务。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow": {
                            "type": "object",
                            "description": "工作流定义，包含 workflow_id 和 nodes。",
                            "properties": {
                                "workflow_id": {"type": "string"},
                                "version": {"type": "string"},
                                "nodes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "task_id": {"type": "string"},
                                            "target_mode": {"type": "string"},
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
                            "description": "标准模板参数：source_tasks、synthesis_task、delivery_tasks。",
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
                    upstream = (
                        "\n上游节点结构化结果（只使用其中已提供的证据，不要臆造缺失信息）：\n"
                        + json.dumps(dependency_results, ensure_ascii=False, default=str)
                    )
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
            report_delivery = build_report_delivery_manifest(snapshot) if is_report_template else None
            return {
                "status": "success" if succeeded else snapshot["status"],
                "success": succeeded,
                "result": "工作流已完成" if succeeded else "工作流未完成",
                "data": {
                    "workflow_id": snapshot["workflow_id"],
                    "status": snapshot["status"],
                    "node_results": snapshot["node_results"],
                    "node_errors": snapshot["node_errors"],
                    "node_lineage": snapshot["node_lineage"],
                    "report_delivery": report_delivery,
                    "snapshot": snapshot,
                },
                "metadata": {
                    "schema_version": "workflow.v1",
                    "generator": "run_agent_workflow",
                    "workflow_id": snapshot["workflow_id"],
                },
                "summary": "工作流执行完成" if succeeded else "工作流执行失败或被取消",
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
        try:
            from app.agent.session.session_manager import get_session_manager

            manager = get_session_manager()
            session_result = manager.get_session(session_id)

            async def save_async(session_awaitable):
                session = await session_awaitable
                if session is None:
                    return
                workflow_id = str(snapshot.get("workflow_id") or "").strip()
                workflows = dict(session.metadata.get("workflow_coordinators") or {})
                if workflow_id:
                    workflows[workflow_id] = dict(snapshot)
                session.metadata["workflow_coordinators"] = workflows
                session.metadata["workflow_coordinator"] = dict(snapshot)
                saved = manager.save_session_metadata(session, update_timestamp=True)
                if inspect.isawaitable(saved):
                    await saved
                event_sink = getattr(context, "workflow_event_sink", None)
                if callable(event_sink):
                    event_sink(dict(snapshot))

            if inspect.isawaitable(session_result):
                task = asyncio.create_task(save_async(session_result))
                pending = getattr(context, "workflow_persistence_tasks", None)
                if pending is None:
                    pending = set()
                    setattr(context, "workflow_persistence_tasks", pending)
                pending.add(task)
                task.add_done_callback(pending.discard)
            else:
                # File-backed managers are synchronous; execute the same
                # metadata update without forcing an event-loop round trip.
                session = session_result
                if session is None:
                    return
                workflow_id = str(snapshot.get("workflow_id") or "").strip()
                workflows = dict(session.metadata.get("workflow_coordinators") or {})
                if workflow_id:
                    workflows[workflow_id] = dict(snapshot)
                session.metadata["workflow_coordinators"] = workflows
                session.metadata["workflow_coordinator"] = dict(snapshot)
                manager.save_session_metadata(session, update_timestamp=True)
                event_sink = getattr(context, "workflow_event_sink", None)
                if callable(event_sink):
                    event_sink(dict(snapshot))
        except Exception:
            # Checkpointing must never turn a successfully running node into a
            # failed node; the coordinator still returns the in-memory snapshot.
            return

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
