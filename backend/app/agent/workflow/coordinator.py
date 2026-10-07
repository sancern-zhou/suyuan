"""Executable, domain-neutral DAG coordinator for cooperating Agents."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import random
import math
import time
from dataclasses import dataclass, field, replace as dataclasses_replace
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional
import uuid

import structlog

from .graph import WorkflowConcurrencyGovernor, WorkflowGraph
from .lineage import build_node_lineage, validate_node_lineage
from .runtime import TERMINAL_STATUSES, WorkflowRuntime
from .routing import validate_condition, evaluate_condition
from .resource_contract import ResourceContractError, validate_contract_definition, assert_resource_contracts, check_resource_contracts, result_handles

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
    required: bool = True
    dependency_policy: str = "all_success"
    when: Optional[Dict[str, Any]] = None
    input_contracts: tuple[Dict[str, Any], ...] = ()
    output_contract: Optional[Dict[str, Any]] = None

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
                self.MAX_ITERATIONS_CAP, self.payload.get("iteration_cap", self.MAX_ITERATIONS_CAP),
                max(1, round(self.max_iterations * factor))
            )
            kwargs["max_iterations"] = scaled_iterations
            kwargs["payload"]["max_iterations"] = scaled_iterations
        if self.timeout_seconds is not None:
            kwargs["timeout_seconds"] = min(self.timeout_seconds * factor, self.MAX_TIMEOUT_SECONDS_CAP,
                                           self.payload.get("timeout_cap", self.MAX_TIMEOUT_SECONDS_CAP))
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
        for key in ("target_mode", "goal", "context", "task_contract", "result_schema", "require_lineage", "phase", "iteration_cap", "timeout_cap"):
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
        required = value.get("required", True)
        if not isinstance(required, bool):
            raise ValueError("workflow node required must be boolean")
        policy = value.get("dependency_policy", "all_success")
        if policy not in {"all_success", "allow_partial"}:
            raise ValueError("invalid workflow dependency_policy")
        when = value.get("when")
        if when is not None:
            validate_condition(when, dependencies)
        contracts = value.get("input_contracts") or []
        if not isinstance(contracts, list):
            raise ValueError("input_contracts must be a list")
        for contract in contracts:
            validate_contract_definition(contract, dependencies)
        output_contract = value.get("output_contract")
        if output_contract is not None:
            validate_contract_definition(output_contract)
        return cls(
            task_id=task_id,
            dependencies=dependencies,
            payload=payload,
            # 默认允许一次自动重试：重试续用子会话 + 预算扩容 + 失败原因反馈，
            # 成本远低于失败后由主 Agent 从头重提整个工作流。
            max_attempts=max(1, int(value.get("max_attempts") or 2)),
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
            phase=phase,
            required=required,
            dependency_policy=policy,
            when=dict(when) if when is not None else None,
            input_contracts=tuple(dict(contract) for contract in contracts),
            output_contract=dict(output_contract) if output_contract is not None else None,
        )


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    nodes: tuple[WorkflowNodeSpec, ...]
    version: str = "1"
    budget: Dict[str, Any] = field(default_factory=dict)

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
        budget = dict(value.get("budget") or {})
        defaults = {"max_nodes": 32, "max_extensions": 3, "max_retries": 16, "timeout_seconds": 3600.0}
        if set(budget) - set(defaults):
            raise ValueError("unknown workflow budget field")
        for key, raw in budget.items():
            number = float(raw)
            if not math.isfinite(number) or number < (0 if key in {"max_extensions", "max_retries", "timeout_seconds"} else 1) or (key == "timeout_seconds" and number == 0):
                raise ValueError(f"invalid workflow budget: {key}")
            if key != "timeout_seconds" and number != int(number):
                raise ValueError(f"workflow budget {key} must be an integer")
            budget[key] = number if key == "timeout_seconds" else int(number)
        if len(nodes) > budget.get("max_nodes", defaults["max_nodes"]):
            raise ValueError("workflow node budget exceeded")
        return cls(workflow_id=workflow_id, nodes=nodes, version=str(value.get("version") or "1"), budget=budget)

    def to_dict(self) -> Dict[str, Any]:
        result = {
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
                    **({"required": False} if not node.required else {}),
                    **({"dependency_policy": node.dependency_policy} if node.dependency_policy != "all_success" else {}),
                    **({"when": node.when} if node.when is not None else {}),
                    **({"input_contracts": list(node.input_contracts)} if node.input_contracts else {}),
                    **({"output_contract": node.output_contract} if node.output_contract is not None else {}),
                }
                for node in self.nodes
            ],
        }
        # Preserve fingerprints of existing definitions/checkpoints.
        if self.budget:
            result["budget"] = dict(self.budget)
        return result

    def fingerprint(self) -> str:
        serialized = json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]


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
        self.definition_hash = self.definition.fingerprint()
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
        self.node_input_hashes: Dict[str, str] = {}
        self.node_decisions: Dict[str, Dict[str, Any]] = {}
        self.node_input_gaps: Dict[str, List[Dict[str, Any]]] = {}
        self.node_contract_errors: Dict[str, List[Dict[str, Any]]] = {}
        self.node_retryable: Dict[str, bool] = {}
        self.status = "queued"
        self._persistence_ready = False
        self.cancel_requested = False
        self.cancel_reason = ""
        self._active_tasks: Dict[str, asyncio.Task] = {}
        snapshot = snapshot or {}
        self.revision = int(snapshot.get("revision") or 0)
        self.budget_state = dict(snapshot.get("budget_state") or {})
        self._run_started: Optional[float] = None
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
        cache_candidates = dict(completed_results or {})
        changed = True
        while changed:
            changed = False
            for task_id, result in list(cache_candidates.items()):
                spec = self.node_specs.get(task_id)
                if spec is None:
                    cache_candidates.pop(task_id)
                    changed = True
                    continue
                available = {**self.node_results, **cache_candidates}
                try:
                    if any(dep not in available for dep in spec.dependencies):
                        raise ValueError("cached dependency unavailable")
                    inputs = [handle for dep in spec.dependencies for handle in result_handles(dep, available[dep])]
                    if check_resource_contracts(list(spec.input_contracts), inputs):
                        raise ValueError("cached input resource unavailable or incompatible")
                    if spec.output_contract is not None:
                        if check_resource_contracts([spec.output_contract], result_handles(task_id, result)):
                            raise ValueError("cached output resource unavailable or incompatible")
                except ValueError:
                    cache_candidates.pop(task_id)
                    changed = True
        for cached_task_id, cached_result in cache_candidates.items():
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
            try:
                if cached_node.output_contract is not None:
                    assert_resource_contracts([cached_node.output_contract], result_handles(str(cached_task_id), cached_result))
            except ValueError:
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
        if self.budget_state.get("exhausted"):
            return self.snapshot()
        self._run_started = time.monotonic()
        try:
            remaining = self.definition.budget.get("timeout_seconds", 3600.0) - float(self.budget_state.get("elapsed_seconds", 0))
            async with asyncio.timeout(max(0, remaining)):
                await self._run()
        except TimeoutError:
            self.budget_state["exhausted"] = "timeout_seconds"
            self.node_errors["__budget__"] = "workflow total active time budget exceeded"
            self.status = "failed"
            if self.workflow_run.status not in TERMINAL_STATUSES:
                self.runtime.transition(self.workflow_run.run_id, "failed", payload={"error": self.node_errors["__budget__"]})
            self._journal_event("workflow.budget_exhausted", limit="timeout_seconds")
        finally:
            # Parent request cancellation must not leave child tasks running.
            for task in self._active_tasks.values():
                task.cancel()
            if self._active_tasks:
                await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)
                self._active_tasks.clear()
            self.budget_state["elapsed_seconds"] = self._elapsed_seconds()
            self._run_started = None
            if self.budget_state.get("exhausted"):
                self._block_pending(self.node_errors.get("__budget__", "workflow budget exhausted"))
            try:
                self._persist_snapshot({})
            except Exception as exc:
                logger.error("workflow_final_persist_failed", error=str(exc))
        return self.snapshot()

    def _elapsed_seconds(self) -> float:
        return float(self.budget_state.get("elapsed_seconds", 0)) + (
            time.monotonic() - self._run_started if self._run_started is not None else 0
        )

    def delivery(self) -> Dict[str, Any]:
        gaps = [{"task_id": node.task_id, "required": self.node_specs[node.task_id].required,
                 "status": node.status, "reason": self.node_errors.get(node.task_id, "upstream unavailable")}
                for node in self._graph_nodes() if node.status in {"failed", "blocked"}]
        gaps += [{"task_id": task_id, "required": False, "status": "resource_gap", "reason": str(item["details"])}
                 for task_id, errors in self.node_contract_errors.items() for item in errors if not item.get("required", True)]
        retryable = [node.task_id for node in self._graph_nodes() if node.status == "failed"
                     and (run := self.runtime.find_run(task_id=node.task_id)) is not None
                     and run.attempt < run.max_attempts and self.node_retryable.get(node.task_id, True)] if hasattr(self, "runtime") and not self.budget_state.get("exhausted") else []
        return {"deliverable": self.status in {"succeeded", "partial"}, "complete": self.status == "succeeded",
                "available_nodes": sorted(self.node_results), "gaps": gaps,
                "skipped_nodes": [node.task_id for node in self._graph_nodes() if node.status == "skipped"],
                "retryable_nodes": retryable,
                "next_actions": (["deliver_with_gaps", "extend_missing_evidence"] if self.status == "partial" else
                                 ["repair_required_evidence"] if self.status == "failed" else []) +
                                (["resume_remaining_attempts"] if retryable else [])}

    def _ready_tasks(self) -> List[str]:
        """Resolve settled edges before scheduling, including unselected branches."""
        changed = True
        while changed:
            changed = False
            for task_id, spec in self.node_specs.items():
                node = self.graph._nodes[task_id]
                if node.status != "pending" or task_id in self._active_tasks:
                    continue
                states = {dep: self.graph._nodes[dep].status for dep in spec.dependencies}
                if any(status not in {"succeeded", "failed", "blocked", "skipped", "cancelled"} for status in states.values()):
                    continue
                unavailable = {dep: status for dep, status in states.items() if status != "succeeded"}
                skip_reason = None
                block_reason = None
                if spec.dependency_policy == "all_success":
                    if any(status in {"failed", "blocked", "cancelled"} for status in unavailable.values()):
                        block_reason = "dependency failed"
                    elif unavailable:
                        skip_reason = "upstream branch was not selected"
                elif states and not any(status == "succeeded" for status in states.values()):
                    if all(status == "skipped" for status in states.values()):
                        skip_reason = "all upstream branches were not selected"
                    else:
                        block_reason = "no successful upstream evidence"
                if block_reason:
                    node.status = "blocked"
                    self.node_errors[task_id] = block_reason
                    self._journal_event("node.blocked", task_id=task_id, dependencies=unavailable)
                    changed = True
                    continue
                if skip_reason is None and spec.when is not None:
                    try:
                        selected = evaluate_condition(spec.when, self.node_results)
                        self.node_decisions[task_id] = {"selected": selected, "condition": spec.when}
                        if not selected:
                            skip_reason = "condition did not select this branch"
                    except ValueError as exc:
                        node.status = "failed"
                        self.node_errors[task_id] = str(exc)
                        self.node_retryable[task_id] = False
                        run = self.runtime.find_run(task_id=task_id)
                        self.runtime.start(run.run_id)
                        self.runtime.transition(run.run_id, "failed", payload={"error": str(exc), "stage": "routing"})
                        self.node_decisions[task_id] = {"selected": None, "error": str(exc), "condition": spec.when}
                        changed = True
                        continue
                if skip_reason:
                    node.status = "skipped"
                    self.node_decisions[task_id] = {**self.node_decisions.get(task_id, {}), "selected": False, "reason": skip_reason}
                    self.runtime.transition(self.runtime.find_run(task_id=task_id).run_id, "skipped", payload={"reason": skip_reason})
                    self._journal_event("node.skipped", task_id=task_id, reason=skip_reason)
                    changed = True
                elif unavailable:
                    self.node_input_gaps[task_id] = [{"task_id": dep, "status": status,
                                                     "reason": self.node_errors.get(dep, "branch not selected")}
                                                    for dep, status in unavailable.items()]
                else:
                    self.node_input_gaps.pop(task_id, None)
                if not skip_reason:
                    for dependency in spec.dependencies:
                        for violation in self.node_contract_errors.get(dependency, []):
                            if not violation.get("required", True):
                                self.node_input_gaps.setdefault(task_id, []).append({
                                    "task_id": dependency, "status": "resource_gap", "reason": str(violation["details"]),
                                })
        self._persist_snapshot({})
        return sorted(task_id for task_id, node in self.graph._nodes.items()
                      if node.status == "pending" and task_id not in self._active_tasks
                      and all(self.graph._nodes[dep].status in (
                          {"succeeded"} if self.node_specs[task_id].dependency_policy == "all_success"
                          else {"succeeded", "failed", "blocked", "skipped", "cancelled"}) for dep in node.dependencies))

    def extend(self, nodes: Iterable[Mapping[str, Any]], *, expected_revision: int, reason: str) -> None:
        """Append a validated DAG between parent rounds; completed nodes are immutable."""
        if self._active_tasks or self.status == "running":
            raise ValueError("cannot extend a running workflow")
        if self.cancel_requested or self.status == "cancelled" or self.budget_state.get("exhausted"):
            raise ValueError("cannot extend a cancelled or budget-exhausted workflow")
        if expected_revision != self.revision:
            raise ValueError("workflow revision conflict")
        if not str(reason).strip():
            raise ValueError("workflow extension reason is required")
        additions = list(nodes)
        if not additions:
            raise ValueError("workflow extension requires new nodes")
        if self.revision >= self.definition.budget.get("max_extensions", 3):
            raise ValueError("workflow extension budget exceeded")
        candidate = self.definition.to_dict()
        candidate["nodes"] += additions
        validated = WorkflowDefinition.from_mapping(candidate)
        # All graph/ID/budget checks precede mutation.
        self.definition = validated
        self.definition_hash = validated.fingerprint()
        self.revision += 1
        new_nodes = validated.nodes[len(self.node_specs):]
        self._persistence_ready = False
        try:
            self.workflow_run = self.runtime.create_run(task_id=validated.workflow_id)
            for node in new_nodes:
                self.graph.add_task(node.task_id)
                self.node_specs[node.task_id] = node
            for node in new_nodes:
                self.graph.add_task(node.task_id, dependencies=node.dependencies)
                self.runtime.create_run(task_id=node.task_id, parent_task_id=validated.workflow_id,
                                        run_id=f"{validated.workflow_id}:{node.task_id}", max_attempts=node.max_attempts)
            for node in validated.nodes:
                self.runtime.register_child(self.workflow_run.run_id, node.task_id)
            self.status = "queued"
        finally:
            self._persistence_ready = True
        self._journal_event("workflow.extended", revision=self.revision, reason=reason,
                            added_tasks=[node.task_id for node in new_nodes])
        self._persist_snapshot({})

    async def _run(self) -> Dict[str, Any]:
        if self.status in {"succeeded", "partial"}:
            return self.snapshot()
        self.status = "running"
        self.runtime.start(self.workflow_run.run_id)
        self._journal_event("workflow.started")
        self._persist_snapshot(self.snapshot())

        while True:
            if self.cancel_requested:
                await self.cancel(reason=self.cancel_reason or "workflow cancelled")
                break
            ready = self._ready_tasks()
            for task_id in ready:
                self._active_tasks[task_id] = asyncio.create_task(self._run_node(task_id))
            if self._active_tasks:
                completed, _ = await asyncio.wait(
                    tuple(self._active_tasks.values()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in completed:
                    task_id = next((key for key, value in self._active_tasks.items() if value is task), None)
                    if task_id is None:
                        continue
                    self._active_tasks.pop(task_id, None)
                    try:
                        await task
                    except asyncio.CancelledError:
                        if not self.cancel_requested:
                            raise
                continue
            if all(node.status in {"succeeded", "skipped", "failed", "blocked"} for node in self._graph_nodes()):
                required_failure = any(node.status in {"failed", "blocked"} and self.node_specs[node.task_id].required for node in self._graph_nodes())
                incomplete = any(node.status in {"failed", "blocked"} for node in self._graph_nodes()) or bool(self.delivery()["gaps"])
                self.status = "failed" if required_failure or self.budget_state.get("exhausted") or (incomplete and not self.node_results) else "partial" if incomplete else "succeeded"
                # 收尾记账（transition/journal/快照）fail-soft：记账异常绝不能
                # 卡死已成功的工作流返回（曾疑似因此挂起过一次运行）。
                try:
                    self.runtime.transition(self.workflow_run.run_id, self.status, payload={"node_errors": dict(self.node_errors)})
                    self._journal_event(f"workflow.{self.status}")
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "workflow_completion_bookkeeping_failed",
                        workflow_id=str(self.definition.workflow_id),
                        error=str(exc),
                    )
                break
            if any(node.status == "failed" for node in self._graph_nodes()):
                self.status = "failed"
                self.runtime.transition(self.workflow_run.run_id, "failed", payload={"node_errors": dict(self.node_errors)})
                self._journal_event(
                    "workflow.failed",
                    node_errors={k: str(v)[:200] for k, v in self.node_errors.items()},
                    progress={k: v for k, v in self.node_progress.items()},
                )
                self._block_pending("dependency failed")
                break
            # A pending graph with no active or ready nodes is inconsistent.
            self.status = "failed"
            self.node_errors["__workflow__"] = "workflow has no runnable nodes"
            try:
                self.runtime.transition(self.workflow_run.run_id, "failed", payload={"error": self.node_errors["__workflow__"]})
            except Exception as exc:  # noqa: BLE001
                logger.error("workflow_failure_transition_failed", error=str(exc))
            self._journal_event("workflow.failed", error=self.node_errors["__workflow__"])
            break

        # 收尾快照 fail-soft：落库失败不能吞掉已完成的工作流返回
        self._journal_event("workflow.settled", status=self.status)
        try:
            self._persist_snapshot(self.snapshot())
        except Exception as exc:  # noqa: BLE001
            logger.error("workflow_final_persist_failed", workflow_id=str(self.definition.workflow_id), error=str(exc))
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
            "definition_hash": self.definition_hash,
            "revision": self.revision,
            "budget_state": {**self.budget_state, "elapsed_seconds": self._elapsed_seconds()},
            "status": self.status,
            "cancel_requested": self.cancel_requested,
            "cancel_reason": self.cancel_reason,
            "graph": self.graph.snapshot(),
            "node_results": dict(self.node_results),
            "node_sessions": dict(self.node_sessions),
            "node_errors": dict(self.node_errors),
            "node_progress": dict(self.node_progress),
            "node_input_hashes": dict(self.node_input_hashes),
            "node_lineage": dict(self.node_lineage),
            "node_decisions": dict(self.node_decisions),
            "node_input_gaps": dict(self.node_input_gaps),
            "node_contract_errors": dict(self.node_contract_errors),
            "node_retryable": dict(self.node_retryable),
            "delivery": self.delivery(),
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
        dependency_results = {dependency: self.node_results[dependency] for dependency in node.dependencies if dependency in self.node_results}
        input_payload = {
            "task_id": task_id,
            "attempt": node_run.attempt,
            "payload": node.payload,
            "dependencies": dependency_results,
        }
        input_hash = hashlib.sha256(
            json.dumps(
                input_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:24]
        self.node_input_hashes[task_id] = input_hash
        self._journal_event(
            "node.started",
            task_id=task_id,
            attempt=node_run.attempt,
            target_mode=node.payload.get("target_mode"),
            phase=node.payload.get("phase"),
            goal=str(node.payload.get("goal") or "")[:200],
            input_hash=input_hash,
        )
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
        if attempt > 1 or task_id in self.node_sessions:
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
            self.node_contract_errors.pop(task_id, None)
            input_handles = [handle for dependency, result in dependency_results.items() for handle in result_handles(dependency, result)]
            violations = check_resource_contracts(list(node.input_contracts), input_handles)
            if violations:
                self.node_contract_errors[task_id] = violations
                self.node_input_gaps.setdefault(task_id, []).extend(
                    {"task_id": item["source_task_id"], "status": "resource_gap", "reason": str(item["details"])}
                    for item in violations if not item["required"]
                )
                assert_resource_contracts(list(node.input_contracts), input_handles)
            async with self.governor:
                executions = self.budget_state.setdefault("executions", {})
                if executions.get(task_id, 0):
                    retries = int(self.budget_state.get("retries_used", 0))
                    if retries >= self.definition.budget.get("max_retries", 16):
                        self.budget_state["exhausted"] = "max_retries"
                        self.node_errors["__budget__"] = "workflow total retry budget exceeded"
                        raise ValueError("workflow total retry budget exceeded")
                    self.budget_state["retries_used"] = retries + 1
                executions[task_id] = executions.get(task_id, 0) + 1
                self._persist_snapshot({})
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
            if node.output_contract is not None:
                warnings = check_resource_contracts([node.output_contract], result_handles(task_id, result))
                if warnings:
                    self.node_contract_errors.setdefault(task_id, []).extend(warnings)
                assert_resource_contracts([node.output_contract], result_handles(task_id, result))
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
            self.node_errors.pop(task_id, None)
            if not self.node_contract_errors.get(task_id):
                self.node_contract_errors.pop(task_id, None)
            self.node_retryable.pop(task_id, None)
            self.graph.set_status(task_id, "succeeded")
            self.runtime.transition(node_run.run_id, "succeeded")
            self._journal_event(
                "node.succeeded",
                task_id=task_id,
                attempt=node_run.attempt,
                delivered_files=(self.node_progress.get(task_id) or {}).get("delivered_files"),
            )
        except asyncio.CancelledError:
            if self.cancel_requested:
                self.graph.set_status(task_id, "cancelled")
                self.runtime.request_cancel(node_run.run_id, reason=self.cancel_reason or "workflow cancelled")
            else:
                # Shutdown/disconnection is resumable; explicit user cancel is terminal.
                self.graph.set_status(task_id, "pending")
                self._persist_snapshot({})
            raise
        except Exception as exc:
            error = (
                f"workflow node timed out after {effective_node.timeout_seconds:g}s"
                if isinstance(exc, TimeoutError) and effective_node.timeout_seconds is not None
                else str(exc)
            )
            self.node_errors[task_id] = error
            if isinstance(exc, ResourceContractError):
                self.node_contract_errors[task_id] = exc.violations
            self.runtime.transition(node_run.run_id, "failed", payload={"error": error})
            retrying = (
                node_run.attempt < node_run.max_attempts
                and not isinstance(exc, (ValueError, TypeError, PermissionError, NotImplementedError))
            )
            self.node_retryable[task_id] = retrying
            self._journal_event(
                "node.failed",
                task_id=task_id,
                attempt=node_run.attempt,
                error=error[:500],
                retrying=retrying,
                progress=self.node_progress.get(task_id),
            )
            if retrying:
                # Transient failures back off; contract repair reuses the child session.
                if isinstance(exc, (ConnectionError, TimeoutError)):
                    await asyncio.sleep(min(8.0, 0.25 * 2 ** (attempt - 1)) + random.uniform(0, 0.1))
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
        self.node_decisions = dict(snapshot.get("node_decisions") or {})
        self.node_input_gaps = dict(snapshot.get("node_input_gaps") or {})
        self.node_contract_errors = dict(snapshot.get("node_contract_errors") or {})
        self.node_retryable = dict(snapshot.get("node_retryable") or {})
        snapshot_definition_hash = str(snapshot.get("definition_hash") or "")
        if snapshot_definition_hash and snapshot_definition_hash != self.definition_hash:
            raise ValueError("workflow snapshot definition does not match current workflow")
        self.node_input_hashes = {
            str(key): str(value)
            for key, value in (snapshot.get("node_input_hashes") or {}).items()
        }
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
        if not snapshot or self.cancel_requested or self.status == "cancelled" or self.budget_state.get("exhausted"):
            return
        runtime_runs = self.runtime.snapshot().get("runs") or {}
        for node in self._graph_nodes():
            # Older snapshots used cancelled for dependency blocking.
            if node.status == "blocked" or (
                node.status == "cancelled"
                and self.node_errors.get(node.task_id) == "dependency failed"
            ):
                node.status = "pending"
                self.node_errors.pop(node.task_id, None)
                continue
            if node.status != "failed":
                continue
            if not self.node_retryable.get(node.task_id, True):
                continue
            run = runtime_runs.get(self._node_run_id(node.task_id, snapshot)) or {}
            if int(run.get("attempt") or 0) < int(
                run.get("max_attempts") or self.node_specs[node.task_id].max_attempts
            ):
                node.status = "pending"
        if self.status in {"failed", "partial"} and any(node.status == "pending" for node in self._graph_nodes()):
            # Older snapshots created the parent with one attempt. Allow one
            # explicit resume while preserving per-node retry budgets.
            if self.workflow_run.status == "partial":
                self.workflow_run = self.runtime.create_run(task_id=self.definition.workflow_id)
                for node in self.definition.nodes:
                    self.runtime.register_child(self.workflow_run.run_id, node.task_id)
            else:
                self.workflow_run.max_attempts = max(self.workflow_run.max_attempts, 2)
            self.status = "queued"
        self.node_errors.pop("__workflow__", None)

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

    def bind_node_session(self, task_id: str, session_id: str) -> None:
        """Expose a running child session before its node returns."""
        if task_id not in self.node_specs or not session_id:
            return
        self.node_sessions[task_id] = session_id
        self._persist_snapshot({})

    def _graph_nodes(self):
        return [self.graph._nodes[node.task_id] for node in self.definition.nodes]

    def _cancel_pending(self, reason: str) -> None:
        for node in self._graph_nodes():
            if node.status == "pending":
                node.status = "cancelled"
                self.node_errors.setdefault(node.task_id, reason)

    def _block_pending(self, reason: str) -> None:
        for node in self._graph_nodes():
            if node.status == "pending":
                node.status = "blocked"
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
