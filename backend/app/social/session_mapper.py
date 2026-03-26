"""Session mapper for social platform user to agent session mapping."""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class SessionMapper:
    """
    Manages one-to-one mapping between social platform users and agent sessions.

    Mapping structure:
        social_user_id (e.g., "qq:123456") -> session_id (e.g., "react_session_abc123")

    Persistence:
        - PostgreSQL table: social_session_mappings
        - Fallback: JSON file backend_data_registry/social/session_mappings.json
    """

    def __init__(self, db_manager=None, data_dir: str | None = None):
        """
        Initialize the session mapper.

        Args:
            db_manager: Optional database manager for PostgreSQL persistence
            data_dir: Fallback data directory for JSON persistence
        """
        self.db_manager = db_manager
        self.data_dir = Path(data_dir or "backend_data_registry/social")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.mappings_file = self.data_dir / "session_mappings.json"

        # In-memory cache
        self._mappings: Dict[str, str] = {}
        self._timestamp_cache: Dict[str, datetime] = {}

        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        """Load mappings from persistent storage."""
        async with self._lock:
            # Try database first
            if self.db_manager:
                try:
                    await self._load_from_db()
                    return
                except Exception as e:
                    logger.warning("Failed to load from database, falling back to JSON", error=str(e))

            # Fallback to JSON file
            await self._load_from_file()

    async def _load_from_db(self) -> None:
        """Load mappings from PostgreSQL database."""
        from sqlalchemy import select
        from datetime import timedelta
        from app.social.models import SocialSessionMapping

        if not self.db_manager:
            return

        # Use async session from database
        async with self.db_manager() as session:
            cutoff = datetime.now() - timedelta(hours=24)
            stmt = select(SocialSessionMapping).where(
                SocialSessionMapping.last_used > cutoff
            )

            result = await session.execute(stmt)
            mappings = result.scalars().all()

            for mapping in mappings:
                self._mappings[mapping.social_user_id] = mapping.session_id
                self._timestamp_cache[mapping.social_user_id] = mapping.last_used

            logger.info("Loaded session mappings from database", count=len(self._mappings))

    async def _load_from_file(self) -> None:
        """Load mappings from JSON file."""
        if not self.mappings_file.exists():
            logger.info("No existing session mappings file found")
            return

        try:
            with open(self.mappings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Filter expired mappings (older than 24 hours)
            now = datetime.now()
            cutoff = now - timedelta(hours=24)

            for social_user_id, entry in data.items():
                last_used = datetime.fromisoformat(entry.get('last_used', now.isoformat()))
                if last_used > cutoff:
                    self._mappings[social_user_id] = entry['session_id']
                    self._timestamp_cache[social_user_id] = last_used

            logger.info("Loaded session mappings from file", count=len(self._mappings))
        except Exception as e:
            logger.error("Failed to load session mappings from file", error=str(e))

    async def save(self) -> None:
        """Save mappings to persistent storage."""
        async with self._lock:
            # Try database first
            if self.db_manager:
                try:
                    await self._save_to_db()
                    return
                except Exception as e:
                    logger.warning("Failed to save to database, falling back to JSON", error=str(e))

            # Fallback to JSON file
            await self._save_to_file()

    async def _save_to_db(self) -> None:
        """Save mappings to PostgreSQL database."""
        from sqlalchemy.dialects.postgresql import insert
        from app.social.models import SocialSessionMapping

        if not self.db_manager:
            return

        try:
            async with self.db_manager() as session:
                # Prepare upsert data
                records = [
                    {
                        'social_user_id': social_user_id,
                        'session_id': session_id,
                        'last_used': self._timestamp_cache.get(social_user_id, datetime.now())
                    }
                    for social_user_id, session_id in self._mappings.items()
                ]

                # Bulk upsert using PostgreSQL ON CONFLICT
                stmt = insert(SocialSessionMapping).__class__
                for record in records:
                    stmt = stmt.values(**record)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['social_user_id'],
                        set_=dict(
                            session_id=stmt.excluded.session_id,
                            last_used=stmt.excluded.last_used
                        )
                    )
                    await session.execute(stmt)

                await session.commit()

            logger.debug("Saved session mappings to database", count=len(self._mappings))
        except Exception as e:
            logger.warning("Failed to save to database, falling back to JSON", error=str(e))
            await self._save_to_file()

    async def _save_to_file(self) -> None:
        """Save mappings to JSON file."""
        try:
            data = {}
            for social_user_id, session_id in self._mappings.items():
                last_used = self._timestamp_cache.get(social_user_id, datetime.now())
                data[social_user_id] = {
                    'session_id': session_id,
                    'last_used': last_used.isoformat()
                }

            with open(self.mappings_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug("Saved session mappings to file", count=len(self._mappings))
        except Exception as e:
            logger.error("Failed to save session mappings to file", error=str(e))

    async def get_or_create_session(self, social_user_id: str) -> str:
        """
        Get existing session ID or create a new one.

        Args:
            social_user_id: Social platform user ID (e.g., "qq:123456")

        Returns:
            Agent session ID
        """
        # 先检查是否有缓存（不需要锁）
        if social_user_id in self._mappings:
            last_used = self._timestamp_cache.get(social_user_id, datetime.now())
            if datetime.now() - last_used < timedelta(hours=24):
                # 更新时间戳
                self._timestamp_cache[social_user_id] = datetime.now()
                # 异步保存（不阻塞）
                asyncio.create_task(self.save())
                return self._mappings[social_user_id]

        # 创建新session（需要锁）
        async with self._lock:
            # 再次检查（防止竞态条件）
            if social_user_id in self._mappings:
                return self._mappings[social_user_id]

            # 创建新session ID
            session_id = f"react_session_{social_user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            self._mappings[social_user_id] = session_id
            self._timestamp_cache[social_user_id] = datetime.now()

            logger.info("Created new session mapping",
                       social_user_id=social_user_id,
                       session_id=session_id)

        # 异步保存（释放锁后再保存）
        asyncio.create_task(self.save())

        return session_id

    async def get_session(self, social_user_id: str) -> Optional[str]:
        """
        Get existing session ID without creating a new one.

        Args:
            social_user_id: Social platform user ID

        Returns:
            Agent session ID or None if not found or expired
        """
        async with self._lock:
            if social_user_id not in self._mappings:
                return None

            last_used = self._timestamp_cache.get(social_user_id, datetime.now())
            if datetime.now() - last_used >= timedelta(hours=24):
                # Expired mapping
                del self._mappings[social_user_id]
                del self._timestamp_cache[social_user_id]
                await self.save()
                return None

            return self._mappings[social_user_id]

    async def delete_mapping(self, social_user_id: str) -> bool:
        """
        Delete a session mapping.

        Args:
            social_user_id: Social platform user ID

        Returns:
            True if mapping was deleted, False if not found
        """
        async with self._lock:
            if social_user_id not in self._mappings:
                return False

            del self._mappings[social_user_id]
            if social_user_id in self._timestamp_cache:
                del self._timestamp_cache[social_user_id]

            await self.save()
            logger.info("Deleted session mapping", social_user_id=social_user_id)
            return True

    async def cleanup_expired(self, ttl_hours: int = 24) -> int:
        """
        Clean up expired mappings.

        Args:
            ttl_hours: Time-to-live in hours (default: 24)

        Returns:
            Number of mappings cleaned up
        """
        async with self._lock:
            cutoff = datetime.now() - timedelta(hours=ttl_hours)
            expired = [
                social_user_id
                for social_user_id, last_used in self._timestamp_cache.items()
                if last_used < cutoff
            ]

            for social_user_id in expired:
                del self._mappings[social_user_id]
                del self._timestamp_cache[social_user_id]

            if expired:
                await self.save()
                logger.info("Cleaned up expired mappings", count=len(expired))

            return len(expired)

    @property
    def mapping_count(self) -> int:
        """Get the number of active mappings."""
        return len(self._mappings)
