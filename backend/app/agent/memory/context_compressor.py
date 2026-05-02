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

    def __init__(self, llm_client):
        """
        初始化压缩器

        Args:
            llm_client: LLM 客户端（用于压缩调用）
        """
        self.llm_client = llm_client

    async def compress(
        self,
        messages: List[Dict[str, Any]],
        model: str = None
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

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return []

        # 记录压缩前的状态
        original_count = len(messages)
        original_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
        logger.info(f"[ContextCompressor] 开始压缩，原始消息数: {original_count}，原始字符数: {original_chars}")

        # 阶段一：工具输出预截断（在 LLM 压缩前，先截断过长的工具输出）
        messages = self._truncate_tool_outputs(messages)

        # 阶段二：保护段机制（保留最近 N 轮对话不压缩）
        protected_messages, messages_to_compress = self._split_protected_and_compressible(messages)

        if protected_messages:
            logger.info(f"[ContextCompressor] 保护段: 保留最近 {len(protected_messages)} 条消息不压缩")

        # 阶段四：渐进式压缩策略
        compressible_count = len(messages_to_compress)

        # 策略1：消息太少，不压缩
        if compressible_count <= self.LIGHT_COMPRESS_THRESHOLD:
            logger.info(f"[ContextCompressor] 消息数 {compressible_count} <= {self.LIGHT_COMPRESS_THRESHOLD}，跳过压缩")
            return messages_to_compress + protected_messages

        # 策略2：中等数量，使用 Snip Compact 轻量裁剪（阶段七）
        if compressible_count <= self.FULL_COMPRESS_THRESHOLD:
            logger.info(f"[ContextCompressor] 消息数 {compressible_count} <= {self.FULL_COMPRESS_THRESHOLD}，使用 Snip Compact 轻量裁剪")
            # 使用 Snip Compact 裁剪可压缩部分
            snipped_messages = self._snip_compact(messages_to_compress)
            return snipped_messages + protected_messages

        # 策略3：大量消息，使用 LLM 全量压缩
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
        if len(messages_to_compress) <= 2:
            logger.info("[ContextCompressor] 可压缩消息太少，跳过 LLM 压缩")
            return messages_to_compress + protected_messages

        try:
            # 构造压缩提示
            conversation_json = json.dumps(messages_to_compress, ensure_ascii=False, indent=2)
            prompt = self.COMPRESSION_PROMPT.format(conversation_json=conversation_json)

            # 调用 LLM 进行压缩
            # 压缩操作处理大量上下文，需要更长的超时时间（300秒）
            chat_params = {
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 16384,  # ✅ 增加到 16384，避免压缩响应被截断
                "timeout": 300.0  # 5分钟超时，处理大量上下文
            }

            # 如果指定了模型，则使用指定模型
            if model:
                chat_params["model"] = model

            response = await self.llm_client.chat(**chat_params)

            # 尝试日志：记录响应信息
            logger.debug(
                f"[ContextCompressor] LLM 压缩响应: 长度={len(response)}, "
                f"预览={response[:200]}..."
            )

            # 解析压缩结果
            compressed = self._parse_compression_result(response)

            # 阶段三：添加压缩边界标记
            boundary_msg = self._create_compaction_boundary(
                original_count=original_count,
                compressed_count=len(compressed) + len(protected_messages),
                compression_type="full"
            )

            # 合并：边界标记 + 压缩后的消息 + 保护段消息
            final_messages = [boundary_msg] + compressed + protected_messages

            # 记录压缩后的状态
            compressed_count = len(final_messages)
            compression_ratio = (1 - compressed_count / original_count) * 100 if original_count > 0 else 0
            logger.info(f"[ContextCompressor] 压缩完成: {original_count} → {compressed_count} 条消息 "
                       f"(压缩率: {compression_ratio:.1f}%)")

            return final_messages

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
            # 降级策略：简单截断，保留最近的消息
            fallback_count = max(10, len(messages) // 2)
            logger.warning(f"[ContextCompressor] 使用降级策略，保留最近 {fallback_count} 条消息")
            return messages[-fallback_count:]

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
            "role": "system",
            "subtype": "compact_boundary",
            "content": f"[上下文已压缩] 原始 {original_count} 条消息 → 压缩后 {compressed_count} 条消息",
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
            msg_type = msg.get('type', '')

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
            msg_type = msg.get('type', '')

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

        truncated_count = 0
        result = []

        for msg in messages:
            msg_copy = dict(msg)
            msg_type = msg_copy.get('type', '')
            content = msg_copy.get('content', '')

            # 处理 observation/tool_result 类型
            if msg_type in ('observation', 'tool_result'):
                if len(content) > self.MAX_OBSERVATION_CHARS:
                    # 提取 data_id（如果有）
                    data_id_match = re.search(r'data_id["\s:]+([^\s,}]+)', content)
                    data_id_ref = f"，data_id: {data_id_match.group(1)}" if data_id_match else ""

                    # 截断内容，保留开头摘要
                    truncated = content[:self.MAX_OBSERVATION_CHARS]
                    # 尝试在句号/换行处截断
                    last_period = max(truncated.rfind('。'), truncated.rfind('\n'), truncated.rfind('.'))
                    if last_period > self.MAX_OBSERVATION_CHARS // 2:
                        truncated = truncated[:last_period + 1]

                    msg_copy['content'] = f"{truncated}... [已截断，原始长度: {len(content)} 字符]{data_id_ref}"
                    truncated_count += 1

            # 处理 action/tool_use 类型（可选：精简参数）
            elif msg_type in ('action', 'tool_use'):
                if len(content) > 1000:
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
