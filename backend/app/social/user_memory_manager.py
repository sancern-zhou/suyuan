"""
用户级记忆管理器

核心功能：
- 管理多个用户的 MemoryStore 实例
- 提供用户记忆隔离
- LRU 缓存优化
"""

from pathlib import Path
from typing import Dict
import asyncio
import structlog

from app.social.memory_store import MemoryStore

logger = structlog.get_logger(__name__)


class UserMemoryManager:
    """用户记忆管理器"""

    def __init__(
        self,
        base_workspace: Path = None,
        max_cache_size: int = 100
    ):
        """
        初始化用户记忆管理器

        Args:
            base_workspace: 基础工作空间目录
            max_cache_size: 最大缓存用户数
        """
        # 解析相对路径为绝对路径（避免工作目录问题）
        if base_workspace is None:
            # 默认使用绝对路径
            base_workspace = Path("/home/xckj/suyuan/backend_data_registry/social/memory")
        elif not base_workspace.is_absolute():
            # 如果是相对路径，转换为绝对路径（相对于backend目录）
            current_file = Path(__file__).resolve()
            backend_dir = current_file.parent.parent  # app/social -> app -> backend
            base_workspace = (backend_dir / base_workspace).resolve()

        self.base_workspace = base_workspace
        self.base_workspace.mkdir(parents=True, exist_ok=True)

        self._memory_cache: Dict[str, MemoryStore] = {}
        self._lock = asyncio.Lock()
        self._max_cache_size = max_cache_size

        logger.info(
            "user_memory_manager_initialized",
            base_workspace=str(self.base_workspace),
            max_cache_size=max_cache_size
        )

    async def get_user_memory(self, user_id: str) -> MemoryStore:
        """
        获取或创建用户 MemoryStore

        Args:
            user_id: 用户ID（格式：{channel}:{bot_account}:{sender_id}）

        Returns:
            用户专属 MemoryStore
        """
        async with self._lock:
            if user_id not in self._memory_cache:
                # LRU 缓存清理
                if len(self._memory_cache) >= self._max_cache_size:
                    oldest_key = next(iter(self._memory_cache))
                    del self._memory_cache[oldest_key]
                    logger.debug("memory_cache_evicted", user_id=oldest_key)

                self._memory_cache[user_id] = MemoryStore(user_id=user_id)
                logger.info("user_memory_created", user_id=user_id)

            return self._memory_cache[user_id]

    async def cleanup_user_memory(self, user_id: str) -> None:
        """
        清理用户记忆缓存

        Args:
            user_id: 用户ID
        """
        async with self._lock:
            if user_id in self._memory_cache:
                del self._memory_cache[user_id]
                logger.info("user_memory_cleanup", user_id=user_id)

    async def get_all_cached_users(self) -> list[str]:
        """
        获取所有缓存中的用户ID列表

        Returns:
            用户ID列表
        """
        async with self._lock:
            return list(self._memory_cache.keys())

    @property
    def cache_size(self) -> int:
        """获取当前缓存用户数"""
        return len(self._memory_cache)
