"""Canonical service boundary for versioned session resource groups."""
from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from app.utils.path_config import get_data_registry, get_sessions_dir

from .contracts import ResourceDeclaration, ResourceRelation


def stable_group_id(session_id: str, group_key: str) -> str:
    return hashlib.sha256(f"{session_id}:{group_key}".encode()).hexdigest()[:32]


def stable_resource_id(
    session_id: str, group_id: str, group_version: int, resource_key: str
) -> str:
    identity = f"{session_id}:{group_id}:{group_version}:{resource_key}"
    return hashlib.sha256(identity.encode()).hexdigest()[:32]


def validate_publication(
    group_key: str, declarations: list[ResourceDeclaration]
) -> dict[str, ResourceDeclaration]:
    """Validate a complete group before any state is changed."""
    if not declarations:
        raise ValueError("resource group publication cannot be empty")
    if any(item.group_key != group_key for item in declarations):
        raise ValueError("all resources must use the published group_key")
    by_key = {item.resource_key: item for item in declarations}
    if len(by_key) != len(declarations):
        raise ValueError("resource keys must be unique within a publication")
    primaries = [
        item for item in declarations if item.relation is ResourceRelation.PRIMARY
    ]
    if len(primaries) != 1:
        raise ValueError("resource group publication requires exactly one primary")
    for item in declarations:
        if item.relation is not ResourceRelation.PRIMARY and item.parent_key not in by_key:
            raise ValueError(
                f"resource parent {item.parent_key!r} is not in the publication batch"
            )
    return by_key


@dataclass(frozen=True)
class StoredResource:
    resource_id: str
    session_id: str
    group_id: str
    parent_resource_id: str | None
    resource_key: str
    relation: str
    kind: str
    role: str
    label: str
    locator: dict
    format: str
    media_type: str
    renderer: str
    capabilities: list[str]
    metadata: dict
    tool_name: str
    run_id: str
    turn_sequence: int
    version: int
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_declaration(
        cls,
        session_id: str,
        run_id: str,
        group_id: str,
        group_version: int,
        declaration: ResourceDeclaration,
        *,
        parent_resource_id: str | None = None,
        created_at: datetime | None = None,
        turn_sequence: int = 0,
    ) -> StoredResource:
        now = created_at or datetime.now(UTC)
        return cls(
            resource_id=stable_resource_id(
                session_id, group_id, group_version, declaration.resource_key
            ),
            session_id=session_id,
            group_id=group_id,
            parent_resource_id=parent_resource_id,
            resource_key=declaration.resource_key,
            relation=declaration.relation.value,
            kind=declaration.kind.value,
            role=declaration.role.value,
            label=declaration.label,
            locator=declaration.locator.model_dump(exclude_none=True),
            format=declaration.format,
            media_type=declaration.media_type,
            renderer=declaration.renderer.value,
            capabilities=sorted(item.value for item in declaration.capabilities),
            metadata=declaration.metadata,
            tool_name=declaration.tool_name,
            run_id=run_id,
            turn_sequence=turn_sequence,
            version=group_version,
            status=declaration.status.value,
            created_at=now,
            updated_at=now,
        )


@dataclass(frozen=True)
class ResourcePublishResult:
    catalog_version: int
    group_version: int
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
    boards: int = 0
    files: int = 0
    products: int = 0


@dataclass
class _MemoryState:
    resources: dict[str, StoredResource] = field(default_factory=dict)
    catalog_versions: dict[str, int] = field(default_factory=dict)
    group_versions: dict[tuple[str, str], int] = field(default_factory=dict)


