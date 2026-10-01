"""Executable, domain-neutral DAG coordinator for cooperating Agents."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field, replace as dataclasses_replace
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional
import uuid

import structlog

from .graph import WorkflowConcurrencyGovernor, WorkflowGraph
from .lineage import build_node_lineage, validate_node_lineage
from .runtime import TERMINAL_STATUSES, WorkflowRuntime

logger = structlog.get_logger()


NodeExecutor = Callable[["WorkflowNodeSpec", Mapping[str, Any], int], Any]


@dataclass(frozen=True)
class WorkflowNodeSpec:
    """Static definition of one executable node."""

    task_id: str
    dependencies: tuple[str, ...] = ()
    payload: Dict[str, Any] = field(default_factory=dict)
    max_attempts: int = 1
    max_iterations: Optional[int] = None
    timeout_seconds: Optional[float] = None
    phase: Optional[str] = None

    # 重试预算递增：每次重试在原预算上放大 50%（迭代封顶 120、超时封顶 1 小时）。
    # 首次尝试保持调用方设定的紧凑预算；预算耗尽型失败（慢任务被杀）重试时
    # 给更多余量，避免"同预算重试→再失败→累计更久"的浪费模式。
    RETRY_BUDGET_STEP = 0.5
    MAX_ITERATIONS_CAP = 120
    MAX_TIMEOUT_SECONDS_CAP = 3600.0

    def expanded_budget(self, attempt: int) -> "WorkflowNodeSpec":
        """返回第 attempt 次尝试（attempt 从 1 计）使用的预算副本。"""
        if attempt <= 1:
            return self
        factor = 1.0 + self.RETRY_BUDGET_STEP * (attempt - 1)
        kwargs: Dict[str, Any] = {"payload": dict(self.payload)}
        if self.max_iterations is not None:
            scaled_iterations = min(
                self.MAX_ITERATIONS_CAP, max(1, round(self.max_iterations * factor))
            )
            kwargs["max_iterations"] = scaled_iterations
            kwargs["payload"]["max_iterations"] = scaled_iterations
        if self.timeout_seconds is not None:
            kwargs["timeout_seconds"] = min(self.timeout_seconds * factor, self.MAX_TIMEOUT_SECONDS_CAP)
        return dataclasses_replace(self, **kwargs)

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
        for key in ("target_mode", "goal", "context", "task_contract", "result_schema", "require_lineage", "phase"):
            if key in value and key not in payload:
                payload[key] = value[key]
        raw_phase = str(value.get("phase") or "").strip()
        phase = raw_phase or None
        raw_max_iterations = value.get("max_iterations")
        max_iterations = int(raw_max_iterations) if raw_max_iterations is not None else None
        if max_iterations is not None and max_iterations < 1:
            raise ValueError("workflow node max_iterations must be at least 1")
        raw_timeout_seconds = value.get("timeout_seconds")
        timeout_seconds = float(raw_timeout_seconds) if raw_timeout_seconds is not None else None
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("workflow node timeout_seconds must be greater than 0")
        return cls(
            task_id=task_id,
            dependencies=dependencies,
            payload=payload,
            max_attempts=max(1, int(value.get("max_attempts") or 1)),
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
            phase=phase,
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
                    "max_iterations": node.max_iterations,
                    "timeout_seconds": node.timeout_seconds,
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
        completed_results: Optional[Mapping[str, Any]] = None,
        journal: Optional[Any] = None,
    ) -> None:
        self.definition = (
            definition
            if isinstance(definition, WorkflowDefinition)
            else WorkflowDefinition.from_mapping(definition)
        )
        self.executor = executor
        self.persist = persist
        self.journal = journal
        self.graph = WorkflowGraph()
        for node in self.definition.nodes:
            self.graph.add_task(node.task_id)
        for node in self.definition.nodes:
            self.graph.add_task(node.task_id, dependencies=node.dependencies)
        self.node_specs = {node.task_id: node for node in self.definition.nodes}
        self.node_results: Dict[str, Any] = {}
        self.node_sessions: Dict[str, str] = {}
        self.node_errors: Dict[str, str] = {}
        self.node_lineage: Dict[str, Dict[str, Any]] = {}
        self.node_progress: Dict[str, Any] = {}
        self.status = "queued"
        self._persistence_ready = False
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
        self._prepare_snapshot_resume(snapshot)
        # 节点成果缓存复用：注入的节点标记为 succeeded 并构建血缘，
        # run 循环自动跳过（依赖闭包完整性由调用方保证，此处只做血缘校验兜底）。
        for cached_task_id, cached_result in (completed_results or {}).items():
            cached_node = self.node_specs.get(str(cached_task_id))
            if cached_node is None:
                continue
            cached_lineage = build_node_lineage(
                task_id=str(cached_task_id),
                dependency_task_ids=cached_node.dependencies,
                result=cached_result,
            )
            cached_lineage_errors = validate_node_lineage(
                cached_lineage,
                expected_task_id=str(cached_task_id),
                expected_dependencies=cached_node.dependencies,
                require_envelope=bool(cached_node.payload.get("require_lineage")),
            )
            if cached_lineage_errors:
                logger.warning(
                    "workflow_cache_lineage_rejected",
                    task_id=str(cached_task_id),
                    errors=cached_lineage_errors,
                )
                continue
            self.graph.set_status(str(cached_task_id), "succeeded")
            self.node_results[str(cached_task_id)] = cached_result
            self.node_lineage[str(cached_task_id)] = cached_lineage
            cached_run = self.runtime.find_run(task_id=str(cached_task_id))
            if cached_run is not None:
                self.runtime.start(cached_run.run_id)
                self.runtime.transition(cached_run.run_id, "succeeded")
            logger.info("workflow_cache_node_reused", task_id=str(cached_task_id))
        self._persistence_ready = True

    def _journal_event(self, event_type: str, task_id: Optional[str] = None, **payload: Any) -> None:
        """事件落 SQLite journal；fail-soft，不影响执行。"""
        if self.journal is None:
            return
        try:
            self.journal.append(
                workflow_id=str(self.definition.workflow_id),
                event_type=event_type,
                task_id=task_id,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("workflow_journal_append_failed", event_type=event_type, error=str(exc))

    async def run(self) -> Dict[str, Any]:
        if self.status == "succeeded":
            return self.snapshot()
        self.status = "running"
        self.runtime.start(self.workflow_run.run_id)
        self._journal_event("workflow.started")
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
                self._journal_event("workflow.succeeded")
                break
            if any(node.status == "failed" for node in self._graph_nodes()):
                self.status = "failed"
                self.runtime.transition(self.workflow_run.run_id, "failed", payload={"node_errors": dict(self.node_errors)})
                self._journal_event(
                    "workflow.failed",
                    node_errors={k: str(v)[:200] for k, v in self.node_errors.items()},
                    progress={k: v for k, v in self.node_progress.items()},
                )
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
            "node_sessions": dict(self.node_sessions),
            "node_errors": dict(self.node_errors),
            "node_progress": dict(self.node_progress),
            "node_lineage": dict(self.node_lineage),
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
        self._journal_event(
            "node.started",
            task_id=task_id,
            attempt=node_run.attempt,
            target_mode=node.payload.get("target_mode"),
            phase=node.payload.get("phase"),
            goal=str(node.payload.get("goal") or "")[:200],
        )
        dependency_results = {dependency: self.node_results.get(dependency) for dependency in node.dependencies}
        # 预算耗尽型失败重试时放宽迭代/超时预算（首试保持调用方原设定）
        attempt = max(1, int(node_run.attempt or 1))
        effective_node = node.expanded_budget(attempt)
        if attempt > 1 and effective_node is not node:
            logger.info(
                "workflow_retry_budget_expanded",
                task_id=task_id,
                attempt=attempt,
                max_iterations=effective_node.max_iterations,
                timeout_seconds=effective_node.timeout_seconds,
            )
            self._journal_event(
                "node.retry_budget_expanded",
                task_id=task_id,
                attempt=attempt,
                max_iterations=effective_node.max_iterations,
                timeout_seconds=effective_node.timeout_seconds,
            )
        # 重试续用上次的子会话：带上失败原因与已交付进度，子 Agent 在已有工作基础上修正
        retry_context = None
        if attempt > 1:
            previous_error = self.node_errors.get(task_id)
            retry_context = {
                "session_id": self.node_sessions.get(task_id),
                "error": previous_error,
                "progress": self.node_progress.get(task_id),
            }
            logger.info(
                "workflow_retry_reuses_child_session",
                task_id=task_id,
                attempt=attempt,
                previous_session_id=retry_context["session_id"],
                previous_error=str(previous_error)[:200] if previous_error else None,
            )
        try:
            async with self.governor:
                async def execute_node() -> Any:
                    result = self.executor(
                        effective_node, dependency_results, node_run.attempt, retry_context
                    )
                    if inspect.isawaitable(result):
                        return await result
                    return result

                if effective_node.timeout_seconds is None:
                    result = await execute_node()
                else:
                    async with asyncio.timeout(effective_node.timeout_seconds):
                        result = await execute_node()
            metadata = result.get("metadata") if isinstance(result, dict) else None
            child_session_id = metadata.get("session_id") if isinstance(metadata, dict) else None
            if isinstance(child_session_id, str) and child_session_id:
                self.node_sessions[task_id] = child_session_id
            # 进度流水账：已交付文件清单（失败也保留，供重试"接着干"）
            if isinstance(result, dict) and isinstance(result.get("data"), Mapping):
                delivered = [
                    str(path)
                    for path in (result["data"].get("file_paths") or [])
                ][:20]
                if delivered:
                    self.node_progress[task_id] = {"delivered_files": delivered}
            if self._result_failed(result):
                raise RuntimeError(self._result_error(result))
            self.node_results[task_id] = result
            lineage = build_node_lineage(
                task_id=task_id,
                dependency_task_ids=node.dependencies,
                result=result,
            )
            lineage_errors = validate_node_lineage(
                lineage,
                expected_task_id=task_id,
                expected_dependencies=node.dependencies,
                require_envelope=bool(node.payload.get("require_lineage")),
            )
            if lineage_errors:
                self.node_results.pop(task_id, None)
                raise RuntimeError(f"node lineage validation failed: {lineage_errors}")
            self.node_lineage[task_id] = lineage
            self.graph.set_status(task_id, "succeeded")
            self.runtime.transition(node_run.run_id, "succeeded")
            self._journal_event(
                "node.succeeded",
                task_id=task_id,
                attempt=node_run.attempt,
                delivered_files=(self.node_progress.get(task_id) or {}).get("delivered_files"),
            )
        except asyncio.CancelledError:
            self.graph.set_status(task_id, "cancelled")
            self.runtime.request_cancel(node_run.run_id, reason=self.cancel_reason or "workflow cancelled")
            raise
        except Exception as exc:
            error = (
                f"workflow node timed out after {effective_node.timeout_seconds:g}s"
                if isinstance(exc, TimeoutError) and effective_node.timeout_seconds is not None
                else str(exc)
            )
            self.node_errors[task_id] = error
            self.runtime.transition(node_run.run_id, "failed", payload={"error": error})
            retrying = node_run.attempt < node_run.max_attempts
            self._journal_event(
                "node.failed",
                task_id=task_id,
                attempt=node_run.attempt,
                error=error[:500],
                retrying=retrying,
                progress=self.node_progress.get(task_id),
            )
            if retrying:
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
        self.node_sessions = dict(snapshot.get("node_sessions") or {})
        self.node_errors = {str(key): str(value) for key, value in (snapshot.get("node_errors") or {}).items()}
        self.node_progress = dict(snapshot.get("node_progress") or {})
        self.node_lineage = {
            str(key): dict(value)
            for key, value in (snapshot.get("node_lineage") or {}).items()
            if isinstance(value, Mapping)
        }
        graph_snapshot = snapshot.get("graph")
        if isinstance(graph_snapshot, Mapping):
            self.graph = WorkflowGraph.from_snapshot(graph_snapshot)
            for node in self._graph_nodes():
                if node.status in {"running", "waiting", "repairing"}:
                    node.status = "pending"

    def _prepare_snapshot_resume(self, snapshot: Mapping[str, Any]) -> None:
        """Normalize a failed snapshot before scheduling retryable nodes."""
        if not snapshot or self.cancel_requested or self.status == "cancelled":
            return
        runtime_runs = self.runtime.snapshot().get("runs") or {}
        for node in self._graph_nodes():
            if node.status != "failed":
                continue
            run = runtime_runs.get(self._node_run_id(node.task_id, snapshot)) or {}
            if int(run.get("attempt") or 0) < int(
                run.get("max_attempts") or self.node_specs[node.task_id].max_attempts
            ):
                node.status = "pending"
        if self.status == "failed" and any(node.status == "pending" for node in self._graph_nodes()):
            # Older snapshots created the parent with one attempt. Allow one
            # explicit resume while preserving per-node retry budgets.
            self.workflow_run.max_attempts = max(self.workflow_run.max_attempts, 2)
            self.status = "queued"

    def _persist_snapshot(self, _runtime_snapshot: Dict[str, Any]) -> None:
        """Persist one complete coordinator snapshot.

        ``WorkflowRuntime`` calls this hook with its runtime-only snapshot.
        The session/API contract stores the coordinator envelope, so rebuild it
        here instead of allowing a runtime fragment to overwrite the index.
        During construction the graph/runtime are still being assembled; the
        first coordinator snapshot is emitted when ``run`` starts.
        """
        if self.persist and self._persistence_ready:
            self.persist(self.snapshot())

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
