"""Per-run resource collection at the shared agent event boundary."""
from __future__ import annotations

from typing import Any

from .manifest import merge_resource_refs
from .models import SessionResourceRef
from .normalizer import normalize_tool_result_refs
from .service import ManifestPersistenceError, SessionResourceManifest


def event_turn_sequence(event_data: dict[str, Any]) -> int:
    try:
        return int(event_data.get("iteration") or 0)
    except (TypeError, ValueError):
        return 0


class RunReferenceAccumulator:
    def __init__(self, *, run_id: str) -> None:
        self.run_id = run_id
        self.refs: list[SessionResourceRef] = []
        self.rejected: list[dict[str, str]] = []

    def capture(self, event: dict[str, Any], *, turn_sequence: int) -> None:
        event_type = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if event_type == "tool_result":
            if data.get("is_error") or data.get("success") is False:
                return
            result = data.get("result")
            tool_name = str(data.get("tool_name") or data.get("name") or "unknown_tool")
        elif event_type in {"office_document", "html_document"}:
            result = data
            tool_name = event_type
        else:
            return
        run_id = str(data.get("run_id") or event.get("run_id") or self.run_id or "unknown-run")
        refs, rejected = normalize_tool_result_refs(
            tool_name=tool_name,
            run_id=run_id,
            turn_sequence=turn_sequence,
            result=result,
        )
        self.refs = merge_resource_refs(self.refs, refs)
        self.rejected = [*self.rejected, *rejected][-50:]


async def flush_resource_accumulator(
    service,
    session_id: str,
    accumulator: RunReferenceAccumulator,
    terminal_data: dict[str, Any],
) -> SessionResourceManifest | None:
    """Persist collected refs and make durability explicit on the terminal event."""
    if not accumulator.refs:
        return None
    try:
        manifest = await service.merge(session_id, accumulator.refs)
    except ManifestPersistenceError:
        terminal_data["resource_refs_durable"] = False
        terminal_data["resource_refs_error"] = "manifest_persistence_failed"
        return None
    terminal_data["resource_refs_version"] = manifest.version
    terminal_data["resource_refs_durable"] = True
    return manifest
