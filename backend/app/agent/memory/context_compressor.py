"""
上下文压缩器 - 使用 LLM 智能压缩对话历史

参考 Claude Code 的压缩策略，保留关键信息，移除冗余内容。
"""

from typing import List, Dict, Any
import json
import structlog

logger = structlog.get_logger()


class ContextCompressor:
    """上下文压缩器（使用 LLM）"""

    # 参考 Claude Code 的压缩提示词
    COMPRESSION_PROMPT = """你是一个对话上下文压缩专家。你的任务是压缩以下对话历史，保留关键信息，移除冗余内容。

**压缩原则**：

**必须完整保留（不压缩）**：
1. 用户的核心需求和问题
2. 重要的 data_id 引用（如 weather_001, pmf_result_002 等）
3. 关键的分析结论和发现
4. 重要的决策点和推理链
5. 关键的数值和统计结果

**可以移除**：
1. 冗长的工具返回详情（保留 data_id 和关键统计即可）
2. 重复的思考过程
3. 详细的中间步骤（保留结论）
4. 已完成任务的详细执行日志（保留结果）
5. 大段的数据展示（用摘要替代）

**压缩策略**：
- 数据查询工具（get_*/calculate_*/download_*等）：压缩为 "调用 get_weather_data → data_id: weather_001 (30条记录, 温度25°C)"
- 思考过程：提炼为关键决策点 "决定先分析气象条件"
- 分析结果：保留核心结论 "发现15天高温天气导致O3浓度升高"
- 办公助理工具（bash/read_file/analyze_image/Office工具/read_docx/grep/glob/list_directory/execute_python）：完整保留工具返回的 data 字段内容

**重要**：
- 保持对话的逻辑连贯性
- 保留所有 data_id 引用（后续分析可能需要）
- 保留用户的每个问题
- 保留助手的最终回答

**原始对话**：
{conversation_json}

**输出要求（CRITICAL - 必须严格遵守）**：

⚠️ **你的输出将直接传递给 json.loads() 解析，任何非 JSON 字符都会导致系统崩溃！**

**强制规则**：
1. 第一个字符必须是 `[`（左方括号）
2. 最后一个字符必须是 `]`（右方括号）
3. 禁止使用 ```json 或 ``` 包裹 JSON
4. 禁止在 JSON 前后添加任何解释文字、空行或其他字符
5. 每条消息必须包含 "role" 和 "content" 字段
6. 返回标准 JSON 数组格式

**错误示例（会导致系统崩溃）**：
```json
[
  {{"role": "user", "content": "分析广州O3污染"}}
]
```

或者：

这是压缩后的结果：
[{{"role": "user", "content": "..."}}]

**正确示例（直接输出 JSON 数组）**：
[
  {{"role": "user", "content": "分析广州O3污染"}},
  {{"role": "assistant", "content": "调用 get_weather_data → data_id: weather_001 (30条记录)"}},
  {{"role": "user", "content": "读取这个图片文件 D:/chart.png 并分析"}},
  {{"role": "assistant", "content": "已读取图片并完成分析。分析结果：\\n\\n图片内容：这是一张折线图，显示了...\\n数据趋势：...\\n关键发现：...（完整的 analyze_image 返回内容）"}}
]

⚠️ 再次强调：你的输出必须以 [ 开头，以 ] 结尾，中间不能有任何非 JSON 内容。
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

        try:
            # 构造压缩提示
            conversation_json = json.dumps(messages, ensure_ascii=False, indent=2)
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
