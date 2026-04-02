"""
通用双层记忆系统

从 app/social/memory_store.py 迁移，支持所有7种模式（社交、助手、专家、问数、编程、报告、图表）

核心功能：
- MEMORY.md：长期事实（用户偏好、历史结论、重要数据）
- HISTORY.md：可搜索日志（完整对话历史）
- 自动整合对话内容到记忆
- 提供记忆上下文给LLM

改进版（参考 nanobot）：
- 使用JSON响应方式（更可靠）
- 失败重试机制
- 原始归档降级
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


class MemoryStore:
    """
    通用双层记忆系统（支持所有模式）

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
        user_id: Optional[str] = None,
        mode: str = "expert",  # ✅ 新增：模式标识（social/assistant/expert/query/code/report/chart）
        workspace: Optional[Path] = None,
        max_memory_size: int = 10000,  # 最大记忆字符数
        max_history_size: int = 50000  # 最大历史字符数
    ):
        """
        初始化记忆存储

        Args:
            user_id: 用户ID（格式：{mode}:{user_identifier}:{shared|unique}）
            mode: 模式标识（social/assistant/expert/query/code/report/chart）
            workspace: 工作空间目录，默认 backend_data_registry/memory
            max_memory_size: MEMORY.md 最大字符数
            max_history_size: HISTORY.md 最大字符数
        """
        self.user_id = user_id or "global"  # 默认全局记忆（向后兼容）
        self.mode = mode
        self.max_memory_size = max_memory_size
        self.max_history_size = max_history_size

        # ✅ 模式专属工作空间
        self.workspace = self._init_workspace(workspace, user_id, mode)
        self.memory_file = self.workspace / "MEMORY.md"
        self.history_file = self.workspace / "HISTORY.md"

        # 初始化文件
        self._init_files()

        logger.debug(
            "memory_store_initialized",
            user_id=self.user_id,
            mode=self.mode,
            workspace=str(self.workspace)
        )

    def _init_workspace(self, workspace: Path, user_id: str, mode: str) -> Path:
        """
        初始化模式专属工作空间

        Args:
            workspace: 基础工作空间
            user_id: 用户ID
            mode: 模式标识

        Returns:
            用户专属工作空间路径
        """
        base = workspace or Path("backend_data_registry/memory")

        # 按mode分组存储
        mode_dir = base / mode
        mode_dir.mkdir(parents=True, exist_ok=True)

        if user_id and user_id != "global":
            # 用户专属目录
            # 文件系统将 : 替换为 _ 以避免路径问题
            safe_user_id = user_id.replace(":", "_")
            user_dir = mode_dir / safe_user_id
            user_dir.mkdir(parents=True, exist_ok=True)
            return user_dir

        # 全局目录（向后兼容）
        return mode_dir

    def _init_files(self) -> None:
        """初始化MEMORY.md和HISTORY.md文件"""
        if not self.memory_file.exists():
            initial_memory = """# 长期记忆 (MEMORY.md)

此文件存储用户的偏好、重要结论和关键信息。

## 用户偏好

## 历史结论

## 重要数据
"""
            self.memory_file.write_text(initial_memory, encoding="utf-8")
            logger.info("memory_file_created", path=str(self.memory_file))

        if not self.history_file.exists():
            initial_history = """# 对话历史 (HISTORY.md)

此文件按时间倒序记录完整的对话历史，用于回溯和查找。

---
"""
            self.history_file.write_text(initial_history, encoding="utf-8")
            logger.info("history_file_created", path=str(self.history_file))

    def get_memory_context(self) -> str:
        """
        获取记忆上下文（用于LLM）

        Returns:
            MEMORY.md的内容（如果为空则返回空字符串）
        """
        try:
            memory_content = self.memory_file.read_text(encoding="utf-8")

            # 过滤掉空内容
            if memory_content.strip() in ["", "# 长期记忆 (MEMORY.md)", "# 长期记忆 (MEMORY.md)\n"]:
                return ""

            return f"## 长期记忆\n{memory_content}"

        except Exception as e:
            logger.error(
                "failed_to_read_memory",
                error=str(e),
                exc_info=True
            )
            return ""

    async def consolidate(
        self,
        messages: List[Dict[str, Any]],
        llm_service=None,
        start_offset: int = 0
    ) -> bool:
        """
        增量整合对话内容到记忆中

        流程：
        1. 当前MEMORY.md + 新对话内容 → LLM分析
        2. 生成新的MEMORY.md（提取重要信息）
        3. 追加到HISTORY.md（完整对话）

        Args:
            messages: 对话消息列表
            llm_service: LLM服务（用于提取重要信息）
            start_offset: 起始消息偏移量（避免重复整合）

        Returns:
            是否成功整合
        """
        if not messages:
            return True

        # 只整合从 start_offset 之后的新消息
        new_messages = messages[start_offset:] if start_offset > 0 else messages

        if not new_messages:
            return True

        try:
            # 1. 追加到HISTORY.md
            await self._append_to_history(new_messages)

            # 2. 整合到MEMORY.md（如果有LLM服务）
            if llm_service:
                await self._update_memory(new_messages, llm_service)

            logger.info(
                "memory_consolidated",
                user_id=self.user_id,
                mode=self.mode,
                message_count=len(new_messages),
                start_offset=start_offset
            )
            return True

        except Exception as e:
            logger.error(
                "memory_consolidation_failed",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e),
                exc_info=True
            )
            return False

    async def _append_to_history(self, messages: List[Dict[str, Any]]) -> None:
        """
        追加对话到HISTORY.md

        Args:
            messages: 对话消息列表
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构建历史条目
        history_entry = f"\n## {timestamp}\n\n"

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                history_entry += f"**用户**: {content}\n\n"
            elif role == "assistant":
                # 只保留前500个字符，避免历史过长
                preview = content[:500] + "..." if len(content) > 500 else content
                history_entry += f"**助手**: {preview}\n\n"

        history_entry += "---\n"

        # 追加到文件
        current_content = self.history_file.read_text(encoding="utf-8")

        # 检查文件大小，超过限制则清理旧内容
        if len(current_content) + len(history_entry) > self.max_history_size:
            # 保留最新的80%
            keep_size = int(self.max_history_size * 0.8)
            current_content = current_content[-keep_size:]

        new_content = current_content + history_entry
        self.history_file.write_text(new_content, encoding="utf-8")

        logger.debug("history_updated", entry_length=len(history_entry))

    async def _update_memory(
        self,
        messages: List[Dict[str, Any]],
        llm_service
    ) -> None:
        """
        使用LLM更新MEMORY.md

        Args:
            messages: 对话消息列表
            llm_service: LLM服务
        """
        # 提取对话内容
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages[-5:]  # 只使用最近5条消息
        ])

        current_memory = self.memory_file.read_text(encoding="utf-8")

        # 构建提示词
        prompt = f"""你是一个记忆管理助手。请根据以下对话内容，更新长期记忆。

