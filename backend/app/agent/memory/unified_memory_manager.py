"""
统一记忆管理器

管理所有7种模式（社交、助手、专家、问数、编程、报告、图表）的记忆存储。

核心功能：
- 模式隔离：每个模式独立的记忆空间
- 用户隔离：每个用户独立的记忆空间
- LRU缓存优化：自动清理不活跃的记忆
- 整合偏移量管理：支持增量记忆整合
"""

from pathlib import Path
from typing import Dict, Optional, Any
import asyncio
import structlog

from app.agent.memory.memory_store import MemoryStore, ImprovedMemoryStore

logger = structlog.get_logger(__name__)


class UnifiedMemoryManager:
    """
    统一记忆管理器（支持所有模式）

    管理所有模式的记忆存储，提供统一的记忆操作接口。
    """

    def __init__(
        self,
        base_workspace: str = "../../backend_data_registry/memory",
        max_cache_size: int = 100
    ):
        """
        初始化统一记忆管理器

        Args:
            base_workspace: 基础工作空间目录（相对于 backend 目录）
            max_cache_size: 最大缓存用户数
        """
        # 解析相对路径为绝对路径（避免工作目录问题）
        workspace_path = Path(base_workspace)
        if not workspace_path.is_absolute():
            # 如果是相对路径，相对于当前文件所在目录的父目录（backend）
            current_file = Path(__file__).resolve()
            backend_dir = current_file.parent.parent.parent  # app/agent/memory -> app -> backend
            self.base_workspace = (backend_dir / workspace_path).resolve()
        else:
            self.base_workspace = workspace_path

        self.base_workspace.mkdir(parents=True, exist_ok=True)

        # MemoryStore 缓存（key: f"{mode}:{user_id}"）
        self._memory_cache: Dict[str, MemoryStore] = {}

        # 整合偏移量缓存（key: user_id, value: offset）
        self._offset_cache: Dict[str, int] = {}

        self._lock = asyncio.Lock()
        self._max_cache_size = max_cache_size

        logger.info(
            "unified_memory_manager_initialized",
            base_workspace=str(self.base_workspace),
            max_cache_size=max_cache_size
        )

    async def get_user_memory(
        self,
        user_id: str,
        mode: str
    ) -> MemoryStore:
        """
        获取或创建用户记忆存储

        Args:
            user_id: 用户ID（格式：{mode}:{user_identifier}:{shared|unique}）
            mode: 模式标识（social/assistant/expert/query/code/report/chart）

        Returns:
            用户专属 MemoryStore
        """
        cache_key = f"{mode}:{user_id}"

        async with self._lock:
            if cache_key not in self._memory_cache:
                # LRU 缓存清理
                if len(self._memory_cache) >= self._max_cache_size:
                    oldest_key = next(iter(self._memory_cache))
                    del self._memory_cache[oldest_key]
                    logger.debug("memory_cache_evicted", cache_key=oldest_key)

                # 创建新的 MemoryStore（使用改进版）
                self._memory_cache[cache_key] = ImprovedMemoryStore(
                    user_id=user_id,
                    mode=mode,
                    workspace=self.base_workspace  # ✅ 传递工作空间
                )
                logger.info(
                    "user_memory_created",
                    user_id=user_id,
                    mode=mode,
                    cache_key=cache_key
                )

            return self._memory_cache[cache_key]

    async def get_consolidation_offset(
        self,
        user_id: str
    ) -> int:
        """
        获取整合偏移量

        Args:
            user_id: 用户ID

        Returns:
            整合偏移量（已整合的消息数）
        """
        return self._offset_cache.get(user_id, 0)

    async def set_consolidation_offset(
        self,
        user_id: str,
        offset: int
    ) -> None:
        """
        设置整合偏移量

        Args:
            user_id: 用户ID
            offset: 整合偏移量（已整合的消息数）
        """
        self._offset_cache[user_id] = offset
        logger.debug(
            "consolidation_offset_updated",
            user_id=user_id,
            offset=offset
        )

    async def cleanup_user_memory(
        self,
        user_id: str,
        mode: str
    ) -> None:
        """
        清理用户记忆缓存

        Args:
            user_id: 用户ID
            mode: 模式标识
        """
        cache_key = f"{mode}:{user_id}"

        async with self._lock:
            if cache_key in self._memory_cache:
                del self._memory_cache[cache_key]
                logger.info(
                    "user_memory_cleanup",
                    user_id=user_id,
                    mode=mode,
                    cache_key=cache_key
                )

    async def cleanup_mode_memory(self, mode: str) -> None:
        """
        清理指定模式的记忆缓存

        Args:
            mode: 模式标识
        """
        async with self._lock:
            # 找出所有匹配模式的缓存
            keys_to_remove = [
                key for key in self._memory_cache.keys()
                if key.startswith(f"{mode}:")
            ]

            for key in keys_to_remove:
                del self._memory_cache[key]

            logger.info(
                "mode_memory_cleanup",
                mode=mode,
                removed_count=len(keys_to_remove)
            )

    async def get_all_cached_users(self, mode: Optional[str] = None) -> list[str]:
        """
        获取所有缓存中的用户ID列表

        Args:
            mode: 可选的模式过滤器

        Returns:
            用户ID列表（格式：{mode}:{user_id}）
        """
        async with self._lock:
            if mode:
                # 返回指定模式的用户
                return [
                    key for key in self._memory_cache.keys()
                    if key.startswith(f"{mode}:")
                ]
            return list(self._memory_cache.keys())

    async def get_all_modes_for_user(self, user_id: str) -> list[str]:
        """
        获取用户在所有模式中的缓存情况

        Args:
            user_id: 用户ID

        Returns:
            模式列表（用户在这些模式中有缓存）
        """
        modes = set()

        async with self._lock:
            for cache_key in self._memory_cache.keys():
                # cache_key 格式：{mode}:{user_id}
                # user_id 可能包含冒号，所以需要从右边分割
                parts = cache_key.rsplit(":", 1)
                if len(parts) == 2 and parts[1] == user_id:
                    # 提取模式（去掉 "mode:" 前缀）
                    mode_part = parts[0]
                    if ":" in mode_part:
                        mode = mode_part.split(":")[0]
                    else:
                        mode = mode_part
                    modes.add(mode)

        return list(modes)

    @property
    def cache_size(self) -> int:
        """获取当前缓存用户数"""
        return len(self._memory_cache)

    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            统计信息字典
        """
        async with self._lock:
            # 按模式统计
            mode_counts: Dict[str, int] = {}

            for cache_key in self._memory_cache.keys():
                # 提取模式
                parts = cache_key.split(":", 1)
                if parts:
                    mode = parts[0]
                    mode_counts[mode] = mode_counts.get(mode, 0) + 1

            return {
                "total_cache_size": len(self._memory_cache),
                "max_cache_size": self._max_cache_size,
                "mode_counts": mode_counts,
                "offset_cache_size": len(self._offset_cache)
            }
