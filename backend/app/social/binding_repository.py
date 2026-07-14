"""Transactional persistence for QR tasks and platform social bindings."""

from datetime import datetime, timedelta
import uuid

from sqlalchemy import select

from app.db.database import async_session
from app.social.models import SocialUser, WeixinScanTask

from .binding_schemas import SocialBindingRecord, WeixinScanTaskRecord


class ForeignWeixinIdentityError(RuntimeError):
    pass


class SocialBindingRepository:
    @staticmethod
    def _task_record(row: WeixinScanTask) -> WeixinScanTaskRecord:
        return WeixinScanTaskRecord.model_validate({
            column.name: getattr(row, column.name)
            for column in WeixinScanTask.__table__.columns
        })

    @staticmethod
    def _binding_record(row: SocialUser) -> SocialBindingRecord:
        return SocialBindingRecord(
            id=row.id,
            platform_user_id=row.platform_user_id,
            platform_username=row.platform_username,
            platform_display_name=row.platform_display_name,
            account_id=row.account_id,
            ilink_user_id=row.ilink_user_id,
            bot_account=row.bot_account,
            status=row.status,
            bound_at=row.bound_at,
        )

    async def create_scan_task(self, user) -> WeixinScanTaskRecord:
        now = datetime.utcnow()
        row = WeixinScanTask(
            id=str(uuid.uuid4()),
            account_id=f"auto_{uuid.uuid4().hex}",
            owner_user_id=user.id,
            owner_username=user.username,
            owner_display_name=user.display_name,
            status="created",
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._task_record(row)

    async def get_scan_task(self, task_id: str) -> WeixinScanTaskRecord | None:
        async with async_session() as session:
            row = await session.get(WeixinScanTask, task_id)
            return self._task_record(row) if row else None

    async def set_scan_status(self, task_id: str, status: str) -> WeixinScanTaskRecord:
        async with async_session() as session:
            row = await session.get(WeixinScanTask, task_id)
            if row is None:
                raise RuntimeError("weixin_scan_not_found")
            row.status = status
            row.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(row)
            return self._task_record(row)

    async def replace_active_binding(
        self,
        *,
        task: WeixinScanTaskRecord,
        ilink_user_id: str,
        bot_account: str,
    ) -> SocialBindingRecord:
        now = datetime.utcnow()
        async with async_session() as session:
            async with session.begin():
                task_row = await session.scalar(
                    select(WeixinScanTask)
                    .where(WeixinScanTask.id == task.id)
                    .with_for_update()
                )
                if task_row is None or task_row.account_id != task.account_id:
                    raise RuntimeError("weixin_scan_not_found")

                active_for_user = await session.scalar(
                    select(SocialUser).where(
                        SocialUser.platform_user_id == task.owner_user_id,
                        SocialUser.status == "active",
                    ).with_for_update()
                )
                active_for_wechat = await session.scalar(
                    select(SocialUser).where(
                        SocialUser.ilink_user_id == ilink_user_id,
                        SocialUser.status == "active",
                    ).with_for_update()
                )
                if (
                    active_for_wechat is not None
                    and active_for_wechat.platform_user_id != task.owner_user_id
                ):
                    raise ForeignWeixinIdentityError(ilink_user_id)

                selected = active_for_wechat
                if active_for_user is not None and active_for_user is not selected:
                    active_for_user.status = "replaced"
                    active_for_user.updated_at = now

                if selected is None:
                    selected = await session.scalar(
                        select(SocialUser).where(
                            SocialUser.platform_user_id == task.owner_user_id,
                            SocialUser.ilink_user_id == ilink_user_id,
                        ).order_by(SocialUser.updated_at.desc()).with_for_update()
                    )
                if selected is None:
                    selected = SocialUser(id=str(uuid.uuid4()), created_at=now)
                    session.add(selected)

                selected.name = task.owner_display_name or task.owner_username
                selected.email = None
                selected.status = "active"
                selected.bind_code = None
                selected.social_user_id = f"weixin:{bot_account}:{ilink_user_id}"
                selected.channel = "weixin"
                selected.bot_account = bot_account
                selected.sender_id = ilink_user_id
                selected.platform_user_id = task.owner_user_id
                selected.platform_username = task.owner_username
                selected.platform_display_name = task.owner_display_name
                selected.account_id = task.account_id
                selected.ilink_user_id = ilink_user_id
                selected.bound_at = now
                selected.last_seen_at = now
                selected.updated_at = now
                task_row.status = "confirmed"
                task_row.updated_at = now

            await session.refresh(selected)
            return self._binding_record(selected)

    async def resolve_sender(
        self, *, bot_account: str, ilink_user_id: str
    ) -> SocialBindingRecord | None:
        async with async_session() as session:
            row = await session.scalar(select(SocialUser).where(
                SocialUser.bot_account == bot_account,
                SocialUser.ilink_user_id == ilink_user_id,
                SocialUser.status == "active",
                SocialUser.platform_user_id.is_not(None),
            ))
            return self._binding_record(row) if row else None

    async def active_for_platform_user(
        self, platform_user_id: str
    ) -> SocialBindingRecord | None:
        async with async_session() as session:
            row = await session.scalar(select(SocialUser).where(
                SocialUser.platform_user_id == platform_user_id,
                SocialUser.status == "active",
            ))
            return self._binding_record(row) if row else None

    async def active_for_account(self, account_id: str) -> SocialBindingRecord | None:
        async with async_session() as session:
            row = await session.scalar(select(SocialUser).where(
                SocialUser.account_id == account_id,
                SocialUser.status == "active",
            ))
            return self._binding_record(row) if row else None

    async def list_active(self) -> list[SocialBindingRecord]:
        async with async_session() as session:
            rows = (await session.scalars(select(SocialUser).where(
                SocialUser.status == "active",
                SocialUser.platform_user_id.is_not(None),
            ))).all()
            return [self._binding_record(row) for row in rows]
