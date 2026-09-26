"""Coordinator quick prompts (常用问题) repository.

The ``coordinator_quick_prompts`` table is the runtime source of truth for
quick prompts on two surfaces:

- ``home``: coordinator home page quick prompts, seeded from
  ``projects/<id>/project.yaml`` (``frontend.coordinator.quick_prompts``).
- ``input``: per-agent-mode suggestions above the chat input box, seeded
  from ``INPUT_QUICK_PROMPT_DEFAULTS`` in ``app.api.coordinator_config_routes``.

Admin edits only touch this table; manifest/hardcoded defaults are only
used to seed an empty surface. Re-seeding triggers whenever a surface has
zero rows, so a surface cannot stay empty.
"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
import structlog

from app.db.database import async_session
from app.db.models.coordinator_quick_prompt_db import CoordinatorQuickPromptDB

logger = structlog.get_logger()


class QuickPromptConflict(Exception):
    """A unique-constraint violation, e.g. a duplicate label in one scope."""


class CoordinatorQuickPromptRepository:
    """CRUD plus first-read defaults seeding for quick prompt rows."""

    async def list_prompts(
        self,
        project_id: str,
        *,
        surface: str | None = None,
        mode: str | None = None,
        enabled_only: bool = False,
    ) -> list[CoordinatorQuickPromptDB]:
        async with async_session() as session:
            return await self._list(
                session, project_id, surface=surface, mode=mode, enabled_only=enabled_only
            )

    async def get_prompt(
        self, project_id: str, prompt_id: int
    ) -> CoordinatorQuickPromptDB | None:
        async with async_session() as session:
            return await session.get(CoordinatorQuickPromptDB, prompt_id)

    async def create_prompt(
        self,
        project_id: str,
        *,
        surface: str,
        label: str,
        prompt: str,
        mode: str | None,
        updated_by: str | None,
    ) -> CoordinatorQuickPromptDB:
        async with async_session() as session:
            row = CoordinatorQuickPromptDB(
                project_id=project_id,
                surface=surface,
                label=label,
                prompt=prompt,
                mode=mode,
                sort_order=await self._next_sort_order(session, project_id, surface, mode),
                enabled=True,
                updated_by=updated_by,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise QuickPromptConflict(str(exc)) from exc
            await session.refresh(row)
            return row

    async def update_prompt(
        self,
        project_id: str,
        prompt_id: int,
        *,
        label: str | None = None,
        prompt: str | None = None,
        mode: str | None = None,
        mode_changed: bool = False,
        enabled: bool | None = None,
        updated_by: str | None = None,
    ) -> CoordinatorQuickPromptDB | None:
        async with async_session() as session:
            row = await session.get(CoordinatorQuickPromptDB, prompt_id)
            if row is None or row.project_id != project_id:
                return None
            if label is not None:
                row.label = label
            if prompt is not None:
                row.prompt = prompt
            if mode_changed:
                row.mode = mode
            if enabled is not None:
                row.enabled = enabled
            row.updated_by = updated_by
            row.updated_at = datetime.now()
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise QuickPromptConflict(str(exc)) from exc
            await session.refresh(row)
            return row

    async def delete_prompt(self, project_id: str, prompt_id: int) -> bool:
        async with async_session() as session:
            row = await session.get(CoordinatorQuickPromptDB, prompt_id)
            if row is None or row.project_id != project_id:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def reorder_prompts(
        self, project_id: str, ordered_ids: list[int], *, surface: str, mode: str | None = None
    ) -> bool:
        """Assign sort positions following the given id order.

        The ids must exactly match the rows in the scope (surface, plus mode
        for the input surface); otherwise returns False and leaves ordering
        untouched.
        """
        async with async_session() as session:
            rows = await self._list(session, project_id, surface=surface, mode=mode)
            by_id = {row.id: row for row in rows}
            if sorted(ordered_ids) != sorted(by_id):
                return False
            now = datetime.now()
            for position, prompt_id in enumerate(ordered_ids):
                row = by_id[prompt_id]
                row.sort_order = position
                row.updated_at = now
            await session.commit()
            return True

    async def seed_defaults(self, project_id: str, surface: str, entries: list[dict]) -> bool:
        """Insert default quick prompts when the surface has no rows yet.

        Entries are normalized dicts with label/prompt/mode keys. Safe to
        call concurrently: the (project_id, surface, label) unique constraint
        makes losing races no-ops.
        """
        if not entries:
            return False
        async with async_session() as session:
            if await self._count(session, project_id, surface=surface) > 0:
                return False
            now = datetime.now()
            for index, entry in enumerate(entries):
                session.add(
                    CoordinatorQuickPromptDB(
                        project_id=project_id,
                        surface=surface,
                        label=entry["label"],
                        prompt=entry["prompt"],
                        mode=entry.get("mode"),
                        sort_order=index,
                        enabled=True,
                        updated_by=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            try:
                await session.commit()
            except IntegrityError:
                # Another worker seeded the same defaults first.
                await session.rollback()
                return False
            logger.info(
                "coordinator_quick_prompts_seeded",
                project=project_id,
                surface=surface,
                count=len(entries),
            )
            return True

    async def _list(
        self,
        session,
        project_id: str,
        *,
        surface: str | None = None,
        mode: str | None = None,
        enabled_only: bool = False,
    ) -> list[CoordinatorQuickPromptDB]:
        stmt = select(CoordinatorQuickPromptDB).where(
            CoordinatorQuickPromptDB.project_id == project_id
        )
        if surface is not None:
            stmt = stmt.where(CoordinatorQuickPromptDB.surface == surface)
        if mode is not None:
            stmt = stmt.where(CoordinatorQuickPromptDB.mode == mode)
        if enabled_only:
            stmt = stmt.where(CoordinatorQuickPromptDB.enabled.is_(True))
        stmt = stmt.order_by(
            CoordinatorQuickPromptDB.sort_order, CoordinatorQuickPromptDB.id
        )
        return list((await session.execute(stmt)).scalars())

    async def _count(
        self, session, project_id: str, *, surface: str | None = None
    ) -> int:
        stmt = select(func.count()).select_from(CoordinatorQuickPromptDB)
        conditions = [CoordinatorQuickPromptDB.project_id == project_id]
        if surface is not None:
            conditions.append(CoordinatorQuickPromptDB.surface == surface)
        stmt = stmt.where(*conditions)
        return int((await session.execute(stmt)).scalar_one())

    async def _next_sort_order(
        self, session, project_id: str, surface: str, mode: str | None
    ) -> int:
        """Next position within the row's visual scope.

        Home prompts are one flat list; input prompts are ordered per agent
        mode.
        """
        stmt = select(func.max(CoordinatorQuickPromptDB.sort_order)).where(
            CoordinatorQuickPromptDB.project_id == project_id,
            CoordinatorQuickPromptDB.surface == surface,
        )
        if mode is not None:
            stmt = stmt.where(CoordinatorQuickPromptDB.mode == mode)
        current_max = (await session.execute(stmt)).scalar_one()
        return (current_max or 0) + 1
