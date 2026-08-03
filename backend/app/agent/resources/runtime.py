"""Per-tool resource publication and durable change notifications."""
from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .contracts import ResourceDeclaration
from .normalizer import normalize_tool_resources


def event_turn_sequence(event_data: dict[str, Any]) -> int:
    try:
        return int(event_data.get("iteration") or 0)
    except (TypeError, ValueError):
        return 0


def _successful_result(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != "tool_result":
        return None
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    if data.get("is_error") or data.get("success") is False:
        return None
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    if not isinstance(result, dict) or result.get("success") is False:
        return None
    return result


def groupby_group_key(
    declarations: Iterable[ResourceDeclaration],
) -> dict[str, list[ResourceDeclaration]]:
    grouped: dict[str, list[ResourceDeclaration]] = {}
    for declaration in declarations:
        grouped.setdefault(declaration.group_key, []).append(declaration)
    return grouped


@dataclass(frozen=True)
class ResourceEventResult:
    catalog_version: int
    changed_resource_ids: list[str] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)

    def changed_event(self, session_id: str, run_id: str) -> dict[str, Any]:
        return {
            "type": "resources_changed",
            "data": {
                "session_id": session_id,
                "run_id": run_id,
                "resource_version": self.catalog_version,
                "changed_resource_ids": self.changed_resource_ids,
                **({"rejected": self.rejected} if self.rejected else {}),
            },
        }


class RunResourceAccumulator:
    """Validation helper retained as a run-scoped rejection ledger."""

    def __init__(self, *, run_id: str):
        self.run_id = run_id
        self.rejected: list[dict[str, str]] = []

    def capture(
        self, event: dict[str, Any], *, turn_sequence: int
    ) -> dict[str, list[ResourceDeclaration]]:
        del turn_sequence
        result = _successful_result(event)
        if result is None:
            return {}
        resources, rejected = normalize_tool_resources(result=result)
        self.rejected = [*self.rejected, *rejected][-50:]
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        tool_name = str(data.get("tool_name") or event.get("tool_name") or "")
        if tool_name:
            resources = [
                item.model_copy(update={"tool_name": tool_name}) for item in resources
            ]
        return groupby_group_key(resources)


async def persist_tool_result_resources(
    service,
    session_id: str,
    run_id: str,
    event: dict[str, Any],
    *,
    turn_sequence: int,
) -> ResourceEventResult | None:
    """Publish all explicit groups in one successful tool result."""
    result = _successful_result(event)
    if result is None:
        return None
    tracking = result.get("resource_tracking")
    if isinstance(tracking, dict) and tracking.get("durable") is True:
        return ResourceEventResult(
            catalog_version=int(tracking.get("version") or 0),
            changed_resource_ids=list(tracking.get("resource_ids") or []),
            rejected=list(tracking.get("rejected") or []),
        )

    declarations, rejected = normalize_tool_resources(result=result)
    if not declarations and not rejected:
        return None
    if rejected:
        raise ValueError(f"invalid resource declarations: {rejected}")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    tool_name = str(data.get("tool_name") or event.get("tool_name") or "")
    if tool_name:
        declarations = [
            item.model_copy(update={"tool_name": tool_name}) for item in declarations
        ]
    published = []
    for group_key, members in groupby_group_key(declarations).items():
        published.append(
            await service.publish_group(
                session_id,
                run_id,
                group_key,
                members,
                turn_sequence=turn_sequence,
            )
        )
    if not published:
        return ResourceEventResult(
            catalog_version=await service.catalog_version(session_id),
            rejected=rejected,
        )
    return ResourceEventResult(
        catalog_version=max(item.catalog_version for item in published),
        changed_resource_ids=[
            resource.resource_id
            for publication in published
            for resource in publication.resources
        ],
        rejected=rejected,
    )


def resource_error_event(
    session_id: str, run_id: str, error: Exception | str
) -> dict[str, Any]:
    return {
        "type": "resource_error",
        "data": {
            "session_id": session_id,
            "run_id": run_id,
            "error": "resource_persistence_failed",
            "detail": str(error)[:500],
        },
    }


async def stream_with_resources(
    events: AsyncIterable[dict[str, Any]] | Iterable[dict[str, Any]],
    *,
    service,
    session_id: str,
    run_id: str,
):
    """Reference transport: commit, forward tool result, then notify change."""
    if hasattr(events, "__aiter__"):
        iterator = events
    else:
        async def _iterate():
            for event in events:
                yield event

        iterator = _iterate()

    async for event in iterator:
        publication = None
        failure = None
        if event.get("type") == "tool_result":
            try:
                publication = await persist_tool_result_resources(
                    service,
                    session_id,
                    run_id,
                    event,
                    turn_sequence=event_turn_sequence(event.get("data") or {}),
                )
            except Exception as exc:
                failure = resource_error_event(session_id, run_id, exc)
        yield event
        if publication is not None and publication.changed_resource_ids:
            yield publication.changed_event(session_id, run_id)
        elif failure is not None:
            yield failure
