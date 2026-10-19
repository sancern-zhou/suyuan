"""One owner-scoped schedule interface over the durable reminder and job engines."""

import json
from datetime import UTC, datetime
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.social.assistant_followup_models import AssistantOutboxDB as Outbox
from app.social.assistant_followup_models import AssistantRunDB as Run
from app.social.assistant_followup_models import AssistantTriggerDB as Trigger
from app.social.assistant_followups import (
    AssistantFollowupService,
    record,
    validate_reminder_recipient,
)
from app.social.assistant_schedule import definition_hash, normalize_schedule
from app.social.assistant_task_models import AssistantTaskDB as Matter
from app.social.assistant_tasks import TaskConflict, TaskNotFound


class PlanSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^(once|interval|cron|feedback)$")
    run_at: str | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=525600)
    cron: str | None = None
    timezone_name: str = "Asia/Shanghai"

    def normalized(self):
        return normalize_schedule(**self.model_dump())

    @model_validator(mode="after")
    def validate_parameters(self):
        expected = {"once": "run_at", "interval": "interval_minutes", "cron": "cron"}
        required = expected.get(self.kind)
        for field in ("run_at", "interval_minutes", "cron"):
            if (getattr(self, field) is not None) != (field == required):
                raise ValueError(f"{self.kind} 仅接受其对应时间参数")
        self.normalized()
        return self


class PlanChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str | None = Field(default=None, min_length=1, max_length=4000)
    schedule: PlanSchedule | None = None


class PlanCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern="^(create|list|get|update|pause|resume|cancel|history|results)$")
    plan_id: str | None = None
    expected_revision: str | None = None
    purpose: str | None = Field(default=None, pattern="^(remind|followup|execute)$")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str | None = Field(default=None, min_length=1, max_length=4000)
    task_id: str | None = None
    expected_version: int | None = Field(default=None, ge=1)
    schedule: PlanSchedule | None = None
    execution_mode: str | None = None
    changes: PlanChanges | None = None
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_action(self):
        if self.action == "create":
            if not self.purpose or not self.instructions or self.schedule is None:
                raise ValueError("创建计划需要 purpose、instructions 和 schedule")
            if self.purpose == "followup" and (not self.task_id or self.expected_version is None):
                raise ValueError("事项跟进需要真实 task_id 和 expected_version")
            if self.purpose == "execute" and self.task_id:
                raise ValueError("后台执行不接受事项 ID")
            if self.task_id and self.expected_version is None:
                raise ValueError("绑定已有事项需要查询得到的 expected_version")
            if (self.purpose == "execute") != bool(self.execution_mode):
                raise ValueError("后台执行必须指定执行模式，提醒和跟进不接受执行模式")
            if self.schedule.kind == "feedback" and self.purpose != "followup":
                raise ValueError("反馈触发仅用于已授权的事项跟进")
        elif self.action != "list" and not self.plan_id:
            raise ValueError("请先查询计划，提供真实 plan_id")
        if self.action in {"update", "pause", "resume", "cancel"} and not self.expected_revision:
            raise ValueError("请提供查询得到的 expected_revision")
        if self.action == "update" and (
            self.changes is None or not self.changes.model_dump(exclude_none=True)
        ):
            raise ValueError("修改需要非空 changes")
        if self.changes is not None and self.action != "update":
            raise ValueError("只有 update 接受 changes")
        if self.action != "create" and any(
            getattr(self, field) is not None
            for field in (
                "purpose",
                "title",
                "instructions",
                "task_id",
                "expected_version",
                "schedule",
                "execution_mode",
            )
        ):
            raise ValueError("修改计划请使用 changes，其他操作不接受创建参数")
        return self


def revision(value):
    return sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:24]


