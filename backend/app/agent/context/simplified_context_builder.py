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

        # ✅ 新增：当前模式（默认expert）
        self.current_mode = "expert"

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
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        mode: str = "expert",  # ✅ 新增：Agent模式
        is_interruption: bool = False  # ✅ 新增：中断标志
    ) -> Dict[str, Any]:
        """
        为 Thought + Action 构建完整上下文

        Args:
            query: 用户查询
            iteration: 当前迭代次数
            latest_observation: 最新观察结果（可选）
            conversation_history: 对话历史（可选，LLM消息格式）
            mode: Agent模式（"assistant" | "expert"）

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
        # 设置当前模式
        self.current_mode = mode

        # ✅ 调试日志：检查查询是否包含记忆
        has_memory_in_query = "长期记忆" in query and "记忆文件路径" in query
        if has_memory_in_query:
            logger.debug(
                "query_contains_memory",
                query_length=len(query),
                memory_marker_found="长期记忆" in query,
                file_path_marker_found="记忆文件路径" in query,
                query_preview=query[:300]
            )

        # 1. 构建系统提示词（固定部分）
        system_prompt = self._build_system_prompt()
        system_tokens = token_budget_manager.count_tokens(system_prompt)

        # 2. 构建用户对话内容（动态部分）
        user_conversation = self._build_user_conversation(
            query=query,
            iteration=iteration,
            latest_observation=latest_observation,
            conversation_history=conversation_history,
            is_interruption=is_interruption  # ✅ 传递中断标志
        )
        user_tokens = token_budget_manager.count_tokens(user_conversation)

        # 3. 计算总token
        total_tokens = system_tokens + user_tokens
        max_allowed = int(self.max_context_tokens * self.compression_threshold)

        logger.info(
            "context_built",
            mode=mode,  # ✅ 记录模式
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

            # ✅ 修复：直接压缩 conversation_history 并持久化到 session
            compressed_history = await self._compress_and_persist_history(conversation_history)

            # 用压缩后的历史重新构建 user_conversation
            user_conversation = self._build_user_conversation(
                query=query,
                iteration=iteration,
                latest_observation=latest_observation,
                conversation_history=compressed_history
            )
            user_tokens_after = token_budget_manager.count_tokens(user_conversation)

            logger.info(
                "user_conversation_compressed",
                before_tokens=user_tokens,
                after_tokens=user_tokens_after,
                compression_ratio=f"{(1 - user_tokens_after/user_tokens)*100:.1f}%",
                history_length_before=len(conversation_history) if conversation_history else 0,
                history_length_after=len(compressed_history) if compressed_history else 0
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
        1. 根据模式选择的系统提示词（assistant or expert）
        2. 回退到简单工具列表（旧版本兼容）
        """
        # ✅ 使用新的提示词构建器
        from ..prompts.prompt_builder import build_react_system_prompt
        return build_react_system_prompt(mode=self.current_mode)

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
        conversation_history: Optional[List[Dict[str, Any]]],
        is_interruption: bool = False  # ✅ 新增：中断标志
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
            is_interruption: 是否为用户中断后的对话

        Returns:
            用户对话内容字符串
        """
        # ✅ 调试日志：检查查询是否包含记忆
        has_memory_in_query = "长期记忆" in query and "用户问题：" in query
        if has_memory_in_query:
            # 提取记忆部分用于日志预览
            memory_preview = ""
            if "用户问题：" in query:
                memory_part = query.split("用户问题：")[0].strip()
                memory_preview = memory_part[:200]

            logger.info(
                "user_conversation_contains_memory",
                query_length=len(query),
                contains_memory_marker="长期记忆" in query,
                contains_user_question_marker="用户问题：" in query,
                memory_part_preview=memory_preview,
                will_add_to_status_section=True  # ✅ 确认会添加到状态部分
            )

        sections = []

        # ✅ 检测到中断时，在对话历史前添加明确提示
        if is_interruption:
            sections.append("""⚠️ **用户已中断对话并重新输入**

