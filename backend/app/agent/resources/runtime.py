"""Per-run collection and durability for explicit session resources."""
from __future__ import annotations

from typing import Any

from .contracts import ResourceDeclaration
from .normalizer import normalize_tool_resources


def event_turn_sequence(event_data: dict[str, Any]) -> int:
    try:
        return int(event_data.get("iteration") or 0)
    except (TypeError, ValueError):
        return 0


class RunResourceAccumulator:
    def __init__(self, *, run_id: str):
        self.run_id = run_id
        self.resources: list[ResourceDeclaration] = []
        self.rejected: list[dict[str, str]] = []

    def capture(self, event: dict[str, Any], *, turn_sequence: int) -> None:
        if event.get("type") != "tool_result":
            return
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if data.get("is_error") or data.get("success") is False:
            return
        result = data.get("result") if isinstance(data.get("result"), dict) else data
        resources, rejected = normalize_tool_resources(result=result)
        self.rejected = [*self.rejected, *rejected][-50:]
        by_key = {item.resource_key(): item for item in self.resources}
        for resource in resources:
            by_key[resource.resource_key()] = resource
        self.resources = list(by_key.values())


async def flush_resource_accumulator(
    service,
    session_id: str,
    accumulator: RunResourceAccumulator,
    terminal_data: dict[str, Any],
    *,
    turn_sequence: int = 0,
):
    """Persist collected resources before reporting terminal durability."""
    if not accumulator.resources:
        return None
    try:
        result = await service.upsert_run_resources(
            session_id,
            accumulator.run_id,
            accumulator.resources,
            turn_sequence=turn_sequence,
        )
    except Exception:
        terminal_data["resource_durable"] = False
        terminal_data["resource_error"] = "resource_persistence_failed"
        return None
    terminal_data["resource_version"] = result.version
    terminal_data["resource_durable"] = True
    if accumulator.rejected:
        terminal_data["resource_errors"] = list(accumulator.rejected)
    return result
