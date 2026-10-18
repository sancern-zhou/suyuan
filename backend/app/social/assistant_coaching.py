"""Hermes-inspired consent/dedup/backlog semantics on transactional owner storage.

See third_party/hermes-assistant-coaching.md for pinned sources and MIT notice.
Unlike the upstream file store, a database owner fence also protects multiple workers.
"""

from datetime import datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.social.assistant_capabilities import capability_catalog, next_action
from app.social.assistant_coaching_models import AssistantCoachingOwnerDB, AssistantSuggestionDB
from app.social.assistant_request import require_assistant_request
from app.social.assistant_tasks import _text

MAX_PENDING = 5


class AssistantCoachingService:
    def __init__(self, session_factory=None, catalog=None):
        if session_factory is None:
            from app.db.database import async_session

            session_factory = async_session
        self.session_factory = session_factory
        self.catalog = catalog or capability_catalog

    @staticmethod
    def _scope(project, owner, model=AssistantSuggestionDB):
        if not project or not owner or owner == "system":
            raise PermissionError("无法确认建议归属")
        return model.project_id == project, model.owner_user_id == owner

    @staticmethod
    def _record(row):
        return {
            col.name: getattr(row, col.name)
            for col in AssistantSuggestionDB.__table__.columns
            if col.name
            not in {"dedup_key", "owner_user_id", "source_user_message", "decision_user_message"}
        }

    @staticmethod
    def _authorize(request):
        # Revoked/inherited background scopes cannot mutate choices after the human turn.
        if require_assistant_request(request.session_id) != request:
            raise PermissionError("建议操作需要当前用户请求")

    async def _lock_owner(self, session, project, owner):
        scope = self._scope(project, owner, AssistantCoachingOwnerDB)
        # A savepoint keeps a concurrent first-use conflict from aborting the transaction.
        try:
            async with session.begin_nested():
                session.add(AssistantCoachingOwnerDB(project_id=project, owner_user_id=owner))
                await session.flush()
        except IntegrityError:
            pass
        await session.execute(
            update(AssistantCoachingOwnerDB)
            .where(*scope)
            .values(revision=AssistantCoachingOwnerDB.revision + 1)
        )

    async def propose(
        self,
        project,
        owner,
        request,
        *,
        capability_id,
        goal,
        reason,
        suggested_prompt,
        missing_inputs=None,
    ):
        scope = self._scope(project, owner)
        self._authorize(request)
        capability = self.catalog().get(capability_id)
        if capability is None:
            raise ValueError("该项目当前未开放此能力，请重新查询能力目录")
        goal = _text(goal, "用户目标", 2000)
        reason = _text(reason, "推荐理由", 2000)
        prompt = _text(suggested_prompt, "建议提问", 6000)
        inputs = [] if missing_inputs is None else missing_inputs
        if not isinstance(inputs, list) or len(inputs) > 10:
            raise ValueError("缺少的信息应为最多10项文本")
        inputs = [_text(item, "缺少的信息", 500) for item in inputs]
        key = sha256(f"{capability_id}\0{' '.join(goal.casefold().split())}".encode()).hexdigest()
        async with self.session_factory() as session:
            await self._lock_owner(session, project, owner)
            existing = (
                await session.execute(
                    select(AssistantSuggestionDB).where(
                        *scope, AssistantSuggestionDB.dedup_key == key
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return {"created": False, "suggestion": self._record(existing)}
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(AssistantSuggestionDB)
                    .where(*scope, AssistantSuggestionDB.state == "pending")
                )
            ).scalar_one()
            if count >= MAX_PENDING:
                raise ValueError("待处理建议已达5条，请先处理已有建议")
            row = AssistantSuggestionDB(
                suggestion_id=str(uuid4()),
                project_id=project,
                owner_user_id=owner,
                dedup_key=key,
                capability_id=capability_id,
                capability_revision=capability["revision"],
                goal=goal,
                reason=reason,
                suggested_prompt=prompt,
                missing_inputs=inputs,
                source_session_id=request.session_id,
                source_request_id=request.request_id,
                source_user_message=request.user_message,
            )
            session.add(row)
            await session.flush()
            self._authorize(request)
            await session.commit()
            return {"created": True, "suggestion": self._record(row)}

    async def list(self, project, owner, *, state="pending", offset=0, limit=20):
        scope = self._scope(project, owner)
        if state not in {"pending", "accepted", "dismissed", "all"}:
            raise ValueError("不支持的建议状态")
        async with self.session_factory() as session:
            stmt = select(AssistantSuggestionDB).where(*scope)
            if state != "all":
                stmt = stmt.where(AssistantSuggestionDB.state == state)
            rows = (
                (
                    await session.execute(
                        stmt.order_by(
                            AssistantSuggestionDB.created_at, AssistantSuggestionDB.suggestion_id
                        )
                        .offset(max(0, int(offset)))
                        .limit(max(1, min(50, int(limit))))
                    )
                )
                .scalars()
                .all()
            )
            return [self._record(row) for row in rows]

    async def decide(self, project, owner, request, *, suggestion_id, expected_version, action):
        scope = self._scope(project, owner)
        self._authorize(request)
        if action not in {"accept", "dismiss"}:
            raise ValueError("不支持的建议操作")
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("请使用查询得到的建议版本")
        async with self.session_factory() as session:
            await self._lock_owner(session, project, owner)
            row = (
                await session.execute(
                    select(AssistantSuggestionDB).where(
                        *scope, AssistantSuggestionDB.suggestion_id == suggestion_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise ValueError("建议不存在或无权访问")
            capability = self.catalog().get(row.capability_id) if action == "accept" else None
            # A repeated decision is idempotent, but acceptance never bypasses live revalidation.
            target = "accepted" if action == "accept" else "dismissed"
            if row.state != target and (row.state != "pending" or row.version != expected_version):
                raise ValueError("建议已处理或版本已变化，请重新查询")
            if action == "accept" and (
                capability is None or capability["revision"] != row.capability_revision
            ):
                raise ValueError("能力已变化或停用，不能采纳旧建议；可忽略后重新讨论需求")
            if row.state == "pending":
                row.state = target
                row.version += 1
                row.decision_session_id = request.session_id
                row.decision_request_id = request.request_id
                row.decision_user_message = request.user_message
                row.resolved_at = datetime.utcnow()
            self._authorize(request)
            await session.commit()
            record = self._record(row)
            return {
                "suggestion": record,
                "next_action": next_action(capability, record) if capability else None,
                "execution_state": "not_started",
            }
