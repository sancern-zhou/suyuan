"""Owner-authorized reminder plans and their durable execution/delivery queue.

The database owns occurrences; APScheduler only wakes the queue consumer.
"""

import json
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.social.assistant_followup_models import (
    AssistantOutboxDB as Outbox,
)
from app.social.assistant_followup_models import (
    AssistantRunDB as Run,
)
from app.social.assistant_followup_models import (
    AssistantTriggerDB as Trigger,
)
from app.social.assistant_schedule import definition_hash, next_occurrence, normalize_schedule
from app.social.assistant_task_models import AssistantTaskDB as Task
from app.social.assistant_tasks import AssistantTaskService, TaskConflict, TaskNotFound, _text


def record(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name != "request_key"}


async def revoke_followups(session, task_id):
    """Called inside the human task-edit transaction, never after its commit."""
    await session.execute(update(Trigger).where(Trigger.task_id == task_id).values(enabled=False))
    await session.execute(
        update(Run)
        .where(Run.task_id == task_id, Run.state.in_(["queued", "running"]))
        .values(state="cancelled", finished_at=datetime.utcnow())
    )
    await session.execute(
        update(Outbox)
        .where(Outbox.task_id == task_id, Outbox.state.in_(["pending", "sending"]))
        .values(state="cancelled")
    )


