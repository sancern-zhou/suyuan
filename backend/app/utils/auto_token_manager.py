"""
Auto Token Manager - 自动Token管理器

学习Mini-Agent的自动Token压缩机制，集成到现有三层记忆系统。
与HybridMemoryManager协同工作，不替换现有记忆机制。

核心功能:
- 准确Token计算（使用tiktoken）
- 自动消息历史摘要（超限时触发）
- 与现有记忆系统无缝集成
"""

from typing import List, Dict, Any, Optional, Callable, Awaitable
from datetime import datetime
import structlog

logger = structlog.get_logger()


class AutoTokenManager:
    """
    自动Token管理器

    与现有三层记忆系统协同工作:
    - WorkingMemory: 短期工作记忆
    - SessionMemory: 会话记忆
    - LongTermMemory: 长期记忆

    本组件负责:
    - 监控Token使用量
    - 在超限时触发自动摘要
    - 提供Token统计信息
    """

    def __init__(
        self,
        token_limit: int = 80000,
        warning_threshold: float = 0.8,
        summarize_callback: Optional[Callable[[List[Dict]], Awaitable[str]]] = None
    ):
        """
        初始化Token管理器

        Args:
            token_limit: Token上限（默认80000）
            warning_threshold: 警告阈值（0.8表示80%时警告）
            summarize_callback: 自定义摘要回调函数
        """
        self.token_limit = token_limit
        self.warning_threshold = warning_threshold
        self.summarize_callback = summarize_callback

        # 跳过下次检查标志（摘要后避免连续触发）
        self._skip_next_check = False

        # API返回的Token使用量（每次LLM调用后更新）
        self.api_total_tokens: int = 0

        # 统计信息
        self.stats = {
            "total_checks": 0,
            "summaries_triggered": 0,
            "tokens_saved": 0,
            "last_check_time": None
        }

        # 尝试加载tiktoken
        self._encoding = None
        try:
            import tiktoken
            self._encoding = tiktoken.get_encoding("cl100k_base")
            logger.info("tiktoken_loaded", encoding="cl100k_base")
        except ImportError:
            logger.warning("tiktoken_not_available", fallback="character_estimation")
        except Exception as e:
            logger.warning("tiktoken_init_failed", error=str(e))

    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        准确计算消息列表的Token数

        Args:
            messages: 消息列表，格式: [{"role": "...", "content": "..."}]

        Returns:
            估算的Token数
        """
        if self._encoding:
            return self._estimate_tokens_tiktoken(messages)
        return self._estimate_tokens_fallback(messages)

    def _estimate_tokens_tiktoken(self, messages: List[Dict[str, Any]]) -> int:
        """使用tiktoken准确计算Token"""
        total_tokens = 0

        for msg in messages:
            # 计算content
            content = msg.get("content", "")
            if isinstance(content, str):
                total_tokens += len(self._encoding.encode(content))
            elif isinstance(content, list):
                # 多模态内容
                for block in content:
                    if isinstance(block, dict):
                        total_tokens += len(self._encoding.encode(str(block)))

            # 计算thinking（如有）
            thinking = msg.get("thinking", "")
            if thinking:
                total_tokens += len(self._encoding.encode(thinking))

            # 计算tool_calls（如有）
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                total_tokens += len(self._encoding.encode(str(tool_calls)))

            # 消息元数据开销（约4个Token）
            total_tokens += 4

        return total_tokens

    def _estimate_tokens_fallback(self, messages: List[Dict[str, Any]]) -> int:
        """后备方案：字符数估算"""
        total_chars = 0

        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total_chars += len(str(block))

            thinking = msg.get("thinking", "")
            if thinking:
                total_chars += len(thinking)

            tool_calls = msg.get("tool_calls")
            if tool_calls:
                total_chars += len(str(tool_calls))

        # 粗略估算：平均2.5字符 = 1 Token
        return int(total_chars / 2.5)

    def update_api_tokens(self, total_tokens: int):
        """
        更新API返回的Token使用量

        Args:
            total_tokens: API返回的总Token数
        """
        self.api_total_tokens = total_tokens
        logger.debug("api_tokens_updated", total_tokens=total_tokens)

    def should_summarize(self, messages: List[Dict[str, Any]]) -> bool:
        """
        检查是否需要触发摘要

        Args:
            messages: 当前消息列表

        Returns:
            是否需要摘要
        """
        self.stats["total_checks"] += 1
        self.stats["last_check_time"] = datetime.now().isoformat()

        # 跳过检查（摘要后首次调用）
        if self._skip_next_check:
            self._skip_next_check = False
            return False

        # 本地估算
        estimated_tokens = self.estimate_tokens(messages)

        # 双重检查：本地估算 OR API返回
        should_summarize = (
            estimated_tokens > self.token_limit or
            self.api_total_tokens > self.token_limit
        )

        if should_summarize:
            logger.info(
                "token_limit_exceeded",
                estimated_tokens=estimated_tokens,
                api_tokens=self.api_total_tokens,
                limit=self.token_limit
            )
        elif estimated_tokens > self.token_limit * self.warning_threshold:
            logger.warning(
                "token_usage_warning",
                estimated_tokens=estimated_tokens,
                threshold=int(self.token_limit * self.warning_threshold)
            )

        return should_summarize

    async def maybe_summarize(
        self,
        messages: List[Dict[str, Any]],
        llm_summarizer: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        检查并可能执行消息摘要

        Args:
            messages: 当前消息列表
            llm_summarizer: LLM摘要函数（可选）

        Returns:
            处理后的消息列表（可能已摘要）
        """
        if not self.should_summarize(messages):
            return messages

        # 记录摘要前Token数
        before_tokens = self.estimate_tokens(messages)

        # 执行摘要
        summarized = await self._summarize_messages(messages, llm_summarizer)

        # 记录统计
        after_tokens = self.estimate_tokens(summarized)
        tokens_saved = before_tokens - after_tokens

        self.stats["summaries_triggered"] += 1
        self.stats["tokens_saved"] += tokens_saved

        # 设置跳过标志
        self._skip_next_check = True

        logger.info(
            "messages_summarized",
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            tokens_saved=tokens_saved,
            messages_before=len(messages),
            messages_after=len(summarized)
        )

        return summarized

    async def _summarize_messages(
        self,
        messages: List[Dict[str, Any]],
        llm_summarizer: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        执行消息摘要（学习Mini-Agent策略）

        策略：
        - 保留system prompt
        - 保留所有user消息
        - 摘要每个user消息后的执行过程

        Args:
            messages: 原始消息列表
            llm_summarizer: LLM摘要函数

        Returns:
            摘要后的消息列表
        """
        # 使用自定义回调（如有）
        if self.summarize_callback:
            try:
                return await self.summarize_callback(messages)
            except Exception as e:
                logger.error("custom_summarize_callback_failed", error=str(e))

        # 默认摘要策略
        if len(messages) < 3:
            return messages

        # 找到所有user消息索引（跳过system prompt）
        user_indices = [
            i for i, msg in enumerate(messages)
            if msg.get("role") == "user" and i > 0
        ]

        if len(user_indices) < 1:
            return messages

        # 构建新消息列表
        new_messages = [messages[0]] if messages[0].get("role") == "system" else []

        for i, user_idx in enumerate(user_indices):
            # 添加user消息
            new_messages.append(messages[user_idx])

            # 确定摘要范围
            if i < len(user_indices) - 1:
                next_user_idx = user_indices[i + 1]
            else:
                next_user_idx = len(messages)

            # 提取执行消息
            execution_messages = messages[user_idx + 1:next_user_idx]

            if execution_messages:
                # 生成摘要
                summary = await self._create_summary(
                    execution_messages,
                    i + 1,
                    llm_summarizer
                )

                if summary:
                    new_messages.append({
                        "role": "user",
                        "content": f"[执行摘要 {i+1}]\n\n{summary}"
                    })

        return new_messages

    async def _create_summary(
        self,
        messages: List[Dict[str, Any]],
        round_num: int,
        llm_summarizer: Optional[Callable] = None
    ) -> str:
        """
        创建单轮执行的摘要

        Args:
            messages: 待摘要的消息
            round_num: 轮次号
            llm_summarizer: LLM摘要函数

        Returns:
            摘要文本
        """
        if not messages:
            return ""

        # 构建摘要内容
        summary_parts = []
        tool_calls = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "assistant":
                if isinstance(content, str) and content:
                    summary_parts.append(f"Assistant: {content[:200]}...")

                if msg.get("tool_calls"):
                    for tc in msg.get("tool_calls", []):
                        if hasattr(tc, "function"):
                            tool_calls.append(tc.function.name)
                        elif isinstance(tc, dict):
                            tool_calls.append(tc.get("function", {}).get("name", "unknown"))

            elif role == "tool":
                tool_name = msg.get("name", "unknown")
                result_preview = str(content)[:100] if content else "无结果"
                summary_parts.append(f"Tool [{tool_name}]: {result_preview}...")

        # 如果有LLM摘要器，使用它生成更好的摘要
        if llm_summarizer and summary_parts:
            try:
                raw_content = "\n".join(summary_parts)
                summary_prompt = f"""请简洁摘要以下Agent执行过程（第{round_num}轮）：

{raw_content}

要求：
1. 聚焦完成了什么任务、调用了哪些工具
2. 保留关键结果和发现
3. 简洁明了，不超过500字
4. 使用中文"""

                summary = await llm_summarizer(summary_prompt)
                return summary
            except Exception as e:
                logger.warning("llm_summary_failed", error=str(e))

        # 后备：简单文本摘要
        if tool_calls:
            return f"第{round_num}轮执行了 {len(tool_calls)} 个工具调用: {', '.join(set(tool_calls))}"

        return f"第{round_num}轮执行了分析步骤"

    def get_stats(self) -> Dict[str, Any]:
        """
        获取Token管理统计信息

        Returns:
            统计信息字典
        """
        return {
            **self.stats,
            "token_limit": self.token_limit,
            "current_api_tokens": self.api_total_tokens,
            "tiktoken_available": self._encoding is not None
        }

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "total_checks": 0,
            "summaries_triggered": 0,
            "tokens_saved": 0,
            "last_check_time": None
        }
        self.api_total_tokens = 0
        logger.info("token_manager_stats_reset")


class TokenAwareMemoryMixin:
    """
    Token感知记忆混入类

    可添加到现有HybridMemoryManager，提供自动Token管理能力
    """

    def __init__(self, token_limit: int = 80000):
        self._token_manager = AutoTokenManager(token_limit=token_limit)

    def get_token_manager(self) -> AutoTokenManager:
        """获取Token管理器"""
        return self._token_manager

    async def check_and_compress_if_needed(
        self,
        messages: List[Dict[str, Any]],
        llm_summarizer: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        检查Token使用并按需压缩

        Args:
            messages: 消息列表
            llm_summarizer: LLM摘要函数

        Returns:
            处理后的消息列表
        """
        return await self._token_manager.maybe_summarize(messages, llm_summarizer)
