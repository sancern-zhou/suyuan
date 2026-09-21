"""Executable, domain-neutral DAG coordinator for cooperating Agents."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional
import uuid

from .graph import WorkflowConcurrencyGovernor, WorkflowGraph
from .runtime import TERMINAL_STATUSES, WorkflowRuntime


NodeExecutor = Callable[["WorkflowNodeSpec", Mapping[str, Any], int], Any]


@dataclass(frozen=True)
class WorkflowNodeSpec:
    """Static definition of one executable node."""

    task_id: str
    dependencies: tuple[str, ...] = ()
    payload: Dict[str, Any] = field(default_factory=dict)
    max_attempts: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "WorkflowNodeSpec":
        task_id = str(value.get("task_id") or value.get("node_id") or "").strip()
        if not task_id:
            raise ValueError("workflow node task_id is required")
        dependencies = tuple(
            str(item).strip()
            for item in value.get("dependencies") or []
            if str(item).strip()
        )
        payload = dict(value.get("payload") or {})
        # Allow concise node definitions while keeping the coordinator's
        # execution contract stable.
        for key in ("target_mode", "goal", "context", "task_contract", "result_schema"):
            if key in value and key not in payload:
                payload[key] = value[key]
        return cls(
            task_id=task_id,
            dependencies=dependencies,
            payload=payload,
            max_attempts=max(1, int(value.get("max_attempts") or 1)),
        )


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    nodes: tuple[WorkflowNodeSpec, ...]
    version: str = "1"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "WorkflowDefinition":
        workflow_id = str(value.get("workflow_id") or value.get("id") or "").strip()
        if not workflow_id:
            raise ValueError("workflow_id is required")
        nodes = tuple(WorkflowNodeSpec.from_mapping(item) for item in value.get("nodes") or [])
        if not nodes:
            raise ValueError("workflow must contain at least one node")
        ids = [node.task_id for node in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("workflow node task_id values must be unique")
        graph = WorkflowGraph()
        for node in nodes:
            graph.add_task(node.task_id)
        for node in nodes:
            graph.add_task(node.task_id, dependencies=node.dependencies)
        return cls(workflow_id=workflow_id, nodes=nodes, version=str(value.get("version") or "1"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "version": self.version,
            "nodes": [
                {
                    "task_id": node.task_id,
                    "dependencies": list(node.dependencies),
                    "payload": dict(node.payload),
                    "max_attempts": node.max_attempts,
                }
                for node in self.nodes
            ],
        }


class WorkflowCoordinator:
    """Run a static DAG with bounded concurrency and resumable state."""

    def __init__(
        self,
        definition: WorkflowDefinition | Mapping[str, Any],
        *,
        executor: NodeExecutor,
        max_concurrency: int = 4,
        snapshot: Optional[Mapping[str, Any]] = None,
        persist: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.definition = (
            definition
            if isinstance(definition, WorkflowDefinition)
            else WorkflowDefinition.from_mapping(definition)
        )
        self.executor = executor
        self.persist = persist
        self.graph = WorkflowGraph()
        for node in self.definition.nodes:
            self.graph.add_task(node.task_id)
        for node in self.definition.nodes:
            self.graph.add_task(node.task_id, dependencies=node.dependencies)
        self.node_specs = {node.task_id: node for node in self.definition.nodes}
        self.node_results: Dict[str, Any] = {}
        self.node_errors: Dict[str, str] = {}
        self.status = "queued"
        self.cancel_requested = False
        self.cancel_reason = ""
        self._active_tasks: Dict[str, asyncio.Task] = {}
        snapshot = snapshot or {}
        self._restore(snapshot)
        self.governor = WorkflowConcurrencyGovernor(max_concurrency)
        self.runtime = WorkflowRuntime(
            snapshot=snapshot.get("runtime") if isinstance(snapshot, Mapping) else None,
            persist=self._persist_snapshot,
        )
        self.workflow_run = self.runtime.create_run(
            task_id=self.definition.workflow_id,
            run_id=(snapshot.get("workflow_run_id") if isinstance(snapshot, Mapping) else None),
        )
        for node in self.definition.nodes:
            node_run = self.runtime.create_run(
                task_id=node.task_id,
                parent_task_id=self.definition.workflow_id,
                run_id=self._node_run_id(node.task_id, snapshot),
                max_attempts=node.max_attempts,
            )
            self.runtime.register_child(self.workflow_run.run_id, node.task_id)
            if node_run.status in {"succeeded", "failed", "cancelled"}:
                self.graph.set_status(node.task_id, node_run.status)

    async def run(self) -> Dict[str, Any]:
        if self.status == "succeeded":
            return self.snapshot()
        self.status = "running"
        self.runtime.start(self.workflow_run.run_id)
        self._persist_snapshot(self.snapshot())

        while True:
            if self.cancel_requested:
                await self.cancel(reason=self.cancel_reason or "workflow cancelled")
                break
            ready = [task_id for task_id in self.graph.ready_tasks() if task_id not in self._active_tasks]
            for task_id in ready:
                self._active_tasks[task_id] = asyncio.create_task(self._run_node(task_id))
            if self._active_tasks:
                completed, _ = await asyncio.wait(
                    tuple(self._active_tasks.values()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in completed:
                    task_id = next(key for key, value in self._active_tasks.items() if value is task)
                    self._active_tasks.pop(task_id, None)
                    try:
                        await task
                    except asyncio.CancelledError:
                        if not self.cancel_requested:
                            raise
                continue
            if all(node.status == "succeeded" for node in self._graph_nodes()):
                self.status = "succeeded"
                self.runtime.transition(self.workflow_run.run_id, "succeeded")
                break
            if any(node.status == "failed" for node in self._graph_nodes()):
                self.status = "failed"
                self.runtime.transition(self.workflow_run.run_id, "failed", payload={"node_errors": dict(self.node_errors)})
                self._cancel_pending("dependency failed")
                break
            # A pending graph with no active or ready nodes is inconsistent.
            self.status = "failed"
            self.node_errors["__workflow__"] = "workflow has no runnable nodes"
            self.runtime.transition(self.workflow_run.run_id, "failed", payload={"error": self.node_errors["__workflow__"]})
            break

        self._persist_snapshot(self.snapshot())
        return self.snapshot()

    async def cancel(self, *, reason: str = "workflow cancelled") -> Dict[str, Any]:
        self.cancel_requested = True
        self.cancel_reason = reason
        for task in self._active_tasks.values():
            task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)
            self._active_tasks.clear()
        self.runtime.request_cancel(self.workflow_run.run_id, reason=reason)
        self._cancel_pending(reason)
        self.status = "cancelled"
        self._persist_snapshot(self.snapshot())
        return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "workflow_id": self.definition.workflow_id,
            "definition": self.definition.to_dict(),
            "status": self.status,
            "cancel_requested": self.cancel_requested,
            "cancel_reason": self.cancel_reason,
            "graph": self.graph.snapshot(),
            "node_results": dict(self.node_results),
            "node_errors": dict(self.node_errors),
            "workflow_run_id": self.workflow_run.run_id if hasattr(self, "workflow_run") else None,
            "runtime": self.runtime.snapshot() if hasattr(self, "runtime") else {},
        }

    async def _run_node(self, task_id: str) -> None:
        node = self.node_specs[task_id]
        node_run = self.runtime.find_run(task_id=task_id)
        if node_run is None:
            raise RuntimeError(f"workflow runtime missing node run: {task_id}")
        self.graph.set_status(task_id, "running")
        self.runtime.start(node_run.run_id)
        dependency_results = {dependency: self.node_results.get(dependency) for dependency in node.dependencies}
        try:
            async with self.governor:
                result = self.executor(node, dependency_results, node_run.attempt)
                if inspect.isawaitable(result):
                    result = await result
            if self._result_failed(result):
                raise RuntimeError(self._result_error(result))
            self.node_results[task_id] = result
            self.graph.set_status(task_id, "succeeded")
            self.runtime.transition(node_run.run_id, "succeeded")
        except asyncio.CancelledError:
            self.graph.set_status(task_id, "cancelled")
            self.runtime.request_cancel(node_run.run_id, reason=self.cancel_reason or "workflow cancelled")
            raise
        except Exception as exc:
            self.node_errors[task_id] = str(exc)
            self.runtime.transition(node_run.run_id, "failed", payload={"error": str(exc)})
            if node_run.attempt < node_run.max_attempts:
                self.graph.set_status(task_id, "pending")
                self.runtime.start(node_run.run_id)
            else:
                self.graph.set_status(task_id, "failed")

    def _restore(self, snapshot: Mapping[str, Any]) -> None:
        if not snapshot:
            return
        if snapshot.get("workflow_id") and snapshot.get("workflow_id") != self.definition.workflow_id:
            raise ValueError("workflow snapshot does not match workflow definition")
        self.status = str(snapshot.get("status") or "queued")
        self.cancel_requested = bool(snapshot.get("cancel_requested"))
        self.cancel_reason = str(snapshot.get("cancel_reason") or "")
        self.node_results = dict(snapshot.get("node_results") or {})
        self.node_errors = {str(key): str(value) for key, value in (snapshot.get("node_errors") or {}).items()}
        graph_snapshot = snapshot.get("graph")
        if isinstance(graph_snapshot, Mapping):
            self.graph = WorkflowGraph.from_snapshot(graph_snapshot)
            for node in self._graph_nodes():
                if node.status in {"running", "waiting", "repairing"}:
                    node.status = "pending"

    def _persist_snapshot(self, snapshot: Dict[str, Any]) -> None:
        if self.persist:
            self.persist(snapshot)

    def _graph_nodes(self):
        return [self.graph._nodes[node.task_id] for node in self.definition.nodes]

    def _cancel_pending(self, reason: str) -> None:
        for node in self._graph_nodes():
            if node.status == "pending":
                node.status = "cancelled"
                self.node_errors.setdefault(node.task_id, reason)

    def _node_run_id(self, task_id: str, snapshot: Mapping[str, Any]) -> str:
        runs = ((snapshot.get("runtime") or {}).get("runs") or {}) if isinstance(snapshot, Mapping) else {}
        for run_id, value in runs.items():
            if isinstance(value, Mapping) and value.get("task_id") == task_id:
                return str(run_id)
        return f"{self.definition.workflow_id}:{task_id}"

    @staticmethod
    def _result_failed(result: Any) -> bool:
        if not isinstance(result, Mapping):
            return False
        if result.get("success") is False:
            return True
        return str(result.get("status") or "").lower() in {"failed", "error", "cancelled", "invalid_result"}

    @staticmethod
    def _result_error(result: Any) -> str:
        if isinstance(result, Mapping):
            return str(result.get("error") or result.get("summary") or result.get("result") or "node execution failed")
        return "node execution failed"