class AssistantFollowupService(AssistantTaskService):
    async def _task(self, session, project, owner, task_id):
        task = (
            await session.execute(
                select(Task)
                .where(
                    *self._scope(project, owner),
                    Task.task_id == task_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if task is None:
            raise TaskNotFound("事项不存在或无权访问")
        return task

    async def create(
        self,
        project,
        owner,
        task_id,
        request,
        *,
        expected_version,
        kind,
        instructions,
        run_at=None,
        interval_minutes=None,
        cron=None,
        timezone_name="Asia/Shanghai",
        now=None,
    ):
        if not request.delivery_user_id:
            raise PermissionError("当前入口没有可验证的个人提醒地址")
        route = request.delivery_user_id.rsplit(":", 2)
        if (
            len(route) != 3
            or route[0] not in {"app", "weixin"}
            and not route[0].startswith("weixin:")
        ):
            raise PermissionError("当前仅支持 App 和已绑定微信的个人提醒")
        if route[0] == "app" and request.delivery_user_id != owner:
            raise PermissionError("不能替其他 App 用户设置提醒")
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("请使用查询得到的事项版本")
        if kind not in {"now", "once", "interval", "cron"}:
            raise ValueError("当前仅支持立即、单次、间隔或 cron 个人提醒")
        instructions = _text(instructions, "提醒内容", 4000)
        # Request replay must not shift a one-shot timestamp or create another interval.
        key = sha256(
            json.dumps(
                [
                    project,
                    owner,
                    task_id,
                    request.session_id,
                    request.request_id,
                    kind,
                    instructions,
                    run_at,
                    interval_minutes,
                    cron,
                    timezone_name,
                ],
                ensure_ascii=False,
                default=str,
            ).encode()
        ).hexdigest()
        async with self.session_factory() as session:
            task = await self._task(session, project, owner, task_id)
            existing = (
                await session.execute(select(Trigger).where(Trigger.request_key == key))
            ).scalar_one_or_none()
            if existing:
                return record(existing)
            schedule, due = normalize_schedule(
                kind,
                run_at=run_at,
                interval_minutes=interval_minutes,
                cron=cron,
                timezone_name=timezone_name,
                now=now,
            )
            if task.version != expected_version or task.status in {"completed", "cancelled"}:
                raise TaskConflict("事项已变化或已结束，请重新查询")
            # Serialize registration against cancellation on both PostgreSQL and SQLite.
            changed = await session.execute(
                update(Task)
                .where(
                    Task.task_id == task_id,
                    Task.version == expected_version,
                    Task.status.notin_(["completed", "cancelled"]),
                )
                .values(updated_at=task.updated_at)
            )
            if changed.rowcount != 1:
                raise TaskConflict("事项已变化，请重新查询")
            trigger = Trigger(
                trigger_id=str(uuid4()),
                task_id=task_id,
                request_key=key,
                kind=kind,
                action="remind",
                instructions=instructions,
                schedule=schedule,
                next_at=due,
                enabled=True,
                definition_hash=definition_hash(task),
                recipient=request.delivery_user_id,
                grant_session_id=request.session_id,
                grant_request_id=request.request_id,
                grant_message=request.user_message,
            )
            session.add(trigger)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = (
                    await session.execute(select(Trigger).where(Trigger.request_key == key))
                ).scalar_one_or_none()
                if existing is None:
                    raise
                return record(existing)
            return record(trigger)

    async def inspect(self, project, owner, task_id):
        async with self.session_factory() as session:
            await self._task(session, project, owner, task_id)
            result = {}
            for name, model, order in (
                ("triggers", Trigger, Trigger.created_at),
                ("runs", Run, Run.created_at),
                ("notifications", Outbox, Outbox.created_at),
            ):
                rows = (
                    (
                        await session.execute(
                            select(model)
                            .where(model.task_id == task_id)
                            .order_by(order.desc())
                            .limit(50)
                        )
                    )
                    .scalars()
                    .all()
                )
                result[name] = [record(row) for row in rows]
            return result

    async def disable(self, project, owner, task_id, request, *, expected_version):
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("请使用查询得到的事项版本")
        async with self.session_factory() as session:
            task = await self._task(session, project, owner, task_id)
            changed = await session.execute(
                update(Task)
                .where(Task.task_id == task_id, Task.version == expected_version)
                .values(version=expected_version + 1, updated_at=datetime.utcnow())
            )
            if changed.rowcount != 1:
                raise TaskConflict("事项已变化，请重新查询")
            await revoke_followups(session, task_id)
            session.add(
                self._event(task_id, expected_version + 1, "followups_disabled", request, {})
            )
            await session.commit()
            return {"task_id": task.task_id, "version": expected_version + 1, "disabled": True}

    async def materialize(self, project, now=None):
        now = now or datetime.utcnow()
        async with self.session_factory() as session:
            due = (
                (
                    await session.execute(
                        select(Trigger)
                        .join(Task)
                        .where(
                            Task.project_id == project,
                            Trigger.enabled.is_(True),
                            Trigger.next_at <= now,
                        )
                        .order_by(Trigger.next_at)
                        .limit(50)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for trigger in due:
                task = await session.get(Task, trigger.task_id)
                at = trigger.next_at
                valid = (
                    task.status not in {"completed", "cancelled"}
                    and definition_hash(task) == trigger.definition_hash
                )
                next_at = next_occurrence(trigger.kind, trigger.schedule, now) if valid else None
                if valid and trigger.kind == "interval":
                    interval = timedelta(minutes=trigger.schedule["interval_minutes"])
                    next_at = at + ((now - at) // interval + 1) * interval
                changed = await session.execute(
                    update(Trigger)
                    .where(
                        Trigger.trigger_id == trigger.trigger_id,
                        Trigger.enabled.is_(True),
                        Trigger.next_at == at,
                    )
                    .values(next_at=next_at, enabled=valid)
                )
                if changed.rowcount != 1 or not valid:
                    continue
                # Coalesce periodic downtime. Expire very old one-shot work visibly.
                expired = trigger.kind in {"once", "now"} and now - at > timedelta(hours=24)
                session.add(
                    Run(
                        run_id=str(uuid4()),
                        trigger_id=trigger.trigger_id,
                        task_id=trigger.task_id,
                        occurrence_key=at.isoformat(),
                        state="expired" if expired else "queued",
                        created_at=now,
                        finished_at=now if expired else None,
                    )
                )
            await session.commit()

    async def prepare_notifications(self, project, now=None):
        """Pure deterministic execution: never infer analysis completion from a reminder."""
        now = now or datetime.utcnow()
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(Run)
                        .join(Task)
                        .where(
                            Task.project_id == project,
                            Run.state == "queued",
                        )
                        .order_by(Run.created_at)
                        .limit(50)
                    )
                )
                .scalars()
                .all()
            )
            for run in rows:
                task = (
                    await session.execute(
                        select(Task).where(Task.task_id == run.task_id).with_for_update()
                    )
                ).scalar_one()
                trigger = await session.get(Trigger, run.trigger_id)
                valid = (
                    trigger.enabled
                    and task.status not in {"completed", "cancelled"}
                    and definition_hash(task) == trigger.definition_hash
                )
                state = "succeeded" if valid else "cancelled"
                claimed = await session.execute(
                    update(Run)
                    .where(Run.run_id == run.run_id, Run.state == "queued")
                    .values(
                        state=state,
                        task_version=task.version,
                        attempts=Run.attempts + 1,
                        finished_at=now,
                        result={"action": "remind"},
                    )
                )
                if claimed.rowcount != 1 or not valid:
                    continue
                session.add(
                    Outbox(
                        message_id=str(uuid4()),
                        run_id=run.run_id,
                        task_id=task.task_id,
                        trigger_id=trigger.trigger_id,
                        recipient=trigger.recipient,
                        content=f"事项提醒：{task.goal}\n{trigger.instructions}",
                        state="pending",
                        created_at=now,
                        available_at=now,
                    )
                )
            await session.commit()

    async def claim_notification(self, project, now=None):
        now = now or datetime.utcnow()
        async with self.session_factory() as session:
            # An interrupted send is ambiguous; never blindly replay a side effect.
            ids = select(Task.task_id).where(Task.project_id == project)
            await session.execute(
                update(Outbox)
                .where(Outbox.task_id.in_(ids), Outbox.state == "sending", Outbox.lease_until < now)
                .values(state="unknown")
            )
            row = (
                await session.execute(
                    select(Outbox)
                    .join(Task)
                    .where(
                        Task.project_id == project,
                        Outbox.state == "pending",
                        Outbox.available_at <= now,
                    )
                    .order_by(Outbox.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if row is None:
                await session.commit()
                return None
            token = str(uuid4())
            result = await session.execute(
                update(Outbox)
                .where(Outbox.message_id == row.message_id, Outbox.state == "pending")
                .values(
                    state="sending",
                    lease_token=token,
                    lease_until=now + timedelta(seconds=90),
                    attempts=Outbox.attempts + 1,
                )
                .returning(Outbox)
            )
            claimed = result.scalar_one_or_none()
            await session.commit()
            return record(claimed) if claimed else None

    async def deliver(self, project, claimed, adapter, *, now=None):
        """Hold the task lock across bounded I/O to serialize human cancellation.

        A cancellation committed before admission prevents sending. If the send was
        admitted first, cancellation cannot recall an already dispatched message.
        """
        import asyncio

        async with self.session_factory() as session:
            task = (
                await session.execute(
                    select(Task)
                    .where(Task.task_id == claimed["task_id"], Task.project_id == project)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if task is None:
                return
            # SQLite has no row-level FOR UPDATE; a no-op write provides the same fence.
            await session.execute(
                update(Task).where(Task.task_id == task.task_id).values(updated_at=task.updated_at)
            )
            row = await session.get(Outbox, claimed["message_id"])
            trigger = await session.get(Trigger, claimed["trigger_id"])
            if row.state != "sending" or row.lease_token != claimed["lease_token"]:
                return
            if row.lease_until is None or row.lease_until < (now or datetime.utcnow()):
                row.state = "unknown"
            elif (
                not trigger.enabled
                or task.status in {"completed", "cancelled"}
                or definition_hash(task) != trigger.definition_hash
            ):
                row.state = "cancelled"
            else:
                try:
                    async with asyncio.timeout(30):
                        # Adapter revalidates the authoritative account binding before I/O.
                        row.state = await adapter(task, trigger, row)
                    if row.state not in {"inbox_saved", "provider_accepted", "rejected", "unknown"}:
                        row.state = "unknown"
                except Exception:
                    row.state = "unknown"
            await session.commit()
