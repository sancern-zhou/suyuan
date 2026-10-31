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
    def __init__(self, session_factory=None, catalog=None, adapter=None, transcript_factory=None):
        injected_factory = session_factory
        if session_factory is None:
            from app.db.database import async_session

            session_factory = async_session
        if catalog is None:
            from app.conversations.dependencies import get_conversation_catalog

            catalog = get_conversation_catalog()
        self.session_factory = session_factory
        self.catalog = catalog
        self.adapter = adapter
        if transcript_factory is None:
            from app.db.session_database import session_async_session
            transcript_factory = injected_factory or session_async_session
        self.transcript_factory = transcript_factory

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
            if row.state in {"pending", "sending"}:
                raise ValueError("通知尚在投递，请稍后再标记已读")
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

    async def _append_web_reply(self, session, row):
        from config.settings import settings

        if settings.assistant_schedule_reply_synthesis:
            try:
                synthesized = await self._synthesize_reply(row)
                if synthesized:
                    row.content = synthesized
            except Exception as exc:
                logger.warning(
                    "assistant_reply_synthesis_failed",
                    message_id=row.message_id,
                    error=str(exc),
                )
        async with self.transcript_factory() as transcript:
            if transcript.get_bind().url == session.get_bind().url:
                return await self._append_transcript(session, row)
            # A crash after transcript commit can replay the outbox. The parent
            # lock and notification identity below make that replay idempotent.
            await self._append_transcript(transcript, row)
            await transcript.commit()

    async def _synthesize_reply(self, row) -> str:
        """以助手身份对定时结果做一轮跟进整理，返回面向用户的最终文本。

        通知结果不再直写对话：先进入助手上下文（含绑定事项的目标与完成
        标准），由助手核对、筛选、更新事项并组织汇报；失败时调用方回退
        为原始内容直写。
        """
        from app.agent.react_agent import create_react_agent
        from app.auth.models import CurrentUser
        from app.social.web_assistant import (
            assistant_account_context,
            web_assistant_context,
        )

        user = CurrentUser(id=row.owner_user_id, username=None, display_name=None)
        data = row.data if isinstance(row.data, dict) else {}
        parts = ["后台定时任务已执行完成，请以助手身份向用户汇报。"]
        title = data.get("task_name") or ""
        if title:
            parts.append(f"任务名称：{title}")
        if getattr(row, "task_id", None):
            try:
                from app.social.assistant_task_models import AssistantTaskDB

                async with self.session_factory() as db:
                    matter = await db.get(AssistantTaskDB, row.task_id)
                if matter is not None:
                    parts.append(
                        f"关联事项：目标={matter.goal}；完成标准={matter.completion_criteria}；"
                        f"状态={matter.status}；下一步={matter.next_step or '无'}。"
                    )
            except Exception as exc:
                logger.warning("assistant_reply_matter_lookup_failed", error=str(exc))
        parts.append("执行结果：\n" + (row.content or "")[:4000])
        parts.append(
            "要求：核对结果是否满足完成标准；向用户输出整理后的汇报（关键结论、口径、产物引用、异常与建议）；"
            "不要复述本提示；如事项状态需要更新，调用 manage_assistant_tasks 更新状态与下一步；"
            "最终回复直接面向用户。"
        )
        agent = create_react_agent()
        final_answer = ""
        async for event in agent.analyze(
            "\n".join(parts),
            session_id=row.source_session_id,
            manual_mode="assistant",
            **web_assistant_context(user),
        ):
            if event.get("type") != "agent_finish":
                continue
            payload = event.get("data") if isinstance(event.get("data"), dict) else {}
            candidate = payload.get("answer") or payload.get("final_message") or ""
            if candidate:
                final_answer = str(candidate)
        if not final_answer.strip():
            logger.warning(
                "assistant_reply_synthesis_empty",
                message_id=row.message_id,
                session_id=row.source_session_id,
            )
        return final_answer.strip()

    @staticmethod
    async def _append_transcript(session, row):
        from app.db.models_session import SessionDB, SessionMessageDB
        from urllib.parse import quote

        await session.execute(update(SessionDB).where(
            SessionDB.session_id == row.source_session_id
        ).values(updated_at=SessionDB.updated_at))
        source = (
            await session.execute(
                select(SessionDB)
                .where(SessionDB.session_id == row.source_session_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if source is None:
            raise ValueError("source_session_missing")
        existing = (await session.execute(select(SessionMessageDB).where(
            SessionMessageDB.session_id == row.source_session_id,
            SessionMessageDB.data["notification_id"].as_string() == row.message_id,
        ))).scalar_one_or_none()
        if existing:
            row.content = existing.content
            row.data = {**row.data, "transcript_message_id": f"msg_{existing.id}"}
            return
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
        from app.scheduled_tasks.models import TaskExecution

        try:
            jobs = {
                t.task_id: t
                for t in job_service.list_tasks(False)
                if "assistant-plan" in t.tags
                and f"project:{project}" in t.tags
                and t.assistant_recipient
            }
            rows = await self._unreported_executions(project, jobs) if jobs else []
            async with self.session_factory() as session:
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

    async def _unreported_executions(self, project, jobs):
        from app.db.models.scheduled_task_execution_db import ScheduledTaskExecutionDB as Execution

        # Execution history may live in SESSION_DATABASE_URL, separate from the outbox.
        missing, after = [], None
        while len(missing) < 20:
            async with self.transcript_factory() as db:
                query = select(Execution).where(
                    Execution.task_id.in_(jobs),
                    Execution.status.in_(["success", "failed", "timeout", "cancelled"]),
                )
                if after is not None:
                    query = query.where(Execution.execution_id > after)
                batch = (await db.execute(query.order_by(Execution.execution_id).limit(100))).scalars().all()
            if not batch:
                break
            async with self.session_factory() as db:
                known = set((await db.execute(select(Notice.message_id).where(
                    Notice.project_id == project,
                    Notice.message_id.in_([f"execution:{row.execution_id}" for row in batch]),
                ))).scalars().all())
            missing.extend(row.data for row in batch if f"execution:{row.execution_id}" not in known)
            after = batch[-1].execution_id
            if len(batch) < 100:
                break
        return missing[:20]


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
