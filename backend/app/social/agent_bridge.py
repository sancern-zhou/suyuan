"""Agent bridge for connecting message bus with ReActAgent.

⚠️ 注意：默认使用social模式（移动端呼吸式Agent）
"""

import asyncio
from typing import Optional, List, Dict, Any

import structlog

from app.agent.react_agent import ReActAgent
from app.social.events import InboundMessage, OutboundMessage
from app.social.message_bus import MessageBus
from app.social.session_mapper import SessionMapper
from app.social.heartbeat_service import HeartbeatService
from app.social.memory_store import MemoryStore

logger = structlog.get_logger(__name__)


class AgentBridge:
    """
    Bridges the MessageBus with ReActAgent for social platform integration.

    Responsibilities:
    - Consume inbound messages from MessageBus
    - Route to appropriate ReActAgent session
    - Aggregate streaming events into final response
    - Publish outbound messages to MessageBus
    - Manage heartbeat service (social mode)
    - Manage memory store (social mode)

    Event aggregation strategy:
    - Collect all streaming_text events
    - Extract tool call progress from agent_action events
    - Generate final Markdown summary from complete event
    - Support streaming output (social mode)
    """

    def __init__(
        self,
        message_bus: MessageBus,
        agent: ReActAgent,
        session_mapper: SessionMapper,
        mode: str = "social",  # ⚠️ 默认使用social模式
        enable_heartbeat: bool = True,  # 是否启用心跳服务
        enable_memory: bool = True  # 是否启用记忆存储
    ):
        """
        Initialize the agent bridge.

        Args:
            message_bus: Message bus for communication
            agent: ReActAgent instance
            session_mapper: Session mapper for user-to-session mapping
            mode: Agent mode ("social"=社交模式, "query"=问数模式, "assistant"=助手, "expert"=专家, "report"=报告)
            enable_heartbeat: 是否启用心跳服务（仅social模式）
            enable_memory: 是否启用记忆存储（仅social模式）
        """
        self.message_bus = message_bus
        self.agent = agent
        self.session_mapper = session_mapper
        self.mode = mode
        self.enable_heartbeat = enable_heartbeat
        self.enable_memory = enable_memory

        self._running = False
        self._consume_task: Optional[asyncio.Task] = None

        # ✅ 新增：心跳服务（social模式）
        self.heartbeat: Optional[HeartbeatService] = None
        if enable_heartbeat and mode == "social":
            self.heartbeat = HeartbeatService(
                interval_s=30 * 60,  # 30分钟
                on_execute=self._on_heartbeat_execute,
                on_notify=self._on_heartbeat_notify
            )
            logger.info("heartbeat_service_initialized")

        # ✅ 新增：记忆存储（social模式）
        self.memory: Optional[MemoryStore] = None
        if enable_memory and mode == "social":
            self.memory = MemoryStore()
            logger.info("memory_store_initialized")

    async def start(self) -> None:
        """Start consuming inbound messages and processing them."""
        if self._running:
            logger.warning("AgentBridge already running")
            return

        self._running = True
        self._consume_task = asyncio.create_task(self._consume_loop())

        # ✅ 启动心跳服务（social模式）
        if self.heartbeat:
            asyncio.create_task(self.heartbeat.start())

        logger.info("AgentBridge started", mode=self.mode)

    async def stop(self) -> None:
        """Stop consuming messages."""
        self._running = False

        if self._consume_task:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass

        # ✅ 停止心跳服务
        if self.heartbeat:
            await self.heartbeat.stop()

        logger.info("AgentBridge stopped")

    async def _consume_loop(self) -> None:
        """Main consumption loop."""
        logger.info("AgentBridge consume loop started", running=self._running)
        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.message_bus.consume_inbound(),
                    timeout=1.0
                )
                logger.info("Message received from bus",
                           channel=msg.channel,
                           sender_id=msg.sender_id,
                           content_preview=msg.content[:50])
                await self._process_message(msg)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("AgentBridge consume loop cancelled")
                break
            except Exception as e:
                logger.error("Error processing inbound message",
                           channel=msg.channel if 'msg' in locals() else 'unknown',
                           sender_id=msg.sender_id if 'msg' in locals() else 'unknown',
                           error=str(e),
                           exc_info=True)

    async def _process_message(self, msg: InboundMessage) -> None:
        """
        Process an inbound message through the agent.

        Args:
            msg: Inbound message from social platform
        """
        try:
            logger.info("Starting to process message",
                       channel=msg.channel,
                       sender_id=msg.sender_id,
                       content_length=len(msg.content))

            # Get or create agent session
            session_id = await self.session_mapper.get_or_create_session(
                f"{msg.channel}:{msg.sender_id}"
            )

            logger.info("Session obtained",
                       channel=msg.channel,
                       sender_id=msg.sender_id,
                       session_id=session_id,
                       mode=self.mode)

            # ✅ 加载记忆上下文（social模式）
            memory_context = ""
            if self.memory and self.mode == "social":
                memory_context = self.memory.get_memory_context()
                logger.debug("memory_context_loaded",
                           length=len(memory_context))

            # Aggregate events from agent
            logger.info("Calling agent.analyze",
                       session_id=session_id,
                       content_preview=msg.content[:100])

            final_answer = await self._aggregate_agent_events(
                content=msg.content,
                session_id=session_id,
                chat_id=msg.chat_id,
                memory_context=memory_context  # ✅ 传递记忆上下文
            )

            logger.info("Agent analysis completed",
                       session_id=session_id,
                       response_length=len(final_answer) if final_answer else 0)

            # ✅ 整合到记忆（social模式）
            if self.memory and self.mode == "social":
                # TODO: 收集对话历史并整合
                pass

            # ✅ 提取图片URL和文档路径
            media_files = self._extract_media_files(final_answer)

            # ✅ 清理内容中的媒体文件引用（去除Markdown语法）
            cleaned_answer = self._clean_media_references(final_answer)

            # Publish outbound response
            outbound_msg = OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=cleaned_answer,  # ✅ 使用清理后的内容
                reply_to=msg.sender_id,
                media=media_files  # ✅ 添加媒体文件列表
            )

            await self.message_bus.publish_outbound(outbound_msg)

            logger.info("Response sent",
                       channel=msg.channel,
                       chat_id=msg.chat_id,
                       session_id=session_id)

        except Exception as e:
            logger.error("Error in _process_message",
                        channel=msg.channel,
                        sender_id=msg.sender_id,
                        error=str(e),
                        exc_info=True)

            # Send error message to user
            error_msg = OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=f"处理请求时出错: {str(e)}",
                reply_to=msg.sender_id
            )
            await self.message_bus.publish_outbound(error_msg)

    async def _aggregate_agent_events(
        self,
        content: str,
        session_id: str,
        chat_id: str,
        memory_context: str = ""
    ) -> str:
        """
        Aggregate streaming events from ReActAgent into final response.

        Args:
            content: User query
            session_id: Agent session ID
            chat_id: Chat ID for progress tracking
            memory_context: Memory context (social mode)

        Returns:
            Aggregated final response in Markdown format
        """
        events_buffer = []
        streaming_text_parts = []
        tool_calls = []
        stream_segments = []  # ✅ 流式输出分段
        current_buffer = []  # ✅ 当前缓冲区

        try:
            # ✅ 增强查询（携带记忆上下文）
            enhanced_query = content
            if memory_context:
                enhanced_query = f"{memory_context}\n\n用户问题：{content}"

            # Call agent and collect events
            async for event in self.agent.analyze(
                user_query=enhanced_query,  # ✅ 使用增强查询
                session_id=session_id,
                manual_mode=self.mode
            ):
                events_buffer.append(event)

                # Process different event types
                event_type = event.get("type", "")

                if event_type == "streaming_text":
                    # Accumulate streaming text
                    data = event.get("data", {})

                    # Handle different data formats
                    if isinstance(data, dict):
                        # New format: {"chunk": "...", "is_complete": false}
                        chunk = data.get("chunk", "")
                        if isinstance(chunk, str):
                            streaming_text_parts.append(chunk)
                        else:
                            streaming_text_parts.append(str(chunk))
                    elif isinstance(data, str):
                        # Legacy format: data is directly a string
                        streaming_text_parts.append(data)
                    else:
                        # Fallback: convert to string
                        streaming_text_parts.append(str(data))

                    # ✅ 流式输出支持（social模式）
                    if self.mode == "social":
                        current_buffer.append(streaming_text_parts[-1])

                        # 每500字或5个chunk发送一次中间结果
                        if len("".join(current_buffer)) > 500 or len(current_buffer) >= 5:
                            await self._send_stream_chunk(
                                chat_id=chat_id,
                                content="".join(current_buffer),
                                segment_id=len(stream_segments),
                                resuming=True
                            )
                            stream_segments.append("".join(current_buffer))
                            current_buffer = []

                elif event_type == "agent_action":
                    # Track tool calls for progress reporting
                    action = event.get("data", {})
                    tool_name = action.get("tool", "")
                    tool_calls.append(tool_name)

                elif event_type == "complete":
                    # Extract final answer
                    final_data = event.get("data", {})
                    if isinstance(final_data, dict):
                        final_answer = final_data.get("final_answer", "")
                        if final_answer:
                            return final_answer

                elif event_type == "error":
                    # Handle error events
                    error_data = event.get("data", {})
                    error_msg = error_data.get("error", "Unknown error")
                    logger.warning("Agent error event", error=error_msg)
                    return f"处理查询时出错: {error_msg}"

            # If no complete event, aggregate streaming text
            if streaming_text_parts:
                # Filter out non-string items
                text_parts = [part for part in streaming_text_parts if isinstance(part, str)]
                if text_parts:
                    full_text = "".join(text_parts)
                else:
                    full_text = str(streaming_text_parts)

                # Add tool call summary if available
                if tool_calls:
                    tool_summary = f"\n\n**使用的工具**: {', '.join(set(tool_calls))}"
                    full_text += tool_summary

                return full_text

            # Fallback: extract content from last event
            if events_buffer:
                last_event = events_buffer[-1]
                data = last_event.get("data", {})
                if isinstance(data, str):
                    return data
                elif isinstance(data, dict):
                    return data.get("content", str(data))

            return "抱歉，未能生成回复。"

        except Exception as e:
            logger.error("Error aggregating agent events",
                        session_id=session_id,
                        error=str(e),
                        exc_info=True)
            return f"处理请求时出错: {str(e)}"

    def _extract_media_files(self, content: str) -> list[str]:
        """
        从Agent返回内容中提取图片URL和文档路径

        Args:
            content: Agent返回的内容

        Returns:
            媒体文件路径列表（图片URL、本地文档路径等）
        """
        import re
        from pathlib import Path

        media_files = []

        # 1. 提取图片URL（/api/image/{image_id}）
        image_pattern = r'\[.*?\]\(/api/image/([a-zA-Z0-9_-]+)\)'
        for match in re.finditer(image_pattern, content):
            image_id = match.group(1)
            # 转换为实际文件路径
            image_path = f"backend_data_registry/images/{image_id}.png"
            if Path(image_path).exists():
                media_files.append(image_path)
                logger.debug("image_extracted", image_id=image_id, path=image_path)

        # 2. 提取本地文档路径
        # 匹配常见文档格式：.docx, .xlsx, .pptx, .pdf
        doc_pattern = r'([a-zA-Z0-9_/\-\.]+\.(docx|xlsx|pptx|pdf))'
        for match in re.finditer(doc_pattern, content):
            doc_path = match.group(1)
            if Path(doc_path).exists():
                media_files.append(doc_path)
                logger.debug("document_extracted", path=doc_path)

        logger.info("media_files_extracted", count=len(media_files), files=media_files)
        return media_files

    def _clean_media_references(self, content: str) -> str:
        """
        清理内容中的媒体文件引用，替换为友好的文本描述

        Args:
            content: 原始内容

        Returns:
            清理后的内容
        """
        import re

        # 1. 清理Markdown图片语法 ![alt](url)
        def replace_image_markdown(match):
            alt_text = match.group(1)  # 图片描述
            return f"\n[图片：{alt_text}]\n"

        content = re.sub(r'!\[([^\]]+)\]\([^\)]+\)', replace_image_markdown, content)

        # 2. 清理裸露的图片URL（/api/image/xxx）
        content = re.sub(r'\(/api/image/[a-zA-Z0-9_-]+\)', '', content)

        # 3. 清理文档路径（避免显示完整路径）
        def replace_doc_path(match):
            filename = Path(match.group(1)).name
            return f"\n[文件：{filename}]\n"

        content = re.sub(r'\([a-zA-Z0-9_/\-\.]+\.(docx|xlsx|pptx|pdf)\)', replace_doc_path, content)

        # 4. 清理多余的空行
        content = re.sub(r'\n{3,}', '\n\n', content)

        return content.strip()

    async def _send_stream_chunk(
        self,
        chat_id: str,
        content: str,
        segment_id: int,
        resuming: bool = False
    ) -> None:
        """
        发送流式片段

        Args:
            chat_id: Chat ID
            content: 内容片段
            segment_id: 片段ID
            resuming: 是否为中间片段
        """
        # TODO: 实现流式输出逻辑
        # 目前只记录日志，实际发送需要通过MessageBus
        logger.debug(
            "stream_chunk",
            chat_id=chat_id,
            segment_id=segment_id,
            length=len(content),
            resuming=resuming
        )

    async def _on_heartbeat_execute(self, tasks: list) -> dict:
        """
        心跳执行回调：执行HEARTBEAT.md中的任务

        Args:
            tasks: 任务列表

        Returns:
            执行结果
        """
        logger.info("heartbeat_execute_callback", task_count=len(tasks))

        # TODO: 实现任务执行逻辑
        # 可以调用Agent来执行任务
        return {
            "should_notify": False,
            "summary": f"执行了 {len(tasks)} 个任务"
        }

    async def _on_heartbeat_notify(self, response: dict) -> None:
        """
        心跳通知回调：主动推送结果

        Args:
            response: 执行结果
        """
        logger.info("heartbeat_notify_callback", summary=response.get("summary"))

        # TODO: 实现通知发送逻辑
        # 可以通过MessageBus发送通知到所有订阅用户

    async def send_message(
        self,
        channel: str,
        chat_id: str,
        content: str,
        sender_id: Optional[str] = None
    ) -> None:
        """
        Send a message to a social platform.

        Args:
            channel: Channel name (qq, weixin, etc.)
            chat_id: Chat ID
            content: Message content
            sender_id: Optional sender ID for reply
        """
        msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=content,
            reply_to=sender_id
        )

        await self.message_bus.publish_outbound(msg)
