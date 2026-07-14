"""Authorization policy for authenticated QR scans and social bindings."""

from datetime import datetime

from fastapi import HTTPException

from app.auth.models import CurrentUser

from .binding_repository import ForeignWeixinIdentityError, SocialBindingRepository
from .binding_schemas import SocialBindingRecord, WeixinScanTaskRecord


class SocialBindingConflict(RuntimeError):
    pass


class SocialBindingService:
    def __init__(self, repository):
        self.repository = repository

    async def create_scan_task(self, user: CurrentUser) -> WeixinScanTaskRecord:
        return await self.repository.create_scan_task(user)

    async def require_scan_task(
        self, task_id: str, user: CurrentUser
    ) -> WeixinScanTaskRecord:
        task = await self.repository.get_scan_task(task_id)
        if task is None or (not user.is_admin and task.owner_user_id != user.id):
            raise HTTPException(status_code=404, detail="weixin_scan_not_found")
        if task.status != "confirmed" and task.expires_at < datetime.utcnow():
            await self.repository.set_scan_status(task_id, "expired")
            raise HTTPException(status_code=410, detail="weixin_scan_expired")
        return task

    async def mark_scan_status(
        self, task_id: str, user: CurrentUser, status: str
    ) -> WeixinScanTaskRecord:
        await self.require_scan_task(task_id, user)
        return await self.repository.set_scan_status(task_id, status)

    async def activate(
        self,
        *,
        task_id: str,
        user: CurrentUser,
        account_id: str,
        ilink_user_id: str,
        bot_account: str,
    ) -> SocialBindingRecord:
        task = await self.require_scan_task(task_id, user)
        if task.account_id != account_id:
            raise HTTPException(status_code=404, detail="weixin_scan_not_found")
        try:
            return await self.repository.replace_active_binding(
                task=task,
                ilink_user_id=ilink_user_id,
                bot_account=bot_account,
            )
        except ForeignWeixinIdentityError as exc:
            raise SocialBindingConflict("weixin_identity_already_bound") from exc

    async def resolve_sender(
        self, *, channel: str, bot_account: str, sender_id: str
    ) -> SocialBindingRecord | None:
        if channel != "weixin" and not channel.startswith("weixin:"):
            return None
        return await self.repository.resolve_sender(
            bot_account=bot_account,
            ilink_user_id=sender_id,
        )

    async def active_for_account(self, account_id: str) -> SocialBindingRecord | None:
        return await self.repository.active_for_account(account_id)

    async def active_for_platform_user(
        self, platform_user_id: str
    ) -> SocialBindingRecord | None:
        return await self.repository.active_for_platform_user(platform_user_id)

    async def list_visible(self, user: CurrentUser) -> list[SocialBindingRecord]:
        rows = await self.repository.list_active()
        return rows if user.is_admin else [row for row in rows if row.platform_user_id == user.id]

    async def deactivate_account(self, account_id: str) -> bool:
        return await self.repository.deactivate_account(account_id)


_service = SocialBindingService(SocialBindingRepository())


def get_social_binding_service() -> SocialBindingService:
    return _service
