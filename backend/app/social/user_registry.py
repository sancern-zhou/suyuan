"""Minimal social user registry and binding-code onboarding service."""

from __future__ import annotations

import json
import os
import re
import secrets
import string
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import structlog
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.path_config import get_social_dir

logger = structlog.get_logger(__name__)

BIND_CODE_PATTERN = re.compile(r"^\s*([0-9]{4})\s*$")
VALID_STATUSES = {"pending_bind", "active", "disabled"}


class SocialUserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None
        if "@" not in value:
            raise ValueError("Invalid email")
        return value


class SocialUserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[str] = Field(default=None, max_length=255)
    status: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None
        if "@" not in value:
            raise ValueError("Invalid email")
        return value


class SocialUserRecord(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    status: str = "pending_bind"
    bind_code: Optional[str] = None
    social_user_id: Optional[str] = None
    channel: Optional[str] = None
    bot_account: Optional[str] = None
    sender_id: Optional[str] = None
    created_at: str
    updated_at: str
    bound_at: Optional[str] = None
    last_seen_at: Optional[str] = None


def build_social_user_id(channel: str, bot_account: str, sender_id: str) -> str:
    return f"{channel}:{bot_account}:{sender_id}"


class SocialUserRegistry:
    """Create, update and bind minimal social user profiles."""

    def __init__(
        self,
        data_path: Optional[Path] = None,
        session_factory: Optional[Callable[[], AsyncSession]] = None,
    ):
        self.data_path = data_path
        self.session_factory = session_factory
        self._users: dict[str, SocialUserRecord] = {}
        self._loaded = False

    async def create_user(
        self,
        payload: SocialUserCreate,
        bind_code: Optional[str] = None,
    ) -> SocialUserRecord:
        if self.session_factory:
            return await self._create_user_db(payload, bind_code)

        await self._load_file()
        now = datetime.now().isoformat()
        code = (bind_code or self._generate_bind_code()).upper()
        while any(user.bind_code == code for user in self._users.values()):
            code = self._generate_bind_code()

        record = SocialUserRecord(
            id=str(uuid.uuid4()),
            name=payload.name.strip(),
            email=str(payload.email) if payload.email else None,
            status="pending_bind",
            bind_code=code,
            created_at=now,
            updated_at=now,
        )
        self._users[record.id] = record
        await self._save_file()
        return record

    async def get_user(self, user_id: str) -> Optional[SocialUserRecord]:
        if self.session_factory:
            return await self._get_user_db(user_id)

        await self._load_file()
        return self._users.get(user_id)

    async def list_users(self) -> list[SocialUserRecord]:
        if self.session_factory:
            return await self._list_users_db()

        await self._load_file()
        return sorted(self._users.values(), key=lambda user: user.created_at, reverse=True)

    async def update_user(
        self,
        user_id: str,
        payload: SocialUserUpdate,
    ) -> Optional[SocialUserRecord]:
        if payload.status and payload.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {payload.status}")

        if self.session_factory:
            return await self._update_user_db(user_id, payload)

        await self._load_file()
        record = self._users.get(user_id)
        if not record:
            return None

        data = record.model_dump()
        if payload.name is not None:
            data["name"] = payload.name.strip()
        if payload.email is not None:
            data["email"] = str(payload.email)
        if payload.status is not None:
            data["status"] = payload.status
        data["updated_at"] = datetime.now().isoformat()
        updated = SocialUserRecord(**data)
        self._users[user_id] = updated
        await self._save_file()
        return updated

    async def bind_by_code(
        self,
        message_text: str,
        channel: str,
        bot_account: str,
        sender_id: str,
    ) -> Optional[SocialUserRecord]:
        match = BIND_CODE_PATTERN.match(message_text or "")
        if not match:
            return None

        code = match.group(1).upper()
        social_user_id = build_social_user_id(channel, bot_account, sender_id)

        if self.session_factory:
            return await self._bind_by_code_db(code, channel, bot_account, sender_id, social_user_id)

        await self._load_file()
        if any(user.social_user_id == social_user_id for user in self._users.values()):
            return None

        for record in self._users.values():
            if record.bind_code != code or record.status != "pending_bind":
                continue

            now = datetime.now().isoformat()
            data = record.model_dump()
            data.update(
                {
                    "status": "active",
                    "bind_code": None,
                    "social_user_id": social_user_id,
                    "channel": channel,
                    "bot_account": bot_account,
                    "sender_id": sender_id,
                    "bound_at": now,
                    "last_seen_at": now,
                    "updated_at": now,
                }
            )
            bound = SocialUserRecord(**data)
            self._users[bound.id] = bound
            await self._save_file()
            return bound

        return None

    async def get_by_social_user_id(self, social_user_id: str) -> Optional[SocialUserRecord]:
        if self.session_factory:
            return await self._get_by_social_user_id_db(social_user_id)

        await self._load_file()
        return next((user for user in self._users.values() if user.social_user_id == social_user_id), None)

    async def touch_social_user(self, social_user_id: str) -> Optional[SocialUserRecord]:
        if self.session_factory:
            return await self._touch_social_user_db(social_user_id)

        await self._load_file()
        record = await self.get_by_social_user_id(social_user_id)
        if not record:
            return None

        data = record.model_dump()
        now = datetime.now().isoformat()
        data["last_seen_at"] = now
        data["updated_at"] = now
        updated = SocialUserRecord(**data)
        self._users[updated.id] = updated
        await self._save_file()
        return updated

    def _generate_bind_code(self) -> str:
        alphabet = string.digits
        return "".join(secrets.choice(alphabet) for _ in range(4))

    async def _load_file(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.data_path or not self.data_path.exists():
            return

        try:
            raw = json.loads(self.data_path.read_text(encoding="utf-8"))
            self._users = {
                item["id"]: SocialUserRecord(**item)
                for item in raw.get("users", [])
                if isinstance(item, dict) and item.get("id")
            }
        except Exception as e:
            logger.warning("social_users_file_load_failed", path=str(self.data_path), error=str(e))

    async def _save_file(self) -> None:
        if not self.data_path:
            return
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"users": [user.model_dump() for user in self._users.values()]}
        self.data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _create_user_db(
        self,
        payload: SocialUserCreate,
        bind_code: Optional[str],
    ) -> SocialUserRecord:
        from app.social.models import SocialUser

        code = (bind_code or self._generate_bind_code()).upper()
        now = datetime.now()
        async with self.session_factory() as session:
            while await session.scalar(select(SocialUser).where(SocialUser.bind_code == code)):
                code = self._generate_bind_code()

            row = SocialUser(
                id=str(uuid.uuid4()),
                name=payload.name.strip(),
                email=str(payload.email) if payload.email else None,
                status="pending_bind",
                bind_code=code,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._from_row(row)

    async def _get_user_db(self, user_id: str) -> Optional[SocialUserRecord]:
        from app.social.models import SocialUser

        async with self.session_factory() as session:
            row = await session.get(SocialUser, user_id)
            return self._from_row(row) if row else None

    async def _list_users_db(self) -> list[SocialUserRecord]:
        from app.social.models import SocialUser

        async with self.session_factory() as session:
            result = await session.execute(select(SocialUser).order_by(SocialUser.created_at.desc()))
            return [self._from_row(row) for row in result.scalars().all()]

    async def _update_user_db(
        self,
        user_id: str,
        payload: SocialUserUpdate,
    ) -> Optional[SocialUserRecord]:
        from app.social.models import SocialUser

        async with self.session_factory() as session:
            row = await session.get(SocialUser, user_id)
            if not row:
                return None
            if payload.name is not None:
                row.name = payload.name.strip()
            if payload.email is not None:
                row.email = str(payload.email)
            if payload.status is not None:
                row.status = payload.status
            row.updated_at = datetime.now()
            await session.commit()
            await session.refresh(row)
            return self._from_row(row)

    async def _bind_by_code_db(
        self,
        code: str,
        channel: str,
        bot_account: str,
        sender_id: str,
        social_user_id: str,
    ) -> Optional[SocialUserRecord]:
        from app.social.models import SocialUser

        async with self.session_factory() as session:
            existing = await session.scalar(
                select(SocialUser).where(SocialUser.social_user_id == social_user_id)
            )
            if existing:
                return None

            row = await session.scalar(
                select(SocialUser).where(
                    SocialUser.bind_code == code,
                    SocialUser.status == "pending_bind",
                )
            )
            if not row:
                return None

            now = datetime.now()
            row.status = "active"
            row.bind_code = None
            row.social_user_id = social_user_id
            row.channel = channel
            row.bot_account = bot_account
            row.sender_id = sender_id
            row.bound_at = now
            row.last_seen_at = now
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return self._from_row(row)

    async def _get_by_social_user_id_db(self, social_user_id: str) -> Optional[SocialUserRecord]:
        from app.social.models import SocialUser

        async with self.session_factory() as session:
            row = await session.scalar(
                select(SocialUser).where(SocialUser.social_user_id == social_user_id)
            )
            return self._from_row(row) if row else None

    async def _touch_social_user_db(self, social_user_id: str) -> Optional[SocialUserRecord]:
        from app.social.models import SocialUser

        async with self.session_factory() as session:
            row = await session.scalar(
                select(SocialUser).where(SocialUser.social_user_id == social_user_id)
            )
            if not row:
                return None
            now = datetime.now()
            row.last_seen_at = now
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return self._from_row(row)

    def _from_row(self, row) -> SocialUserRecord:
        return SocialUserRecord(
            id=row.id,
            name=row.name,
            email=row.email,
            status=row.status,
            bind_code=row.bind_code,
            social_user_id=row.social_user_id,
            channel=row.channel,
            bot_account=row.bot_account,
            sender_id=row.sender_id,
            created_at=row.created_at.isoformat(),
            updated_at=row.updated_at.isoformat(),
            bound_at=row.bound_at.isoformat() if row.bound_at else None,
            last_seen_at=row.last_seen_at.isoformat() if row.last_seen_at else None,
        )


_registry: Optional[SocialUserRegistry] = None


def get_social_user_registry() -> SocialUserRegistry:
    global _registry
    if _registry is None:
        if os.getenv("DATABASE_URL"):
            from app.db.database import async_session

            _registry = SocialUserRegistry(session_factory=async_session)
        else:
            _registry = SocialUserRegistry(data_path=get_social_dir() / "users.json")
    return _registry