class SessionResourceService:
    def __init__(
        self,
        state: _MemoryState | None = None,
        repository=None,
        storage_root: Path | None = None,
    ):
        self._state = state or _MemoryState()
        self._repository = repository
        self._storage_root = storage_root

    @classmethod
    def in_memory(cls) -> SessionResourceService:
        return cls(_MemoryState())

    @classmethod
    def database(cls) -> SessionResourceService:
        from app.db.session_resources_repository import SessionResourcesRepository

        return cls(
            repository=SessionResourcesRepository(),
            storage_root=get_sessions_dir() / "resource_content",
        )

    def _materialize_declarations(
        self, session_id: str, declarations: list[ResourceDeclaration]
    ) -> list[ResourceDeclaration]:
        """Copy path-backed products into the canonical registry before publication."""
        if self._storage_root is None:
            return declarations
        registry_root = get_data_registry().resolve()
        session_key = hashlib.sha256(session_id.encode()).hexdigest()[:24]
        materialized: list[ResourceDeclaration] = []
        for declaration in declarations:
            raw_path = declaration.locator.path
            if not raw_path:
                materialized.append(declaration)
                continue
            source = Path(raw_path).expanduser().resolve()
            if source.is_relative_to(registry_root):
                materialized.append(declaration)
                continue
            if not source.exists():
                raise ValueError(f"resource path does not exist: {source}")
            source_key = hashlib.sha256(str(source).encode()).hexdigest()[:24]
            destination_dir = self._storage_root / session_key / source_key
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination = destination_dir / source.name
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)
            materialized.append(
                declaration.model_copy(
                    update={
                        "locator": declaration.locator.model_copy(
                            update={"path": str(destination.resolve())}
                        )
                    }
                )
            )
        return materialized

    async def publish_group(
        self,
        session_id: str,
        run_id: str,
        group_key: str,
        resources: Iterable[ResourceDeclaration],
        *,
        turn_sequence: int = 0,
    ) -> ResourcePublishResult:
        declarations = list(resources)
        validate_publication(group_key, declarations)
        declarations = self._materialize_declarations(session_id, declarations)
        if self._repository is not None:
            return await self._repository.publish_group(
                session_id,
                run_id,
                group_key,
                declarations,
                turn_sequence=turn_sequence,
            )
        return self._publish_memory_group(
            session_id,
            run_id,
            group_key,
            declarations,
            turn_sequence=turn_sequence,
        )

    async def attach_resources(
        self,
        session_id: str,
        run_id: str,
        parent_resource_id: str,
        resources: Iterable[ResourceDeclaration],
        *,
        turn_sequence: int = 0,
    ) -> ResourcePublishResult:
        declarations = list(resources)
        if not declarations:
            raise ValueError("resource attachment cannot be empty")
        declarations = self._materialize_declarations(session_id, declarations)
        if self._repository is not None:
            return await self._repository.attach_resources(
                session_id,
                run_id,
                parent_resource_id,
                declarations,
                turn_sequence=turn_sequence,
            )
        return self._attach_memory_resources(
            session_id,
            run_id,
            parent_resource_id,
            declarations,
            turn_sequence=turn_sequence,
        )

    def _publish_memory_group(
        self,
        session_id: str,
        run_id: str,
        group_key: str,
        declarations: list[ResourceDeclaration],
        *,
        turn_sequence: int,
    ) -> ResourcePublishResult:
        group_id = stable_group_id(session_id, group_key)
        group_version_key = (session_id, group_id)
        group_version = self._state.group_versions.get(group_version_key, 0) + 1
        now = datetime.now(UTC)
        new_resources: list[StoredResource] = []
        ids_by_key: dict[str, str] = {}
        pending = list(declarations)
        while pending:
            progressed = False
            for declaration in pending[:]:
                if declaration.parent_key and declaration.parent_key not in ids_by_key:
                    continue
                stored = StoredResource.from_declaration(
                    session_id,
                    run_id,
                    group_id,
                    group_version,
                    declaration,
                    parent_resource_id=ids_by_key.get(declaration.parent_key or ""),
                    created_at=now,
                    turn_sequence=turn_sequence,
                )
                ids_by_key[declaration.resource_key] = stored.resource_id
                new_resources.append(stored)
                pending.remove(declaration)
                progressed = True
            if not progressed:
                raise ValueError("resource publication contains a cyclic parent relation")

        for resource_id, existing in list(self._state.resources.items()):
            if (
                existing.session_id == session_id
                and existing.group_id == group_id
                and existing.status == "active"
            ):
                self._state.resources[resource_id] = replace(
                    existing, status="superseded", updated_at=now
                )
        for resource in new_resources:
            self._state.resources[resource.resource_id] = resource
        self._state.group_versions[group_version_key] = group_version
        catalog_version = self._state.catalog_versions.get(session_id, 0) + 1
        self._state.catalog_versions[session_id] = catalog_version
        return ResourcePublishResult(catalog_version, group_version, new_resources)

    def _attach_memory_resources(
        self,
        session_id: str,
        run_id: str,
        parent_resource_id: str,
        declarations: list[ResourceDeclaration],
        *,
        turn_sequence: int,
    ) -> ResourcePublishResult:
        parent = self._state.resources.get(parent_resource_id)
        if parent is None or parent.session_id != session_id or parent.status != "active":
            raise ValueError("active parent resource was not found")
        if any(item.relation is ResourceRelation.PRIMARY for item in declarations):
            raise ValueError("attached resources cannot be primary")
        if any(stable_group_id(session_id, item.group_key) != parent.group_id for item in declarations):
            raise ValueError("attached resources must use the parent group")
        if any(item.parent_key != parent.resource_key for item in declarations):
            raise ValueError("attached resource parent_key must identify the parent resource")
        keys = [item.resource_key for item in declarations]
        if len(keys) != len(set(keys)):
            raise ValueError("attached resource keys must be unique")

        now = datetime.now(UTC)
        attached = [
            StoredResource.from_declaration(
                session_id,
                run_id,
                parent.group_id,
                parent.version,
                declaration,
                parent_resource_id=parent.resource_id,
                created_at=now,
                turn_sequence=turn_sequence,
            )
            for declaration in declarations
        ]
        for resource in attached:
            previous = self._state.resources.get(resource.resource_id)
            if previous is not None:
                resource = replace(resource, created_at=previous.created_at)
            self._state.resources[resource.resource_id] = resource
        catalog_version = self._state.catalog_versions.get(session_id, 0) + 1
        self._state.catalog_versions[session_id] = catalog_version
        return ResourcePublishResult(catalog_version, parent.version, attached)

    async def list_resources(
        self,
        session_id: str,
        *,
        kind: str | None = None,
        role: str | None = None,
        renderer: str | None = None,
        group_id: str | None = None,
        status: str | None = "active",
        limit: int = 100,
        cursor: str | None = None,
    ) -> ResourcePage:
        if self._repository is not None:
            return await self._repository.list_resources(
                session_id,
                kind=kind,
                role=role,
                renderer=renderer,
                group_id=group_id,
                status=status,
                limit=limit,
                cursor=cursor,
            )
        resources = [
            resource
            for resource in self._state.resources.values()
            if resource.session_id == session_id
            and (kind is None or resource.kind == kind)
            and (role is None or resource.role == role)
            and (renderer is None or resource.renderer == renderer)
            and (group_id is None or resource.group_id == group_id)
            and (status is None or resource.status == status)
        ]
        resources.sort(
            key=lambda resource: (resource.updated_at, resource.resource_key), reverse=True
        )
        start = int(cursor or 0)
        page = resources[start : start + limit]
        next_cursor = str(start + limit) if start + limit < len(resources) else None
        return ResourcePage(page, next_cursor)

    async def resource_counts(self, session_id: str) -> ResourceCounts:
        if self._repository is not None:
            return await self._repository.resource_counts(session_id)
        resources = (await self.list_resources(session_id)).resources
        document_renderers = {
            "pdf", "html", "markdown", "spreadsheet", "presentation", "image"
        }
        return ResourceCounts(
            total=len(resources),
            documents=sum(item.renderer in document_renderers for item in resources),
            visualizations=sum(item.renderer == "chart" for item in resources),
            boards=sum(item.renderer == "board" for item in resources),
            files=sum(item.kind in {"file", "artifact"} for item in resources),
            products=sum(item.role in {"output", "report"} for item in resources),
        )

    async def catalog_version(self, session_id: str) -> int:
        if self._repository is not None:
            return await self._repository.catalog_version(session_id)
        return self._state.catalog_versions.get(session_id, 0)

    async def get_resource(
        self, session_id: str, resource_id: str, *, status: str | None = "active"
    ) -> StoredResource | None:
        if self._repository is not None:
            return await self._repository.get_resource(session_id, resource_id, status=status)
        resource = self._state.resources.get(resource_id)
        if resource is None or resource.session_id != session_id:
            return None
        if status is not None and resource.status != status:
            return None
        return resource

    async def delete_resource(self, session_id: str, resource_id: str) -> bool:
        if self._repository is not None:
            return await self._repository.delete_resource(session_id, resource_id)
        resource = self._state.resources.get(resource_id)
        if resource is None or resource.session_id != session_id:
            return False
        children = [
            item.resource_id
            for item in self._state.resources.values()
            if item.parent_resource_id == resource_id
        ]
        for child_id in children:
            self._state.resources.pop(child_id, None)
        self._state.resources.pop(resource_id, None)
        self._state.catalog_versions[session_id] = (
            self._state.catalog_versions.get(session_id, 0) + 1
        )
        return True

    async def delete_session_resources(self, session_id: str) -> bool:
        if self._repository is not None:
            return await self._repository.delete_session(session_id)
        resource_ids = [
            resource_id
            for resource_id, resource in self._state.resources.items()
            if resource.session_id == session_id
        ]
        for resource_id in resource_ids:
            self._state.resources.pop(resource_id, None)
        for key in [key for key in self._state.group_versions if key[0] == session_id]:
            self._state.group_versions.pop(key, None)
        self._state.catalog_versions.pop(session_id, None)
        return bool(resource_ids)
