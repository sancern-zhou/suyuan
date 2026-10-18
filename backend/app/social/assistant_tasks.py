"""Database-backed assistant matters with scoped ownership and optimistic writes."""

from datetime import datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.social.assistant_request import AssistantRequest
from app.social.assistant_task_models import AssistantTaskDB, AssistantTaskEventDB


class TaskConflict(ValueError):
    pass


class TaskNotFound(ValueError):
    pass


def _text(value, field: str, limit: int = 20000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field} 必须为非空文本且不超过 {limit} 字")
    return value.strip()


class AssistantTaskService:
    """Never falls back to process-private files when the database is unavailable."""

    def __init__(self, session_factory=None):
        if session_factory is None:
            from app.db.database import async_session

            session_factory = async_session
        self.session_factory = session_factory

    @staticmethod
    def _scope(project_id, owner_user_id):
        if not project_id or not owner_user_id or owner_user_id == "system":
            raise PermissionError("无法确认事项归属")
        return (
            AssistantTaskDB.project_id == project_id,
            AssistantTaskDB.owner_user_id == owner_user_id,
        )

    @staticmethod
    def _record(row):
        return {
            column.name: getattr(row, column.name)
            for column in AssistantTaskDB.__table__.columns
            if column.name != "request_key"
        }

    @staticmethod
    def _event(task_id, version, kind, request, changes):
        return AssistantTaskEventDB(
            event_id=str(uuid4()),
            task_id=task_id,
            version=version,
            kind=kind,
            source_session_id=request.session_id,
            source_request_id=request.request_id,
            user_message=request.user_message,
            changes=changes,
        )

    async def create(
        self, project_id, owner_user_id, request: AssistantRequest, *, goal, completion_criteria
    ):
        scope = self._scope(project_id, owner_user_id)
        goal = _text(goal, "目标")
        criteria = _text(completion_criteria, "完成条件")
        key = sha256(f"{request.session_id}\0{request.request_id}\0{goal}".encode()).hexdigest()
        row = AssistantTaskDB(
            task_id=str(uuid4()),
            project_id=project_id,
            owner_user_id=owner_user_id,
            source_session_id=request.session_id,
            request_key=key,
            goal=goal,
            completion_criteria=criteria,
            status="ready",
            version=1,
        )
        async with self.session_factory() as session:
            try:
                session.add(row)
                await session.flush()
            except IntegrityError:
                await session.rollback()
                existing = (
                    await session.execute(
                        select(AssistantTaskDB).where(
                            *scope,
                            AssistantTaskDB.request_key == key,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    raise
                return self._record(existing)
            session.add(
                self._event(
                    row.task_id,
                    1,
                    "created",
                    request,
                    {"goal": goal, "completion_criteria": criteria, "status": "ready"},
                )
            )
            await session.commit()
            return self._record(row)

    async def list(self, project_id, owner_user_id, *, limit=20, offset=0):
        scope = self._scope(project_id, owner_user_id)
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AssistantTaskDB)
                        .where(*scope)
                        .order_by(
                            AssistantTaskDB.updated_at.desc(),
                            AssistantTaskDB.task_id,
                        )
                        .offset(max(0, int(offset)))
                        .limit(max(1, min(50, int(limit))))
                    )
                )
                .scalars()
                .all()
            )
            return [self._record(row) for row in rows]

    async def get(self, project_id, owner_user_id, task_id):
        scope = self._scope(project_id, owner_user_id)
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(AssistantTaskDB).where(
                        *scope,
                        AssistantTaskDB.task_id == task_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise TaskNotFound("事项不存在或无权访问")
            events = (
                (
                    await session.execute(
                        select(AssistantTaskEventDB)
                        .where(
                            AssistantTaskEventDB.task_id == task_id,
                        )
                        .order_by(AssistantTaskEventDB.version)
                    )
                )
                .scalars()
                .all()
            )
            return {
                **self._record(row),
                "events": [
                    {
                        col.name: getattr(event, col.name)
                        for col in AssistantTaskEventDB.__table__.columns
                    }
                    for event in events
                ],
            }

    async def change(
        self,
        project_id,
        owner_user_id,
        task_id,
        request: AssistantRequest,
        *,
        expected_version,
        action,
        next_step=None,
        result_summary=None,
        goal=None,
        completion_criteria=None,
    ):
        scope = self._scope(project_id, owner_user_id)
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("请使用查询结果中的事项版本")
        statuses = {
            "update": None,
            "feedback": None,
            "wait": "waiting_input",
            "block": "blocked",
            "resume": "ready",
            "complete": "completed",
            "cancel": "cancelled",
        }
        if action not in statuses:
            raise ValueError("不支持的事项操作")
        changes = {}
        for field, value in (("goal", goal), ("completion_criteria", completion_criteria)):
            if value is not None:
                if action != "update":
                    raise ValueError("仅修改事项时可变更目标或完成条件")
                changes[field] = _text(value, field)
        if next_step is not None:
            changes["next_step"] = _text(next_step, "下一步")
        if action in {"wait", "block"} and "next_step" not in changes:
            raise ValueError("等待或阻塞时必须说明缺少的信息及下一步")
        if action == "complete":
            changes["result_summary"] = _text(result_summary, "完成依据")
        elif result_summary is not None:
            raise ValueError("仅完成事项时可写入完成依据")
        if statuses[action]:
            changes["status"] = statuses[action]
        if action == "update" and not changes:
            raise ValueError("请提供需要修改的目标、完成条件或下一步")
        async with self.session_factory() as session:
            result = await session.execute(
                update(AssistantTaskDB)
                .where(
                    *scope,
                    AssistantTaskDB.task_id == task_id,
                    AssistantTaskDB.version == expected_version,
                    AssistantTaskDB.status.notin_(["completed", "cancelled"]),
                )
                .values(**changes, version=expected_version + 1, updated_at=datetime.utcnow())
                .returning(AssistantTaskDB)
            )
            row = result.scalar_one_or_none()
            if row is None:
                existing = (
                    await session.execute(
                        select(AssistantTaskDB.task_id).where(
                            *scope,
                            AssistantTaskDB.task_id == task_id,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    raise TaskNotFound("事项不存在或无权访问")
                raise TaskConflict("事项已变化或已结束，请重新查询后再操作")
            session.add(self._event(task_id, row.version, action, request, changes))
            await session.commit()
            return self._record(row)
