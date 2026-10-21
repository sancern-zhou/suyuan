"""Dependency graph and concurrency primitives for Agent workflows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Set


@dataclass
class WorkflowNode:
    task_id: str
    dependencies: Set[str] = field(default_factory=set)
    status: str = "pending"


class WorkflowGraph:
    """A deterministic DAG used to decide which Agent tasks may start."""

    def __init__(self) -> None:
        self._nodes: Dict[str, WorkflowNode] = {}

    def add_task(self, task_id: str, *, dependencies: Optional[Iterable[str]] = None) -> WorkflowNode:
        if not task_id or not str(task_id).strip():
            raise ValueError("task_id is required")
        task_id = str(task_id)
        dependency_set = {str(item) for item in (dependencies or []) if str(item).strip()}
        if task_id in dependency_set:
            raise ValueError(f"task cannot depend on itself: {task_id}")
        existing = self._nodes.get(task_id)
        if existing:
            previous_dependencies = set(existing.dependencies)
            existing.dependencies.update(dependency_set)
            try:
                self.validate()
            except Exception:
                existing.dependencies = previous_dependencies
                raise
            return existing
        node = WorkflowNode(task_id=task_id, dependencies=dependency_set)
        self._nodes[task_id] = node
        try:
            self.validate()
        except Exception:
            self._nodes.pop(task_id, None)
            raise
        return node

    def set_status(self, task_id: str, status: str) -> WorkflowNode:
        node = self._require(task_id)
        node.status = status
        return node

    def ready_tasks(self) -> List[str]:
        return sorted(
            node.task_id
            for node in self._nodes.values()
            if node.status == "pending"
            and all(self._nodes[dependency].status == "succeeded" for dependency in node.dependencies)
        )

    def validate(self) -> None:
        missing = sorted(
            dependency
            for node in self._nodes.values()
            for dependency in node.dependencies
            if dependency not in self._nodes
        )
        if missing:
            raise ValueError(f"workflow dependencies not registered: {missing}")
        visiting: Set[str] = set()
        visited: Set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError(f"workflow dependency cycle detected at: {task_id}")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in self._nodes[task_id].dependencies:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in self._nodes:
            visit(task_id)

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        return {
            task_id: {
                "task_id": node.task_id,
                "dependencies": sorted(node.dependencies),
                "status": node.status,
            }
            for task_id, node in self._nodes.items()
        }

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Mapping[str, object]]) -> "WorkflowGraph":
        graph = cls()
        for task_id in snapshot:
            graph.add_task(task_id)
        for task_id, value in snapshot.items():
            graph.add_task(task_id, dependencies=value.get("dependencies") or [])
            graph.set_status(task_id, str(value.get("status") or "pending"))
        graph.validate()
        return graph

    def _require(self, task_id: str) -> WorkflowNode:
        if task_id not in self._nodes:
            raise KeyError(f"unknown workflow task: {task_id}")
        return self._nodes[task_id]


class WorkflowConcurrencyGovernor:
    """Bound concurrent child tasks without tying scheduling to a model/provider."""

    def __init__(self, limit: int = 4) -> None:
        if int(limit) < 1:
            raise ValueError("concurrency limit must be at least 1")
        self.limit = int(limit)
        self._semaphore = asyncio.Semaphore(self.limit)

    async def __aenter__(self) -> "WorkflowConcurrencyGovernor":
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._semaphore.release()