用户之前中断了对话，这通常意味着之前的分析方向不符合预期。请：
1. **优先理解用户新输入的完整意图**，而不是继续之前的方向
2. 结合对话历史中的数据和结果，但**不要被之前的分析思路限制**
3. 重新规划执行步骤，确保符合用户当前的真实需求

---""")

        # 1. 对话历史（优先使用LLM格式）
        if conversation_history:
            # 使用LLM消息格式的历史
            sections.append(self._format_llm_conversation_history(conversation_history))
        else:
            logger.warning("context_builder_no_conversation_history", iteration=iteration)

        # 2. 当前进行的任务
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ✅ 检测记忆增强内容
        has_memory_enhancement = "长期记忆" in query and "用户问题：" in query
        memory_section = ""
        user_question_section = ""

        if has_memory_enhancement:
            # 提取记忆部分（在"用户问题："之前）
            if "用户问题：" in query:
                parts = query.split("用户问题：", 1)
                memory_part = parts[0].strip()
                # 提取用户问题和附件信息（在"用户问题："之后的所有内容）
                user_question_and_attachments = parts[1].strip() if len(parts) > 1 else ""
                memory_section = f"\n\n{memory_part}\n\n"
                # ✅ 用户问题部分：包含用户问题和可能的附件信息
                user_question_section = f"\n\n{user_question_and_attachments}\n\n"

                # ✅ 调试日志：确认用户问题和附件信息
                logger.debug(
                    "user_question_section_extracted",
                    section_length=len(user_question_section),
                    has_attachments="**用户上传的附件**" in user_question_section,
                    preview=user_question_section[:200]
                )

        if conversation_history:
            # 已有对话历史：不要重复完整查询，避免LLM重复执行工具
            # 对话历史中已包含工具结果，只需提醒LLM检查是否完成
            status_section = (
                f"## 当前状态\n"
                f"**迭代次数**: {iteration} | **当前时间**: {current_time}\n\n"
                f"{memory_section}"  # ✅ 添加记忆增强内容
                f"{user_question_section}"  # ✅ 添加用户问题和附件信息
                f"请根据上方对话历史中的工具执行结果，判断用户任务是否已完成。\n"
                f"- 如果已完成：直接使用 FINAL_ANSWER 回复用户\n"
                f"- 如果未完成：继续调用必要的工具，但**不要重复执行已经成功过的工具调用**"
            )
            sections.append(status_section)

            # ✅ 调试日志：确认记忆和用户问题内容已添加
            if has_memory_enhancement:
                logger.debug(
                    "memory_context_added_to_status",
                    memory_length=len(memory_section),
                    user_question_length=len(user_question_section),
                    has_attachments="**用户上传的附件**" in user_question_section,
                    iteration=iteration
                )
        else:
            # 首次迭代：显示完整查询
            sections.append(f"## 当前进行的任务\n{query}\n\n**当前时间**: {current_time}\n**迭代次数**: {iteration}")

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

    async def _compress_and_persist_history(self, conversation_history: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """
        压缩对话历史并持久化到 session

        ✅ 修复：压缩后直接写回 session.conversation_history，避免下次迭代重新处理完整历史

        Args:
            conversation_history: 原始对话历史（LLM消息格式）

        Returns:
            压缩后的对话历史
        """
        if not conversation_history:
            return None

        try:
            # 使用 LLM 压缩对话历史
            compressed_messages = await self.compressor.compress(conversation_history)

            # ✅ 关键修复：将压缩后的消息写回 session
            self.memory.session.update_messages(compressed_messages)

            logger.info(
                "conversation_history_persisted",
                original_count=len(conversation_history),
                compressed_count=len(compressed_messages),
                session_id=self.memory.session_id
            )

            return compressed_messages

        except Exception as e:
            logger.error("llm_compression_failed", error=str(e))
            # 降级策略：简单截断，保留最近的消息
            fallback_count = max(10, len(conversation_history) // 2)
            truncated = conversation_history[-fallback_count:]

            # 即使降级也要写回 session
            self.memory.session.update_messages(truncated)

            logger.warning(
                "conversation_history_truncated_fallback",
                original_count=len(conversation_history),
                truncated_count=len(truncated)
            )

            return truncated

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