当前记忆：
{current_memory}

新的对话内容：
{conversation_text}

请执行以下任务：
1. 提取对话中的重要信息（用户偏好、关键结论、有用数据）
2. 整合到当前记忆中
3. 去除重复或过时的信息
4. 返回更新后的完整记忆内容（Markdown格式）

**重要**：
- 只返回更新后的记忆内容，不要有其他解释
- 保持简洁，记忆内容不超过1000字
- 使用清晰的分类和标题
"""

        try:
            # 调用LLM
            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000
            )

            # 提取LLM返回的内容
            if isinstance(response, dict):
                new_memory = response.get("content", "")
            else:
                new_memory = str(response)

            # 限制大小
            if len(new_memory) > self.max_memory_size:
                new_memory = new_memory[:self.max_memory_size]

            # 更新MEMORY.md
            if new_memory.strip():
                self.memory_file.write_text(new_memory, encoding="utf-8")
                logger.debug("memory_updated_by_llm", new_size=len(new_memory))

        except Exception as e:
            logger.error(
                "failed_to_update_memory_with_llm",
                error=str(e),
                exc_info=True
            )

    def search_history(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索HISTORY.md历史对话

        Args:
            query: 搜索关键词
            limit: 返回结果数量限制

        Returns:
            匹配的历史条目列表
        """
        try:
            history_content = self.history_file.read_text(encoding="utf-8")

            # 简单的文本搜索（按行匹配）
            results = []
            lines = history_content.split("\n")

            for i, line in enumerate(lines):
                if query.lower() in line.lower():
                    # 获取上下文（前后各2行）
                    context_start = max(0, i - 2)
                    context_end = min(len(lines), i + 3)
                    context = "\n".join(lines[context_start:context_end])

                    results.append({
                        "match": line.strip(),
                        "context": context,
                        "line_number": i + 1
                    })

                    if len(results) >= limit:
                        break

            logger.info(
                "history_searched",
                mode=self.mode,
                query=query,
                results_found=len(results)
            )
            return results

        except Exception as e:
            logger.error(
                "failed_to_search_history",
                error=str(e),
                exc_info=True
            )
            return []

    def get_user_preferences(self) -> Dict[str, Any]:
        """
        获取用户偏好（从MEMORY.md解析）

        Returns:
            用户偏好字典
        """
        try:
            memory_content = self.memory_file.read_text(encoding="utf-8")

            preferences = {}

            # 简单解析：提取 "用户偏好" 部分的内容
            if "## 用户偏好" in memory_content:
                section_start = memory_content.index("## 用户偏好")
                section_end = memory_content.find("\n##", section_start + 1)
                if section_end == -1:
                    section_end = len(memory_content)

                section_content = memory_content[section_start:section_end]

                # 提取条目（简化实现）
                pattern = r"-\s*(.+?):\s*(.+)"
                matches = re.findall(pattern, section_content)
                for key, value in matches:
                    preferences[key.strip()] = value.strip()

            return preferences

        except Exception as e:
            logger.error(
                "failed_to_get_user_preferences",
                error=str(e)
            )
            return {}


