"""
社交模式双层记忆系统（兼容层）

⚠️ 此文件为兼容层，实际逻辑已迁移到 app/agent/memory/memory_store.py

核心功能：
- MEMORY.md：长期事实（用户偏好、历史结论、重要数据）
- HISTORY.md：可搜索日志（完整对话历史）
- 自动整合对话内容到记忆
- 提供记忆上下文给LLM

改进版（参考 nanobot）：
- 使用JSON响应方式（更可靠）
- 失败重试机制
- 原始归档降级

**向后兼容**：
- 保持社交模式现有API不变
- 内部委托给通用MemoryStore（mode="social"）
"""

import asyncio
import json
import re
import weakref
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

# 导入通用MemoryStore（从通用位置）
from app.agent.memory.memory_store import (
    MemoryStore as BaseMemoryStore,
    ImprovedMemoryStore as BaseImprovedMemoryStore,
    MemoryConsolidator as BaseMemoryConsolidator
)


class MemoryStore(BaseMemoryStore):
    """
    社交模式双层记忆系统（兼容层）

    ⚠️ 此类为兼容层，内部委托给通用MemoryStore（mode="social"）

    MEMORY.md：
    - 长期事实（用户偏好、历史结论、重要数据）
    - 持久化存储
    - 自动整合到上下文

    HISTORY.md：
    - 可搜索日志（完整对话历史）
    - 按时间倒序
    - 用于回溯和查找
    """

    def __init__(
        self,
        user_id: Optional[str] = None,  # 用户ID（格式：{channel}:{bot_account}:{sender_id}）
        workspace: Optional[Path] = None,  # ⚠️ 已弃用：保留用于向后兼容
        max_memory_size: int = 10000,  # 最大记忆字符数
        max_history_size: int = 50000  # 最大历史字符数
    ):
        """
        初始化社交模式记忆存储（兼容层）

        Args:
            user_id: 用户ID（格式：{channel}:{bot_account}:{sender_id}）
            workspace: ⚠️ 已弃用：保留用于向后兼容（现在使用 backend_data_registry/social/memory）
            max_memory_size: MEMORY.md 最大字符数
            max_history_size: HISTORY.md 最大字符数
        """
        # 社交模式使用特殊的工作空间路径（向后兼容）
        # 旧格式：{workspace}/{safe_user_id}/
        # 新格式（其他模式）：{workspace}/{mode}/{safe_user_id}/

        # 解析相对路径为绝对路径（避免工作目录问题）
        if workspace is None:
            # 默认使用绝对路径
            social_workspace = Path("/home/xckj/suyuan/backend_data_registry/social/memory")
        elif not workspace.is_absolute():
            # 如果是相对路径，转换为绝对路径（相对于backend目录）
            current_file = Path(__file__).resolve()
            backend_dir = current_file.parent.parent  # app/social -> app -> backend
            social_workspace = (backend_dir / workspace).resolve()
        else:
            social_workspace = workspace

        # 调用父类构造函数，传递 mode="social"
        super().__init__(
            user_id=user_id,
            mode="social",  # ✅ 固定为 social 模式
            workspace=social_workspace,
            max_memory_size=max_memory_size,
            max_history_size=max_history_size
        )

        # ✅ 向后兼容：修正工作空间路径
        # 父类会创建 {workspace}/social/{safe_user_id}/
        # 我们需要修改为 {workspace}/{safe_user_id}/（旧格式）
        if user_id and user_id != "global":
            safe_user_id = user_id.replace(":", "_")
            # 重新设置工作空间为旧格式
            self.workspace = social_workspace / safe_user_id
            self.workspace.mkdir(parents=True, exist_ok=True)
            # 重新设置文件路径
            self.memory_file = self.workspace / "MEMORY.md"
            self.history_file = self.workspace / "HISTORY.md"
            # 重新初始化文件（如果不存在）
            self._init_files()

        logger.debug(
            "social_memory_store_initialized",
            user_id=self.user_id,
            workspace=str(self.workspace)
        )


# ============================================================================
# 改进版记忆合并器（兼容层）
# ============================================================================

