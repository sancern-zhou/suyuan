"""Fenced analysis claims, feedback wakeups and transactional result publication."""

import json
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.social.assistant_analysis_agent import validate_output
from app.social.assistant_followup_models import AssistantOutboxDB as Outbox
from app.social.assistant_followup_models import AssistantRunDB as Run
from app.social.assistant_followup_models import AssistantTriggerDB as Trigger
from app.social.assistant_followups import AssistantFollowupService, record
from app.social.assistant_request import AssistantRequest
from app.social.assistant_schedule import definition_hash
from app.social.assistant_task_models import AssistantTaskDB as Task
from app.social.assistant_task_models import AssistantTaskEventDB as Event


async def enqueue_feedback(session, task):
    """Part of the authenticated feedback transaction, not a new authorization."""
    triggers = (
        (
            await session.execute(
                select(Trigger).where(
                    Trigger.task_id == task.task_id,
                    Trigger.enabled.is_(True),
                    Trigger.kind == "feedback",
                    Trigger.action == "analyze",
                )
            )
        )
        .scalars()
        .all()
    )
    for trigger in triggers:
        if trigger.definition_hash != definition_hash(task):
            continue
        await session.execute(
            update(Run)
            .where(Run.trigger_id == trigger.trigger_id, Run.state == "queued")
            .values(state="superseded", finished_at=datetime.utcnow())
        )
        session.add(
            Run(
                run_id=str(uuid4()),
                trigger_id=trigger.trigger_id,
                task_id=task.task_id,
                occurrence_key=f"feedback:{task.version}",
                state="queued",
            )
        )