class AssistantPlanService(AssistantFollowupService):
    """IDs and views are unified; engines keep sole ownership of execution state."""

    @staticmethod
    def _job_service():
        from app.scheduled_tasks.service import get_scheduled_task_service

        return get_scheduled_task_service()

    @staticmethod
    def _job_view(task):
        data = task.model_dump(mode="json")
        return {
            "plan_id": f"execution:{task.task_id}",
            "purpose": "execute",
            "title": task.name,
            "instructions": task.prompt,
            "execution_mode": task.execution_mode,
            "state": "cancelled"
            if "assistant-plan:cancelled" in task.tags
            else ("active" if task.enabled else "paused"),
            "schedule": {
                "kind": task.schedule_type.value if task.schedule_type else "event",
                "run_at": data["run_at"],
                "interval_minutes": task.interval_minutes,
                "cron": task.cron,
                "timezone_name": task.timezone_name,
            },
            "next_at": data["next_run_at"] if task.enabled else None,
            "revision": revision(data),
            "created_at": data["created_at"],
        }

    @staticmethod
    def _reminder_view(trigger, matter):
        cancelled = trigger.schedule.get("cancelled", False)
        return {
            "plan_id": f"reminder:{trigger.trigger_id}",
            "purpose": "remind" if trigger.action == "remind" else "followup",
            "title": matter.goal,
            "task_id": matter.task_id,
            "instructions": trigger.instructions,
            "state": "cancelled"
            if cancelled
            else (
                "completed"
                if matter.status == "completed"
                else "cancelled"
                if matter.status == "cancelled"
                else "active"
                if trigger.enabled
                else "paused"
            ),
            "schedule": {
                "kind": trigger.kind,
                **{
                    key: value
                    for key, value in trigger.schedule.items()
                    if key not in {"cancelled", "tool_names", "timezone", "run_at"}
                },
                "timezone_name": trigger.schedule["timezone"],
                **(
                    {"run_at": trigger.schedule["run_at"] + "+00:00"}
                    if trigger.kind == "once"
                    else {}
                ),
            },
            "next_at": trigger.next_at if trigger.enabled else None,
            "revision": revision([record(trigger), matter.version, matter.status]),
            "created_at": trigger.created_at,
        }

    async def _reminders(self, project, user):
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(Trigger, Matter)
                    .join(Matter)
                    .where(
                        *self._scope(project, user.id),
                    )
                )
            ).all()
            return [self._reminder_view(trigger, matter) for trigger, matter in rows]

    async def dispatch(self, project, user, command, request=None):
        self._scope(project, user.id)
        if command.action not in {"list", "get", "history", "results"} and request is None:
            raise PermissionError("计划变更需要当前用户交办")
        if command.action == "create":
            return {"plan": await self._create(project, user, command, request)}
        if command.action == "list":
            from app.project_config.loader import load_project_context

            backend_enabled = load_project_context(project).manifest.scheduled_tasks_enabled
            jobs = [
                self._job_view(task)
                for task in (self._job_service().list_tasks(False) if backend_enabled else [])
                if task.owner_user_id == user.id
                and f"project:{project}" in task.tags
                and "assistant-plan" in task.tags
            ]
            plans = jobs + await self._reminders(project, user)
            plans.sort(key=lambda item: (str(item["created_at"]), item["plan_id"]), reverse=True)
            return {
                "plans": plans[command.offset : command.offset + command.limit],
                "total": len(plans),
            }
        if command.plan_id.startswith("execution:"):
            return await self._job_operation(project, user, command)
        if not command.plan_id.startswith("reminder:"):
            raise ValueError("无效的计划 ID，请重新查询")
        return await self._reminder_operation(project, user, command, request)

    async def _create(self, project, user, command, request):
        if request is None:
            raise PermissionError("创建需要当前用户交办")
        if command.purpose == "execute":
            return await self._create_job(project, user, command, request)
        from config.settings import settings

        if not settings.assistant_followups_enabled:
            raise PermissionError("个人提醒与事项跟进尚未启用")
        reminder = command.purpose == "remind"
        standalone = reminder and command.task_id is None
        arguments = dict(
            expected_version=1 if standalone else command.expected_version,
            instructions=command.instructions,
            execution_action="remind" if reminder else "analyze",
            standalone_goal=(command.title or command.instructions) if standalone else None,
            **command.schedule.model_dump(),
        )
        # A competing replay may have committed the standalone matter first.
        try:
            created = await self.create(project, user.id, command.task_id, request, **arguments)
        except IntegrityError:
            created = await self.create(project, user.id, command.task_id, request, **arguments)
        async with self.session_factory() as session:
            trigger = await session.get(Trigger, created["trigger_id"])
            matter = await self._task(session, project, user.id, trigger.task_id)
            return self._reminder_view(trigger, matter)

    @staticmethod
    def _job_schedule(schedule):
        config, due = schedule.normalized()
        values = {
            "schedule_type": schedule.kind,
            "run_at": None,
            "interval_minutes": None,
            "cron": None,
            "timezone_name": schedule.timezone_name,
        }
        if schedule.kind == "once":
            values["run_at"] = due.replace(tzinfo=UTC)
        elif schedule.kind == "interval":
            values["interval_minutes"] = schedule.interval_minutes
        elif schedule.kind == "cron":
            values["cron"] = config["cron"]
        else:
            raise ValueError("后台执行不支持事项反馈触发")
        return values

    async def _create_job(self, project, user, command, request):
        from app.agent.prompts.tool_registry import get_tools_by_mode
        from app.project_config.loader import load_project_context
        from app.scheduled_tasks.models.task import ScheduledTask

        manifest = load_project_context(project).manifest
        if not manifest.scheduled_tasks_enabled:
            raise PermissionError("后台定时任务尚未启用")
        modes = set(manifest.frontend.agent_modes)
        modes.discard("assistant")
        modes.add("office")
        if command.execution_mode not in modes or not get_tools_by_mode(command.execution_mode):
            raise ValueError("请选择当前项目可用的办公或专业执行模式")
        key = revision(
            [
                project,
                user.id,
                request.session_id,
                request.request_id,
                command.model_dump(exclude_none=True),
            ]
        )
        service = self._job_service()
        task_id = f"plan_{key}"
        existing = service.get_task(task_id)
        if existing is not None:
            if existing.owner_user_id != user.id:
                raise PermissionError("计划归属不匹配")
            return self._job_view(existing)
        task = ScheduledTask(
            task_id=task_id,
            name=command.title or command.instructions[:100],
            description=command.instructions,
            prompt=command.instructions,
            execution_mode=command.execution_mode,
            owner_user_id=user.id,
            owner_username=user.username,
            owner_display_name=user.display_name,
            source_session_id=request.session_id,
            source_request_id=request.request_id,
            authorization_message=request.user_message,
            tags=["assistant-plan", f"project:{project}"],
            **self._job_schedule(command.schedule),
        )
        return self._job_view(service.create_task(task))

    async def _job_operation(self, project, user, command):
        service = self._job_service()
        task = service.get_task(command.plan_id.removeprefix("execution:"))
        # Personal assistant access never inherits the administrator's global task access.
        if (
            task is None
            or task.owner_user_id != user.id
            or "assistant-plan" not in task.tags
            or f"project:{project}" not in task.tags
        ):
            raise TaskNotFound("计划不存在或无权访问")
        view = self._job_view(task)
        if command.action == "get":
            return {"plan": view}
        if command.action in {"history", "results"}:
            from app.api import scheduled_task_routes as routes

            page = command.offset // command.limit + 1
            if command.action == "history":
                result = await routes.get_task_executions(
                    task.task_id,
                    page=page,
                    page_size=command.limit,
                    limit=None,
                    user=user,
                )
                return {"plan": view, "history": result.model_dump(mode="json")}
            rows, total = service.list_task_results(
                task_id=task.task_id, page=page, page_size=command.limit
            )
            return {
                "plan": view,
                "results": [r.model_dump(mode="json", exclude={"extra"}) for r in rows],
                "total": total,
            }
        if command.expected_revision != view["revision"]:
            raise TaskConflict("计划已变化，请重新查询")
        if view["state"] == "cancelled":
            raise ValueError("已取消的计划不能修改或恢复，请重新交办")
        if command.action == "update":
            if command.changes.instructions is not None:
                task.prompt = command.changes.instructions
                task.description = command.changes.instructions
            if command.changes.schedule is not None:
                data = task.model_dump()
                data.update(self._job_schedule(command.changes.schedule))
                task = type(task).model_validate(data)
        elif command.action in {"pause", "cancel"}:
            task.enabled = False
            task.next_run_at = None
            if command.action == "cancel":
                task.tags.append("assistant-plan:cancelled")
        elif command.action == "resume":
            from app.project_config.loader import load_project_context

            if not load_project_context(project).manifest.scheduled_tasks_enabled:
                raise PermissionError("后台定时任务尚未启用")
            if task.schedule_type.value == "once" and task.run_at <= datetime.now(
                task.run_at.tzinfo
            ):
                raise ValueError("单次计划时间已过，请修改时间或重新交办")
            task.enabled = True
        result = service.update_task(task)
        return {
            "plan": self._job_view(result),
            "in_flight_policy": "已停止后续触发；已开始的执行可能继续，已发出的消息无法撤回",
        }

    async def _reminder_operation(self, project, user, command, request):
        async with self.session_factory() as session:
            trigger = (
                await session.execute(
                    select(Trigger)
                    .join(Matter)
                    .where(
                        *self._scope(project, user.id),
                        Trigger.trigger_id == command.plan_id.removeprefix("reminder:"),
                    )
                )
            ).scalar_one_or_none()
            if trigger is None:
                raise TaskNotFound("计划不存在或无权访问")
            matter = await self._task(session, project, user.id, trigger.task_id)
            await session.refresh(trigger)
            view = self._reminder_view(trigger, matter)
            if command.action == "get":
                return {"plan": view}
            if command.action in {"history", "results"}:
                results = {"plan": view}
                for name, model in (("runs", Run), ("notifications", Outbox)):
                    rows = (
                        (
                            await session.execute(
                                select(model)
                                .where(
                                    model.trigger_id == trigger.trigger_id,
                                )
                                .order_by(model.created_at.desc())
                                .offset(command.offset)
                                .limit(command.limit)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    results[name] = [record(row) for row in rows]
                return results
            if view["revision"] != command.expected_revision:
                raise TaskConflict("计划已变化，请重新查询")
            if view["state"] in {"cancelled", "completed"}:
                raise ValueError("已取消或结束的计划不能恢复，请重新交办")
            if request is None:
                raise PermissionError("修改需要当前用户交办")
            changed = await session.execute(
                update(Matter)
                .where(
                    Matter.task_id == matter.task_id,
                    Matter.version == matter.version,
                )
                .values(version=matter.version + 1, updated_at=datetime.utcnow())
            )
            if changed.rowcount != 1:
                raise TaskConflict("事项已变化，请重新查询")
            await session.execute(
                update(Run)
                .where(
                    Run.trigger_id == trigger.trigger_id,
                    Run.state.in_(["queued", "running"]),
                )
                .values(state="cancelled", finished_at=datetime.utcnow())
            )
            await session.execute(
                update(Outbox)
                .where(
                    Outbox.trigger_id == trigger.trigger_id,
                    Outbox.state.in_(["pending", "sending"]),
                )
                .values(state="cancelled")
            )
            if command.action in {"resume", "update"}:
                validate_reminder_recipient(request, user.id)
                from config.settings import settings

                if not settings.assistant_followups_enabled or (
                    trigger.action == "analyze" and not settings.assistant_analysis_enabled
                ):
                    raise PermissionError("对应后台能力尚未启用")
                if command.action == "update" and command.changes.instructions is not None:
                    trigger.instructions = command.changes.instructions
                if command.action == "update" and command.changes.schedule is not None:
                    schedule = command.changes.schedule
                else:
                    config = trigger.schedule
                    schedule = PlanSchedule(
                        kind=trigger.kind,
                        run_at=(config["run_at"] + "+00:00") if trigger.kind == "once" else None,
                        interval_minutes=config.get("interval_minutes"),
                        cron=config.get("cron"),
                        timezone_name=config["timezone"],
                    )
                if schedule.kind == "feedback" and trigger.action != "analyze":
                    raise ValueError("普通提醒不能改成反馈分析")
                config, due = schedule.normalized()
                if trigger.action == "analyze":
                    config["tool_names"] = trigger.schedule.get("tool_names", [])
                trigger.kind, trigger.schedule, trigger.next_at = schedule.kind, config, due
                if command.action == "resume":
                    trigger.enabled = True
                trigger.definition_hash = definition_hash(matter)
                trigger.grant_session_id = request.session_id
                trigger.grant_request_id = request.request_id
                trigger.grant_message = request.user_message
                trigger.recipient = request.delivery_user_id
            else:
                trigger.enabled = False
                trigger.next_at = None
                if command.action == "cancel":
                    trigger.schedule = {**trigger.schedule, "cancelled": True}
            session.add(
                self._event(
                    matter.task_id,
                    matter.version,
                    f"plan_{command.action}",
                    request,
                    {"plan_id": command.plan_id},
                )
            )
            await session.commit()
            return {
                "plan": self._reminder_view(trigger, matter),
                "in_flight_policy": "待执行和待投递已撤销；已发出的消息无法撤回",
            }
