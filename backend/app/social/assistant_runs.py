"""Personal delegation records; execution and cancellation reuse workflow runtime."""

import asyncio
import json
import os
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from app.agent.workflow.registry import active_workflow_registry
from app.social.assistant_request import require_assistant_request
from app.tools.scheduled_tasks.session_identity import resolve_task_user
from app.utils.path_config import get_data_registry, resolve_agent_path

_LIVE_TASKS = set()
managed_delegation = ContextVar("managed_assistant_delegation", default=None)
TERMINAL = {"succeeded", "failed", "cancelled", "partial"}


def _now():
    return datetime.now(UTC).isoformat()


class AssistantRunService:
    def __init__(self, root=None, registry=None):
        self.root = (
            resolve_agent_path(root) if root is not None else get_data_registry() / "assistant_runs"
        )
        self.registry = registry or active_workflow_registry

    def _directory(self, project, owner):
        return self.root / sha256(f"{project}\0{owner}".encode()).hexdigest()

    def _path(self, project, owner, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"delegation_[0-9a-f]{32}", run_id):
            raise ValueError("无效的委派运行 ID")
        return self._directory(project, owner) / f"{run_id}.json"

    def get(self, project, owner, run_id):
        path = self._path(project, owner, run_id)
        if not path.is_file():
            raise ValueError("未找到本人的委派运行")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, project, owner, record):
        path = self._path(project, owner, record["run_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, default=str))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    async def inspect(self, project, owner, record):
        view = {key: value for key, value in record.items() if key != "result"}
        if record["status"] not in TERMINAL:
            active = await self.registry.is_active(record["run_id"])
            if not active:
                view["status"] = "unknown"
                view["notice"] = "没有可确认的活动执行器；不能据此判定完成，未自动重跑"
        return view

    async def command(self, context, *, action, run_id=None, message=None, offset=0, limit=20):
        from config.settings import settings

        user = await resolve_task_user(context)
        project, owner = settings.project_id, user.id
        if action not in {"list", "get", "result", "cancel", "steer"}:
            raise ValueError("不支持的委派操作")
        if action == "list":
            paths = sorted(
                self._directory(project, owner).glob("delegation_*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            records = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in paths[offset : offset + min(limit, 50)]
            ]
            return {"runs": [await self.inspect(project, owner, record) for record in records]}
        record = self.get(project, owner, run_id)
        if action in {"cancel", "steer"}:
            require_assistant_request(context.session_id)
            if getattr(context, "scheduled_task_context", None):
                raise PermissionError("后台任务不能新增委派指令")
            if record["status"] in TERMINAL:
                raise ValueError("该运行已经结束，请读取结果；后续修改需显式复用子会话")
            if action == "cancel":
                accepted = await self.registry.cancel(run_id, reason="assistant_user_cancelled")
            else:
                from app.agent.runtime.steering import steering_registry

                if not isinstance(message, str) or not message.strip() or len(message) > 20000:
                    raise ValueError("补充要求须为非空文本且不超过20000字符")
                if record["kind"] != "child" or not record.get("child_session_id"):
                    raise ValueError("该运行暂不支持补充要求；不要重启或伪造已受理")
                accepted = await steering_registry.add_input(record["child_session_id"], message)
            return {
                "run_id": run_id,
                "accepted": accepted,
                "status": f"{action}_requested" if accepted else "not_accepted",
                "notice": "受理不等于已停止或已处理；请再次查询真实状态",
            }
        if action == "result":
            if "result" not in record:
                return {
                    "run": await self.inspect(project, owner, record),
                    "result_available": False,
                }
            serialized = json.dumps(record["result"], ensure_ascii=False, default=str)
            size = min(limit, 20000)
            return {
                "run_id": run_id,
                "status": record["status"],
                "result_available": True,
                "content": serialized[offset : offset + size],
                "offset": offset,
                "total_chars": len(serialized),
                "has_more": offset + size < len(serialized),
            }
        return {"run": await self.inspect(project, owner, record)}

    async def launch(self, context, execute, kwargs, *, kind):
        from config.settings import settings

        user = await resolve_task_user(context)
        request = require_assistant_request(context.session_id)
        if getattr(context, "scheduled_task_context", None):
            raise PermissionError("后台任务不能新增用户委派")
        project, owner = settings.project_id, user.id
        kwargs = dict(kwargs)
        background = bool(kwargs.pop("run_in_background", False))
        if kwargs.get("background_task_id") or kwargs.get("cancel_background_task"):
            raise ValueError("查询或停止委派请使用 manage_assistant_runs")
        run_id = "delegation_" + uuid4().hex
        record = {
            "run_id": run_id,
            "kind": kind,
            "status": "running",
            "source_session_id": context.session_id,
            "source_request_id": request.request_id,
            "target_mode": kwargs.get("target_mode"),
            "goal": str(
                kwargs.get("goal")
                or kwargs.get("task_description")
                or (kwargs.get("workflow") or {}).get("goal")
                or "工作流委派"
            )[:500],
            "created_at": _now(),
            "updated_at": _now(),
        }
        if kind == "child":
            kwargs = self.child_arguments(project, owner, record, kwargs)
        self._save(project, owner, record)
        gate = asyncio.Event()
        entered = asyncio.Event()

        async def run():
            token = managed_delegation.set((self, project, owner, record))
            try:
                entered.set()
                await gate.wait()
                result = await execute(context=context, **kwargs)
                record["result"] = result
                status = result.get("status") if isinstance(result, dict) else None
                record["status"] = (
                    status
                    if status in TERMINAL
                    else "failed"
                    if isinstance(result, dict) and result.get("success") is False
                    else "succeeded"
                )
                return {
                    **result,
                    "metadata": {**(result.get("metadata") or {}), "assistant_run_id": run_id},
                }
            except asyncio.CancelledError:
                record["status"] = "cancelled"
                raise
            except Exception:
                record["status"] = "failed"
                raise
            finally:
                managed_delegation.reset(token)
                record["updated_at"] = _now()
                try:
                    self._save(project, owner, record)
                finally:
                    await self.registry.unregister(run_id)

        task = asyncio.create_task(run())

        class CancellationHandle:
            async def cancel(self, *, reason):
                task.cancel()

        try:
            await self.registry.register(
                run_id, CancellationHandle(), session_id=context.session_id
            )
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await self.registry.unregister(run_id)
            record["status"] = "failed"
            self._save(project, owner, record)
            raise
        gate.set()
        _LIVE_TASKS.add(task)

        def finished(done):
            _LIVE_TASKS.discard(done)
            if not done.cancelled():
                done.exception()

        task.add_done_callback(finished)
        # Do not expose a handle before the coroutine can persist cancellation.
        try:
            await entered.wait()
        except asyncio.CancelledError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        if background:
            return {
                "success": True,
                "status": "async_launched",
                "data": {"run_id": run_id},
                "summary": "委派已受理，使用 manage_assistant_runs 查询实际进度和结果",
            }
        return await task

    def child_arguments(self, project, owner, record, kwargs):
        kwargs = dict(kwargs)
        supplied_session = kwargs.get("session_id")
        if supplied_session:
            paths = self._directory(project, owner).glob("delegation_*.json")
            records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
            if not any(supplied_session in item.get("child_sessions", []) for item in records):
                raise PermissionError("子会话不属于本人的委派记录")
        kwargs["force_new_session"] = not bool(supplied_session)
        prior_callback = kwargs.get("_on_session_started")

        def started(session_id):
            sessions = record.setdefault("child_sessions", [])
            if session_id not in sessions:
                sessions.append(session_id)
            if record["kind"] == "child":
                record["child_session_id"] = session_id
            self._save(project, owner, record)
            if prior_callback:
                prior_callback(session_id)

        kwargs["_on_session_started"] = started
        return kwargs
