"""
上下文压缩器 - 使用 LLM 智能压缩对话历史

保留消息类型结构，让前端可以像处理实时对话一样处理历史对话。
"""

from typing import List, Dict, Any
import json
import structlog

logger = structlog.get_logger()


class ContextCompressor:
    """上下文压缩器（使用 LLM）"""

    COMPACT_MEMORY_PREFIX = (
        "Runtime memory summary from earlier turns.\n"
        "This is compressed context, not ground truth.\n"
        "The session history and persisted files remain authoritative; re-read data or files when exact details matter.\n\n"
    )

    COMPACT_MEMORY_PROMPT = """You compress older tool-using agent history into short working memory for continued execution.
Return plain text only. Do not call tools. Do not invent facts.

Original task:
{original_task}

Write a concise working memory with these sections:
- Goal
- Constraints
- Files and artifacts
- Evidence and results
- Open issues
- Next useful actions

Rules:
- Prefer concrete data_id/report_data_id values, file paths, numeric results, URLs, and grounded facts.
- Mention uncertainty when details may need to be re-read from files or tool results.
- Merge any prior compressed memory with the newer history below into one refreshed memory.
- Deduplicate repeated sections and do not repeat earlier summaries verbatim.
- The session history and persisted files remain authoritative.

{prior_memory_block}
Older history to compress:
{history_text}
"""

    # ⭐ 新版压缩提示词：保留消息类型结构
    COMPRESSION_PROMPT = """你是一个对话上下文压缩专家。你的任务是压缩以下对话历史，保留关键信息，移除冗余内容。

**⚠️ 核心原则（CRITICAL）**：
- **保留消息类型结构**：保持每条消息的 "type" 和 "role" 字段不变
- **只压缩消息内容**：不要合并或删除消息，只精简每条消息的 content 字段
- **支持前端折叠渲染**：保留 thought/action/observation/final 消息类型，让前端可以折叠显示

**必须保留的消息类型**：
1. **user** - 用户问题（完整保留）
2. **thought** - 思考过程（提炼关键决策点）
3. **action** - 工具调用（保留工具名和关键参数）
4. **observation** - 工具结果（保留 data_id 和摘要）
5. **final/assistant** - 最终答案（完整保留）

**压缩策略（按消息类型）**：

**user 消息**：
- 完整保留，不压缩

**thought 消息**：
- 提炼关键决策点，去除冗余推理
- 原始："我需要分析广州的臭氧污染情况。首先，我应该查询气象数据，了解温度、湿度、风速等条件。然后，我需要查看臭氧浓度数据，分析其变化趋势。最后，我将综合这些信息，给出分析结论。"
- 压缩后："决定先查询气象数据，再分析臭氧浓度趋势，最后给出综合结论"

**action 消息**：
- 保留工具名和关键参数，省略详细参数
- 原始：完整的工具调用 JSON，包含所有参数
- 压缩后："调用 get_weather_data，参数：城市=广州，日期=2024-03-01"

**observation 消息**：
- 保留 data_id 和摘要，省略详细数据
- 原始：包含完整的工具返回数据（可能有数千条记录）
- 压缩后："成功获取 30 条气象记录，data_id: weather_001，平均温度 25°C"

**final/assistant 消息**：
- 完整保留，不压缩（这是用户看到的最终答案）

**重要提示**：
- 保留所有 data_id 引用（后续分析可能需要）
- 保持对话的逻辑连贯性
- 不要合并或删除任何消息

**原始对话**：
{conversation_json}

**输出要求（CRITICAL - 必须严格遵守）**：

⚠️ **你的输出将直接传递给 json.loads() 解析，任何非 JSON 字符都会导致系统崩溃！

**强制规则**：
1. 第一个字符必须是 `[`（左方括号）
2. 最后一个字符必须是 `]`（右方括号）
3. 禁止使用 ```json 或 ``` 包裹 JSON
4. 禁止在 JSON 前后添加任何解释文字、空行或其他字符
5. 每条消息必须保留原始的 "type" 和 "role" 字段
6. 返回标准 JSON 数组格式

**正确示例（保留消息类型结构）**：
[
  {{"type": "user", "role": "user", "content": "分析广州O3污染"}},
  {{"type": "thought", "role": "assistant", "content": "决定先查询气象数据"}},
  {{"type": "tool_use", "role": "assistant", "content": "调用 get_weather_data，参数：城市=广州"}},
  {{"type": "tool_result", "role": "user", "content": "成功获取 30 条记录，data_id: weather_001"}},
  {{"type": "final", "role": "assistant", "content": "根据分析，发现..."}}
]

⚠️ 再次强调：
1. 保持每条消息的 type 字段不变
2. 只压缩 content 字段的内容
3. 不要合并或删除消息
4. 输出必须以 [ 开头，以 ] 结尾
"""

    # 工具输出截断配置
    MAX_OBSERVATION_CHARS = 3000  # observation 最大字符数
    MAX_TOOL_RESULT_CHARS = 5000  # tool_result 最大字符数

    # 保护段配置
    PROTECTED_TURNS = 2  # 保留最近 N 轮对话不压缩

    # 渐进式压缩配置
    LIGHT_COMPRESS_THRESHOLD = 10  # 轻量压缩阈值（消息数）
    FULL_COMPRESS_THRESHOLD = 30   # 全量压缩阈值（消息数）

    # ✅ 阶段七：Snip Compact 配置（轻量裁剪，零 token 消耗）
    SNIP_HEAD_COUNT = 2  # 头部保留消息数（系统提示 + 初始上下文）
    SNIP_TAIL_TURNS = 4  # 尾部保留轮数（最近 N 轮对话）
    COMPACT_RECENT_GROUPS = 4
    MAX_RENDERED_HISTORY_CHARS = 64_000
    COMPACT_SUMMARY_MAX_TOKENS = 2048

    def __init__(self, llm_client):
        """
        初始化压缩器

        Args:
            llm_client: LLM 客户端（用于压缩调用）
        """
        self.llm_client = llm_client

    def _message_kind(self, msg: Dict[str, Any]) -> str:
        """Return a stable message kind for both app turns and raw LLM messages."""
        msg_type = msg.get("type")
        if msg_type:
            return msg_type

        content = msg.get("content")
        if isinstance(content, list):
            block_types = {
                block.get("type")
                for block in content
                if isinstance(block, dict)
            }
            if "tool_result" in block_types:
                return "tool_result"
            if "tool_use" in block_types:
                return "tool_use"

        role = msg.get("role")
        if role == "user":
            return "user"
        if role == "assistant":
            return "assistant"
        return ""

    def _content_to_text(self, content: Any, max_chars: int = 4000) -> str:
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for block in content:
                if not isinstance(block, dict):
                    parts.append(str(block))
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    parts.append(str(block.get("text", "")))
                elif block_type == "tool_use":
                    parts.append(
                        f"[tool_use name={block.get('name', '')} id={block.get('id', '')} input={block.get('input', {})}]"
                    )
                elif block_type == "tool_result":
                    parts.append(
                        f"[tool_result id={block.get('tool_use_id', '')} content={block.get('content', '')}]"
                    )
                elif block_type == "image_url":
                    parts.append("[image_url]")
                elif block_type == "thinking":
                    parts.append("[thinking]")
                else:
                    parts.append(str(block))
            text = " ".join(part for part in parts if part)
        else:
            try:
                text = json.dumps(content, ensure_ascii=False, default=str)
            except Exception:
                text = str(content)

        text = " ".join(text.split())
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 16].rstrip() + "...[truncated]"

    def _extract_user_anchor(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Preserve the first substantive user request as an anchor for compaction."""
        for msg in messages:
            if self._message_kind(msg) != "user":
                continue

            text = self._content_to_text(msg.get("content", ""), max_chars=4000).strip()
            if not text or text.startswith("[系统提示]"):
                continue

            return [{
                "type": "user",
                "role": "user",
                "content": f"[压缩保留的原始任务锚点]\n{text[:4000]}"
            }]

        return []

    def _contains_anchor_equivalent(self, messages: List[Dict[str, Any]], anchor: Dict[str, Any]) -> bool:
        anchor_content = str(anchor.get("content", ""))
        anchor_text = anchor_content.replace("[压缩保留的原始任务锚点]\n", "").strip()
        if not anchor_text:
            return True

        needle = anchor_text[:200]
        return any(needle in str(msg.get("content", "")) for msg in messages)

    def _is_compact_memory_message(self, msg: Dict[str, Any]) -> bool:
        content = msg.get("content", "")
        return (
            msg.get("type") == "compact_memory"
            or (
                isinstance(content, str)
                and content.startswith(self.COMPACT_MEMORY_PREFIX)
            )
        )

    def _split_existing_compact_memory(
        self,
        messages: List[Dict[str, Any]],
    ) -> tuple[str, List[Dict[str, Any]]]:
        summaries = []
        remaining = []
        for msg in messages:
            if self._is_compact_memory_message(msg):
                content = str(msg.get("content", ""))
                summaries.append(content.replace(self.COMPACT_MEMORY_PREFIX, "", 1).strip())
                continue
            remaining.append(msg)
        return "\n\n".join(summary for summary in summaries if summary).strip(), remaining

    def _turn_groups(self, messages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        groups: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "")
            if role == "assistant" and current:
                groups.append(current)
                current = [msg]
                continue
            current.append(msg)
        if current:
            groups.append(current)
        return groups

    def _split_recent_groups(
        self,
        messages: List[Dict[str, Any]],
    ) -> tuple[List[List[Dict[str, Any]]], List[List[Dict[str, Any]]]]:
        groups = self._turn_groups(messages)
        if not groups:
            return [], []

        recent_groups = groups[-self.COMPACT_RECENT_GROUPS:]
        if len(recent_groups) >= len(groups):
            recent_groups = recent_groups[1:]
        compacted_count = max(0, len(groups) - len(recent_groups))
        return groups[:compacted_count], recent_groups

    def _render_history_text(self, groups: List[List[Dict[str, Any]]]) -> str:
        parts = []
        used = 0
        max_chars_per_message = 3000
        for index, group in enumerate(groups, start=1):
            lines = [f"[Turn group {index}]"]
            for msg in group:
                role = msg.get("role", "unknown")
                kind = self._message_kind(msg)
                content = self._content_to_text(msg.get("content", ""), max_chars=max_chars_per_message)
                lines.append(f"{role}/{kind}: {content}")
            rendered = "\n".join(lines)
            if parts and used + len(rendered) > self.MAX_RENDERED_HISTORY_CHARS:
                remaining = self.MAX_RENDERED_HISTORY_CHARS - used
                if remaining > 80:
                    parts.append(rendered[: remaining - 40].rstrip() + "\n...[history truncated]")
                break
            parts.append(rendered)
            used += len(rendered)
        return "\n\n".join(parts).strip()

    def _create_compact_memory_message(
        self,
        summary_text: str,
        original_count: int,
        compacted_group_count: int,
        kept_group_count: int,
        existing_memory_text: str = "",
    ) -> Dict[str, Any]:
        from datetime import datetime

        return {
            "type": "compact_memory",
            "role": "user",
            "content": self.COMPACT_MEMORY_PREFIX + summary_text.strip(),
            "metadata": {
                "compact_memory": True,
                "compression_type": "harness_summary",
                "original_count": original_count,
                "compacted_group_count": compacted_group_count,
                "kept_group_count": kept_group_count,
                "had_existing_memory": bool(existing_memory_text),
                "compressed_at": datetime.now().isoformat(),
            },
        }

    def _flatten_groups(self, groups: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        flattened = []
        for group in groups:
            flattened.extend(dict(msg) for msg in group)
        return flattened

    def _fallback_compact(
        self,
        messages: List[Dict[str, Any]],
        anchor_messages: List[Dict[str, Any]],
        original_count: int,
        error: Exception,
    ) -> List[Dict[str, Any]]:
        compacted_groups, recent_groups = self._split_recent_groups(messages)
        recent_messages = self._flatten_groups(recent_groups)
        boundary_msg = self._create_compaction_boundary(
            original_count=original_count,
            compressed_count=len(anchor_messages) + 1 + len(recent_messages),
            compression_type="fallback",
        )
        boundary_msg["content"] = (
            f"[系统提示] 上下文压缩失败，已保留原始任务锚点和最近消息。错误: {str(error)[:200]}"
        )
        return anchor_messages + [boundary_msg] + recent_messages

    async def _harness_compact(
        self,
        messages_to_compress: List[Dict[str, Any]],
        protected_messages: List[Dict[str, Any]],
        anchor_messages: List[Dict[str, Any]],
        original_count: int,
        model: str = None,
    ) -> List[Dict[str, Any]]:
        existing_memory_text, eligible_messages = self._split_existing_compact_memory(messages_to_compress)
        compacted_groups, recent_groups = self._split_recent_groups(eligible_messages)

        if not compacted_groups:
            logger.info("[ContextCompressor] 没有可摘要的旧轮次，使用确定性裁剪")
            return self._fallback_compact(
                messages_to_compress + protected_messages,
                anchor_messages,
                original_count,
                RuntimeError("no older turn groups to summarize"),
            )

        history_text = self._render_history_text(compacted_groups)
        original_task = self._content_to_text(anchor_messages[0].get("content", ""), max_chars=4000) if anchor_messages else ""
        prior_memory_block = ""
        if existing_memory_text:
            prior_memory_block = (
                "Previously compressed memory to preserve and refine:\n"
                f"{self._content_to_text(existing_memory_text, max_chars=12000)}\n\n"
            )

        prompt = self.COMPACT_MEMORY_PROMPT.format(
            original_task=original_task,
            prior_memory_block=prior_memory_block,
            history_text=history_text,
        )
        chat_params = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.COMPACT_SUMMARY_MAX_TOKENS,
            "timeout": 300.0,
        }
        if model:
            chat_params["model"] = model

        response = await self.llm_client.chat(**chat_params)
        summary_text = str(response or "").strip()
        if not summary_text:
            raise ValueError("context compaction summary call returned empty text")

        compact_memory = self._create_compact_memory_message(
            summary_text=summary_text,
            original_count=original_count,
            compacted_group_count=len(compacted_groups),
            kept_group_count=len(recent_groups) + (1 if protected_messages else 0),
            existing_memory_text=existing_memory_text,
        )

        recent_messages = self._flatten_groups(recent_groups)
        final_messages = anchor_messages + [compact_memory] + recent_messages + protected_messages

        logger.info(
            "[ContextCompressor] Harness Compact 完成",
            original_count=original_count,
            compressed_count=len(final_messages),
            compacted_group_count=len(compacted_groups),
            recent_group_count=len(recent_groups),
            protected_count=len(protected_messages),
            summary_length=len(summary_text),
        )
        return final_messages

    async def compress(
        self,
        messages: List[Dict[str, Any]],
        model: str = None,
        force: bool = False,
        force_reason: str = ""
    ) -> List[Dict[str, Any]]:
        """
        使用渐进式策略压缩对话历史

        压缩流程（阶段四：渐进式压缩）：
        1. 工具输出预截断（阶段一）
        2. 保护段分离（阶段二）
        3. 根据消息数量选择压缩策略：
           - < LIGHT_COMPRESS_THRESHOLD: 不压缩
           - < FULL_COMPRESS_THRESHOLD: 轻量压缩（仅工具输出截断）
           - >= FULL_COMPRESS_THRESHOLD: 全量 LLM 压缩
        4. 添加压缩边界标记（阶段三）

        Args:
            messages: 需要压缩的消息列表
            model: 使用的模型（如果为 None，使用系统配置的模型）
            force: 外层已判定上下文超阈值时强制压缩，避免被消息数阈值短路
            force_reason: 强制压缩原因，用于日志排查

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return []

        # 记录压缩前的状态
        original_count = len(messages)
        original_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
        logger.info(
            f"[ContextCompressor] 开始压缩，原始消息数: {original_count}，原始字符数: {original_chars}，"
            f"force={force}，force_reason={force_reason or 'none'}"
        )

        # 阶段一：工具输出预截断（在 LLM 压缩前，先截断过长的工具输出）
        messages = self._truncate_tool_outputs(messages)

        anchor_messages = self._extract_user_anchor(messages)

        # 阶段二：保护段机制（保留最近 N 轮对话不压缩）
        protected_messages, messages_to_compress = self._split_protected_and_compressible(messages)

        if protected_messages:
            logger.info(f"[ContextCompressor] 保护段: 保留最近 {len(protected_messages)} 条消息不压缩")

        # 阶段四：渐进式压缩策略
        compressible_count = len(messages_to_compress)

        if compressible_count == 0:
            logger.info("[ContextCompressor] 所有消息均在保护段内，跳过 LLM 压缩")
            return protected_messages

        # 策略1：消息太少，不压缩。外层已判定超限时不能被该条件短路。
        if compressible_count <= self.LIGHT_COMPRESS_THRESHOLD and not force:
            logger.info(f"[ContextCompressor] 消息数 {compressible_count} <= {self.LIGHT_COMPRESS_THRESHOLD}，跳过压缩")
            return messages_to_compress + protected_messages

        # 策略2：中等数量，使用 Snip Compact 轻量裁剪（阶段七）
        if compressible_count <= self.FULL_COMPRESS_THRESHOLD and not force:
            logger.info(f"[ContextCompressor] 消息数 {compressible_count} <= {self.FULL_COMPRESS_THRESHOLD}，使用 Snip Compact 轻量裁剪")
            # 使用 Snip Compact 裁剪可压缩部分
            snipped_messages = self._snip_compact(messages_to_compress)
            return snipped_messages + protected_messages

        # 策略3：大量消息，使用 LLM 全量压缩
        if force:
            logger.info(
                f"[ContextCompressor] 强制压缩：消息数 {compressible_count}，原因={force_reason or 'context_over_threshold'}，"
                "进入全量 LLM 压缩"
            )
        else:
            logger.info(f"[ContextCompressor] 消息数 {compressible_count} > {self.FULL_COMPRESS_THRESHOLD}，全量 LLM 压缩")

        # 预截断：LLM 无法处理超大输入，限制发送的消息量
        MAX_COMPRESS_CHARS = 300_000
        messages_to_compress = self._pre_truncate_for_compression(messages_to_compress, MAX_COMPRESS_CHARS)
        if len(messages_to_compress) < compressible_count:
            logger.warning(
                f"[ContextCompressor] 预截断: {compressible_count} → {len(messages_to_compress)} 条消息 "
                f"(原始内容过大，仅压缩最近部分)"
            )

        # 如果可压缩的消息太少，直接返回
        if len(messages_to_compress) <= 2 and not force:
            logger.info("[ContextCompressor] 可压缩消息太少，跳过 LLM 压缩")
            return messages_to_compress + protected_messages

        try:
            return await self._harness_compact(
                messages_to_compress=messages_to_compress,
                protected_messages=protected_messages,
                anchor_messages=anchor_messages,
                original_count=original_count,
                model=model,
            )

        except Exception as e:
            import traceback
            logger.error(
                f"[ContextCompressor] 压缩失败: {e}",
                exc_info=True
            )
            logger.error(
                f"[ContextCompressor] 压缩失败详情: error_type={type(e).__name__}, "
                f"llm_client_type={type(self.llm_client).__name__ if self.llm_client else None}"
            )
            logger.debug(f"[ContextCompressor] 压缩失败堆栈:\n{traceback.format_exc()}")
            logger.warning("[ContextCompressor] 使用 Harness 降级策略，保留任务锚点和最近消息")
            return self._fallback_compact(messages, anchor_messages, original_count, e)

    async def compress_messages(
        self,
        messages: List[Dict[str, Any]],
        model: str = None,
    ) -> List[Dict[str, Any]]:
        """Compatibility wrapper used by reactive context-overflow recovery."""
        return await self.compress(
            messages,
            model=model,
            force=True,
            force_reason="provider_context_overflow",
        )

    def _create_compaction_boundary(
        self,
        original_count: int,
        compressed_count: int,
        compression_type: str
    ) -> Dict[str, Any]:
        """
        阶段三：创建压缩边界标记消息

        Args:
            original_count: 原始消息数
            compressed_count: 压缩后消息数
            compression_type: 压缩类型（light/full）

        Returns:
            边界标记消息
        """
        from datetime import datetime

        return {
            "type": "system",
            "role": "user",
            "subtype": "compact_boundary",
            "content": f"[系统提示] 上下文已压缩：原始 {original_count} 条消息 → 压缩后 {compressed_count} 条消息。",
            "metadata": {
                "compact_boundary": True,
                "compression_type": compression_type,
                "original_count": original_count,
                "compressed_count": compressed_count,
                "compression_ratio": round((1 - compressed_count / original_count) * 100, 1) if original_count > 0 else 0,
                "compressed_at": datetime.now().isoformat()
            }
        }

    def _snip_compact(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        阶段七：Snip Compact - 轻量级裁剪（零 token 消耗）

        参考 Claude Code 的 snipCompact 策略：
        - 保留头部 N 条消息（系统提示 + 初始上下文）
        - 保留尾部最近 N 轮对话（user + assistant/final + 关联的 thought/action/observation）
        - 中间部分直接删除，不走 LLM 压缩
        - 速度快，零 token 消耗

        适用场景：
        - 消息数量中等（10-30条），不需要 LLM 全量压缩
        - 需要快速裁剪，避免 LLM 调用延迟和成本

        Args:
            messages: 完整消息列表

        Returns:
            裁剪后的消息列表（头部 + 边界标记 + 尾部）
        """
        if len(messages) <= self.SNIP_HEAD_COUNT + 4:
            # 消息太少，不需要裁剪
            return messages

        # 1. 提取头部保留消息
        head_messages = messages[:self.SNIP_HEAD_COUNT]

        # 2. 从尾部提取最近 N 轮对话
        tail_messages = []
        turns_found = 0

        for msg in reversed(messages[self.SNIP_HEAD_COUNT:]):
            msg_type = self._message_kind(msg)

            # 保留 user、final、assistant 类型的消息
            if msg_type in ('user', 'final', 'assistant'):
                tail_messages.insert(0, msg)
                if msg_type == 'user':
                    turns_found += 1
            elif msg_type in ('thought', 'action', 'tool_use', 'observation', 'tool_result'):
                # 如果已经在保护范围内，也保留这些关联消息
                if turns_found > 0:
                    tail_messages.insert(0, msg)
                else:
                    # 尾部第一个非 user/assistant 消息，且还没有轮次计数，跳过
                    continue
            else:
                # 其他类型消息，如果已有轮次计数则保留
                if turns_found > 0:
                    tail_messages.insert(0, msg)
                else:
                    continue

            if turns_found >= self.SNIP_TAIL_TURNS:
                break

        # 3. 计算被裁剪的消息数
        snipped_count = len(messages) - len(head_messages) - len(tail_messages)

        if snipped_count <= 0:
            # 没有需要裁剪的消息
            return messages

        # 4. 创建边界标记
        boundary_msg = self._create_compaction_boundary(
            original_count=len(messages),
            compressed_count=len(head_messages) + len(tail_messages),
            compression_type="snip"
        )

        # 5. 组合结果：头部 + 边界标记 + 尾部
        result = head_messages + [boundary_msg] + tail_messages

        logger.info(
            f"[ContextCompressor] Snip Compact 裁剪完成: "
            f"{len(messages)} → {len(result)} 条消息 "
            f"(头部保留: {len(head_messages)}, 尾部保留: {len(tail_messages)}, "
            f"裁剪: {snipped_count} 条)"
        )

        return result

    def _split_protected_and_compressible(
        self,
        messages: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        阶段二：保护段机制 - 分离保护段和可压缩段

        策略：
        - 保留最近 N 轮对话（user + assistant/final）不压缩
        - 这些消息的前缀不变，prompt cache 命中率得以保持
        - 只有更早的消息被压缩

        Args:
            messages: 完整消息列表

        Returns:
            (protected_messages, compressible_messages)
        """
        if len(messages) <= 4:
            # 消息太少，全部保护
            return messages, []

        # 从尾部往前找 N 轮对话
        # 一轮 = user 消息 + assistant/final 消息
        protected = []
        turns_found = 0

        for msg in reversed(messages):
            msg_type = self._message_kind(msg)

            # 保护 user、final、assistant 类型的消息
            if msg_type in ('user', 'final', 'assistant'):
                protected.insert(0, msg)
                if msg_type == 'user':
                    turns_found += 1
            elif msg_type in ('thought', 'action', 'tool_use', 'observation', 'tool_result'):
                # 如果已经在保护范围内，也保护这些关联消息
                if turns_found > 0:
                    protected.insert(0, msg)
                else:
                    break
            else:
                break

            if turns_found >= self.PROTECTED_TURNS:
                break

        # 如果保护的消息太少（少于2条），不启用保护
        if len(protected) < 2:
            return [], messages

        # 可压缩的消息 = 总消息 - 保护消息
        compressible = messages[:len(messages) - len(protected)]

        return protected, compressible

    def _parse_compression_result(self, response: str) -> List[Dict[str, Any]]:
        """
        解析 LLM 返回的压缩结果

        Args:
            response: LLM 返回的响应文本

        Returns:
            解析后的消息列表
        """
        try:
            # 尝试直接解析 JSON
            compressed = json.loads(response)

            # 验证格式
            if not isinstance(compressed, list):
                raise ValueError("压缩结果不是列表格式")

            for msg in compressed:
                if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                    raise ValueError("消息格式不正确")

            return compressed

        except json.JSONDecodeError as e:
            # 尝试从 markdown 代码块中提取 JSON
            import re

            # 策略1: 匹配代码块内的内容（使用贪婪匹配以支持嵌套结构）
            # 模式: ```json ... ``` 或 ``` ... ```
            code_block_patterns = [
                r'```json\s*(.*?)\s*```',  # 带 json 标签
                r'```\s*(.*?)\s*```'       # 不带标签
            ]

            for pattern in code_block_patterns:
                match = re.search(pattern, response, re.DOTALL)
                if match:
                    try:
                        compressed = json.loads(match.group(1).strip())
                        # 验证格式
                        if isinstance(compressed, list) and all(
                            isinstance(msg, dict) and "role" in msg and "content" in msg
                            for msg in compressed
                        ):
                            return compressed
                    except (json.JSONDecodeError, ValueError):
                        continue

            # 策略2: 查找第一个 [ 到最后一个 ] 之间的内容
            start_idx = response.find('[')
            end_idx = response.rfind(']')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                try:
                    compressed = json.loads(response[start_idx:end_idx+1])
                    # 验证格式
                    if isinstance(compressed, list) and all(
                        isinstance(msg, dict) and "role" in msg and "content" in msg
                        for msg in compressed
                    ):
                        return compressed
                except json.JSONDecodeError:
                    pass

            # 所有策略失败，抛出详细错误
            raise ValueError(
                f"无法解析压缩结果: {str(e)}\n"
                f"响应预览: {response[:500]}...\n"
                f"响应长度: {len(response)} 字符"
            )

    def _pre_truncate_for_compression(
        self,
        messages: List[Dict[str, Any]],
        max_chars: int
    ) -> List[Dict[str, Any]]:
        """
        压缩前预截断：确保发给 LLM 的内容不超过其输入上限。
        策略：保留头部 2 条（初始上下文）+ 尽可能多的尾部最近消息。
        """
        total_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
        if total_chars <= max_chars:
            return messages

        # 头部保留前 2 条
        head = messages[:2]
        tail_candidates = messages[2:]

        # 从尾部往前累积，直到接近上限
        head_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in head)
        budget = max_chars - head_chars
        tail = []
        accumulated = 0
        for msg in reversed(tail_candidates):
            msg_chars = len(json.dumps(msg, ensure_ascii=False))
            if accumulated + msg_chars > budget:
                break
            tail.insert(0, msg)
            accumulated += msg_chars

        return head + tail

    def _truncate_tool_outputs(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        阶段一：在 LLM 压缩前，预截断过长的工具输出

        策略：
        - observation/tool_result 类型：截断到 MAX_OBSERVATION_CHARS，保留 data_id
        - action/tool_use 类型：保留工具名和关键参数
        - user/final 类型：不处理
        """
        import re

        def content_char_len(value: Any) -> int:
            if isinstance(value, str):
                return len(value)
            return len(json.dumps(value, ensure_ascii=False, default=str))

        def extract_data_ref(value: Any) -> str:
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
            match = re.search(r'(?:report_data_id|data_id)["\s:]+([^\s,}"]+)', text)
            return f"，data_id: {match.group(1)}" if match else ""

        def truncate_text(text: str, max_chars: int) -> str:
            if len(text) <= max_chars:
                return text
            truncated = text[:max_chars]
            last_period = max(truncated.rfind('。'), truncated.rfind('\n'), truncated.rfind('.'))
            if last_period > max_chars // 2:
                truncated = truncated[:last_period + 1]
            return f"{truncated}... [已截断，原始长度: {len(text)} 字符]"

        def todo_counts(items: Any) -> Dict[str, int]:
            if not isinstance(items, list):
                return {
                    "total_count": 0,
                    "completed_count": 0,
                    "in_progress_count": 0,
                    "pending_count": 0,
                }
            counts = {
                "total_count": len(items),
                "completed_count": 0,
                "in_progress_count": 0,
                "pending_count": 0,
            }
            for item in items:
                status = item.get("status") if isinstance(item, dict) else None
                if status == "completed":
                    counts["completed_count"] += 1
                elif status == "in_progress":
                    counts["in_progress_count"] += 1
                elif status == "pending":
                    counts["pending_count"] += 1
            return counts

        def compact_todo_items(items: Any, max_items: int = 8) -> List[Dict[str, Any]]:
            if not isinstance(items, list):
                return []
            compacted = []
            for item in items[:max_items]:
                if not isinstance(item, dict):
                    continue
                content = str(item.get("content", ""))
                compacted.append({
                    "content": content[:180] + ("..." if len(content) > 180 else ""),
                    "status": item.get("status"),
                })
            if len(items) > max_items:
                compacted.append({
                    "_truncated": True,
                    "original_count": len(items),
                    "sampled_count": len(compacted),
                })
            return compacted

        def compact_todowrite_payload(payload: Dict[str, Any]) -> Dict[str, Any] | None:
            metadata = payload.get("metadata")
            if not (
                payload.get("tool_name") == "TodoWrite"
                or payload.get("tool") == "TodoWrite"
                or (isinstance(metadata, dict) and metadata.get("generator") == "TodoWrite")
            ):
                return None

            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            active_items = data.get("active_items") or payload.get("active_items") or []
            submitted_items = data.get("new_items") or data.get("items") or payload.get("items")
            counts = {
                "total_count": payload.get("total_count"),
                "completed_count": payload.get("completed_count"),
                "in_progress_count": payload.get("in_progress_count"),
                "pending_count": payload.get("pending_count"),
            }
            if not all(isinstance(value, int) for value in counts.values()):
                counts = todo_counts(submitted_items)

            summary = payload.get("summary", "Legacy task housekeeping result compacted.")
            summary = str(summary).replace("TodoWrite", "legacy task list")
            return {
                "status": payload.get("status", "success"),
                "success": bool(payload.get("success", True)),
                "tool_name": "LegacyTaskState",
                "housekeeping": True,
                "no_op": bool(payload.get("no_op") or data.get("no_op")),
                "all_completed": bool(payload.get("all_completed") or data.get("all_completed")),
                **counts,
                "active_items": compact_todo_items(active_items),
                "summary": summary,
                "metadata": {
                    "generator": "legacy_task_state",
                    "history_compacted": True,
                    "omitted_fields": ["rendered", "items", "old_items", "new_items"],
                },
            }

        def compact_todowrite_content(value: Any) -> tuple[Any, bool]:
            if not isinstance(value, str):
                return value, False
            try:
                payload = json.loads(value)
            except Exception:
                return value, False
            if not isinstance(payload, dict):
                return value, False
            compacted = compact_todowrite_payload(payload)
            if compacted is None:
                return value, False
            return json.dumps(compacted, ensure_ascii=False, default=str), True

        def compact_todowrite_tool_use_blocks(value: Any) -> tuple[Any, bool]:
            if not isinstance(value, list):
                return value, False
            changed = False
            blocks = []
            for block in value:
                if not isinstance(block, dict) or block.get("type") != "tool_use" or block.get("name") != "TodoWrite":
                    blocks.append(block)
                    continue
                block_copy = dict(block)
                block_copy["name"] = "TaskList"
                block_copy["input"] = {}
                blocks.append(block_copy)
                changed = True
            return blocks, changed

        def truncate_tool_result_blocks(value: Any, max_chars: int) -> tuple[Any, bool]:
            if isinstance(value, str):
                compacted_content, compacted = compact_todowrite_content(value)
                if compacted:
                    return compacted_content, True
                if len(value) <= max_chars:
                    return value, False
                return truncate_text(value, max_chars), True

            if isinstance(value, list):
                changed = False
                blocks = []
                for block in value:
                    if not isinstance(block, dict):
                        blocks.append(block)
                        continue

                    block_copy = dict(block)
                    block_content = block_copy.get("content")
                    compacted_content, compacted = compact_todowrite_content(block_content)
                    if compacted:
                        block_copy["content"] = compacted_content
                        changed = True
                        blocks.append(block_copy)
                        continue
                    if content_char_len(block_content) > max_chars:
                        content_text = (
                            block_content
                            if isinstance(block_content, str)
                            else json.dumps(block_content, ensure_ascii=False, default=str)
                        )
                        block_copy["content"] = truncate_text(content_text, max_chars)
                        changed = True
                    blocks.append(block_copy)
                return blocks, changed

            value_text = json.dumps(value, ensure_ascii=False, default=str)
            if len(value_text) <= max_chars:
                return value, False
            return truncate_text(value_text, max_chars), True

        truncated_count = 0
        result = []

        for msg in messages:
            msg_copy = dict(msg)
            msg_type = self._message_kind(msg_copy)
            content = msg_copy.get('content', '')

            # 处理 observation/tool_result 类型
            if msg_type in ('observation', 'tool_result'):
                max_chars = self.MAX_TOOL_RESULT_CHARS if msg_type == 'tool_result' else self.MAX_OBSERVATION_CHARS
                truncated_content, changed = truncate_tool_result_blocks(content, max_chars)
                if changed:
                    if isinstance(truncated_content, str) and content_char_len(content) > max_chars:
                        truncated_content = f"{truncated_content}{extract_data_ref(content)}"
                    msg_copy['content'] = truncated_content
                    truncated_count += 1

            # 处理 action/tool_use 类型（可选：精简参数）
            elif msg_type in ('action', 'tool_use'):
                compacted_content, changed = compact_todowrite_tool_use_blocks(content)
                if changed:
                    msg_copy['content'] = compacted_content
                    truncated_count += 1
                    result.append(msg_copy)
                    continue
                if content_char_len(content) > 1000 and isinstance(content, str):
                    # 保留工具名和前500字符参数
                    msg_copy['content'] = content[:1000] + "... [参数已精简]"
                    truncated_count += 1

            result.append(msg_copy)

        if truncated_count > 0:
            logger.info(f"[ContextCompressor] 工具输出预截断: {truncated_count} 条消息被截断")

        return result

    def estimate_compression_benefit(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        估算压缩的潜在收益（用于决策是否值得压缩）

        Args:
            messages: 消息列表

        Returns:
            包含估算信息的字典
        """
        total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)

        # 简单估算：假设可以压缩 40-60%
        estimated_compressed_chars = total_chars * 0.5

        return {
            "original_messages": len(messages),
            "original_chars": total_chars,
            "estimated_compressed_chars": int(estimated_compressed_chars),
            "estimated_compression_ratio": 50.0
        }
