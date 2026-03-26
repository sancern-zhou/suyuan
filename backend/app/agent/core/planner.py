"""
ReAct Agent 规划器 (Planner)

实现一次性参数生成架构:
- LLM 在提示词中看到完整工具信息，一次性生成参数
- 复杂工具参数通过 "源码即文档" 策略获取

优点: 减少50%的LLM调用次数，提升响应速度
"""

import json
import structlog
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.tools.base.registry import ToolRegistry
from app.agent.context.execution_context import ExecutionContext
from app.services.llm_service import llm_service
from app.utils.llm_response_parser import LLMResponseParser
from app.utils.llm_context_logger import get_llm_context_logger
from config.settings import settings

logger = structlog.get_logger()


class ReActPlanner:
    """
    ReAct规划器: 实现思考-行动-观察循环

    核心特性:
    - 一次性参数生成（提示词中包含完整工具信息）
    - 上下文感知的参数构造
    - 智能LLM响应解析
    """

    def __init__(
        self,
        tool_registry: ToolRegistry = None,
        context: Optional[ExecutionContext] = None,
        llm_client=None,
        max_context_turns: int = 3
    ):
        # 如果没有提供 tool_registry，延迟到使用时从 executor 获取
        self._tool_registry = tool_registry
        self.context = context
        self.llm_service = llm_service
        self.max_context_turns = max_context_turns
        self.is_interruption = False  # 中断标志

    @property
    def tool_registry(self):
        """延迟加载 tool_registry，支持从外部注入"""
        if self._tool_registry is not None:
            return self._tool_registry

        # 尝试从全局工具注册表获取
        try:
            from app.agent.tool_adapter import get_react_agent_tool_registry
            return get_react_agent_tool_registry()
        except:
            # 返回空字典作为fallback
            return {}

    async def think_and_action_v2(
        self,
        query: str,
        system_prompt: str,
        user_conversation: str,
        iteration: int,
        latest_observation: Any = None,
        mode: str = None  # 添加模式参数
    ) -> Dict:
        """
        V2版本：思考和行动合并（单次LLM调用）

        用于单步模式的 ReAct 循环，接收已构建好的上下文，直接调用 LLM。

        Args:
            query: 用户查询
            system_prompt: 系统提示词（包含工具摘要）
            user_conversation: 用户对话内容（字符串格式）
            iteration: 当前迭代次数
            latest_observation: 最近的观察结果（可选）

        Returns:
            {
                "thought": "思考过程",
                "reasoning": "推理过程（可选）",
                "action": {
                    "type": "TOOL_CALL" | "TOOL_CALLS",
                    "tool": "工具名称",
                    "args": {...}
                }
            }
        """
        # 构建消息列表
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_conversation}
        ]

        # 调用LLM
        logger.debug(f"[Planner V2] 调用LLM，iteration={iteration}, mode={mode}")

        # ✅ 报告模式设置max_tokens限制，避免代码过长导致截断
        max_tokens = None
        if mode == "report":
            max_tokens = settings.report_mode_max_tokens
            logger.info(f"[Planner V2] 报告模式设置max_tokens={max_tokens}")

        llm_response = await self.llm_service.chat(messages, max_tokens=max_tokens)

        # ✅ 添加完整LLM响应日志（调试用）
        logger.info(f"[Planner V2] LLM完整响应 - iteration={iteration}, length={len(llm_response)}")
        logger.debug(f"[Planner V2] 完整响应内容:\n{llm_response}")

        # 解析响应 - 使用全局 parser 实例
        from app.utils.llm_response_parser import parser
        parsed_result = parser.parse(llm_response)

        # 检查解析是否成功
        if not parsed_result.get("success") or not parsed_result.get("data"):
            # 解析失败 → 判断为纯文本回复（LLM 直接输出文本，无需工具调用）
            logger.info("[Planner V2] 检测到纯文本回复（非 JSON 格式）")
            return {
                "thought": "直接回复用户",
                "reasoning": "LLM 输出纯文本，无需工具调用",
                "action": {
                    "type": "PLAIN_TEXT_REPLY",
                    "answer": llm_response.strip()
                },
                "raw_response": llm_response
            }

        # 提取解析后的数据
        data = parsed_result["data"]

        # 兼容两种格式：
        # 1. 新格式（推荐）：{"thought": "...", "reasoning": "...", "action": {...}}
        # 2. 旧格式：{"thought": "...", "action": "...", "action_input": {...}}

        thought = data.get("thought", "")
        reasoning = data.get("reasoning", "")

        # 兼容两种格式：
        # 1. 新格式（推荐）：{"thought": "...", "reasoning": "...", "action": {...}}
        # 2. 旧格式：{"thought": "...", "action": "...", "action_input": {...}}

        # 检查是否是新格式（直接包含 action 对象）
        if "action" in data and isinstance(data["action"], dict):
            # 新格式：action 已经是完整的对象
            action = data["action"]
        else:
            # 旧格式：需要从 action 和 action_input 构造
            action_input = data.get("action_input", {})
            action_name = data.get("action", "")

            if isinstance(action_input, dict) and "type" in action_input:
                # action_input 本身就是 action 对象
                action = action_input
            elif action_name == "final_answer":
                action = {
                    "type": "FINISH_SUMMARY",
                    "tool": "FINISH_SUMMARY",
                    "args": {"answer": action_input.get("answer", "")} if isinstance(action_input, dict) else {"answer": str(action_input)}
                }
            else:
                action = {
                    "type": "TOOL_CALL",
                    "tool": action_name,
                    "args": action_input if isinstance(action_input, dict) else {}
                }

        # ========== 统一采用一次性参数生成 ==========
        # 所有工具在提示词中已包含参数说明，LLM 一次性生成完整参数
        # 如果参数为空（如 list_tools），说明该工具不需要参数，直接执行

        return {
            "thought": thought,
            "reasoning": reasoning,
            "action": action
        }

    async def think_and_action_v2_streaming(
        self,
        query: str,
        system_prompt: str,
        user_conversation: str,
        iteration: int,
        latest_observation: Any = None,
        mode: str = None  # 添加模式参数
    ):
        """
        V2流式版本：边接收LLM输出边检测格式，支持纯文本流式输出

        与 think_and_action_v2 的区别：
        - 使用流式 LLM 调用
        - 边输出边检测 JSON 格式
        - 检测到纯文本时立即 yield streaming_text 事件

        Args:
            同 think_and_action_v2

        Yields:
            - {"type": "streaming_text", "data": {"chunk": str}}
            - {"type": "action", "data": {...}} (最终的 action)
        """
        import json
        from app.utils.llm_response_parser import parser

        # 构建消息列表
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_conversation}
        ]

        # ✅ 使用LLMContextLogger记录完整的请求上下文到文件
        try:
            # 获取当前session_id（从query参数或外部获取）
            # 这里使用一个简化的方式，实际应该从外部传入
            import uuid
            session_id = getattr(self, '_current_session_id', str(uuid.uuid4()))

            llm_context_logger = get_llm_context_logger()
            log_file_path = llm_context_logger.log_request_context(
                session_id=session_id,
                iteration=iteration,
                mode=mode or "unknown",
                messages=messages,
                metadata={
                    "query": query[:100] if len(query) > 100 else query,
                }
            )

            # 在控制台只显示预览和文件路径
            system_prompt_preview = system_prompt[:200] + "..." if len(system_prompt) > 200 else system_prompt
            user_conversation_preview = user_conversation[:300] + "..." if len(user_conversation) > 300 else user_conversation

            logger.info(
                "llm_request_context_logged",
                iteration=iteration,
                mode=mode,
                messages_count=len(messages),
                system_prompt_length=len(system_prompt),
                user_conversation_length=len(user_conversation),
                system_prompt_preview=system_prompt_preview,
                user_conversation_preview=user_conversation_preview,
                log_file=log_file_path,
            )
        except Exception as e:
            logger.error("llm_context_logging_failed", error=str(e), iteration=iteration)

        # 流式累积缓冲区
        buffer = ""
        is_final_answer = False  # 是否已确认为最终回答
        is_finish_summary = False  # 是否已确认为总结结束
        final_answer_buffer = ""  # 最终回答的累积缓冲区
        chunk_count = 0
        last_parse_offset = 0  # 上次解析位置（优化：减少重复解析）
        answer_extracted = ""  # 已提取的 answer 内容（用于正则模式）

        # ✅ SSE流结束信号机制（替代延迟退出机制）
        json_detected = False  # 是否检测到JSON完成（用于日志记录）
        json_detect_time = None  # JSON检测到的时间戳（用于日志记录）

        # ✅ 正则表达式模式：从流式文本中提取 answer 字段
        import re
        # 简单模式：直接从 "answer": " 之后提取所有内容（不等待 JSON 完成）
        answer_start_pattern = re.compile(r'"answer"\s*:\s*"')
        # 精确模式：用于最终验证和清理
        answer_exact_pattern = re.compile(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"')

        try:
            stream_start_time = None
            stream_complete = False  # 流结束标记

            async for stream_result in self.llm_service.chat_streaming_with_status(messages):
                if stream_start_time is None:
                    stream_start_time = datetime.now()
                    # logger.info(f"[Planner V2 Streaming] 收到第一个 chunk，延迟: {(datetime.now() - stream_start_time).total_seconds()}s")

                # 提取chunk和is_complete状态
                chunk = stream_result.get("chunk", "")
                is_complete = stream_result.get("is_complete", False)

                # 检查流是否结束
                if is_complete:
                    stream_complete = True
                    break  # 流结束，立即退出循环

                chunk_count += 1
                buffer += chunk

                # 每10个chunk输出一次日志（已关闭）
                # if chunk_count % 10 == 0:
                #     logger.info(f"[Planner V2 Streaming] 已收到 {chunk_count} chunks，缓冲区大小: {len(buffer)} 字符")

                # ✅ 快速检测：是否包含 FINAL_ANSWER 或 FINISH_SUMMARY 标记
                if not is_final_answer and not is_finish_summary:
                    if '"FINAL_ANSWER"' in buffer or '"FINISH_SUMMARY"' in buffer:
                        # 检测到最终回答标记，立即启用正则提取模式
                        action_type = "FINAL_ANSWER" if '"FINAL_ANSWER"' in buffer else "FINISH_SUMMARY"
                        if action_type == "FINAL_ANSWER":
                            is_final_answer = True
                            # logger.info(f"[Planner V2 Streaming] 检测到 {action_type} 标记，启用正则提取模式")
                        else:
                            is_finish_summary = True
                            # logger.info(f"[Planner V2 Streaming] 检测到 {action_type} 标记，启用正则提取模式")

                # ✅ 正则提取模式：直接从流式文本中提取 answer 内容（不等待 JSON 完成）
                if is_final_answer or is_finish_summary:
                    # 查找 answer 字段的开始位置
                    answer_start = answer_start_pattern.search(buffer)
                    if answer_start:
                        # 简单模式：直接从 "answer": " 之后提取所有内容
                        start_pos = answer_start.end()  # 跳过 "answer": "
                        remaining = buffer[start_pos:]

                        # 提取内容（直到遇到 JSON 结束标记或 end of buffer）
                        # 假设 answer 内容是 "...\n" 的形式
                        extracted = ""
                        i = 0
                        while i < len(remaining):
                            char = remaining[i]
                            if char == '"' and i > 0 and remaining[i-1] != '\\':
                                # 遇到未转义的引号，可能是 JSON 字符串结束
                                break
                            elif char == '\\' and i + 1 < len(remaining):
                                # 处理转义字符
                                next_char = remaining[i + 1]
                                if next_char == 'n':
                                    extracted += '\n'
                                elif next_char == 't':
                                    extracted += '\t'
                                elif next_char == 'r':
                                    extracted += '\r'
                                elif next_char == '"':
                                    extracted += '"'
                                elif next_char == '\\':
                                    extracted += '\\'
                                else:
                                    extracted += next_char
                                i += 2
                            else:
                                extracted += char
                                i += 1

                        # 计算新增内容
                        new_content = extracted[len(answer_extracted):]
                        if new_content:
                            answer_extracted = extracted
                            # 立即 yield 新增内容（零延迟！）
                            yield {
                                "type": "streaming_text",
                                "data": {"chunk": new_content, "is_complete": False}
                            }
                            # logger.info(f"[Planner V2 Streaming] 简单模式提取新增内容: {len(new_content)} 字符，累计: {len(answer_extracted)} 字符")

                # ✅ 使用SSE流结束信号，而非延迟退出机制
                if not is_final_answer and not is_finish_summary:
                    # 去除可能的思考标签
                    test_buffer = buffer
                    if "<thinking>" in test_buffer:
                        test_buffer = test_buffer.split("<thinking>")[-1]
                    if "</thinking>" in test_buffer:
                        test_buffer = test_buffer.split("</thinking>")[-1]

                    # 尝试解析 JSON（用于非最终回答类型）
                    # 注意：不再使用延迟退出机制，而是依赖SSE流的is_complete信号
                    try:
                        parsed = parser.parse(test_buffer)
                        if parsed.get("success") and parsed.get("data"):
                            # JSON解析成功，但不立即退出，等待流真正结束
                            if not json_detected:
                                json_detected = True
                                json_detect_time = datetime.now()
                                # logger.info(f"[Planner V2 Streaming] JSON首次解析成功，等待SSE流结束信号")
                    except Exception:
                        # JSON 解析失败 → 继续累积
                        pass

        except Exception as e:
            logger.error(f"[Planner V2 Streaming] 流式调用失败: {e}")
            # 降级到非流式
            result = await self.think_and_action_v2(
                query, system_prompt, user_conversation, iteration, latest_observation
            )
            yield {"type": "action", "data": result}
            return

        # 流式输出完成
        total_time = (datetime.now() - stream_start_time).total_seconds() if stream_start_time else 0

        # 流式输出完成，处理最终结果
        if is_final_answer or is_finish_summary:
            # 最终回答或总结流式输出完成
            action_type_name = "FINAL_ANSWER" if is_final_answer else "FINISH_SUMMARY"
            # 使用 answer_extracted（正则提取的内容）或 final_answer_buffer（JSON 解析的内容）
            final_content = answer_extracted or final_answer_buffer
            # logger.info(f"[Planner V2 Streaming] {action_type_name} 流式输出完成，answer 总长度: {len(final_content)} 字符")
            yield {
                "type": "streaming_text",
                "data": {"chunk": "", "is_complete": True}
            }
            # 解析完整的 JSON（获取完整的 action 结构）
            parsed_result = parser.parse(buffer)
            if parsed_result.get("success") and parsed_result.get("data"):
                data = parsed_result["data"]
                # 如果 JSON 解析有 answer 字段，使用它；否则使用正则提取的内容
                action_data = data.get("action", {})
                if "answer" not in action_data or not action_data["answer"]:
                    action_data["answer"] = final_content
                yield {
                    "type": "action",
                    "data": {
                        "thought": data.get("thought", ""),
                        "reasoning": data.get("reasoning", ""),
                        "action": action_data
                    }
                }
            else:
                logger.error(f"[Planner V2 Streaming] {action_type_name} 最终JSON解析失败")
                # 降级：使用正则提取的内容
                yield {
                    "type": "action",
                    "data": {
                        "thought": "解析错误",
                        "reasoning": "JSON解析失败",
                        "action": {
                            "type": action_type_name,
                            "answer": final_content
                        }
                    }
                }
        else:
            # 非 FINAL_ANSWER，完整解析 JSON
            parsed_result = parser.parse(buffer)

            if not parsed_result.get("success") or not parsed_result.get("data"):
                logger.error(
                    "[Planner V2 Streaming] JSON解析失败",
                    buffer_length=len(buffer),
                    buffer_preview=buffer[:500],
                    parse_error=parsed_result.get("error", "unknown")
                )
                # JSON 解析失败，返回错误
                yield {
                    "type": "action",
                    "data": {
                        "thought": "JSON解析错误",
                        "reasoning": f"LLM输出格式错误: {parsed_result.get('error', 'unknown')}",
                        "action": {
                            "type": "ERROR",
                            "error": "JSON解析失败"
                        }
                    }
                }
                return
            else:
                # 解析成功，提取 action
                data = parsed_result["data"]
                thought = data.get("thought", "")
                reasoning = data.get("reasoning", "")

                if "action" in data and isinstance(data["action"], dict):
                    action = data["action"]
                else:
                    # 旧格式兼容
                    action_input = data.get("action_input", {})
                    action_name = data.get("action", "")

                    if isinstance(action_input, dict) and "type" in action_input:
                        action = action_input
                    elif action_name == "final_answer":
                        action = {
                            "type": "FINAL_ANSWER",
                            "answer": action_input.get("answer", "") if isinstance(action_input, dict) else str(action_input)
                        }
                    else:
                        action = {
                            "type": "TOOL_CALL",
                            "tool": action_name,
                            "args": action_input if isinstance(action_input, dict) else {}
                        }

                # ========== 统一采用一次性参数生成 ==========
                # 所有工具在提示词中已包含参数说明，LLM 一次性生成完整参数
                # 如果参数为空（如 list_tools），说明该工具不需要参数，直接执行

                yield {
                    "type": "action",
                    "data": {
                        "thought": thought,
                        "reasoning": reasoning,
                        "action": action
                    }
                }


    async def stream_user_answer(self, prompt: str):
        """
        流式生成用户答案（异步生成器）

        用于 FINISH_SUMMARY 阶段，生成最终的分析报告。

        Args:
            prompt: 生成答案的提示词

        Yields:
            str: 生成的文本片段
        """
        import httpx

        # 构建消息列表
        messages = [{"role": "user", "content": prompt}]

        # 获取请求配置
        url, headers = self.llm_service._get_request_config()

        # 构建请求payload
        payload = {
            "model": self.llm_service.model,
            "messages": messages,
            "temperature": 0.7,
            "stream": True,
        }

        # 千问3特殊处理：禁用思考模式
        if self.llm_service.provider == "qwen":
            payload["enable_thinking"] = False

        logger.info(f"[Planner] 开始流式生成用户答案，prompt长度: {len(prompt)}")
        chunk_count = 0
        total_length = 0

        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line:
                            continue

                        # OpenAI / Qwen 兼容接口使用 "data: {...}" 和 "data: [DONE]" 形式
                        if line.startswith("data: "):
                            data_str = line[len("data: ") :].strip()
                            if data_str == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data_str)
                            except Exception:
                                # 非法 JSON 片段直接跳过
                                continue

                            # 兼容不同provider的流式返回格式
                            choices = chunk.get("choices")
                            if not isinstance(choices, list) or not choices:
                                continue

                            first_choice = choices[0]
                            if not isinstance(first_choice, dict):
                                continue

                            # 提取内容片段
                            delta = first_choice.get("delta") or first_choice.get("message") or {}
                            piece = delta.get("content") or ""
                            if piece:
                                chunk_count += 1
                                total_length += len(piece)
                                # 每50个chunk输出一次日志
                                if chunk_count % 50 == 0:
                                    logger.info(f"[Planner] 流式生成进度: {chunk_count} chunks, {total_length} 字符")
                                yield piece

            logger.info(f"[Planner] 流式生成完成: {chunk_count} chunks, {total_length} 字符")

        except Exception as e:
            logger.error(f"[Planner] 流式生成失败: {e}")
            # 如果流式生成失败，返回错误信息
            yield f"\n\n[生成失败: {str(e)}]"
