"""
ReAct Agent 规划器 (Planner) - V4 按模式过滤

使用 Anthropic 原生工具调用，但按模式过滤 tools schema。

核心特性:
- 按模式过滤工具定义（Expert 只传 44 个工具，不是 94 个）
- 系统提示词不包含工具列表（避免与 tools schema 重复）
- 节省 token：Expert 模式节省 53%（163 KB），Query 模式节省 62%（190 KB）
- LLM 从 tools 参数获取工具定义，生成原生 tool_use 调用
"""

import json
import structlog
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
from app.tools.base.registry import ToolRegistry
from app.agent.context.execution_context import ExecutionContext
from app.services.llm_service import llm_service
from app.utils.llm_context_logger import get_llm_context_logger
from config.settings import settings

logger = structlog.get_logger()


class ReActPlanner:
    """
    ReAct规划器: 按模式过滤工具定义（V4 架构）

    核心优化:
    - 按模式过滤 tools schema（不同模式传递不同的工具集）
    - 系统提示词不包含工具列表（避免与 tools schema 重复）
    - 节省 token：Expert 模式节省 53%，Query 模式节省 62%

    工作原理:
    - 传递按模式过滤的 tools schema（让 Anthropic 生成原生 tool_use）
    - LLM 从 tools 参数获取工具定义
    - 解析 tool_use blocks（不需要原始 schema）
    """

    def __init__(
        self,
        tool_registry: ToolRegistry = None,
        context: Optional[ExecutionContext] = None,
        llm_client=None,
        max_context_turns: int = 3
    ):
        self._tool_registry = tool_registry
        self.context = context
        self.llm_service = llm_service
        self.max_context_turns = max_context_turns
        self.is_interruption = False

    @property
    def tool_registry(self):
        """延迟加载 tool_registry，支持从外部注入"""
        if self._tool_registry is not None:
            return self._tool_registry
        try:
            from app.agent.tool_adapter import get_react_agent_tool_registry
            return get_react_agent_tool_registry()
        except:
            return {}

    def _fix_missing_tool_results(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """检测并修复缺失的 tool_result 消息

        Anthropic API 要求每个 tool_use 都有对应的 tool_result，
        缺失会导致 API 报错。此方法自动补全缺失的 error tool_result。

        Args:
            conversation_history: 对话历史

        Returns:
            修复后的对话历史
        """
        from app.agent.utils.anthropic_messages import detect_missing_tool_results, generate_missing_tool_result_messages

        missing_tool_use_ids = detect_missing_tool_results(conversation_history)
        if missing_tool_use_ids:
            logger.warning(
                "missing_tool_results_detected",
                missing_count=len(missing_tool_use_ids),
                missing_ids=list(missing_tool_use_ids)
            )
            assistant_messages = [
                msg for msg in conversation_history
                if msg.get("role") == "assistant"
            ]
            missing_messages = generate_missing_tool_result_messages(
                assistant_messages[-5:],
                error_message="工具执行被中断或失败"
            )
            conversation_history.extend(missing_messages)
            logger.info(
                "missing_tool_results_fixed",
                added_count=len(missing_messages)
            )
        return conversation_history

    async def think_and_action(
        self,
        query: str,
        system_prompt: str,
        user_conversation: str,
        tools: List[Dict],
        iteration: int = 0,
        mode: str = "expert",
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """原生工具调用规划器（非流式）

        使用 Anthropic 原生 tool_use blocks，按模式过滤工具定义。

        Args:
            tools: 按模式过滤的工具 schema（Expert 模式约 44 个工具，节省 53% token）

        Returns:
            {
                "thought": str,
                "action": {
                    "type": "TOOL_CALL" | "PLAIN_TEXT_REPLY",
                    "tool": str,
                    "tool_call_id": str,
                    "args": Dict,
                    "answer": str
                }
            }
        """
        from app.agent.tool_adapter import convert_openai_to_anthropic_schema

        if conversation_history is None:
            conversation_history = []

        conversation_history = self._fix_missing_tool_results(conversation_history)

        # 构建 messages（Anthropic API 不接受 system 在 messages 中）
        messages = conversation_history + [
            {"role": "user", "content": user_conversation}
        ]

        # 转换工具为 Anthropic 格式
        anthropic_tools = [
            convert_openai_to_anthropic_schema(tool)
            for tool in tools
        ]

        logger.info("anthropic_planner_call", iteration=iteration, mode=mode, tool_count=len(tools))

        llm_response = await self.llm_service.chat_anthropic(
            messages=messages,
            tools=anthropic_tools,
            temperature=0.3,
            system=system_prompt
        )

        return self._parse_anthropic_response(llm_response)

    async def think_and_action_streaming(
        self,
        query: str,
        system_prompt: str,
        user_conversation: str,
        tools: List[Dict],
        iteration: int = 0,
        mode: str = "expert",
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式规划器（按模式过滤 tools schema）

        使用 Anthropic streaming API，按模式传递工具定义。
        按 content_block 事件逐步 yield：
        - text blocks: 流式输出文本内容
        - tool_use blocks: 完成后 yield 工具调用

        Args:
            tools: 按模式过滤的工具 schema（Expert 模式约 44 个工具，节省 53% token）

        Yields:
            流式事件:
            - {"type": "streaming_text", "data": {"chunk": str, "is_complete": bool}}
            - {"type": "thought", "data": {"thought": str}}
            - {"type": "tool_use", "data": {"tool_use_id": str, "tool_name": str, "input": Dict}}
            - {"type": "action", "data": {"thought": str, "action": Dict}}
        """
        from app.agent.tool_adapter import convert_openai_to_anthropic_schema

        if conversation_history is None:
            conversation_history = []

        conversation_history = self._fix_missing_tool_results(conversation_history)

        messages = conversation_history + [
            {"role": "user", "content": user_conversation}
        ]

        # 转换工具为 Anthropic 格式
        anthropic_tools = [
            convert_openai_to_anthropic_schema(tool)
            for tool in tools
        ]

        logger.info("planner_streaming_call", iteration=iteration, mode=mode, tool_count=len(tools))

        # 累积 content blocks
        current_blocks: List[Dict[str, Any]] = []
        current_thinking_block: Optional[Dict[str, Any]] = None  # ✅ 新增：thinking block
        current_text_block: Optional[Dict[str, Any]] = None  # {"index": int, "text": str}
        current_tool_block: Optional[Dict[str, Any]] = None  # {"index": int, "id": str, "name": str, "input_json": str}
        # V4: 追踪已 yield 的 tool_use 数量（避免重复处理）
        yielded_tool_use_count = 0

        try:
            async for event in self.llm_service.chat_anthropic_streaming(
                messages=messages,
                tools=anthropic_tools,
                temperature=0.3,
                system=system_prompt
            ):
                event_type = event["type"]
                event_data = event["data"]

                if event_type == "content_block_start":
                    block = event_data["block"]
                    index = event_data["index"]

                    if block.type == "thinking":
                        # ✅ 处理 thinking block
                        current_thinking_block = {"index": index, "thinking": ""}
                    elif block.type == "text":
                        current_text_block = {"index": index, "text": ""}
                    elif block.type == "tool_use":
                        current_tool_block = {
                            "index": index,
                            "id": block.id,
                            "name": block.name,
                            "input_json": ""
                        }

                elif event_type == "content_block_delta":
                    index = event_data["index"]
                    delta = event_data["delta"]

                    if delta.type == "text_delta":
                        text_chunk = delta.text
                        if current_text_block and current_text_block["index"] == index:
                            current_text_block["text"] += text_chunk
                        # 流式输出文本
                        yield {
                            "type": "streaming_text",
                            "data": {"chunk": text_chunk, "is_complete": False}
                        }

                    elif delta.type == "thinking_delta":
                        # ✅ 处理 thinking 增量
                        thinking_chunk = delta.thinking
                        if current_thinking_block and current_thinking_block["index"] == index:
                            current_thinking_block["thinking"] += thinking_chunk

                            # ✅ 实时发送 thinking_delta 事件（流式显示思考过程）
                            yield {
                                "type": "thinking_delta",
                                "data": {
                                    "chunk": thinking_chunk,
                                    "is_complete": False
                                }
                            }

                    elif delta.type == "signature_delta":
                        # ✅ 处理 redacted_thinking 签名增量
                        # 当收到 signature_delta 时，该 block 是 redacted_thinking
                        if current_thinking_block and current_thinking_block["index"] == index:
                            current_thinking_block["is_redacted"] = True
                            current_thinking_block["signature"] = getattr(delta, "signature", "")

                    elif delta.type == "input_json_delta":
                        json_chunk = delta.partial_json
                        if current_tool_block and current_tool_block["index"] == index:
                            current_tool_block["input_json"] += json_chunk

                elif event_type == "content_block_stop":
                    index = event_data["index"]

                    if current_thinking_block and current_thinking_block["index"] == index:
                        # ✅ 保存完整的 thinking block
                        # ⚠️ DeepSeek 不支持 redacted_thinking，只支持 thinking
                        # 对于 DeepSeek，即使有 signature_delta，也保存为 thinking 类型
                        is_deepseek = (
                            self.llm_service.provider == "deepseek" or
                            "deepseek" in self.llm_service.model.lower()
                        )

                        if is_deepseek:
                            # DeepSeek: 始终使用 thinking 类型，忽略 signature_delta
                            current_blocks.append({
                                "type": "thinking",
                                "thinking": current_thinking_block["thinking"]
                            })
                        elif current_thinking_block.get("is_redacted"):
                            # 真正的 Anthropic API: 支持 redacted_thinking
                            current_blocks.append({
                                "type": "redacted_thinking",
                                "data": current_thinking_block.get("signature", "")
                            })
                        else:
                            current_blocks.append({
                                "type": "thinking",
                                "thinking": current_thinking_block["thinking"]
                            })

                        # ✅ 发送 thinking 完成事件
                        yield {
                            "type": "thinking_delta",
                            "data": {
                                "chunk": "",
                                "is_complete": True
                            }
                        }

                        current_thinking_block = None

                    if current_text_block and current_text_block["index"] == index:
                        current_blocks.append({
                            "type": "text",
                            "text": current_text_block["text"]
                        })
                        current_text_block = None

                    elif current_tool_block and current_tool_block["index"] == index:
                        # 解析完整的 tool_use input JSON
                        tool_input = {}
                        if current_tool_block["input_json"]:
                            try:
                                tool_input = json.loads(current_tool_block["input_json"])
                            except json.JSONDecodeError:
                                logger.warning(
                                    "tool_use_input_json_parse_failed",
                                    tool_name=current_tool_block["name"],
                                    raw_json=current_tool_block["input_json"][:200]
                                )
                                tool_input = {}

                        tool_block = {
                            "type": "tool_use",
                            "id": current_tool_block["id"],
                            "name": current_tool_block["name"],
                            "input": tool_input
                        }
                        current_blocks.append(tool_block)
                        current_tool_block = None

                        # V4 核心：content_block_stop 时立即 yield tool_use 事件
                        # 让 StreamingToolExecutor 可以在流中立即启动工具执行
                        yielded_tool_use_count += 1
                        yield {
                            "type": "tool_use",
                            "data": {
                                "tool_use_id": tool_block["id"],
                                "tool_name": tool_block["name"],
                                "input": tool_input
                            }
                        }

                        logger.info(
                            "streaming_tool_use_yielded_early",
                            tool_name=tool_block["name"],
                            tool_use_id=tool_block["id"][:12],
                            yielded_count=yielded_tool_use_count,
                        )

                elif event_type == "message_delta":
                    stop_reason = event_data.get("stop_reason")
                    logger.info(
                        "anthropic_stream_message_delta",
                        stop_reason=stop_reason
                    )

                elif event_type == "message_stop":
                    # 流结束，处理累积的 content blocks
                    # ✅ 调试日志：打印原始 blocks
                    logger.info(
                        "message_stop_blocks_received",
                        iteration=iteration,
                        total_blocks=len(current_blocks),
                        blocks_types=[b.get("type") for b in current_blocks],
                        blocks_preview=[{"type": b.get("type"), "preview": str(b)[:100]} for b in current_blocks[:3]]
                    )
                    result = self._parse_accumulated_blocks(current_blocks)

                    # 提取 thought
                    text_content = ""
                    for b in current_blocks:
                        if b["type"] == "text":
                            text_content = b["text"]
                            break

                    # ✅ 先 yield thought 事件（在 streaming_text complete 之前）
                    # 这样前端可以在最终答案消息创建前收到思考内容
                    yield {
                        "type": "thought",
                        "data": {
                            "thought": result.get("thought", ""),
                            "text_content": text_content
                        }
                    }

                    # 发送 streaming_text 完成标记（如果有文本块）
                    has_text = any(b["type"] == "text" for b in current_blocks)
                    if has_text:
                        yield {
                            "type": "streaming_text",
                            "data": {"chunk": "", "is_complete": True}
                        }

                    # yield 最终 action 事件（包含所有 tool_use blocks 信息）
                    # V4: 将已 yield 的 tool_use 数量传给 loop，让它知道哪些已在流中启动
                    result["yielded_tool_use_count"] = yielded_tool_use_count
                    yield {
                        "type": "action",
                        "data": result
                    }

        except Exception as e:
            logger.error(
                "anthropic_planner_streaming_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            # 降级到非流式
            logger.info("anthropic_planner_fallback_to_non_streaming")
            result = await self.think_and_action(
                query=query,
                system_prompt=system_prompt,
                user_conversation=user_conversation,
                tools=tools,
                iteration=iteration,
                mode=mode,
                conversation_history=conversation_history
            )
            yield {
                "type": "streaming_text",
                "data": {"chunk": "", "is_complete": True}
            }
            yield {
                "type": "thought",
                "data": {
                    "thought": result.get("thought", "")
                }
            }
            yield {
                "type": "action",
                "data": result
            }

    def _parse_anthropic_response(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Anthropic 非流式响应

        通过遍历 content blocks 检测工具调用（不依赖 stop_reason）

        Args:
            llm_response: Anthropic API 响应

        Returns:
            标准化的规划结果
        """
        content_blocks = llm_response["content"]

        # 分离不同类型的 blocks
        thinking_blocks = [
            block for block in content_blocks
            if block.type == "thinking"
        ]
        tool_use_blocks = [
            block for block in content_blocks
            if block.type == "tool_use"
        ]
        text_blocks = [
            block for block in content_blocks
            if block.type == "text"
        ]

        # ✅ 提取 thinking 内容（如果有）
        thinking_text = ""
        if thinking_blocks:
            # 合并所有 thinking blocks
            thinking_text = " ".join([
                (block.thinking if hasattr(block, 'thinking') else "")
                for block in thinking_blocks
            ])

        # ✅ 提取对话文本（用于answer字段）
        full_text = " ".join([
            (block.text if hasattr(block, 'text') else "")
            for block in text_blocks
        ])

        if not tool_use_blocks:
            # 无工具调用 - 纯文本回复
            return {
                "thought": thinking_text or "思考回复策略",
                "action": {
                    "type": "PLAIN_TEXT_REPLY",
                    "answer": full_text
                }
            }

        # 有工具调用
        tool_call = tool_use_blocks[0]
        return {
            "thought": thinking_text or f"准备调用工具: {tool_call.name}",
            "action": {
                "type": "TOOL_CALL",
                "tool": tool_call.name,
                "tool_call_id": tool_call.id,
                "args": tool_call.input
            }
        }

    def _parse_accumulated_blocks(self, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """解析流式累积的 content blocks

        Args:
            blocks: 累积的 content block 列表

        Returns:
            标准化的规划结果
        """
        # 分离不同类型的 blocks
        # ✅ 同时检测 thinking 和 redacted_thinking（DeepSeek 返回 redacted_thinking）
        thinking_blocks = [b for b in blocks if b.get("type") in ("thinking", "redacted_thinking")]
        tool_use_blocks = [b for b in blocks if b.get("type") == "tool_use"]
        text_blocks = [b for b in blocks if b.get("type") == "text"]

        # ✅ 调试日志：打印所有 blocks 的类型和内容摘要
        logger.debug(
            "parse_accumulated_blocks_debug",
            total_blocks=len(blocks),
            thinking_count=len(thinking_blocks),
            tool_use_count=len(tool_use_blocks),
            text_count=len(text_blocks),
            blocks_types=[b.get("type") for b in blocks],
            text_blocks_preview=[{"type": b.get("type"), "text_length": len(b.get("text", "")), "text_preview": b.get("text", "")[:100]} for b in text_blocks[:3]]
        )

        # ✅ 提取 thinking 内容
        thinking_text = ""
        if thinking_blocks:
            # ⚠️ DeepSeek 返回的是 redacted_thinking，需要特殊处理
            # 提取 thinking 内容（redacted_thinking 的 data 字段是签名）
            thinking_text_parts = []
            for b in thinking_blocks:
                if b.get("type") == "thinking":
                    thinking_text_parts.append(b.get("thinking", ""))
                elif b.get("type") == "redacted_thinking":
                    # redacted_thinking 的 data 字段是签名（不包含实际内容）
                    # DeepSeek 官方文档：redacted_thinking Not Supported（只返回不接受）
                    # 我们记录日志，但不提取内容
                    logger.debug(
                        "redacted_thinking_found",
                        signature=b.get("data", "")[:50]  # 只记录前50个字符
                    )
            thinking_text = " ".join(thinking_text_parts)

        # ✅ 提取对话文本
        full_text = " ".join([
            b.get("text", "") for b in text_blocks
        ])

        # ⚠️ 特殊处理：如果没有 text blocks，使用 thinking blocks 的内容
        # DeepSeek 在 thinking mode 下可能只返回 thinking blocks
        if not full_text and thinking_blocks:
            logger.warning(
                "no_text_blocks_using_thinking",
                thinking_count=len(thinking_blocks),
                thinking_preview=[b.get("thinking", "")[:200] for b in thinking_blocks[:2]]
            )
            # 使用最后一个 thinking block 的内容（通常是最终答案）
            full_text = thinking_blocks[-1].get("thinking", "")

        if not tool_use_blocks:
            # 纯文本回复
            logger.info(
                "parse_accumulated_blocks_plain_text",
                full_text_length=len(full_text),
                full_text_preview=full_text[:200],
                thinking_text_length=len(thinking_text),
                thinking_text_preview=thinking_text[:200] if thinking_text else ""
            )
            return {
                "thought": thinking_text or "思考回复策略",
                "action": {
                    "type": "PLAIN_TEXT_REPLY",
                    "answer": full_text
                },
                # ✅ 保留原始 thinking blocks
                "raw_thinking_blocks": thinking_blocks,
            }

        # 有工具调用
        logger.info(
            "parse_accumulated_blocks_tool_call",
            tool_count=len(tool_use_blocks),
            tool_names=[b.get("name") for b in tool_use_blocks],
            has_text=bool(text_blocks),
            text_length=len(full_text),
            text_preview=full_text[:200] if full_text else "",
            thinking_length=len(thinking_text)
        )
        # V4: 包含所有 tool_use blocks 信息（支持流式多工具执行）
        tool_call = tool_use_blocks[0]
        result = {
            "thought": thinking_text or f"准备调用工具: {tool_call['name']}",
            "action": {
                "type": "TOOL_CALL",
                "tool": tool_call["name"],
                "tool_call_id": tool_call["id"],
                "args": tool_call["input"]
            },
            "all_tool_calls": [
                {
                    "type": "TOOL_CALL",
                    "tool": block["name"],
                    "tool_call_id": block["id"],
                    "args": block["input"]
                }
                for block in tool_use_blocks
            ],
            # ✅ 保留原始 thinking blocks（DeepSeek 等兼容 API 要求回传 thinking blocks）
            "raw_thinking_blocks": thinking_blocks,
        }

        # 当有多个工具调用时，action 使用 TOOL_CALLS 类型
        if len(tool_use_blocks) > 1:
            result["action"] = {
                "type": "TOOL_CALLS",
                "tools": result["all_tool_calls"]
            }

        return result

    async def stream_user_answer(self, prompt: str) -> AsyncGenerator[str, None]:
        """流式生成用户答案

        用于 FINISH_SUMMARY 阶段，生成最终的分析报告。
        优先使用 Anthropic 流式 API，如果不可用则降级到 SSE。

        Args:
            prompt: 生成答案的提示词

        Yields:
            str: 生成的文本片段
        """
        messages = [{"role": "user", "content": prompt}]

        logger.info("stream_user_answer_start", prompt_length=len(prompt))
        chunk_count = 0
        total_length = 0

        # 优先使用 Anthropic 流式 API
        if self.llm_service.anthropic_client:
            try:
                async for event in self.llm_service.chat_anthropic_streaming(
                    messages=messages,
                    temperature=0.7,
                    system="你是一个专业的数据分析助手，请用清晰、准确的语言回答用户的问题。"
                ):
                    if event["type"] == "content_block_delta":
                        delta = event["data"].get("delta")
                        if delta and delta.type == "text_delta":
                            piece = delta.text
                            if piece:
                                chunk_count += 1
                                total_length += len(piece)
                                yield piece

                logger.info("stream_user_answer_complete_anthropic", chunks=chunk_count, length=total_length)
                return

            except Exception as e:
                logger.error("stream_user_answer_anthropic_failed", error=str(e))
                # 降级到 SSE 方式

        # 降级: 使用 SSE 流式 API
        import httpx

        url, headers = self.llm_service._get_request_config()
        payload = {
            "model": self.llm_service.model,
            "messages": messages,
            "temperature": 0.7,
            "stream": True,
        }
        if self.llm_service.provider == "qwen":
            payload["enable_thinking"] = False

        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[len("data: "):].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                            except Exception:
                                continue
                            choices = chunk.get("choices")
                            if not isinstance(choices, list) or not choices:
                                continue
                            first_choice = choices[0]
                            if not isinstance(first_choice, dict):
                                continue
                            delta = first_choice.get("delta") or first_choice.get("message") or {}
                            piece = delta.get("content") or ""
                            if piece:
                                chunk_count += 1
                                total_length += len(piece)
                                yield piece

            logger.info("stream_user_answer_complete_sse", chunks=chunk_count, length=total_length)

        except Exception as e:
            logger.error("stream_user_answer_sse_failed", error=str(e))
            yield f"\n\n[生成失败: {str(e)}]"