# ============================================================================
# 改进版记忆合并器（使用 JSON 响应，无需工具调用）
# ============================================================================

class ImprovedMemoryStore(MemoryStore):
    """
    改进版记忆存储（参考 nanobot）

    改进点：
    1. 使用JSON响应方式（更可靠）
    2. 失败重试机制（最多3次）
    3. 原始归档降级
    4. 更好的错误处理
    """

    _MAX_FAILURES_BEFORE_RAW_ARCHIVE = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._consecutive_failures = 0

    @staticmethod
    def _format_messages(messages: List[Dict[str, Any]]) -> str:
        """格式化消息列表为文本（用于提示词）"""
        lines = []
        for message in messages:
            if not message.get("content"):
                continue

            role = message.get("role", "unknown").upper()
            content = message.get("content", "")

            # 添加工具使用信息
            tools = message.get("tools_used", [])
            tool_info = f" [工具: {', '.join(tools)}]" if tools else ""

            # 添加时间戳
            timestamp = message.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))

            lines.append(f"[{timestamp}] {role}{tool_info}: {content}")

        return "\n".join(lines)

    async def consolidate_improved(
        self,
        messages: List[Dict[str, Any]],
        model: str = "mimo-v2-flash",
    ) -> bool:
        """
        改进版记忆合并（使用 JSON 响应）

        Args:
            messages: 要合并的消息列表
            model: 使用的模型

        Returns:
            是否成功合并
        """
        if not messages:
            return True

        from app.services.llm_service import LLMService

        current_memory = self.read_long_term()

        # 构造提示词（要求返回 JSON）
        prompt = f"""请分析以下对话并返回 JSON 格式的记忆合并结果。

## 当前长期记忆
{current_memory or "(空)"}

## 待处理的对话
{self._format_messages(messages)}

**任务**：
1. 分析对话内容，提取重要信息（用户偏好、关键结论、重要数据）
2. 生成 history_entry：一段简洁的对话摘要（格式：[YYYY-MM-DD HH:MM] 摘要内容，包含关键事件、决策、主题，便于 grep 搜索）
3. 生成 memory_update：更新后的长期记忆（Markdown格式，包含所有原有记忆+新信息）

**要求**：
- 保持记忆简洁（不超过1000字）
- 使用清晰的分类和标题
- 避免重复信息

**返回格式（必须严格遵守）**：
```json
{{
    "history_entry": "对话摘要",
    "memory_update": "更新后的长期记忆（Markdown格式）"
}}
```

请只返回 JSON，不要有其他内容。"""

        try:
            # 使用现有的 JSON 响应方法
            llm_service = LLMService()
            response = await llm_service.call_llm_with_json_response(
                prompt=prompt,
                max_retries=2
            )

            if not response.get("success"):
                logger.warning(
                    "memory_consolidation_llm_failed",
                    user_id=self.user_id,
                    mode=self.mode,
                    error=response.get("error", "Unknown error")
                )
                return self._fail_or_raw_archive(messages)

            # 提取数据
            data = response.get("data")

            if not data:
                logger.warning(
                    "memory_consolidation_no_data",
                    user_id=self.user_id,
                    mode=self.mode,
                    response=response
                )
                return self._fail_or_raw_archive(messages)

            # 验证字段
            if "history_entry" not in data or "memory_update" not in data:
                logger.warning(
                    "memory_consolidation_missing_fields",
                    user_id=self.user_id,
                    mode=self.mode,
                    data_keys=list(data.keys())
                )
                return self._fail_or_raw_archive(messages)

            entry = data["history_entry"]
            update = data["memory_update"]

            if not entry or not update:
                logger.warning(
                    "memory_consolidation_empty_fields",
                    user_id=self.user_id,
                    mode=self.mode
                )
                return self._fail_or_raw_archive(messages)

            # 保存到文件
            entry = str(entry).strip()
            update = str(update).strip()

            if not entry:
                logger.warning(
                    "memory_consolidation_empty_entry",
                    user_id=self.user_id,
                    mode=self.mode
                )
                return self._fail_or_raw_archive(messages)

            # 追加到历史
            self.append_history(entry)

            # 更新长期记忆
            if update != current_memory:
                self.write_long_term(update)

            # 重置失败计数
            self._consecutive_failures = 0
            logger.info(
                "memory_consolidation_success",
                user_id=self.user_id,
                mode=self.mode,
                messages_count=len(messages),
                entry_length=len(entry),
                memory_length=len(update)
            )
            return True

        except Exception as e:
            logger.exception(
                "memory_consolidation_failed",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e)
            )
            return self._fail_or_raw_archive(messages)

    def append_history(self, entry: str) -> None:
        """追加到历史记录"""
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(entry.rstrip() + "\n\n")
            logger.debug(
                "history_appended",
                user_id=self.user_id,
                mode=self.mode,
                entry_length=len(entry)
            )
        except Exception as e:
            logger.error(
                "failed_to_append_history",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e)
            )
            raise

    def read_long_term(self) -> str:
        """读取长期记忆内容"""
        try:
            if not self.memory_file.exists():
                return ""

            content = self.memory_file.read_text(encoding="utf-8")

            # 过滤掉空内容或只有标题的情况
            if content.strip() in ["", "# 长期记忆 (MEMORY.md)", "# 长期记忆 (MEMORY.md)\n"]:
                return ""

            return content

        except Exception as e:
            logger.error(
                "failed_to_read_long_term_memory",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e)
            )
            return ""

    def write_long_term(self, content: str) -> None:
        """写入长期记忆"""
        try:
            self.memory_file.write_text(content, encoding="utf-8")
            logger.info(
                "long_term_memory_updated",
                user_id=self.user_id,
                mode=self.mode,
                length=len(content)
            )
        except Exception as e:
            logger.error(
                "failed_to_write_long_term_memory",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e)
            )
            raise

    def _fail_or_raw_archive(self, messages: List[Dict[str, Any]]) -> bool:
        """
        失败处理：增加失败计数，达到阈值后原始归档

        Returns:
            False - 仍需重试
            True - 已原始归档，不需要重试
        """
        self._consecutive_failures += 1

        if self._consecutive_failures < self._MAX_FAILURES_BEFORE_RAW_ARCHIVE:
            return False

        # 原始归档（直接保存消息，不通过 LLM）
        self._raw_archive(messages)
        self._consecutive_failures = 0
        return True

    def _raw_archive(self, messages: List[Dict[str, Any]]) -> None:
        """原始归档：直接将消息转存到 HISTORY.md"""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        formatted_messages = self._format_messages(messages)

        entry = f"[{ts}] [原始归档] {len(messages)} 条消息\n{formatted_messages}\n\n"

        self.append_history(entry)
        logger.warning(
            "memory_consolidation_raw_archive",
            user_id=self.user_id,
            mode=self.mode,
            messages_count=len(messages)
        )