class ImprovedMemoryStore(BaseImprovedMemoryStore):
    """
    社交模式改进版记忆存储（兼容层）

    ⚠️ 此类为兼容层，内部委托给通用ImprovedMemoryStore（mode="social"）

    改进点：
    1. 使用JSON响应方式（更可靠）
    2. 失败重试机制（最多3次）
    3. 原始归档降级
    4. 更好的错误处理
    """

    def __init__(self, *args, **kwargs):
        # 调用父类构造函数，传递 mode="social"
        # 如果 kwargs 中没有 mode，则添加 mode="social"
        if 'mode' not in kwargs:
            kwargs['mode'] = 'social'

        # ✅ 提取参数用于路径覆盖
        user_id = kwargs.get('user_id')
        workspace = kwargs.get('workspace')

        # 解析社交模式专用工作空间
        if workspace is None:
            from pathlib import Path
            social_workspace = Path("/home/xckj/suyuan/backend_data_registry/social/memory")
        elif not workspace.is_absolute():
            from pathlib import Path
            current_file = Path(__file__).resolve()
            backend_dir = current_file.parent.parent
            social_workspace = (backend_dir / workspace).resolve()
        else:
            social_workspace = workspace

        # ✅ 更新 kwargs 中的 workspace，确保父类使用正确的路径
        kwargs['workspace'] = social_workspace

        # 调用父类构造函数
        super().__init__(*args, **kwargs)

        # ✅ 路径覆盖逻辑（与 MemoryStore 一致）
        # 父类会创建 {workspace}/social/{safe_user_id}/
        # 我们需要修改为 {workspace}/{safe_user_id}/（用户隔离格式）
        if user_id and user_id != "global":
            safe_user_id = user_id.replace(":", "_")
            # 重新设置工作空间为用户隔离格式
            self.workspace = social_workspace / safe_user_id
            self.workspace.mkdir(parents=True, exist_ok=True)
            # 重新设置文件路径
            self.memory_file = self.workspace / "MEMORY.md"
            self.history_file = self.workspace / "HISTORY.md"
            # 重新初始化文件（如果不存在）
            self._init_files()

        logger.debug(
            "social_improved_memory_store_initialized",
            user_id=self.user_id,
            mode=self.mode,
            workspace=str(self.workspace)
        )


class MemoryConsolidator(BaseMemoryConsolidator):
    """
    社交模式记忆合并器（兼容层）

    ⚠️ 此类为兼容层，内部委托给通用MemoryConsolidator（mode="social"）

    职责：
    1. 合并策略管理
    2. 会话锁定（避免并发冲突）
    3. Token预算控制
    4. 自动触发合并
    """

    def __init__(
        self,
        context_window_tokens: int = 200000,
        max_completion_tokens: int = 4096,
    ):
        """
        初始化社交模式记忆合并器（兼容层）

        Args:
            context_window_tokens: 上下文窗口大小（tokens）
            max_completion_tokens: 最大完成tokens
        """
        # 调用父类构造函数
        super().__init__(
            context_window_tokens=context_window_tokens,
            max_completion_tokens=max_completion_tokens
        )

        logger.debug(
            "social_memory_consolidator_initialized",
            context_window_tokens=context_window_tokens,
            max_completion_tokens=max_completion_tokens
        )

    async def consolidate_messages(
        self,
        user_id: str,
        messages: List[Dict[str, Any]],
        llm_call: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,  # ⚠️ 已弃用
        model: str = "mimo-v2-flash",
    ) -> bool:
        """
        合并消息到持久化存储（兼容层）

        Args:
            user_id: 用户ID
            messages: 要合并的消息列表
            llm_call: ⚠️ 已弃用：保留用于向后兼容（现在使用内部LLM服务）
            model: 使用的模型

        Returns:
            是否成功
        """
        # 调用父类方法，传递 mode="social"
        return await super().consolidate_messages(
            user_id=user_id,
            mode="social",
            messages=messages,
            model=model
        )

    async def maybe_consolidate_by_tokens(
        self,
        session_key: str,
        current_tokens: int,
        user_id: str,
        messages: List[Dict[str, Any]],
        llm_call: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,  # ⚠️ 已弃用
        model: str = "mimo-v2-flash",
    ) -> bool:
        """
        根据 Token预算自动触发合并（兼容层）

        Args:
            session_key: 会话键
            current_tokens: 当前使用的tokens
            user_id: 用户ID
            messages: 当前消息列表
            llm_call: ⚠️ 已弃用：保留用于向后兼容（现在使用内部LLM服务）
            model: 使用的模型

        Returns:
            是否执行了合并
        """
        # 调用父类方法，传递 mode="social"
        return await super().maybe_consolidate_by_tokens(
            session_key=session_key,
            current_tokens=current_tokens,
            user_id=user_id,
            mode="social",
            messages=messages,
            model=model
        )

