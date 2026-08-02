"""Transactional persistence for versioned session resource groups."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.resources.contracts import ResourceDeclaration, ResourceRelation
from app.agent.resources.resource_service import (
    ResourceCounts,
    ResourcePage,
    ResourcePublishResult,
    StoredResource,
    stable_group_id,
    stable_resource_id,
    validate_publication,
)
from app.db.database import engine
from app.db.models_session import SessionResourceDB, SessionResourceVersionDB


def _stored(row: SessionResourceDB) -> StoredResource:
    return StoredResource(
        resource_id=row.resource_id,
        session_id=row.session_id,
        group_id=row.group_id,
        parent_resource_id=row.parent_resource_id,
        resource_key=row.resource_key,
        relation=row.relation,
        kind=row.kind,
        role=row.role,
        label=row.label,
        locator=row.locator or {},
        format=row.format,
        media_type=row.media_type,
        renderer=row.renderer,
        capabilities=list(row.capabilities or []),
        metadata=row.resource_metadata or {},
        tool_name=row.tool_name,
        run_id=row.run_id,
        turn_sequence=row.turn_sequence,
        version=row.version,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _insert_values(resource: StoredResource) -> dict:
    return {
        "resource_id": resource.resource_id,
        "session_id": resource.session_id,
        "group_id": resource.group_id,
        "parent_resource_id": resource.parent_resource_id,
        "resource_key": resource.resource_key,
        "relation": resource.relation,
        "kind": resource.kind,
        "role": resource.role,
        "label": resource.label,
        "locator": resource.locator,
        "format": resource.format,
        "media_type": resource.media_type,
        "renderer": resource.renderer,
        "capabilities": resource.capabilities,
        "resource_metadata": resource.metadata,
        "tool_name": resource.tool_name,
        "run_id": resource.run_id,
        "turn_sequence": resource.turn_sequence,
        "version": resource.version,
        "status": resource.status,
        "created_at": resource.created_at.replace(tzinfo=None),
        "updated_at": resource.updated_at.replace(tzinfo=None),
    }


class SessionResourcesRepository:
    def __init__(self, db_engine=None):
        self.engine = db_engine or engine

    async def _lock_catalog_version(
        self, db: AsyncSession, session_id: str
    ) -> SessionResourceVersionDB:
        await db.execute(
            insert(SessionResourceVersionDB)
            .values(session_id=session_id, version=0)
            .on_conflict_do_nothing(
                index_elements=[SessionResourceVersionDB.session_id]
            )
        )
        result = await db.execute(
            select(SessionResourceVersionDB)
            .where(SessionResourceVersionDB.session_id == session_id)
            .with_for_update()
        )
        return result.scalar_one()

    async def publish_group(
        self,
        session_id: str,
        run_id: str,
        group_key: str,
        resources: list[ResourceDeclaration],
        *,
        turn_sequence: int = 0,
    ) -> ResourcePublishResult:
        validate_publication(group_key, resources)
        group_id = stable_group_id(session_id, group_key)
        async with AsyncSession(self.engine, expire_on_commit=False) as db:
            async with db.begin():
                catalog = await self._lock_catalog_version(db, session_id)
                locked_rows = await db.execute(
                    select(SessionResourceDB)
                    .where(
                        SessionResourceDB.session_id == session_id,
                        SessionResourceDB.group_id == group_id,
                    )
                    .with_for_update()
                )
                existing = list(locked_rows.scalars().all())
                group_version = max((row.version for row in existing), default=0) + 1

                now = datetime.utcnow()
                await db.execute(
                    update(SessionResourceDB)
                    .where(
                        SessionResourceDB.session_id == session_id,
                        SessionResourceDB.group_id == group_id,
                        SessionResourceDB.status == "active",
                    )
                    .values(status="superseded", updated_at=now)
                )

                stored_resources: list[StoredResource] = []
                ids_by_key: dict[str, str] = {}
                pending = list(resources)
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
                            parent_resource_id=ids_by_key.get(
                                declaration.parent_key or ""
                            ),
                            turn_sequence=turn_sequence,
                        )
                        await db.execute(
                            insert(SessionResourceDB).values(**_insert_values(stored))
                        )
                        ids_by_key[declaration.resource_key] = stored.resource_id
                        stored_resources.append(stored)
                        pending.remove(declaration)
                        progressed = True
                    if not progressed:
                        raise ValueError(
                            "resource publication contains a cyclic parent relation"
                        )

                catalog.version += 1
                catalog.updated_at = now
                catalog_version = catalog.version
            return ResourcePublishResult(
                catalog_version, group_version, stored_resources
            )

    async def attach_resources(
        self,
        session_id: str,
        run_id: str,
        parent_resource_id: str,
        resources: list[ResourceDeclaration],
        *,
        turn_sequence: int = 0,
    ) -> ResourcePublishResult:
        if not resources:
            raise ValueError("resource attachment cannot be empty")
        async with AsyncSession(self.engine, expire_on_commit=False) as db:
            async with db.begin():
                catalog = await self._lock_catalog_version(db, session_id)
                result = await db.execute(
                    select(SessionResourceDB)
                    .where(
                        SessionResourceDB.session_id == session_id,
                        SessionResourceDB.resource_id == parent_resource_id,
                        SessionResourceDB.status == "active",
                    )
                    .with_for_update()
                )
                parent_row = result.scalar_one_or_none()
                if parent_row is None:
                    raise ValueError("active parent resource was not found")
                if any(
                    item.relation is ResourceRelation.PRIMARY for item in resources
                ):
                    raise ValueError("attached resources cannot be primary")
                if any(
                    stable_group_id(session_id, item.group_key) != parent_row.group_id
                    for item in resources
                ):
                    raise ValueError("attached resources must use the parent group")
                if any(
                    item.parent_key != parent_row.resource_key for item in resources
                ):
                    raise ValueError(
                        "attached resource parent_key must identify the parent resource"
                    )
                keys = [item.resource_key for item in resources]
                if len(keys) != len(set(keys)):
                    raise ValueError("attached resource keys must be unique")

                attached: list[StoredResource] = []
                for declaration in resources:
                    stored = StoredResource.from_declaration(
                        session_id,
                        run_id,
                        parent_row.group_id,
                        parent_row.version,
                        declaration,
                        parent_resource_id=parent_row.resource_id,
                        turn_sequence=turn_sequence,
                    )
                    values = _insert_values(stored)
                    updates = {
                        key: value
                        for key, value in values.items()
                        if key not in {"resource_id", "created_at"}
                    }
                    statement = insert(SessionResourceDB).values(**values)
                    statement = statement.on_conflict_do_update(
                        index_elements=[SessionResourceDB.resource_id],
                        set_=updates,
                    )
                    await db.execute(statement)
                    attached.append(stored)

                now = datetime.utcnow()
                catalog.version += 1
                catalog.updated_at = now
                catalog_version = catalog.version
            return ResourcePublishResult(
                catalog_version, parent_row.version, attached
            )

    async def replace_primary_file(
        self,
        session_id: str,
        run_id: str,
        resource_id: str,
        path: str,
        metadata: dict,
    ) -> ResourcePublishResult:
        async with AsyncSession(self.engine, expire_on_commit=False) as db:
            async with db.begin():
                catalog = await self._lock_catalog_version(db, session_id)
                result = await db.execute(
                    select(SessionResourceDB)
                    .where(
                        SessionResourceDB.session_id == session_id,
                        SessionResourceDB.resource_id == resource_id,
                        SessionResourceDB.status == "active",
                    )
                    .with_for_update()
                )
                primary_row = result.scalar_one_or_none()
                if primary_row is None or primary_row.relation != "primary":
                    raise ValueError("active primary resource was not found")
                group_rows = list(
                    (
                        await db.execute(
                            select(SessionResourceDB)
                            .where(
                                SessionResourceDB.session_id == session_id,
                                SessionResourceDB.group_id == primary_row.group_id,
                            )
                            .with_for_update()
                        )
                    ).scalars().all()
                )
                group_version = max(row.version for row in group_rows) + 1
                now = datetime.utcnow()
                await db.execute(
                    update(SessionResourceDB)
                    .where(
                        SessionResourceDB.session_id == session_id,
                        SessionResourceDB.group_id == primary_row.group_id,
                        SessionResourceDB.status == "active",
                    )
                    .values(status="superseded", updated_at=now)
                )
                current = _stored(primary_row)
                replacement = replace(
                    current,
                    resource_id=stable_resource_id(
                        session_id,
                        current.group_id,
                        group_version,
                        current.resource_key,
                    ),
                    parent_resource_id=None,
                    locator={"path": path},
                    metadata=metadata,
                    run_id=run_id,
                    version=group_version,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
                await db.execute(
                    insert(SessionResourceDB).values(**_insert_values(replacement))
                )
                catalog.version += 1
                catalog.updated_at = now
                catalog_version = catalog.version
            return ResourcePublishResult(
                catalog_version, group_version, [replacement]
            )

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
        async with AsyncSession(self.engine) as db:
            statement = select(SessionResourceDB).where(
                SessionResourceDB.session_id == session_id
            )
            if kind:
                statement = statement.where(SessionResourceDB.kind == kind)
            if role:
                statement = statement.where(SessionResourceDB.role == role)
            if renderer:
                statement = statement.where(SessionResourceDB.renderer == renderer)
            if group_id:
                statement = statement.where(SessionResourceDB.group_id == group_id)
            if status:
                statement = statement.where(SessionResourceDB.status == status)
            statement = statement.order_by(
                SessionResourceDB.updated_at.desc(), SessionResourceDB.resource_key
            )
            offset = int(cursor or 0)
            rows = list(
                (
                    await db.execute(statement.offset(offset).limit(limit + 1))
                ).scalars().all()
            )
            next_cursor = str(offset + limit) if len(rows) > limit else None
            return ResourcePage([_stored(row) for row in rows[:limit]], next_cursor)

    async def resource_counts(self, session_id: str) -> ResourceCounts:
        page = await self.list_resources(session_id, status="active", limit=100000)
        document_renderers = {
            "pdf", "html", "markdown", "spreadsheet", "presentation", "image"
        }
        return ResourceCounts(
            total=len(page.resources),
            documents=sum(
                row.renderer in document_renderers for row in page.resources
            ),
            visualizations=sum(
                row.renderer == "chart" for row in page.resources
            ),
            boards=sum(row.renderer == "board" for row in page.resources),
            files=sum(
                row.kind in {"file", "artifact"} for row in page.resources
            ),
            products=sum(
                row.role in {"output", "report"} for row in page.resources
            ),
        )

    async def catalog_version(self, session_id: str) -> int:
        async with AsyncSession(self.engine) as db:
            value = await db.scalar(
                select(SessionResourceVersionDB.version).where(
                    SessionResourceVersionDB.session_id == session_id
                )
            )
            return int(value or 0)

    async def get_resource(
        self,
        session_id: str,
        resource_id: str,
        *,
        status: str | None = "active",
    ) -> StoredResource | None:
        async with AsyncSession(self.engine) as db:
            statement = select(SessionResourceDB).where(
                SessionResourceDB.session_id == session_id,
                SessionResourceDB.resource_id == resource_id,
            )
            if status:
                statement = statement.where(SessionResourceDB.status == status)
            row = (await db.execute(statement)).scalar_one_or_none()
            return _stored(row) if row is not None else None

    async def delete_resource(self, session_id: str, resource_id: str) -> bool:
        async with AsyncSession(self.engine) as db:
            async with db.begin():
                catalog = await self._lock_catalog_version(db, session_id)
                result = await db.execute(
                    delete(SessionResourceDB).where(
                        SessionResourceDB.session_id == session_id,
                        SessionResourceDB.resource_id == resource_id,
                    )
                )
                if result.rowcount:
                    catalog.version += 1
                    catalog.updated_at = datetime.utcnow()
                return bool(result.rowcount)

    async def delete_session(self, session_id: str) -> bool:
        async with AsyncSession(self.engine) as db:
            async with db.begin():
                result = await db.execute(
                    delete(SessionResourceDB).where(
                        SessionResourceDB.session_id == session_id
                    )
                )
                await db.execute(
                    delete(SessionResourceVersionDB).where(
                        SessionResourceVersionDB.session_id == session_id
                    )
                )
                return bool(result.rowcount)