class AssistantAnalysisQueue(AssistantFollowupService):
    async def claim(self, project, now=None):
        now = now or datetime.utcnow()
        async with self.session_factory() as session:
            candidates = (
                (
                    await session.execute(
                        select(Run)
                        .join(Task)
                        .join(Trigger, Trigger.trigger_id == Run.trigger_id)
                        .where(
                            Task.project_id == project,
                            Run.state == "queued",
                            Trigger.action == "analyze",
                            Trigger.enabled.is_(True),
                            Task.status != "blocked",
                            Task.task_id.notin_(
                                select(Run.task_id).where(Run.state == "running").correlate(None)
                            ),
                        )
                        .order_by(Run.created_at, Run.run_id)
                        .limit(20)
                    )
                )
                .scalars()
                .all()
            )
            for run in candidates:
                task = (
                    await session.execute(
                        select(Task).where(Task.task_id == run.task_id).with_for_update()
                    )
                ).scalar_one()
                await session.execute(
                    update(Task)
                    .where(Task.task_id == task.task_id)
                    .values(updated_at=task.updated_at)
                )
                trigger = await session.get(Trigger, run.trigger_id)
                if task.status == "blocked":
                    continue
                if (
                    task.status in {"completed", "cancelled"}
                    or not trigger.enabled
                    or definition_hash(task) != trigger.definition_hash
                ):
                    await session.execute(
                        update(Run)
                        .where(Run.run_id == run.run_id, Run.state == "queued")
                        .values(state="cancelled", finished_at=now)
                    )
                    continue
                running = (
                    await session.execute(
                        select(Run.run_id)
                        .where(Run.task_id == task.task_id, Run.state == "running")
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if running:
                    continue
                token = str(uuid4())
                changed = await session.execute(
                    update(Run)
                    .where(Run.run_id == run.run_id, Run.state == "queued")
                    .values(
                        state="running",
                        task_version=task.version,
                        lease_token=token,
                        lease_until=now + timedelta(minutes=5),
                        attempts=Run.attempts + 1,
                    )
                )
                if changed.rowcount != 1:
                    continue
                events = (
                    (
                        await session.execute(
                            select(Event)
                            .where(
                                Event.task_id == task.task_id,
                                Event.kind == "feedback",
                                Event.version <= task.version,
                            )
                            .order_by(Event.version.desc())
                            .limit(20)
                        )
                    )
                    .scalars()
                    .all()
                )
                feedback, remaining = [], 12000
                for item in events:
                    if remaining <= 0:
                        break
                    text = item.user_message[: min(6000, remaining)]
                    feedback.append(
                        {
                            "id": f"feedback:{item.version}",
                            "text": text,
                            "truncated": len(text) < len(item.user_message),
                        }
                    )
                    remaining -= len(text)
                claim = {
                    **record(run),
                    "lease_token": token,
                    "task_version": task.version,
                    "task": self._record(task),
                    "trigger": record(trigger),
                    "feedback": list(reversed(feedback)),
                }
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    return None
                return claim
            await session.commit()
            return None

    async def is_active(self, project, claim, now=None):
        async with self.session_factory() as session:
            return (
                await session.execute(
                    select(Run.run_id)
                    .join(Task)
                    .join(Trigger, Trigger.trigger_id == Run.trigger_id)
                    .where(
                        Task.project_id == project,
                        Run.run_id == claim["run_id"],
                        Run.task_id == claim["task_id"],
                        Run.lease_token == claim["lease_token"],
                        Run.state == "running",
                        Run.lease_until > (now or datetime.utcnow()),
                        Task.version == claim["task_version"],
                        Trigger.enabled.is_(True),
                        Task.status.notin_(["completed", "cancelled"]),
                    )
                )
            ).scalar_one_or_none() is not None

    async def recover(self, project, now=None):
        now = now or datetime.utcnow()
        async with self.session_factory() as session:
            expired = (
                (
                    await session.execute(
                        select(Run)
                        .join(Task)
                        .where(
                            Task.project_id == project,
                            Run.state == "running",
                            Run.lease_until <= now,
                        )
                        .limit(50)
                    )
                )
                .scalars()
                .all()
            )
            claims = [record(run) for run in expired]
        for claim in claims:
            await self.finish(project, claim, error="interrupted", now=now)

    async def finish(self, project, claim, *, result=None, error=None, now=None):
        now = now or datetime.utcnow()
        async with self.session_factory() as session:
            task = (
                await session.execute(
                    select(Task)
                    .where(Task.task_id == claim["task_id"], Task.project_id == project)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if task is None:
                return
            await session.execute(
                update(Task).where(Task.task_id == task.task_id).values(updated_at=task.updated_at)
            )
            run = await session.get(Run, claim["run_id"])
            if (
                run is None
                or run.task_id != task.task_id
                or run.state != "running"
                or run.lease_token != claim["lease_token"]
            ):
                return
            trigger = await session.get(Trigger, run.trigger_id)
            run.finished_at = now
            if (
                not trigger.enabled
                or task.status in {"completed", "cancelled"}
                or definition_hash(task) != trigger.definition_hash
            ):
                run.state = "cancelled"
            elif task.version != run.task_version:
                run.state = "superseded"
            elif error or run.lease_until is None or run.lease_until <= now:
                run.state = "failed"
                run.result = {"error": error or "lease_expired"}
                self._notify(
                    session,
                    task,
                    trigger,
                    run,
                    "后台分析本轮未完成，请查看事项记录或重新交办。",
                    "analysis_failed",
                    now,
                )
            else:
                if not isinstance(result, dict) or not isinstance(result.get("observations"), list):
                    raise ValueError("后台分析结果格式不完整")
                evidence = [
                    f"feedback:{item}"
                    for item in (
                        await session.execute(
                            select(Event.version).where(
                                Event.task_id == task.task_id,
                                Event.kind == "feedback",
                                Event.version <= run.task_version,
                            )
                        )
                    ).scalars()
                ]
                evidence += [item["id"] for item in result["observations"]]
                output = validate_output(result.get("output"), evidence)
                run.result = {"output": output, "observations": result["observations"]}
                run.state = "succeeded"
                changes = {
                    "status": "ready" if output["status"] == "progress" else "waiting_input",
                    "next_step": output["next_step"],
                }
                old_version = task.version
                changed = await session.execute(
                    update(Task)
                    .where(Task.task_id == task.task_id, Task.version == old_version)
                    .values(**changes, version=old_version + 1, updated_at=now)
                )
                if changed.rowcount != 1:
                    raise ValueError("事项版本在分析提交时变化")
                session.add(
                    self._event(
                        task.task_id,
                        old_version + 1,
                        "analysis_result",
                        AssistantRequest(trigger.grant_session_id, f"run:{run.run_id}", ""),
                        {**changes, "run_id": run.run_id, "review_status": output["status"]},
                    )
                )
                if output["should_notify"] or output["status"] != "progress":
                    label = {
                        "progress": "持续推进",
                        "waiting_input": "等待补充信息",
                        "ready_for_review": "待验收",
                    }[output["status"]]
                    self._notify(
                        session,
                        task,
                        trigger,
                        run,
                        f"事项分析：{task.goal}\n阶段：{label}\n{output['summary']}\n下一步：{output['next_step']}",
                        json.dumps(
                            [output["status"], output["summary"], output["next_step"]],
                            ensure_ascii=False,
                        ),
                        now,
                    )
            await session.commit()

    @staticmethod
    def _notify(session, task, trigger, run, content, signature, now):
        digest = sha256(signature.encode()).hexdigest()
        if trigger.last_result_hash == digest:
            return
        trigger.last_result_hash = digest
        session.add(
            Outbox(
                message_id=str(uuid4()),
                run_id=run.run_id,
                task_id=task.task_id,
                trigger_id=trigger.trigger_id,
                recipient=trigger.recipient,
                content=content,
                state="pending",
                created_at=now,
                available_at=now,
            )
        )
