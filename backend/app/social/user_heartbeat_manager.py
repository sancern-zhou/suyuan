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
                heartbeat = HeartbeatService(
                    interval_s=30 * 60,
                    workspace=user_workspace,
                    user_id=user_id,
                    on_execute=lambda tasks: self._on_execute_callback(tasks, user_id),
                    on_notify=lambda response: self._on_notify_callback(response, user_id)
                )
                await heartbeat.start()
                self._heartbeat_cache[user_id] = heartbeat

                logger.info("user_heartbeat_created", user_id=user_id)

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
            return user_dir
        return self.base_workspace

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

    async def shutdown(self) -> None:
        """停止所有用户心跳服务"""
        async with self._lock:
            for user_id, heartbeat in self._heartbeat_cache.items():
                await heartbeat.stop()
            self._heartbeat_cache.clear()
            logger.info("user_heartbeat_manager_shutdown")
