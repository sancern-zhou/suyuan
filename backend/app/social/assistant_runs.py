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
# 进程内登记：源会话 → 后台委派 task。用于会话运行时在交付边界等待
# 委派完成并把结果作为工具观察注入（参考 _LIVE_TASKS 的进程内语义：
# 进程重启后登记丢失，等待自然退化为"无待完成委派"）。
_PENDING_BY_SESSION: dict[str, set] = {}
managed_delegation = ContextVar("managed_assistant_delegation", default=None)
TERMINAL = {"succeeded", "failed", "cancelled", "partial"}


def _now():
    return datetime.now(UTC).isoformat()


def background_runs_view(session_id: str) -> list[dict]:
    """源会话在跑的后台委派概览（不含结果），供会话快照/状态卡使用。"""
    view = []
    for task in _PENDING_BY_SESSION.get(session_id) or ():
        record = getattr(task, "_assistant_run_record", None) or {}
        view.append(
            {
                "run_id": record.get("run_id"),
                "kind": record.get("kind"),
                "status": record.get("status"),
                "goal": record.get("goal"),
                "target_mode": record.get("target_mode"),
            }
        )
    return view


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

    def pending_background_count(self, session_id: str) -> int:
        """源会话当前仍在运行的后台委派数（进程内登记）。"""
        return len(_PENDING_BY_SESSION.get(session_id) or ())

    async def wait_for_session_runs(self, session_id: str, timeout: float) -> tuple[list[dict], int]:
        """等待该会话的后台委派完成，返回 (已完成结果列表, 仍在运行数)。

        结果取自进程内 record 引用（状态由 run() 就地更新），不落盘读取；
        超时后仅返回已完成部分，未完成者留给调用方决定后续。
        """
        tasks = set(_PENDING_BY_SESSION.get(session_id) or ())
        if not tasks:
            return [], 0
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        results = []
        for task in done:
            record = getattr(task, "_assistant_run_record", None) or {}
            results.append(
                {
                    "run_id": record.get("run_id"),
                    "kind": record.get("kind"),
                    "status": record.get("status"),
                    "target_mode": record.get("target_mode"),
                    "goal": record.get("goal"),
                    "result": record.get("result"),
                }
            )
        return results, len(pending)

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
        if background:
            # 供源会话运行时在交付边界等待并读取结果（wait_for_session_runs）。
            task._assistant_run_record = record
            _PENDING_BY_SESSION.setdefault(context.session_id, set()).add(task)

        def finished(done):
            _LIVE_TASKS.discard(done)
            record = getattr(done, "_assistant_run_record", None)
            if record is not None:
                session_tasks = _PENDING_BY_SESSION.get(
                    str(record.get("source_session_id") or "")
                )
                if session_tasks is not None:
                    session_tasks.discard(done)
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
