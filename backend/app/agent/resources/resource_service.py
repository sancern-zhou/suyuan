"""Canonical service boundary for versioned session resource groups."""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.utils import path_config
from app.utils.path_config import (
    TEMP_ROOT,
    get_data_registry,
    get_sessions_dir,
    get_uploads_dir,
    is_agent_sensitive_path,
    is_path_within,
)

from .contracts import ResourceDeclaration, ResourceRelation


_CHART_SNAPSHOT_DIR = "chart_snapshots"
_CHART_PATH_DELIMITERS = re.compile(r"[\[\]`<>\r\n\x00]")


def normalize_chart_path(path: str) -> str | None:
    """Normalize a catalog lookup key without opening or statting a model path."""
    if not isinstance(path, str) or not path.strip() or _CHART_PATH_DELIMITERS.search(path):
        return None
    if "://" in path or (os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", path)):
        return None
    candidate = Path(path.strip())
    if candidate.anchor and not candidate.is_absolute():
        return None
    return Path(os.path.abspath(path_config.PROJECT_ROOT / candidate)).as_posix()


def select_inline_chart_member(declarations: list[ResourceDeclaration]) -> ResourceDeclaration | None:
    active = [item for item in declarations if item.status.value == "active" and item.locator.path]
    spec = next(
        (item for item in active if item.resource_key == "chart-spec" and item.renderer.value == "chart"),
        None,
    )
    if spec and spec.metadata.get("interactive") is not False:
        return spec
    return next(
        (
            item for item in active
            if item.renderer.value == "image"
            and (item.relation is ResourceRelation.PRIMARY or item.resource_key == "chart-image")
        ),
        None,
    )


def stable_group_id(session_id: str, group_key: str) -> str:
    return hashlib.sha256(f"{session_id}:{group_key}".encode()).hexdigest()[:32]


def chart_publication_identity(
    run_id: str, tool_name: str, turn_sequence: int, tool_call_id: str, chart_index: int,
) -> str:
    return f"{run_id}:{tool_name}:{turn_sequence}:{tool_call_id}:{chart_index}"


def _fingerprint_chart_sources(declarations: list[ResourceDeclaration]) -> str:
    """Disambiguate direct publications made without a tool-call identity."""
    digest = hashlib.sha256()
    allowed = [get_data_registry(), get_uploads_dir(), TEMP_ROOT]
    for item in sorted(declarations, key=lambda decl: decl.resource_key):
        if item.locator.path:
            source = Path(item.locator.path)
            _require_chart_source(source, allowed)
            with source.open("rb") as contents:
                digest.update(hashlib.file_digest(contents, "sha256").digest())
        digest.update(item.resource_key.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _require_chart_source(source: Path, allowed: list[Path]) -> None:
    if (
        not source.is_file()
        or is_agent_sensitive_path(source)
        or not is_path_within(source, allowed)
    ):
        raise ValueError(f"chart snapshot source is unavailable: {source}")


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
    primary = primaries[0]
    if group_key.startswith("report:") and primary.role.value == "report":
        if (
            primary.resource_key not in {"qmd", "primary:qmd"}
            or primary.format != "qmd"
            or "render" not in {capability.value for capability in primary.capabilities}
        ):
            raise ValueError(
                "report resource groups require a renderable QMD primary"
            )
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


def inline_chart_path(resource: StoredResource) -> str | None:
    """Return the copyable path for the catalog's selected inline chart member."""
    raw_path = resource.locator.get("path")
    if resource.status != "active" or resource.metadata.get("inline_chart") is not True:
        return None
    if not normalize_chart_path(raw_path):
        return None
    path = Path(raw_path)
    try:
        return path.relative_to(path_config.PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def project_inline_chart(resource: StoredResource) -> dict[str, str] | None:
    path = inline_chart_path(resource)
    if path is None:
        return None
    return {"label": resource.label, "path": path, "marker": f"[[chart:{path}]]"}


def confirmed_chart_publication(
    catalog_version: int,
    existing: list[StoredResource],
    resources: list[ResourceDeclaration],
) -> ResourcePublishResult:
    """Return the original complete group on retry, including its original IDs."""
    expected = {item.resource_key: item.locator.path for item in resources}
    selected = select_inline_chart_member(resources)
    if (
        {item.resource_key: item.locator.get("path") for item in existing} != expected
        or len(existing) != len(expected)
        or any(item.status != "active" for item in existing)
        or not selected
        or not any(item.resource_key == selected.resource_key and inline_chart_path(item) for item in existing)
    ):
        raise ValueError("confirmed chart publication is incomplete or inconsistent")
    by_key = {item.resource_key: item for item in existing}
    return ResourcePublishResult(
        catalog_version,
        existing[0].version,
        [by_key[item.resource_key] for item in resources],
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
    def in_memory(cls, *, storage_root: Path | None = None) -> SessionResourceService:
        return cls(_MemoryState(), storage_root=storage_root)

    @classmethod
    def database(cls) -> SessionResourceService:
        from app.db.session_resources_repository import SessionResourcesRepository

        return cls(
            repository=SessionResourcesRepository(),
            storage_root=get_sessions_dir() / "resource_content",
        )

    def _existing_snapshot_key(self, declarations: list[ResourceDeclaration]) -> str | None:
        if self._storage_root is None:
            return None
        root = (self._storage_root / _CHART_SNAPSHOT_DIR).resolve()
        paths = [Path(item.locator.path) for item in declarations if item.locator.path]
        if not paths or len({path.parent for path in paths}) != 1:
            return None
        directory = paths[0].parent
        if directory.parent == root and re.fullmatch(r"[0-9a-f]{32}", directory.name):
            return f"chart-publication:{directory.name}"
        return None

    def _snapshot_chart_group(
        self,
        group_key: str,
        declarations: list[ResourceDeclaration],
        selected: ResourceDeclaration,
    ) -> list[ResourceDeclaration]:
        if self._storage_root is None:
            return declarations
        snapshot_root = (self._storage_root / _CHART_SNAPSHOT_DIR).resolve()
        paths = {item.resource_key: Path(item.locator.path) for item in declarations if item.locator.path}
        if self._existing_snapshot_key(declarations) != group_key:
            destination = snapshot_root / group_key.removeprefix("chart-publication:")
            # Each complete group becomes visible in one atomic rename. The first
            # completed write wins, including when two processes retry together.
            names = {
                item.resource_key: hashlib.sha256(item.resource_key.encode()).hexdigest()[:12]
                + (f".{item.format}" if re.fullmatch(r"[a-zA-Z0-9]{1,12}", item.format) else "")
                for item in declarations if item.locator.path
            }
            if not destination.exists():
                snapshot_root.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=snapshot_root, prefix=".staging-") as temporary:
                    staged = Path(temporary) / "group"
                    staged.mkdir()
                    allowed = [get_data_registry(), get_uploads_dir(), TEMP_ROOT]
                    for key, source in paths.items():
                        _require_chart_source(source, allowed)
                        shutil.copyfile(source, staged / names[key])
                    try:
                        staged.rename(destination)
                    except OSError:
                        if not destination.is_dir():
                            raise
            paths = {key: destination / name for key, name in names.items()}
        if not all(path.is_file() and normalize_chart_path(path.as_posix()) for path in paths.values()):
            raise ValueError("chart snapshot is missing or has an unsupported path")
        published = []
        for item in declarations:
            metadata = dict(item.metadata)
            metadata.pop("visual_id", None)
            metadata.pop("inline_chart", None)
            if item.resource_key == selected.resource_key:
                metadata["inline_chart"] = True
            updates = {"metadata": metadata}
            if path := paths.get(item.resource_key):
                updates["locator"] = item.locator.model_copy(update={"path": path.as_posix()})
                metadata["size"] = path.stat().st_size
            published.append(item.model_copy(update=updates))
        return published

    def _materialize_declarations(
        self, session_id: str, declarations: list[ResourceDeclaration]
    ) -> list[ResourceDeclaration]:
        """Copy path-backed products into the canonical registry before publication."""
        if self._storage_root is None:
            return declarations
        registry_root = get_data_registry().resolve()
        session_key = hashlib.sha256(session_id.encode()).hexdigest()[:24]
        publication_key = uuid4().hex
        publication_root: Path | None = None
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
            # 防止任意主机文件被发布为可下载会话资源：
            # 仅允许数据注册表、上传目录与临时目录来源。
            if not is_path_within(source, [registry_root, get_uploads_dir(), TEMP_ROOT]):
                raise ValueError(
                    f"resource path outside allowed data areas: {source}"
                )
            if publication_root is None:
                publication_root = (
                    self._storage_root / session_key / publication_key
                ).resolve()
                publication_root.mkdir(parents=True, exist_ok=False)
            member_key = hashlib.sha256(
                f"{declaration.resource_key}:{source}".encode()
            ).hexdigest()[:20]
            destination_dir = publication_root / member_key
            destination_dir.mkdir(parents=True, exist_ok=False)
            destination = destination_dir / source.name
            temporary = destination_dir / f".{source.name}.tmp-{uuid4().hex}"
            try:
                if source.is_dir():
                    shutil.copytree(source, temporary)
                else:
                    shutil.copy2(source, temporary)
                temporary.replace(destination)
            except Exception:
                if temporary.is_dir():
                    shutil.rmtree(temporary)
                elif temporary.exists():
                    temporary.unlink()
                raise
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

    def materialize_file_bytes(
        self,
        *,
        session_id: str,
        group_key: str,
        resource_key: str,
        filename: str,
        content: bytes,
        checksum: str | None = None,
    ) -> Path:
        """Idempotently materialize bytes in the canonical session resource store."""
        if self._storage_root is None:
            raise RuntimeError("session resource storage is not configured")
        actual_checksum = hashlib.sha256(content).hexdigest()
        if checksum and checksum != actual_checksum:
            raise ValueError("resource content checksum mismatch")
        safe_name = Path(
            str(filename).replace("\x00", "").replace("\\", "/")
        ).name
        if safe_name in {"", ".", ".."}:
            safe_name = "document"
        session_key = hashlib.sha256(session_id.encode()).hexdigest()[:24]
        group_key_hash = hashlib.sha256(group_key.encode()).hexdigest()[:20]
        resource_key_hash = hashlib.sha256(resource_key.encode()).hexdigest()[:20]
        destination_dir = (
            self._storage_root
            / session_key
            / "materialized"
            / group_key_hash
            / resource_key_hash
            / actual_checksum[:20]
        ).resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / safe_name
        if destination.is_symlink():
            destination.unlink()
        if destination.is_file():
            existing_checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
            if existing_checksum == actual_checksum:
                return destination
        temporary = destination_dir / f".{safe_name}.tmp-{uuid4().hex}"
        temporary.write_bytes(content)
        temporary.replace(destination)
        return destination

    async def publish_group(
        self,
        session_id: str,
        run_id: str,
        group_key: str,
        resources: Iterable[ResourceDeclaration],
        *,
        turn_sequence: int = 0,
        publication_id: str | None = None,
    ) -> ResourcePublishResult:
        declarations = list(resources)
        validate_publication(group_key, declarations)
        selected = select_inline_chart_member(declarations)
        immutable = selected is not None and self._storage_root is not None
        if immutable:
            # Cross-session handoff uses the original snapshot key. For newly
            # produced charts the caller's stable operation identity scopes retries.
            snapshot_key = self._existing_snapshot_key(declarations)
            if snapshot_key is None:
                if publication_id is None:
                    fingerprint = await asyncio.to_thread(_fingerprint_chart_sources, declarations)
                    publication_id = f"{run_id}:{turn_sequence}:{group_key}:{fingerprint}"
                snapshot_key = "chart-publication:" + stable_group_id(session_id, publication_id)
            group_key = snapshot_key
            declarations = await asyncio.to_thread(
                self._snapshot_chart_group, group_key, declarations, selected,
            )
            declarations = [item.model_copy(update={"group_key": group_key}) for item in declarations]
        else:
            declarations = await asyncio.to_thread(self._materialize_declarations, session_id, declarations)
        if self._repository is not None:
            return await self._repository.publish_group(
                session_id,
                run_id,
                group_key,
                declarations,
                turn_sequence=turn_sequence,
                immutable=immutable,
            )
        return self._publish_memory_group(
            session_id,
            run_id,
            group_key,
            declarations,
            turn_sequence=turn_sequence,
            immutable=immutable,
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

    def _materialize_replacement(
        self, session_id: str, resource: StoredResource, source_path: str | Path
    ) -> Path:
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise ValueError("replacement resource file does not exist")
        if self._storage_root is None:
            return source
        session_key = hashlib.sha256(session_id.encode()).hexdigest()[:24]
        destination_dir = (
            self._storage_root
            / session_key
            / uuid4().hex
            / hashlib.sha256(resource.resource_key.encode()).hexdigest()[:20]
        ).resolve()
        destination_dir.mkdir(parents=True, exist_ok=False)
        destination = destination_dir / source.name
        temporary = destination_dir / f".{source.name}.tmp-{uuid4().hex}"
        shutil.copy2(source, temporary)
        temporary.replace(destination)
        return destination

    async def replace_primary_file(
        self,
        session_id: str,
        run_id: str,
        resource_id: str,
        path: str | Path,
    ) -> ResourcePublishResult:
        resource = await self.get_resource(session_id, resource_id, status="active")
        if resource is None or resource.relation != "primary":
            raise ValueError("active primary resource was not found")
        destination = self._materialize_replacement(session_id, resource, path)
        metadata = {**resource.metadata, "size": destination.stat().st_size}
        if self._repository is not None:
            return await self._repository.replace_primary_file(
                session_id,
                run_id,
                resource_id,
                str(destination),
                metadata,
            )
        group_version = max(
            (
                item.version
                for item in self._state.resources.values()
                if item.session_id == session_id and item.group_id == resource.group_id
            ),
            default=resource.version,
        ) + 1
        now = datetime.now(UTC)
        for existing_id, existing in list(self._state.resources.items()):
            if (
                existing.session_id == session_id
                and existing.group_id == resource.group_id
                and existing.status == "active"
            ):
                self._state.resources[existing_id] = replace(
                    existing, status="superseded", updated_at=now
                )
        replacement = replace(
            resource,
            resource_id=stable_resource_id(
                session_id, resource.group_id, group_version, resource.resource_key
            ),
            parent_resource_id=None,
            locator={"path": str(destination)},
            metadata=metadata,
            run_id=run_id,
            version=group_version,
            status="active",
            created_at=now,
            updated_at=now,
        )
        self._state.resources[replacement.resource_id] = replacement
        self._state.group_versions[(session_id, resource.group_id)] = group_version
        catalog_version = self._state.catalog_versions.get(session_id, 0) + 1
        self._state.catalog_versions[session_id] = catalog_version
        return ResourcePublishResult(catalog_version, group_version, [replacement])

    def _publish_memory_group(
        self,
        session_id: str,
        run_id: str,
        group_key: str,
        declarations: list[ResourceDeclaration],
        *,
        turn_sequence: int,
        immutable: bool = False,
    ) -> ResourcePublishResult:
        group_id = stable_group_id(session_id, group_key)
        group_version_key = (session_id, group_id)
        if immutable:
            existing = [
                item for item in self._state.resources.values()
                if item.session_id == session_id and item.group_id == group_id
            ]
            if existing:
                return confirmed_chart_publication(
                    self._state.catalog_versions.get(session_id, 0), existing, declarations,
                )
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
            "pdf", "html", "markdown", "spreadsheet", "presentation", "docx", "image"
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

    async def get_resources_by_ids(
        self, session_id: str, resource_ids: Iterable[str], *, status: str | None = "active",
    ) -> list[StoredResource]:
        ids = list(dict.fromkeys(resource_ids))
        if self._repository is not None:
            return await self._repository.get_resources_by_ids(session_id, ids, status=status)
        resources = []
        for resource_id in ids:
            resource = await self.get_resource(session_id, resource_id, status=status)
            if resource is not None:
                resources.append(resource)
        return resources

    async def find_inline_charts_by_paths(
        self, session_id: str, paths: Iterable[str],
    ) -> dict[str, list[StoredResource]]:
        matches = {
            key: [] for path in paths if (key := normalize_chart_path(path)) is not None
        }
        if not matches:
            return matches
        if self._repository is not None:
            resources = await self._repository.find_inline_charts_by_paths(session_id, list(matches))
        else:
            resources = self._state.resources.values()
        for resource in resources:
            if resource.session_id != session_id or inline_chart_path(resource) is None:
                continue
            key = resource.locator.get("path")
            if key in matches:
                matches[key].append(resource)
        return matches

    async def find_inline_charts_by_path(self, session_id: str, path: str) -> list[StoredResource]:
        matches = await self.find_inline_charts_by_paths(session_id, [path])
        return next(iter(matches.values()), [])

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
