"""Single service boundary for current session resources."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from .contracts import ResourceDeclaration


@dataclass
class StoredResource:
    session_id: str
    resource_key: str
    resource_id: str
    kind: str
    role: str
    label: str
    locator: dict
    presentation_type: str | None
    presentation: dict | None
    metadata: dict
    tool_name: str
    run_id: str
    turn_sequence: int
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_declaration(
        cls,
        session_id: str,
        run_id: str,
        declaration: ResourceDeclaration,
        *,
        created_at: datetime | None = None,
        turn_sequence: int = 0,
    ) -> "StoredResource":
        now = created_at or datetime.now(timezone.utc)
        key = declaration.resource_key()
        resource_id = hashlib.sha256(f"{session_id}:{key}".encode()).hexdigest()[:32]
        return cls(
            session_id=session_id,
            resource_key=key,
            resource_id=resource_id,
            kind=declaration.kind.value,
            role=declaration.role.value,
            label=declaration.label,
            locator=declaration.locator.model_dump(exclude_none=True),
            presentation_type=declaration.presentation_type.value if declaration.presentation_type else None,
            presentation=declaration.presentation.model_dump(mode="json") if declaration.presentation else None,
            metadata=declaration.metadata,
            tool_name="",
            run_id=run_id,
            turn_sequence=turn_sequence,
            status=declaration.status.value,
            created_at=now,
            updated_at=now,
        )


@dataclass(frozen=True)
class ResourceBatchResult:
    version: int
    resources: list[StoredResource]


@dataclass(frozen=True)
class ResourcePage:
    resources: list[StoredResource]
    next_cursor: str | None = None


@dataclass(frozen=True)
class ResourceCounts:
    total: int = 0
    documents: int = 0
    visualizations: int = 0
    files: int = 0


@dataclass
class _MemoryState:
    resources: dict[tuple[str, str], StoredResource] = field(default_factory=dict)
    versions: dict[str, int] = field(default_factory=dict)


class SessionResourceService:
    def __init__(self, state: _MemoryState | None = None):
        self._state = state or _MemoryState()

    @classmethod
    def in_memory(cls) -> "SessionResourceService":
        return cls(_MemoryState())

    async def upsert_run_resources(
        self,
        session_id: str,
        run_id: str,
        resources: Iterable[ResourceDeclaration],
        *,
        turn_sequence: int = 0,
    ) -> ResourceBatchResult:
        declarations = list(resources)
        if not declarations:
            return ResourceBatchResult(
                version=self._state.versions.get(session_id, 0),
                resources=await self._resources_for(session_id),
            )

        for declaration in declarations:
            stored = StoredResource.from_declaration(
                session_id,
                run_id,
                declaration,
                turn_sequence=turn_sequence,
            )
            previous = self._state.resources.get((session_id, stored.resource_key))
            if previous is not None:
                stored.created_at = previous.created_at
            stored.updated_at = datetime.now(timezone.utc)
            self._state.resources[(session_id, stored.resource_key)] = stored

        self._state.versions[session_id] = self._state.versions.get(session_id, 0) + 1
        return ResourceBatchResult(
            version=self._state.versions[session_id],
            resources=await self._resources_for(session_id),
        )

    async def list_resources(
        self,
        session_id: str,
        *,
        kind: str | None = None,
        presentation_type: str | None = None,
        role: str | None = None,
        status: str = "active",
        limit: int = 100,
        cursor: str | None = None,
    ) -> ResourcePage:
        resources = await self._resources_for(session_id)
        filtered = [
            item for item in resources
            if (kind is None or item.kind == kind)
            and (presentation_type is None or item.presentation_type == presentation_type)
            and (role is None or item.role == role)
            and (status is None or item.status == status)
        ]
        start = int(cursor or 0)
        page = filtered[start:start + limit]
        next_cursor = str(start + limit) if start + limit < len(filtered) else None
        return ResourcePage(page, next_cursor)

    async def resource_counts(self, session_id: str) -> ResourceCounts:
        resources = await self._resources_for(session_id)
        return ResourceCounts(
            total=len(resources),
            documents=sum(item.presentation_type == "document" for item in resources),
            visualizations=sum(item.presentation_type == "visualization" for item in resources),
            files=sum(item.kind in {"file", "artifact"} for item in resources),
        )

    async def delete_resource(self, session_id: str, resource_key: str) -> bool:
        return self._state.resources.pop((session_id, resource_key), None) is not None

    async def delete_session_resources(self, session_id: str) -> bool:
        keys = [key for key in self._state.resources if key[0] == session_id]
        for key in keys:
            self._state.resources.pop(key, None)
        self._state.versions.pop(session_id, None)
        return bool(keys)

    async def _resources_for(self, session_id: str) -> list[StoredResource]:
        return sorted(
            [item for (sid, _), item in self._state.resources.items() if sid == session_id],
            key=lambda item: (item.created_at, item.resource_key),
        )
