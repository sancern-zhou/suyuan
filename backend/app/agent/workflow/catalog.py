"""Shared catalog for fixed Agent-mode and scheduled workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional


WorkflowEntryPoint = Literal["agent_mode", "scheduled_task"]


@dataclass(frozen=True)
class WorkflowPhaseDefinition:
    """One bounded phase in a fixed workflow."""

    name: str
    description: str
    allowed_tools: tuple[str, ...] = ()
    advance_tools: tuple[str, ...] = ()
    max_attempts: int = 1
    allow_completion: bool = False


@dataclass(frozen=True)
class FixedWorkflowDefinition:
    """Versioned workflow metadata shared by every execution entry point."""

    name: str
    entrypoint: WorkflowEntryPoint
    phases: tuple[WorkflowPhaseDefinition, ...]
    version: str = "1"
    description: str = ""
    handler: Optional[Callable[..., Any]] = None

    @property
    def max_iterations(self) -> int:
        return sum(max(1, phase.max_attempts) for phase in self.phases)


class WorkflowCatalog:
    """Process-local registry for versioned fixed workflow definitions."""

    def __init__(self) -> None:
        self._definitions: dict[tuple[WorkflowEntryPoint, str], FixedWorkflowDefinition] = {}

    def register(self, definition: FixedWorkflowDefinition) -> None:
        key = (definition.entrypoint, definition.name)
        self._definitions[key] = definition

    def get(
        self,
        entrypoint: WorkflowEntryPoint,
        name: str,
    ) -> Optional[FixedWorkflowDefinition]:
        return self._definitions.get((entrypoint, str(name)))

    def names(self, entrypoint: WorkflowEntryPoint) -> list[str]:
        return sorted(
            name
            for kind, name in self._definitions
            if kind == entrypoint
        )


workflow_catalog = WorkflowCatalog()