class MemoryConsolidator:
    """
    记忆合并器（参考 nanobot）

    职责：
    1. 合并策略管理
    2. 会话锁定（避免并发冲突）
    3. Token预算控制
    4. 自动触发合并
    """

    _MAX_CONSOLIDATION_ROUNDS = 5
    _SAFETY_BUFFER = 1024  # Token估算的额外缓冲

    def __init__(
        self,
        context_window_tokens: int = 200000,
        max_completion_tokens: int = 4096,
    ):
        """
        初始化记忆合并器

        Args:
            context_window_tokens: 上下文窗口大小（tokens）
            max_completion_tokens: 最大完成tokens
        """
        self.context_window_tokens = context_window_tokens
        self.max_completion_tokens = max_completion_tokens
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    def get_lock(self, session_key: str) -> asyncio.Lock:
        """获取会话的合并锁（避免并发冲突）"""
        return self._locks.setdefault(session_key, asyncio.Lock())

    async def consolidate_messages(
        self,
        user_id: str,
        mode: str,
        messages: List[Dict[str, Any]],
        model: str = "mimo-v2-flash",
    ) -> bool:
        """
        合并消息到持久化存储

        Args:
            user_id: 用户ID
            mode: 模式标识
            messages: 要合并的消息列表
            model: 使用的模型

        Returns:
            是否成功
        """
        store = ImprovedMemoryStore(user_id=user_id, mode=mode)
        return await store.consolidate_improved(messages, model)

    async def maybe_consolidate_by_tokens(
        self,
        session_key: str,
        current_tokens: int,
        user_id: str,
        mode: str,
        messages: List[Dict[str, Any]],
        model: str = "mimo-v2-flash",
    ) -> bool:
        """
        根据 Token预算自动触发合并

        Args:
            session_key: 会话键
            current_tokens: 当前使用的tokens
            user_id: 用户ID
            mode: 模式标识
            messages: 当前消息列表
            model: 使用的模型

        Returns:
            是否执行了合并
        """
        if not messages:
            return False

        # 计算预算
        budget = self.context_window_tokens - self.max_completion_tokens - self._SAFETY_BUFFER
        target = budget // 2  # 目标：保持一半预算

        if current_tokens <= 0:
            return False

        # 如果在预算内，不需要合并
        if current_tokens < budget:
            logger.debug(
                "token_consolidation_idle",
                session_key=session_key,
                current_tokens=current_tokens,
                budget=budget
            )
            return False

        # 获取锁
        lock = self.get_lock(session_key)
        async with lock:
            # 需要移除的tokens
            tokens_to_remove = current_tokens - target

            # 计算要合并的消息数量（估算：每条消息平均500 tokens）
            avg_tokens_per_message = 500
            messages_to_consolidate = max(1, tokens_to_remove // avg_tokens_per_message)

            # 取最近的消息
            messages_chunk = messages[:messages_to_consolidate]

            if not messages_chunk:
                return False

            logger.info(
                "token_consolidation_triggered",
                session_key=session_key,
                current_tokens=current_tokens,
                budget=budget,
                messages_to_consolidate=len(messages_chunk)
            )

            # 执行合并
            success = await self.consolidate_messages(
                user_id=user_id,
                mode=mode,
                messages=messages_chunk,
                model=model,
            )

            return success
