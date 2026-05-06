"""
用户级心跳管理器

核心功能：
- 管理多个用户的 HeartbeatService 实例
- 提供用户心跳任务隔离
- LRU 缓存优化
"""

from pathlib import Path
from typing import Dict, Callable, Optional
import asyncio
import structlog
import json

from app.social.heartbeat_service import HeartbeatService

logger = structlog.get_logger(__name__)


class UserHeartbeatManager:
    """用户心跳管理器"""

    def __init__(
        self,
        base_workspace: Path = None,
        max_cache_size: int = 100,
        on_execute_callback: Optional[Callable] = None,
        on_notify_callback: Optional[Callable] = None
    ):
        """
        初始化用户心跳管理器

        Args:
            base_workspace: 基础工作空间目录
            max_cache_size: 最大缓存用户数
            on_execute_callback: 执行任务回调函数
            on_notify_callback: 发送通知回调函数
        """
        self.base_workspace = base_workspace or Path("backend_data_registry/social/heartbeat")
        self.base_workspace.mkdir(parents=True, exist_ok=True)

        self._heartbeat_cache: Dict[str, HeartbeatService] = {}
        self._lock = asyncio.Lock()
        self._max_cache_size = max_cache_size
        self._on_execute_callback = on_execute_callback
        self._on_notify_callback = on_notify_callback

        logger.info(
            "user_heartbeat_manager_initialized",
            base_workspace=str(self.base_workspace),
            max_cache_size=max_cache_size
        )

    def _metadata_file(self, user_workspace: Path) -> Path:
        """Return the metadata file used to preserve the original user id."""
        return user_workspace / ".user_id"

    def _write_user_metadata(self, user_workspace: Path, user_id: str) -> None:
        """Persist original user id because directory names replace ':' with '_'."""
        try:
            self._metadata_file(user_workspace).write_text(user_id, encoding="utf-8")
        except Exception as e:
            logger.warning("write_heartbeat_user_metadata_failed", user_id=user_id, error=str(e))

    def _recover_user_id_from_workspace(self, user_workspace: Path) -> Optional[str]:
        """Recover original user id for a persisted heartbeat workspace."""
        metadata_file = self._metadata_file(user_workspace)
        if metadata_file.exists():
            try:
                user_id = metadata_file.read_text(encoding="utf-8").strip()
                if user_id:
                    return user_id
            except Exception as e:
                logger.warning(
                    "read_heartbeat_user_metadata_failed",
                    workspace=str(user_workspace),
                    error=str(e)
                )

        # Prefer session mappings when available because safe directory names are lossy.
        mappings_file = self.base_workspace.parent / "session_mappings.json"
        if mappings_file.exists():
            try:
                mappings = json.loads(mappings_file.read_text(encoding="utf-8"))
                for social_user_id in mappings.keys():
                    if social_user_id.replace(":", "_") == user_workspace.name:
                        return social_user_id
            except Exception as e:
                logger.warning("recover_user_id_from_mapping_failed", error=str(e))

        # Backward-compatible fallback for old workspaces. This assumes
        # channel and bot account do not contain underscores.
        parts = user_workspace.name.split("_", 2)
        if len(parts) == 3:
            return f"{parts[0]}:{parts[1]}:{parts[2]}"

        logger.warning(
            "unable_to_recover_heartbeat_user_id",
            workspace=str(user_workspace)
        )
        return None

    async def _create_user_heartbeat_locked(self, user_id: str, user_workspace: Path) -> HeartbeatService:
        heartbeat = HeartbeatService(
            interval_s=30 * 60,
            workspace=user_workspace,
            user_id=user_id,
            on_execute=lambda tasks: self._on_execute_callback(tasks, user_id),
            on_notify=lambda response: self._on_notify_callback(response, user_id)
        )
        await heartbeat.start()
        self._heartbeat_cache[user_id] = heartbeat
        self._write_user_metadata(user_workspace, user_id)
        logger.info("user_heartbeat_created", user_id=user_id)
        return heartbeat

    async def get_user_heartbeat(self, user_id: str) -> HeartbeatService:
        """
        获取或创建用户 HeartbeatService

        Args:
            user_id: 用户ID（格式：{channel}:{bot_account}:{sender_id}）

        Returns:
            用户专属 HeartbeatService
        """
        async with self._lock:
            if user_id not in self._heartbeat_cache:
                # LRU 缓存清理
                if len(self._heartbeat_cache) >= self._max_cache_size:
                    oldest_key = next(iter(self._heartbeat_cache))
                    await self._heartbeat_cache[oldest_key].stop()
                    del self._heartbeat_cache[oldest_key]
                    logger.debug("heartbeat_cache_evicted", user_id=oldest_key)

                # 创建用户专属 HeartbeatService
                user_workspace = self._init_user_workspace(user_id)
                heartbeat = await self._create_user_heartbeat_locked(user_id, user_workspace)

            return self._heartbeat_cache[user_id]

    def _init_user_workspace(self, user_id: str) -> Path:
        """
        初始化用户工作空间

        Args:
            user_id: 用户ID

        Returns:
            用户工作空间路径
        """
        if user_id and user_id != "global":
            # 路径安全：将 : 替换为 _
            safe_user_id = user_id.replace(":", "_")
            user_dir = self.base_workspace / safe_user_id
            user_dir.mkdir(parents=True, exist_ok=True)
            self._write_user_metadata(user_dir, user_id)
            return user_dir
        return self.base_workspace

    async def restore_existing_heartbeats(self) -> int:
        """
        Restore persisted user heartbeat loops after backend restart.

        Scheduled social tasks live in per-user HEARTBEAT.md files. The manager's
        cache is in-memory, so restart must scan persisted workspaces and recreate
        HeartbeatService instances before any user sends a new message.
        """
        restored = 0
        async with self._lock:
            heartbeat_files = sorted(self.base_workspace.glob("*/HEARTBEAT.md"))
            for heartbeat_file in heartbeat_files:
                user_workspace = heartbeat_file.parent
                user_id = self._recover_user_id_from_workspace(user_workspace)
                if not user_id:
                    continue

                if user_id in self._heartbeat_cache:
                    continue

                if len(self._heartbeat_cache) >= self._max_cache_size:
                    logger.warning(
                        "heartbeat_restore_cache_limit_reached",
                        max_cache_size=self._max_cache_size
                    )
                    break

                await self._create_user_heartbeat_locked(user_id, user_workspace)
                restored += 1

        logger.info("existing_user_heartbeats_restored", count=restored)
        return restored

    async def cleanup_user_heartbeat(self, user_id: str) -> None:
        """
        清理用户心跳缓存

        Args:
            user_id: 用户ID
        """
        async with self._lock:
            if user_id in self._heartbeat_cache:
                await self._heartbeat_cache[user_id].stop()
                del self._heartbeat_cache[user_id]
                logger.info("user_heartbeat_cleanup", user_id=user_id)

    async def get_all_cached_users(self) -> list[str]:
        """
        获取所有缓存中的用户ID列表

        Returns:
            用户ID列表
        """
        async with self._lock:
            return list(self._heartbeat_cache.keys())

    @property
    def cache_size(self) -> int:
        """获取当前缓存用户数"""
        return len(self._heartbeat_cache)

    async def auto_load_existing_tasks(self) -> None:
        """
        启动时自动扫描所有用户的 HEARTBEAT.md 文件，为有任务的用户创建并启动 HeartbeatService。

        解决问题：后台重启后，即使用户没有发消息，定时任务也能自动执行。
        """
        import re

        loaded_count = 0
        skipped_count = 0

        try:
            # 扫描 heartbeat 目录下的所有用户子目录
            if not self.base_workspace.exists():
                logger.info("heartbeat_workspace_not_exist", path=str(self.base_workspace))
                return

            for user_dir in self.base_workspace.iterdir():
                if not user_dir.is_dir():
                    continue

                heartbeat_file = user_dir / "HEARTBEAT.md"
                if not heartbeat_file.exists():
                    continue

                # 检查文件中是否有启用的任务
                try:
                    content = heartbeat_file.read_text(encoding="utf-8")
                    # 简单检查是否有 enabled: true 的任务
                    if "enabled: true" not in content:
                        skipped_count += 1
                        continue

                    # 还原 user_id（将路径中的 _ 替换回 :）
                    user_id = user_dir.name.replace("_", ":")

                    # 创建并启动 HeartbeatService
                    async with self._lock:
                        if user_id not in self._heartbeat_cache:
                            heartbeat = HeartbeatService(
                                interval_s=30 * 60,
                                workspace=user_dir,
                                user_id=user_id,
                                on_execute=lambda tasks, uid=user_id: self._on_execute_callback(tasks, uid),
                                on_notify=lambda response, uid=user_id: self._on_notify_callback(response, uid)
                            )
                            await heartbeat.start()
                            self._heartbeat_cache[user_id] = heartbeat
                            loaded_count += 1
                            logger.info(
                                "auto_loaded_user_heartbeat",
                                user_id=user_id,
                                heartbeat_file=str(heartbeat_file)
                            )

                except Exception as e:
                    logger.warning(
                        "auto_load_user_failed",
                        user_dir=str(user_dir),
                        error=str(e)
                    )
                    skipped_count += 1

            logger.info(
                "auto_load_existing_tasks_completed",
                loaded=loaded_count,
                skipped=skipped_count,
                total_cached=len(self._heartbeat_cache)
            )

        except Exception as e:
            logger.error("auto_load_existing_tasks_failed", error=str(e), exc_info=True)

    async def shutdown(self) -> None:
        """停止所有用户心跳服务"""
        async with self._lock:
            for user_id, heartbeat in self._heartbeat_cache.items():
                await heartbeat.stop()
            self._heartbeat_cache.clear()
            logger.info("user_heartbeat_manager_shutdown")
