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
  {{"type": "action", "role": "assistant", "content": "调用 get_weather_data，参数：城市=广州"}},
  {{"type": "observation", "role": "assistant", "content": "成功获取 30 条记录，data_id: weather_001"}},
  {{"type": "final", "role": "assistant", "content": "根据分析，发现..."}}
]

⚠️ 再次强调：
1. 保持每条消息的 type 字段不变
2. 只压缩 content 字段的内容
3. 不要合并或删除消息
4. 输出必须以 [ 开头，以 ] 结尾
"""

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
        使用 LLM 压缩对话历史

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
        logger.info(f"[ContextCompressor] 开始压缩，原始消息数: {original_count}")

        # 预截断：LLM 无法处理超大输入，限制发送的消息量
        # 保留头部 2 条（初始上下文）+ 尾部最近消息，总字符不超过 300,000
        MAX_COMPRESS_CHARS = 300_000
        messages_to_compress = self._pre_truncate_for_compression(messages, MAX_COMPRESS_CHARS)
        if len(messages_to_compress) < original_count:
            logger.warning(
                f"[ContextCompressor] 预截断: {original_count} → {len(messages_to_compress)} 条消息 "
                f"(原始内容过大，仅压缩最近部分)"
            )

        try:
            # 构造压缩提示
            conversation_json = json.dumps(messages_to_compress, ensure_ascii=False, indent=2)
            prompt = self.COMPRESSION_PROMPT.format(conversation_json=conversation_json)

            # 调用 LLM 进行压缩
            # 压缩操作处理大量上下文，需要更长的超时时间（300秒）
            chat_params = {
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 8000,
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

            # 记录压缩后的状态
            compressed_count = len(compressed)
            compression_ratio = (1 - compressed_count / original_count) * 100 if original_count > 0 else 0
            logger.info(f"[ContextCompressor] 压缩完成: {original_count} → {compressed_count} 条消息 "
                       f"(压缩率: {compression_ratio:.1f}%)")

            return compressed

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
            msg_chars = len(json.dumps(m, ensure_ascii=False))
            if accumulated + msg_chars > budget:
                break
            tail.insert(0, msg)
            accumulated += msg_chars

        return head + tail

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
