"""后台委派终态唤醒：完成即触发源会话整合回复（对齐 ZCode task-notification）。

设计契约见 backend/docs/assistant-delegation-wakeup-plan.md，要点：

- 完成即入账本（委派记录 wake_state）、唤醒走统一 drain 门；模型不再负责轮询，
  ``manage_assistant_runs`` 保留为人工查询通道。
- 活跃回合让路：drain 经 ``cancellation_registry.register`` 排队在跑回合之后，
  同回合的交付边界等待（wait_for_session_runs）优先吸收并就地标记
  ``absorbed_in_turn``；被新用户消息顶掉的唤醒回合按尝试上限重排，
  用户主动 Stop 则丢弃——通知不静默丢失。
- 返回=投递（D5）：通知只带摘要卡 + 缺口 + 产物指针，完整结果仍按需读取；
  合成失败时降级直写摘要卡，结果不滞留。
- 后台事件不能代用户授权：唤醒回合不带 assistant request 上下文，不能续委派。
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import structlog

from config.settings import settings

logger = structlog.get_logger()

# 被用户消息连续顶掉的重试上限；超过后降级为 discarded（可经 manage_assistant_runs 查询）。
WAKE_MAX_ATTEMPTS = 3

# 会话 → 待唤醒委派记录（进程内登记，持有 record 引用；吸收方就地改 wake_state
# 后 drain 侧即时可见）。进程崩溃后磁盘残留 pending 不自动补投（与上游 ZCode
# resume 收口 discarded 的"不静默重放"同语义），由后续 drain/人工查询收口。
_PENDING_WAKES: dict[str, list] = {}
_DRAINING: set[str] = set()
_DRAIN_TASKS: set[asyncio.Task] = set()

_TERMINAL_WAKEABLE = {"succeeded", "failed", "partial"}


def request_delegation_wakeup(record: dict) -> None:
    """委派终态回调入口：入账本并调度 drain（等价 ZCode enqueueRuntimeCommand）。"""
    if not settings.assistant_delegation_wakeup_enabled:
        return
    session_id = str(record.get("source_session_id") or "")
    if not session_id:
        return
    _PENDING_WAKES.setdefault(session_id, []).append(record)
    _schedule_drain(session_id)


def pending_wakeup_count(session_id: str) -> int:
    return len(_PENDING_WAKES.get(session_id) or ())


def _schedule_drain(session_id: str) -> None:
    if session_id in _DRAINING:
        return
    task = asyncio.ensure_future(_drain_session(session_id))
    _DRAIN_TASKS.add(task)
    task.add_done_callback(_DRAIN_TASKS.discard)


async def _drain_session(session_id: str) -> None:
    # 单飞 drain gate：同会话串行；退出沿发现新 pending 再续排（对齐 ZCode
    # drainRuntimeCommandQueue 的 finally 重查语义）。
    if session_id in _DRAINING:
        return
    _DRAINING.add(session_id)
    try:
        while True:
            batch = _take_pending_batch(session_id)
            if not batch:
                return
            try:
                await _run_wake_turn(session_id, batch)
            except asyncio.CancelledError:
                raise
            except Exception:
                # 投递失败（合成/落库异常）：记录留在队首等下一次触发重试，
                # 本轮 drain 结束，避免原地死循环烧模型。
                logger.exception("delegation_wake_turn_failed", session_id=session_id)
                for record in reversed(batch):
                    _requeue_front(session_id, record)
                return
    finally:
        _DRAINING.discard(session_id)
        if _PENDING_WAKES.get(session_id):
            _schedule_drain(session_id)


def _take_pending_batch(session_id: str) -> list:
    records = _PENDING_WAKES.get(session_id) or []
    batch = list(records)
    records.clear()
    return batch


def _requeue_front(session_id: str, record: dict) -> None:
    _PENDING_WAKES.setdefault(session_id, []).insert(0, record)


async def _run_wake_turn(session_id: str, records: list) -> None:
    from app.agent.runtime.cancellation import AgentRunCancelled, cancellation_registry
    from app.agent.runtime.session_advisory_lock import SessionRunConflict, session_advisory_lock

    eligible: list[dict] = []
    for record in records:
        if record.get("wake_state") in {"absorbed_in_turn", "promoted", "discarded"}:
            continue
        if record.get("status") == "cancelled":
            _set_wake_state(record, "discarded", reason="delegation_cancelled")
            continue
        eligible.append(record)
    if not eligible:
        return

    wake_id = "wake_" + uuid4().hex
    logger.info(
        "delegation_wake_turn_started",
        session_id=session_id,
        wake_id=wake_id,
        runs=[record.get("run_id") for record in eligible],
    )
    owner = await _resolve_owner(session_id, eligible[0])
    if not owner:
        # 身份解不出来（旧记录且会话目录缺失）：无法构造助手上下文，丢弃留痕。
        for record in eligible:
            _set_wake_state(record, "discarded", reason="owner_unresolved")
        return
    # register 会在会话仍有在跑回合时排队等待——这即"活跃回合让路"；
    # 同回合交付边界吸收方此刻会把记录就地改为 absorbed_in_turn。
    cancel_event = await cancellation_registry.register(session_id)
    try:
        try:
            # 会话咨询锁补齐跨 worker 互斥（3 uvicorn worker 下用户回合可能
            # 落在其他进程）；等待上限与交付边界对齐，超时收口 discarded。
            async with session_advisory_lock(
                session_id, wait_timeout=float(settings.assistant_delegation_wait_seconds)
            ):
                answer = await _synthesize_wake_reply(session_id, owner, eligible, cancel_event)
        except SessionRunConflict:
            for record in eligible:
                _set_wake_state(record, "discarded", reason="session_lock_timeout")
            logger.info("delegation_wake_turn_lock_timeout", session_id=session_id)
            return
    except asyncio.CancelledError:
        await _handle_wake_cancellation(session_id, cancel_event, eligible)
        raise
    except AgentRunCancelled:
        # 运行时取消检查点抛出的是 AgentRunCancelled（任务本身未被 cancel）：
        # 同走顶掉/丢弃判定，重排记录交由 drain 循环的 register 排队续投。
        await _handle_wake_cancellation(session_id, cancel_event, eligible)
        return
    finally:
        await cancellation_registry.unregister(session_id, cancel_event)

    if not answer:
        logger.warning(
            "delegation_wake_synthesis_empty",
            session_id=session_id,
            wake_id=wake_id,
        )
        answer = _fallback_digest(eligible)
    message_id = await _append_wake_reply(session_id, answer, eligible, wake_id)
    if message_id is None:
        # 源会话已不存在：无处投递，收口 discarded。
        for record in eligible:
            _set_wake_state(record, "discarded", reason="session_missing")
        return
    for record in eligible:
        record["wake_state"] = "promoted"
        record["wake_message_id"] = message_id
        _persist_record(record)
    logger.info(
        "delegation_wake_turn_completed",
        session_id=session_id,
        wake_id=wake_id,
        answer_chars=len(answer),
    )


async def _handle_wake_cancellation(
    session_id: str, cancel_event: asyncio.Event, eligible: list[dict]
) -> None:
    """被顶掉（新用户消息）按尝试上限重排；用户主动 Stop 丢弃。

    句柄此刻尚未注销（except 先于 finally unregister 执行），且唤醒回合不绑定
    run_id，pause_reason 直接返回本地原因。
    """
    from app.agent.runtime.cancellation import cancellation_registry

    try:
        reason = await cancellation_registry.pause_reason(session_id, cancel_event)
    except Exception:
        reason = None
    superseded = reason in {None, "superseded_by_new_run"}
    for record in eligible:
        attempts = int(record.get("wake_attempts") or 0) + 1
        record["wake_attempts"] = attempts
        if not superseded or attempts >= WAKE_MAX_ATTEMPTS:
            _set_wake_state(
                record, "discarded", reason=f"wake_cancelled:{reason or 'unknown'}"
            )
            continue
        record["wake_state"] = "pending"
        _persist_record(record)
        _requeue_front(session_id, record)
    logger.info(
        "delegation_wake_turn_cancelled",
        session_id=session_id,
        reason=reason,
        superseded=superseded,
    )


async def _synthesize_wake_reply(
    session_id: str, owner: str, records: list[dict], cancel_event: asyncio.Event
) -> str:
    from app.agent.react_agent import create_react_agent
    from app.agent.runtime.cancellation import cancellation_registry
    from app.auth.models import CurrentUser
    from app.social.web_assistant import web_assistant_context

    task = asyncio.current_task()
    if task is not None:
        await cancellation_registry.attach_run_task(session_id, task)
        await cancellation_registry.arm_run_task(session_id, cancel_event)

    user = CurrentUser(id=owner, username=None, display_name=None)
    prompt = build_wake_prompt(records)
    answer = ""
    agent = create_react_agent()
    async for event in agent.analyze(
        prompt,
        session_id=session_id,
        manual_mode="assistant",
        cancel_event=cancel_event,
        **web_assistant_context(user),
    ):
        if event.get("type") != "agent_finish":
            continue
        payload = event.get("data") if isinstance(event.get("data"), dict) else {}
        candidate = payload.get("answer") or payload.get("final_message") or ""
        if candidate:
            answer = str(candidate)
    return answer.strip()


async def _resolve_owner(session_id: str, record: dict) -> str | None:
    owner = record.get("owner_user_id")
    if owner:
        return str(owner)
    # 旧记录（升级前落盘）没有 owner_user_id：从会话目录表回查。
    try:
        from sqlalchemy import select

        from app.conversations.models import ConversationCatalogDB as Catalog
        from app.db.session_database import session_async_session

        async with session_async_session() as session:
            row = (
                await session.execute(
                    select(Catalog.owner_user_id).where(Catalog.session_id == session_id)
                )
            ).scalar_one_or_none()
        return str(row) if row else None
    except Exception:
        logger.warning("delegation_wake_owner_lookup_failed", session_id=session_id)
        return None


def build_wake_prompt(records: list[dict]) -> str:
    """把终态委派渲染成 <task-notification> 契约块（对齐 ZCode 通知 XML）。"""
    from app.social.assistant_runs import build_delegation_result_card

    parts = ["后台委派任务已执行完成，请以助手身份向用户汇报整合结论。"]
    for record in records:
        raw = record.get("result")
        serialized = json.dumps(raw, ensure_ascii=False, default=str) if raw else ""
        card = build_delegation_result_card(
            {"run_id": record.get("run_id"), "result": raw}, serialized
        )
        lines = [
            "<task-notification>",
            f"  <run-id>{record.get('run_id')}</run-id>",
            f"  <target-mode>{record.get('target_mode') or 'unknown'}</target-mode>",
            f"  <status>{record.get('status')}</status>",
            f"  <goal>{str(record.get('goal') or '')[:500]}</goal>",
        ]
        if card.get("content"):
            lines.append(f"  <summary>{card['content']}</summary>")
        gaps = card.get("data_gaps") or []
        if gaps:
            lines.append(f"  <data-gaps>{'; '.join(str(gap) for gap in gaps)}</data-gaps>")
        artifacts = card.get("artifacts") or []
        if artifacts:
            rendered = "; ".join(
                f"{item.get('kind')}:{item.get('path') or item.get('url') or item.get('resource_id')}"
                for item in artifacts
            )
            lines.append(f"  <artifacts>{rendered}</artifacts>")
        if card.get("full_result_pointer"):
            lines.append(f"  <full-result-pointer>{card['full_result_pointer']}</full-result-pointer>")
        lines.append("</task-notification>")
        parts.append("\n".join(lines))
    parts.append(
        "要求：逐条核对通知结果与数据缺口；向用户输出整合后的汇报（关键结论、口径、"
        "产物引用、异常与建议），缺口必须如实声明，不得当作零；不要复述本提示；"
        "不要重启或伪造已受理的委派；最终回复直接面向用户。"
    )
    return "\n\n".join(parts)


def _fallback_digest(records: list[dict]) -> str:
    from app.social.assistant_runs import build_delegation_result_card

    lines = ["后台委派已返回结果："]
    for record in records:
        raw = record.get("result")
        serialized = json.dumps(raw, ensure_ascii=False, default=str) if raw else ""
        card = build_delegation_result_card(
            {"run_id": record.get("run_id"), "result": raw}, serialized
        )
        summary = card.get("content") or "（无结果摘要，可经 manage_assistant_runs 读取完整结果）"
        lines.append(f"- [{record.get('status')}] {str(record.get('goal') or '')[:120]}：{summary}")
        for gap in card.get("data_gaps") or []:
            lines.append(f"  缺口：{gap}")
    return "\n".join(lines)


async def _append_wake_reply(
    session_id: str, answer: str, records: list[dict], wake_id: str
) -> str | None:
    """把整合回复幂等追加进源会话 transcript（对齐定时回落的 notification_id 语义）。

    返回 None 表示源会话已不存在（调用方收口 discarded）；数据库异常向上抛出，
    由 drain 重排等下一次触发重试。
    """
    from sqlalchemy import func, select

    from app.db.models_session import SessionDB, SessionMessageDB
    from app.db.session_database import session_async_session

    run_ids = [str(record.get("run_id") or "") for record in records]
    async with session_async_session() as session:
        source = (
            await session.execute(
                select(SessionDB).where(SessionDB.session_id == session_id).with_for_update()
            )
        ).scalar_one_or_none()
        if source is None:
            logger.warning("delegation_wake_session_missing", session_id=session_id)
            return None
        existing = (
            await session.execute(
                select(SessionMessageDB.id).where(
                    SessionMessageDB.session_id == session_id,
                    SessionMessageDB.data["wake_id"].as_string() == wake_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return f"msg_{existing}"
        sequence = (
            await session.execute(
                select(func.max(SessionMessageDB.sequence_number)).where(
                    SessionMessageDB.session_id == session_id
                )
            )
        ).scalar_one()
        now = datetime.now(UTC).replace(tzinfo=None)
        message = SessionMessageDB(
            session_id=session_id,
            role="assistant",
            msg_type="final",
            content=answer,
            data={
                "answer": answer,
                "wake_id": wake_id,
                "source": "delegation_wakeup",
                "delegation_run_ids": run_ids,
            },
            sequence_number=(sequence if sequence is not None else -1) + 1,
            timestamp=now,
            created_at=now,
        )
        session.add(message)
        await session.flush()
        source.updated_at = now
        await session.commit()
        return f"msg_{message.id}"


def _set_wake_state(record: dict, state: str, *, reason: str = "") -> None:
    record["wake_state"] = state
    if reason:
        record["wake_state_reason"] = reason
    _persist_record(record)


def _persist_record(record: dict) -> None:
    try:
        from config.settings import settings

        from app.social.assistant_runs import AssistantRunService

        owner = record.get("owner_user_id")
        if not owner:
            return
        AssistantRunService()._save(settings.project_id, str(owner), record)
    except Exception:
        logger.warning(
            "delegation_wake_state_persist_failed",
            run_id=record.get("run_id"),
            exc_info=True,
        )
