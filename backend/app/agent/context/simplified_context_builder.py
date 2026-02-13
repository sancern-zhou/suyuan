"""
简化的上下文构建器

按照提示词结构分为两部分：
1. 系统提示词：REACT_SYSTEM_PROMPT + 工具摘要
2. 用户对话内容：Conversation History + Current Query + Latest Observation
"""

from typing import Dict, Any, List, Optional
import structlog
from datetime import datetime

from ..memory.context_compressor import ContextCompressor
from ...utils.token_budget import token_budget_manager

logger = structlog.get_logger()


class SimplifiedContextBuilder:
    """
    简化的上下文构建器

    核心职责：
    1. 构建系统提示词（固定部分）
    2. 构建用户对话内容（动态部分）
    3. 超过80%阈值时触发LLM压缩
    """

    def __init__(self, llm_client, memory_manager, tool_registry=None):
        """
        初始化简化的上下文构建器

        Args:
            llm_client: LLM客户端（用于压缩）
            memory_manager: HybridMemoryManager实例
            tool_registry: 工具注册表（可选）
        """
        self.llm_client = llm_client
        self.memory = memory_manager
        self.tool_registry = tool_registry
        self.compressor = ContextCompressor(llm_client)

        # Token配置
        self.max_context_tokens = token_budget_manager.max_context_tokens
        self.safety_buffer = token_budget_manager.safety_buffer
        self.compression_threshold = 0.8  # 80%阈值

        logger.info(
            "simplified_context_builder_initialized",
            max_context=self.max_context_tokens,
            safety_buffer=self.safety_buffer,
            compression_threshold=f"{self.compression_threshold*100}%"
        )

    async def build_for_thought_action(
        self,
        query: str,
        iteration: int,
        latest_observation: str = "",
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        为 Thought + Action 构建完整上下文

        Args:
            query: 用户查询
            iteration: 当前迭代次数
            latest_observation: 最新观察结果（可选）
            conversation_history: 对话历史（可选，LLM消息格式）

        Returns:
            {
                "system_prompt": str,      # 系统提示词（固定）
                "user_conversation": str,   # 用户对话内容（动态）
                "tokens": {
                    "system": int,
                    "user": int,
                    "total": int,
                    "compressed": bool
                }
            }
        """
        # 1. 构建系统提示词（固定部分）
        system_prompt = self._build_system_prompt()
        system_tokens = token_budget_manager.count_tokens(system_prompt)

        # 2. 构建用户对话内容（动态部分）
        user_conversation = self._build_user_conversation(
            query=query,
            iteration=iteration,
            latest_observation=latest_observation,
            conversation_history=conversation_history
        )
        user_tokens = token_budget_manager.count_tokens(user_conversation)

        # 3. 计算总token
        total_tokens = system_tokens + user_tokens
        max_allowed = int(self.max_context_tokens * self.compression_threshold)

        logger.info(
            "context_built",
            system_tokens=system_tokens,
            user_tokens=user_tokens,
            total_tokens=total_tokens,
            max_allowed=max_allowed,
            usage_ratio=f"{total_tokens/self.max_context_tokens*100:.1f}%"
        )

        # 4. 判断是否需要压缩
        compressed = False
        if total_tokens > max_allowed:
            logger.warning(
                "context_exceeds_threshold_compression_needed",
                total_tokens=total_tokens,
                max_allowed=max_allowed,
                overflow=total_tokens - max_allowed,
                overflow_ratio=f"{(total_tokens/max_allowed - 1)*100:.1f}%"
            )

            # 压缩用户对话内容
            user_conversation = await self._compress_user_conversation(user_conversation)
            user_tokens_after = token_budget_manager.count_tokens(user_conversation)

            logger.info(
                "user_conversation_compressed",
                before_tokens=user_tokens,
                after_tokens=user_tokens_after,
                compression_ratio=f"{(1 - user_tokens_after/user_tokens)*100:.1f}%"
            )

            compressed = True
            user_tokens = user_tokens_after

        return {
            "system_prompt": system_prompt,
            "user_conversation": user_conversation,
            "tokens": {
                "system": system_tokens,
                "user": user_tokens,
                "total": system_tokens + user_tokens,
                "compressed": compressed
            }
        }

    def _build_system_prompt(self) -> str:
        """
        构建系统提示词（固定部分）

        包括：
        1. REACT_SYSTEM_PROMPT
        2. 工具摘要
        """
        from ..prompts.react_prompts import REACT_SYSTEM_PROMPT

        # 获取工具摘要
        try:
            from ...agent.tool_adapter import get_tool_summaries
            tool_summaries = get_tool_summaries()
        except Exception as e:
            logger.warning("failed_to_get_tool_summaries", error=str(e))
            # 回退：使用简单工具列表
            tool_summaries = self._get_simple_tool_list()

        # 拼接系统提示词
        return f"{REACT_SYSTEM_PROMPT}\n\n{tool_summaries}"

    def _get_simple_tool_list(self) -> str:
        """获取简单工具列表（回退方案）"""
        if not self.tool_registry:
            return "**可用工具**：工具加载失败"

        tool_names = list(self.tool_registry.keys())
        return f"**可用工具**：{', '.join(tool_names[:20])}..."

    def _build_user_conversation(
        self,
        query: str,
        iteration: int,
        latest_observation: str,
        conversation_history: Optional[List[Dict[str, Any]]]
    ) -> str:
        """
        构建用户对话内容（动态部分）

        包括：
        1. 对话历史（从WorkingMemory获取）
        2. 当前查询
        3. 最新观察结果

        Args:
            query: 用户查询
            iteration: 当前迭代次数
            latest_observation: 最新观察结果
            conversation_history: 对话历史（LLM格式，优先使用）

        Returns:
            用户对话内容字符串
        """
        sections = []

        # 1. 对话历史（优先使用LLM格式）
        if conversation_history:
            # 使用LLM消息格式的历史
            sections.append(self._format_llm_conversation_history(conversation_history))
        else:
            # 回退：从WorkingMemory获取
            working_history = self.memory.working.get_context_for_llm(include_raw_data=True)
            if working_history:
                sections.append(working_history)

        # 2. 当前进行的任务
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sections.append(f"## 当前进行的任务（请根据对话记录确认是否已经完成）\n{query}\n\n**当前时间**: {current_time}\n**迭代次数**: {iteration}")

        # 3. 最新观察结果（仅当conversation_history为空时添加，避免重复）
        # conversation_history已包含所有历史对话，包括完整的observation数据
        # latest_observation通常已经包含在conversation_history的最后一条助手消息中
        if latest_observation and not conversation_history:
            sections.append(f"## 最新观察结果\n{latest_observation}")

        return "\n\n".join(sections)

    def _format_llm_conversation_history(self, history: List[Dict[str, Any]]) -> str:
        """
        格式化LLM对话历史为文本

        Args:
            history: LLM消息格式的历史 [{"role": "user", "content": "..."}, ...]

        Returns:
            格式化的文本
        """
        lines = ["## 对话历史"]

        for i, msg in enumerate(history, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # 转换角色名称
            role_name = {
                "user": "用户",
                "assistant": "助手",
                "system": "系统"
            }.get(role, role)

            lines.append(f"\n### {role_name} {i}")
            lines.append(content)

        return "\n".join(lines)

    async def _compress_user_conversation(self, conversation: str) -> str:
        """
        压缩用户对话内容

        使用ContextCompressor进行LLM智能压缩

        Args:
            conversation: 用户对话内容

        Returns:
            压缩后的对话内容
        """
        try:
            # 转换为消息格式
            messages = self._convert_conversation_to_messages(conversation)

            # 使用LLM压缩
            compressed_messages = await self.compressor.compress(messages)

            # 转回文本格式
            compressed = self._convert_messages_to_text(compressed_messages)

            return compressed

        except Exception as e:
            logger.error("llm_compression_failed", error=str(e))
            # 降级：使用简单截断
            return self._simple_truncate(conversation)

    def _convert_conversation_to_messages(self, conversation: str) -> List[Dict[str, Any]]:
        """
        将对话文本转换为消息格式

        简单实现：整个对话作为一条user消息
        """
        return [{"role": "user", "content": conversation}]

    def _convert_messages_to_text(self, messages: List[Dict[str, Any]]) -> str:
        """
        将消息格式转换回文本

        Args:
            messages: LLM消息格式

        Returns:
            文本格式
        """
        return "\n\n".join(msg.get("content", "") for msg in messages)

    def _simple_truncate(self, text: str) -> str:
        """
        简单截断（降级策略）

        按段落截断，保留最近的内容

        Args:
            text: 输入文本

        Returns:
            截断后的文本
        """
        target_tokens = int(self.max_context_tokens * 0.6)
        return token_budget_manager._truncate_to_tokens(text, target_tokens)
