"""
文件读取状态管理器 - 用于跟踪文件读取时间戳和内容

参考 Claude Code 官方实现：
- 记录文件读取时间戳（用于检测文件是否被修改）
- 记录文件内容（用于验证文件是否变化）
- 记录是否是完整读取（full read vs partial read）
- 支持过期时间（避免内存泄漏）

用途：
1. edit_file 验证文件是否在读取后被修改
2. edit_file 强制要求先读取文件（预读验证）
3. 检测并发编辑冲突
"""
import time
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from threading import Lock
import structlog

logger = structlog.get_logger()


@dataclass
class ReadTimestamp:
    """
    文件读取时间戳记录

    Attributes:
        timestamp: 读取时间戳（Unix时间戳）
        content: 文件内容（完整读取时记录）
        offset: 分页读取的起始位置（None表示完整读取）
        limit: 分页读取的行数限制（None表示完整读取）
        is_partial_view: 是否是部分视图（分页读取或大文件截断）
        file_size: 文件大小（字节）
        encoding: 文件编码
    """
    timestamp: float
    content: Optional[str] = None
    offset: Optional[int] = None
    limit: Optional[int] = None
    is_partial_view: bool = False
    file_size: int = 0
    encoding: str = "utf-8"

    @property
    def is_full_read(self) -> bool:
        """是否是完整读取（无分页）"""
        return self.offset is None and self.limit is None


class FileReadStateManager:
    """
    文件读取状态管理器（线程安全）

    功能：
    1. 记录文件读取时间和内容
    2. 检测文件是否在读取后被修改
    3. 验证文件是否被读取过（用于edit_file预读验证）
    4. 自动清理过期记录（避免内存泄漏）
    """

    # 默认过期时间（1小时）
    DEFAULT_TTL = 3600

    def __init__(self, ttl: int = DEFAULT_TTL):
        """
        初始化状态管理器

        Args:
            ttl: 记录过期时间（秒），默认1小时
        """
        self._state: Dict[str, ReadTimestamp] = {}
        self._lock = Lock()
        self._ttl = ttl

    def set(
        self,
        file_path: str,
        content: Optional[str] = None,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        is_partial_view: bool = False,
        file_size: int = 0,
        encoding: str = "utf-8"
    ) -> None:
        """
        记录文件读取状态

        Args:
            file_path: 文件路径（绝对路径）
            content: 文件内容（完整读取时记录）
            offset: 分页读取的起始位置
            limit: 分页读取的行数限制
            is_partial_view: 是否是部分视图
            file_size: 文件大小（字节）
            encoding: 文件编码
        """
        with self._lock:
            self._state[file_path] = ReadTimestamp(
                timestamp=time.time(),
                content=content,
                offset=offset,
                limit=limit,
                is_partial_view=is_partial_view,
                file_size=file_size,
                encoding=encoding
            )

            # 清理过期记录
            self._cleanup_expired()

    def get(self, file_path: str) -> Optional[ReadTimestamp]:
        """
        获取文件读取状态

        Args:
            file_path: 文件路径（绝对路径）

        Returns:
            ReadTimestamp 对象，如果文件未被读取则返回 None
        """
        with self._lock:
            return self._state.get(file_path)

    def exists(self, file_path: str) -> bool:
        """
        检查文件是否被读取过

        Args:
            file_path: 文件路径（绝对路径）

        Returns:
            True 如果文件被读取过，否则 False
        """
        return self.get(file_path) is not None

    def is_full_read(self, file_path: str) -> bool:
        """
        检查文件是否是完整读取（无分页）

        Args:
            file_path: 文件路径（绝对路径）

        Returns:
            True 如果文件是完整读取，否则 False
        """
        record = self.get(file_path)
        return record.is_full_read if record else False

    def remove(self, file_path: str) -> None:
        """
        移除文件读取状态

        Args:
            file_path: 文件路径（绝对路径）
        """
        with self._lock:
            self._state.pop(file_path, None)

    def clear(self) -> None:
        """清空所有记录"""
        with self._lock:
            self._state.clear()

    def _cleanup_expired(self) -> None:
        """清理过期记录（内部方法，需在锁内调用）"""
        current_time = time.time()
        expired_keys = [
            path for path, record in self._state.items()
            if current_time - record.timestamp > self._ttl
        ]
        for key in expired_keys:
            del self._state[key]

        if expired_keys:
            logger.debug(
                "file_read_state_cleanup",
                expired_count=len(expired_keys),
                remaining_count=len(self._state)
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        获取状态统计信息（用于调试）

        Returns:
            统计信息字典
        """
        with self._lock:
            current_time = time.time()
            full_reads = sum(
                1 for record in self._state.values() if record.is_full_read
            )
            partial_reads = len(self._state) - full_reads

            return {
                "total_files": len(self._state),
                "full_reads": full_reads,
                "partial_reads": partial_reads,
                "ttl": self._ttl,
                "oldest_record": min(
                    (record.timestamp for record in self._state.values()),
                    default=None
                ),
                "newest_record": max(
                    (record.timestamp for record in self._state.values()),
                    default=None
                )
            }


# 全局单例实例
_global_instance: Optional[FileReadStateManager] = None
_instance_lock = Lock()


def get_file_read_state() -> FileReadStateManager:
    """
    获取全局文件读取状态管理器实例（单例模式）

    Returns:
        FileReadStateManager 实例
    """
    global _global_instance

    if _global_instance is None:
        with _instance_lock:
            if _global_instance is None:
                _global_instance = FileReadStateManager()
                logger.info(
                    "file_read_state_manager_initialized",
                    ttl=_global_instance._ttl
                )

    return _global_instance


def reset_file_read_state() -> None:
    """重置全局文件读取状态管理器（主要用于测试）"""
    global _global_instance

    with _instance_lock:
        if _global_instance is not None:
            _global_instance.clear()
        _global_instance = None

    logger.info("file_read_state_manager_reset")
