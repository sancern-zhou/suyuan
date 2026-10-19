"""Durable task replies; Web transcript writes and receipt state commit together."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.social.assistant_notification_models import AssistantNotificationDB as Notice

logger = structlog.get_logger(__name__)
JOB_ID = "assistant-result-replies"


class AssistantNotificationService:
    def __init__(self, session_factory=None, catalog=None, adapter=None):
        if session_factory is None:
            from app.db.database import async_session

            session_factory = async_session
        if catalog is None:
            from app.conversations.dependencies import get_conversation_catalog

            catalog = get_conversation_catalog()
        self.session_factory = session_factory
        self.catalog = catalog
        self.adapter = adapter

    @staticmethod
    def record(row):
        return {
            "message_id": row.message_id,
            "source_session_id": row.source_session_id,
            "content": row.content,
            "created_at": row.created_at,
            "read_at": row.read_at,
            "delivery_state": row.state,
            **row.data,
        }

    async def enqueue(
        self, *, message_id, project, owner, source_session_id, recipient, content, data
    ):
        async with self.session_factory() as session:
            existing = await session.get(Notice, message_id)
            if existing:
                if (existing.project_id, existing.owner_user_id) != (project, owner):
                    raise PermissionError("通知归属不匹配")
                return message_id
            session.add(
                Notice(
                    message_id=message_id,
                    project_id=project,
                    owner_user_id=owner,
                    source_session_id=source_session_id,
                    recipient=recipient,
                    content=content,
                    data=data,
                    state="pending",
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.get(Notice, message_id)
                if not existing or (existing.project_id, existing.owner_user_id) != (
                    project,
                    owner,
                ):
                    raise
        return message_id

    async def enqueue_execution(self, project, task, execution):
        from app.scheduled_tasks.models import ExecutionStatus

        if (
            "assistant-plan" not in task.tags
            or f"project:{project}" not in task.tags
            or not task.assistant_recipient
            or not task.source_session_id
            or not task.owner_user_id
            or task.owner_user_id == "system"
            or execution.status in {ExecutionStatus.PENDING, ExecutionStatus.RUNNING}
        ):
            return
        message_id = "execution:" + execution.execution_id
        successful = execution.status == ExecutionStatus.SUCCESS
        labels = {
            "success": "已执行完成",
            "failed": "执行失败",
            "timeout": "执行超时",
            "cancelled": "执行已取消",
        }
        summary = next(
            (s.agent_response for s in reversed(execution.steps) if s.agent_response), ""
        )
        if not successful:
            summary = "本次任务未完成，请查看执行记录后决定是否重试。"
        elif not summary:
            summary = "任务已执行完成，详细过程请查看执行记录。"
        content = f"任务「{task.name}」{labels.get(execution.status.value, execution.status.value)}。\n\n{summary[:16000]}"
        data = {
            "kind": "assistant_execution_result",
            "execution_id": execution.execution_id,
            "execution_session_id": execution.session_id,
            "execution_status": execution.status.value,
            "scheduled_task_id": task.task_id,
            "task_id": task.assistant_matter_id,
        }
        from app.db.models.scheduled_task_result_db import ScheduledTaskResultDB

        async with self.session_factory() as session:
            result = await session.get(ScheduledTaskResultDB, execution.execution_id)
            data["media"] = (
                list(dict.fromkeys((result.document_paths or []) + (result.image_paths or [])))
                if result and successful
                else []
            )
        await self.enqueue(
            message_id=message_id,
            project=project,
            owner=task.owner_user_id,
            source_session_id=task.source_session_id,
            recipient=task.assistant_recipient,
            content=content,
            data=data,
        )
        await self._update_matter(task, message_id, successful)
        return message_id

    async def publish_web(
        self, session, *, message_id, project, owner, source_session_id, recipient, content, data
    ):
        """Share the reminder transaction so cancellation and reply stay atomic."""
        async with session.begin_nested():
            return await self._publish_web(
                session,
                message_id=message_id,
                project=project,
                owner=owner,
                source_session_id=source_session_id,
                recipient=recipient,
                content=content,
                data=data,
            )

    async def _publish_web(
        self, session, *, message_id, project, owner, source_session_id, recipient, content, data
    ):
        row = (
            await session.execute(
                select(Notice).where(Notice.message_id == message_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            row = Notice(
                message_id=message_id,
                project_id=project,
                owner_user_id=owner,
                source_session_id=source_session_id,
                recipient=recipient,
                content=content,
                data=data,
                state="pending",
                created_at=datetime.utcnow(),
            )
            session.add(row)
            await session.flush()
        if (row.project_id, row.owner_user_id, row.source_session_id) != (
            project,
            owner,
            source_session_id,
        ):
            raise PermissionError("通知归属不匹配")
        if row.state == "pending":
            await self._append_web_reply(session, row)
            row.state = "inbox_saved"
            await session.flush()
        return row.state

    async def _update_matter(self, task, message_id, successful):
        from app.social.assistant_task_models import (
            AssistantTaskDB as Matter,
            AssistantTaskEventDB as Event,
        )
        from app.social.assistant_tasks import AssistantTaskService
        from app.social.assistant_request import AssistantRequest

        if not task.assistant_matter_id:
            return
        async with self.session_factory() as session:
            notice = (
                await session.execute(
                    select(Notice).where(Notice.message_id == message_id).with_for_update()
                )
            ).scalar_one()
            if "matter_update" in notice.data:
                return
            matter = (
                await session.execute(
                    select(Matter)
                    .where(
                        Matter.task_id == task.assistant_matter_id,
                        Matter.project_id == notice.project_id,
                        Matter.owner_user_id == notice.owner_user_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            version = task.assistant_matter_version
            if matter and matter.version != version:
                last_event = (
                    await session.execute(
                        select(Event).where(
                            Event.task_id == matter.task_id,
                            Event.version == matter.version,
                        )
                    )
                ).scalar_one_or_none()
                if (
                    last_event
                    and last_event.kind == "execution_result"
                    and last_event.changes.get("scheduled_task_id") == task.task_id
                ):
                    version = matter.version
            changes = {
                "status": "waiting_input" if successful else "blocked",
                "result_summary": notice.content,
                "next_step": "请验收执行结果，确认是否达到事项完成条件"
                if successful
                else "请查看执行记录，补充信息或重新安排执行",
            }
            changed = await session.execute(
                update(Matter)
                .where(
                    Matter.task_id == task.assistant_matter_id,
                    Matter.project_id == notice.project_id,
                    Matter.owner_user_id == notice.owner_user_id,
                    Matter.version == version,
                    Matter.status.notin_(["completed", "cancelled"]),
                )
                .values(**changes, version=Matter.version + 1, updated_at=datetime.utcnow())
            )
            applied = changed.rowcount == 1
            if applied:
                session.add(
                    AssistantTaskService._event(
                        task.assistant_matter_id,
                        version + 1,
                        "execution_result",
                        AssistantRequest(task.source_session_id, message_id, ""),
                        {
                            **changes,
                            "scheduled_task_id": task.task_id,
                            "execution_id": notice.data["execution_id"],
                        },
                    )
                )
            notice.data = {**notice.data, "matter_update": "applied" if applied else "superseded"}
            await session.commit()

    async def list(self, project, owner, *, limit=20, offset=0, unread_only=False):
        async with self.session_factory() as session:
            scope = [Notice.project_id == project, Notice.owner_user_id == owner]
            unread = (
                await session.execute(
                    select(func.count()).select_from(Notice).where(*scope, Notice.read_at.is_(None))
                )
            ).scalar_one()
            if unread_only:
                scope.append(Notice.read_at.is_(None))
            rows = (
                (
                    await session.execute(
                        select(Notice)
                        .where(*scope)
                        .order_by(Notice.created_at.desc(), Notice.message_id)
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return {"notifications": [self.record(row) for row in rows], "unread_count": unread}

    async def mark_read(self, project, owner, message_id):
        async with self.session_factory() as session:
            row = await session.get(Notice, message_id)
            if not row or (row.project_id, row.owner_user_id) != (project, owner):
                from app.social.assistant_tasks import TaskNotFound

                raise TaskNotFound("通知不存在或无权访问")
            row.read_at = row.read_at or datetime.utcnow()
            await session.commit()

    async def deliver(self, message_id):
        from app.conversations import ConversationSource
        from app.social.web_assistant import web_assistant_recipient

        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(Notice).where(Notice.message_id == message_id).with_for_update()
                )
            ).scalar_one()
            if row.state != "pending":
                return row.state
            claimed = await session.execute(
                update(Notice)
                .where(Notice.message_id == message_id, Notice.state == "pending")
                .values(state="sending", lease_until=datetime.utcnow() + timedelta(seconds=90))
            )
            if claimed.rowcount != 1:
                await session.rollback()
                return "sending"
            source = await self.catalog.find(row.source_session_id)
            if not source or source.owner_user_id != row.owner_user_id:
                row.state = "rejected"
                await session.commit()
                return row.state
            if row.recipient.startswith("web:"):
                if (
                    source.source != ConversationSource.WEB
                    or row.recipient != web_assistant_recipient(row.owner_user_id)
                ):
                    row.state = "rejected"
                else:
                    await self._append_web_reply(session, row)
                    row.state = "inbox_saved"
                await session.commit()
                return row.state
            content, recipient, owner, source_id = (
                row.content,
                row.recipient,
                row.owner_user_id,
                row.source_session_id,
            )
            media = row.data.get("media", [])
            await session.commit()
        if self.adapter is None:
            from app.social.assistant_reminder_delivery import deliver_reminder

            adapter = deliver_reminder
        else:
            adapter = self.adapter
        state = "unknown"
        try:
            async with asyncio.timeout(30):
                state = await adapter(
                    SimpleNamespace(task_id=message_id, owner_user_id=owner),
                    SimpleNamespace(grant_session_id=source_id),
                    SimpleNamespace(
                        message_id=message_id,
                        recipient=recipient,
                        content=content,
                        media=media,
                        kind="assistant_execution_result",
                    ),
                )
            if state not in {"inbox_saved", "provider_accepted", "rejected", "unknown"}:
                state = "unknown"
        except Exception:
            logger.exception("assistant_result_delivery_failed", message_id=message_id)
        async with self.session_factory() as session:
            await session.execute(
                update(Notice)
                .where(Notice.message_id == message_id, Notice.state == "sending")
                .values(state=state, lease_until=None)
            )
            await session.commit()
        return state

    @staticmethod
    async def _append_web_reply(session, row):
        from app.db.models_session import SessionDB, SessionMessageDB
        from urllib.parse import quote

        source = (
            await session.execute(
                select(SessionDB)
                .where(SessionDB.session_id == row.source_session_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if source is None:
            raise ValueError("source_session_missing")
        result_session = row.data.get("execution_session_id")
        if result_session:
            row.content += f"\n\n[查看执行详情与附件](/session/{quote(result_session, safe='')})"
        sequence = (
            await session.execute(
                select(func.max(SessionMessageDB.sequence_number)).where(
                    SessionMessageDB.session_id == row.source_session_id
                )
            )
        ).scalar_one()
        message = SessionMessageDB(
            session_id=row.source_session_id,
            role="assistant",
            msg_type="final",
            content=row.content,
            data={"answer": row.content, "notification_id": row.message_id, **row.data},
            sequence_number=(sequence if sequence is not None else -1) + 1,
            timestamp=row.created_at,
            created_at=datetime.utcnow(),
        )
        session.add(message)
        await session.flush()
        row.data = {**row.data, "transcript_message_id": f"msg_{message.id}"}
        source.updated_at = datetime.utcnow()

    async def tick(self, project, job_service):
        from app.db.models.scheduled_task_execution_db import ScheduledTaskExecutionDB as Execution
        from app.scheduled_tasks.models import TaskExecution

        try:
            jobs = {
                t.task_id: t
                for t in job_service.list_tasks(False)
                if "assistant-plan" in t.tags
                and f"project:{project}" in t.tags
                and t.assistant_recipient
            }
            async with self.session_factory() as session:
                # Reconcile the crash window between terminal execution persistence and enqueue.
                rows = (
                    (
                        await session.execute(
                            select(Execution.data)
                            .outerjoin(
                                Notice, Notice.message_id == "execution:" + Execution.execution_id
                            )
                            .where(
                                Execution.task_id.in_(jobs),
                                Execution.status.in_(["success", "failed", "timeout", "cancelled"]),
                                Notice.message_id.is_(None),
                            )
                            .order_by(Execution.started_at)
                            .limit(20)
                        )
                    )
                    .scalars()
                    .all()
                    if jobs
                    else []
                )
                await session.execute(
                    update(Notice)
                    .where(
                        Notice.project_id == project,
                        Notice.state == "sending",
                        Notice.lease_until < datetime.utcnow(),
                    )
                    .values(state="unknown")
                )
                await session.commit()
            for data in rows:
                execution = TaskExecution.model_validate(data)
                await self.enqueue_execution(project, jobs[execution.task_id], execution)
            async with self.session_factory() as session:
                unfinished = (
                    (
                        await session.execute(
                            select(Notice)
                            .where(
                                Notice.project_id == project,
                                Notice.data["matter_update"].as_string().is_(None),
                                Notice.data["task_id"].as_string().is_not(None),
                                Notice.data["kind"].as_string() == "assistant_execution_result",
                            )
                            .limit(20)
                        )
                    )
                    .scalars()
                    .all()
                )
            for notice in unfinished:
                task = jobs.get(notice.data["scheduled_task_id"])
                if task:
                    await self._update_matter(
                        task, notice.message_id, notice.data["execution_status"] == "success"
                    )
            async with self.session_factory() as session:
                ids = (
                    (
                        await session.execute(
                            select(Notice.message_id)
                            .where(Notice.project_id == project, Notice.state == "pending")
                            .order_by(Notice.created_at)
                            .limit(20)
                        )
                    )
                    .scalars()
                    .all()
                )
            for message_id in ids:
                try:
                    await self.deliver(message_id)
                except Exception:
                    logger.exception("assistant_reply_pending", message_id=message_id)
        except Exception:
            logger.exception("assistant_reply_clock_failed")


def start_result_replies(scheduler, project, job_service):
    service = AssistantNotificationService()
    scheduler.add_job(
        service.tick,
        "interval",
        seconds=10,
        id=JOB_ID,
        args=[project, job_service],
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
