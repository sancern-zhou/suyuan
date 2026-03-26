"""
双层记忆系统

参考：/tmp/nanobot-main/nanobot/agent/memory.py

核心功能：
- MEMORY.md：长期事实（用户偏好、历史结论、重要数据）
- HISTORY.md：可搜索日志（完整对话历史）
- 自动整合对话内容到记忆
- 提供记忆上下文给LLM
"""

import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class MemoryStore:
    """
    双层记忆系统

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
        workspace: Optional[Path] = None,
        max_memory_size: int = 10000,  # 最大记忆字符数
        max_history_size: int = 50000  # 最大历史字符数
    ):
        """
        初始化记忆存储

        Args:
            workspace: 工作空间目录，默认 backend_data_registry/social/memory
            max_memory_size: MEMORY.md 最大字符数
            max_history_size: HISTORY.md 最大字符数
        """
        self.workspace = workspace or Path("backend_data_registry/social/memory")
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.max_memory_size = max_memory_size
        self.max_history_size = max_history_size

        self.memory_file = self.workspace / "MEMORY.md"
        self.history_file = self.workspace / "HISTORY.md"

        # 初始化文件
        self._init_files()

        logger.info(
            "memory_store_initialized",
            workspace=str(self.workspace),
            max_memory_size=max_memory_size,
            max_history_size=max_history_size
        )

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
        llm_service=None
    ) -> bool:
        """
        整合对话内容到记忆中

        流程：
        1. 当前MEMORY.md + 新对话内容 → LLM分析
        2. 生成新的MEMORY.md（提取重要信息）
        3. 追加到HISTORY.md（完整对话）

        Args:
            messages: 对话消息列表
            llm_service: LLM服务（用于提取重要信息）

        Returns:
            是否成功整合
        """
        try:
            # 1. 追加到HISTORY.md
            await self._append_to_history(messages)

            # 2. 整合到MEMORY.md（如果有LLM服务）
            if llm_service:
                await self._update_memory(messages, llm_service)

            logger.info(
                "memory_consolidated",
                message_count=len(messages)
            )
            return True

        except Exception as e:
            logger.error(
                "memory_consolidation_failed",
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
            response = await llm_service(
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

    def remember_fact(
        self,
        fact: str,
        category: str = "general"
    ) -> bool:
        """
        记住重要事实到MEMORY.md

        Args:
            fact: 事实内容
            category: 分类（如 "user_preference", "conclusion", "data"）

        Returns:
            是否成功
        """
        try:
            current_content = self.memory_file.read_text(encoding="utf-8")

            # 构建新条目
            timestamp = datetime.now().strftime("%Y-%m-%d")
            new_entry = f"\n- {timestamp}: {fact}\n"

            # 根据分类插入到对应位置
            if f"## {category}" in current_content:
                # 插入到对应分类下
                section_pattern = rf"(## {category}.*?\n)"
                import re
                new_content = re.sub(
                    section_pattern,
                    r"\1" + new_entry,
                    current_content,
                    count=1
                )
            else:
                # 添加到文件末尾
                new_content = current_content + f"\n## {category}\n" + new_entry

            # 限制大小
            if len(new_content) > self.max_memory_size:
                # 保留最新的80%
                keep_size = int(self.max_memory_size * 0.8)
                new_content = new_content[-keep_size:]

            self.memory_file.write_text(new_content, encoding="utf-8")

            logger.info(
                "fact_remembered",
                category=category,
                fact_length=len(fact)
            )
            return True

        except Exception as e:
            logger.error(
                "failed_to_remember_fact",
                error=str(e),
                exc_info=True
            )
            return False

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
                import re
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
