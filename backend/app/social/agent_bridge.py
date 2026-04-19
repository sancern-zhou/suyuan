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
from app.social.task_status_store import TaskStatusStore
from app.social.user_preferences import UserPreferences

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

        # ✅ 替换全局 HeartbeatService 为 UserHeartbeatManager
        from app.social.user_heartbeat_manager import UserHeartbeatManager
        from app.social.user_heartbeat_singleton import set_user_heartbeat_manager

        self.user_heartbeat_manager: Optional[UserHeartbeatManager] = None
        if enable_heartbeat and mode == "social":
            self.user_heartbeat_manager = UserHeartbeatManager(
                on_execute_callback=self._on_heartbeat_execute,
                on_notify_callback=self._on_heartbeat_notify
            )
            # 设置全局单例，供工具使用
            set_user_heartbeat_manager(self.user_heartbeat_manager)
            logger.info("user_heartbeat_manager_initialized")

        # ✅ 替换全局 MemoryStore 为 UserMemoryManager
        from app.social.user_memory_manager import UserMemoryManager

        self.user_memory_manager: Optional[UserMemoryManager] = None
        if enable_memory and mode == "social":
            self.user_memory_manager = UserMemoryManager()
            logger.info("user_memory_manager_initialized")

        # ✅ 新增：SubagentManager（后台任务管理）
        from app.social.subagent_manager import SubagentManager
        from app.social.subagent_singleton import set_subagent_manager

        self.subagent_manager: Optional[SubagentManager] = None
        if mode == "social":
            self.task_status_store = TaskStatusStore(db_manager=None)  # JSON storage
            self.subagent_manager = SubagentManager(
                agent=self.agent,
                task_store=self.task_status_store,
                message_bus=message_bus
            )
            # 设置全局单例，供工具使用
            set_subagent_manager(self.subagent_manager)
            logger.info("subagent_manager_initialized")

        # ✅ 新增：Channel 映射（用于获取机器人账号）
        self._channel_map: Dict[str, "BaseChannel"] = {}

    async def start(self) -> None:
        """Start consuming inbound messages and processing them."""
        if self._running:
            logger.warning("AgentBridge already running")
            return

        self._running = True
        self._consume_task = asyncio.create_task(self._consume_loop())

        # ✅ UserHeartbeatManager 不需要全局启动，每个用户独立启动

        # ✅ 启动 SubagentManager
        if self.subagent_manager:
            await self.subagent_manager.start()

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

        # ✅ 停止所有用户心跳服务
        if self.user_heartbeat_manager:
            await self.user_heartbeat_manager.shutdown()

        # ✅ 停止 SubagentManager
        if self.subagent_manager:
            await self.subagent_manager.shutdown()

        logger.info("AgentBridge stopped")

    def register_channel(self, channel: "BaseChannel") -> None:
        """
        注册渠道（用于获取机器人账号）

        Args:
            channel: 渠道实例
        """
        from app.channels.base import BaseChannel

        if not isinstance(channel, BaseChannel):
            logger.warning("invalid_channel_type", type=type(channel))
            return

        self._channel_map[channel.name] = channel
        logger.info("channel_registered", channel_name=channel.name)

    async def _get_bot_account(self, channel_name: str) -> str:
        """
        获取机器人账号

        Args:
            channel_name: 渠道名称

        Returns:
            机器人账号（如 wxid_abc）
        """
        channel = self._channel_map.get(channel_name)
        if channel:
            return channel.bot_account
        return "default"

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

            # ✅ 获取机器人账号并构建用户ID
            bot_account = await self._get_bot_account(msg.channel)
            social_user_id = f"{msg.channel}:{bot_account}:{msg.sender_id}"

            # Get or create agent session（传递模式参数）
            session_id = await self.session_mapper.get_or_create_session(social_user_id, mode=self.mode)

            logger.info("Session obtained",
                       channel=msg.channel,
                       sender_id=msg.sender_id,
                       bot_account=bot_account,
                       session_id=session_id,
                       chat_id=msg.chat_id,
                       mode=self.mode)

            # ✅ 设置全局 chat_id 和 channel（用于工具访问）
            from app.social.message_bus_singleton import set_current_chat_id, set_current_channel
            set_current_chat_id(msg.chat_id)
            set_current_channel(msg.channel)
            logger.debug("current_context_set", chat_id=msg.chat_id, channel=msg.channel)

            # ✅ 启动用户心跳服务（social模式）
            if self.user_heartbeat_manager and self.mode == "social":
                heartbeat = await self.user_heartbeat_manager.get_user_heartbeat(social_user_id)
                logger.debug("user_heartbeat_started", user_id=social_user_id)

            # ✅ 记忆上下文由 react_agent.py 通过 social_memory_store 管理，此处不再加载
            # （避免双重注入：之前是 agent_bridge 拼接到 query + react_agent 注入到系统提示词）
            user_preferences = None

            # ✅ 加载 soul.md 和 USER.md（social模式）
            # Agent 将自主管理这些文件，检测到 soul.md 为空时会引导用户
            social_soul_file_path = None
            social_user_file_path = None
            social_soul_context = None
            social_user_context = None
            if self.mode == "social":
                preferences_manager = UserPreferences(social_user_id)

                # 获取文件路径
                social_soul_file_path = str(preferences_manager.soul_file) if preferences_manager.soul_file else None
                social_user_file_path = str(preferences_manager.user_file) if preferences_manager.user_file else None

                # 加载 soul.md（助理灵魂档案，Agent 自主管理）
                social_soul_context = preferences_manager.load_soul_md()
                has_soul = len(social_soul_context.strip()) > 0 if social_soul_context else False

                # 加载 USER.md（用户档案，Agent 自主管理）
                social_user_context = preferences_manager.load_user_md()

                logger.info(
                    "soul_and_user_context_loaded",
                    user_id=social_user_id,
                    soul_file_path=social_soul_file_path,
                    user_file_path=social_user_file_path,
                    has_soul=has_soul,
                    soul_length=len(social_soul_context) if social_soul_context else 0,
                    has_user_context=social_user_context is not None,
                    user_context_length=len(social_user_context) if social_user_context else 0
                )

            # Aggregate events from agent
            logger.info("Calling agent.analyze",
                       session_id=session_id,
                       content_preview=msg.content[:100])

            # ✅ 获取用户隔离的memory_store和用户偏好（社交模式专用）
            social_memory_store = None
            social_user_prefs = None
            social_user_context = None  # ✅ 新增：用户上下文（USER.md内容）
            if self.user_memory_manager and self.mode == "social":
                social_memory_store = await self.user_memory_manager.get_user_memory(social_user_id)

                # ✅ 加载USER.md内容（用户档案）
                social_user_context = preferences_manager.load_user_md() if self.mode == "social" else None
                logger.debug(
                    "user_context_loaded",
                    user_id=social_user_id,
                    has_context=social_user_context is not None,
                    context_length=len(social_user_context) if social_user_context else 0
                )

            # ✅ 获取用户偏好（用于动态提示词）
            if self.mode == "social" and user_preferences:
                social_user_prefs = user_preferences

            final_answer = await self._aggregate_agent_events(
                content=msg.content,
                session_id=session_id,
                chat_id=msg.chat_id,
                channel=msg.channel,  # ✅ 传递渠道信息
                social_user_id=social_user_id if self.mode == "social" else None,  # ✅ 传递用户标识
                social_memory_store=social_memory_store,  # ✅ 传递用户隔离的memory_store
                social_user_preferences=social_user_prefs,  # ✅ 传递用户偏好
                social_soul_file_path=social_soul_file_path,  # ✅ 传递 soul.md 文件路径
                social_user_file_path=social_user_file_path,  # ✅ 传递 USER.md 文件路径
                social_soul_context=social_soul_context,  # ✅ 传递 soul.md 内容
                social_user_context=social_user_context  # ✅ 传递 USER.md 内容
            )

            logger.info("Agent analysis completed",
                       session_id=session_id,
                       response_length=len(final_answer) if final_answer else 0)

            # ✅ 整合到用户专属记忆（social模式）
            if self.user_memory_manager and self.mode == "social":
                # 收集本次对话消息
                from datetime import datetime
                messages = [
                    {"role": "user", "content": msg.content, "timestamp": datetime.now().isoformat()},
                    {"role": "assistant", "content": final_answer, "timestamp": datetime.now().isoformat()}
                ]

                # 执行整合（内部会检查触发条件）
                await self._check_and_consolidate_memory(session_id, social_user_id)

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
        channel: str = None,  # ✅ 新增：渠道信息
        memory_context: str = "",  # ⚠️ 保留参数兼容但不再使用（记忆由react_agent通过social_memory_store注入）
        social_user_id: str = None,  # ✅ 新增：社交用户标识
        social_memory_store = None,  # ✅ 新增：社交模式用户隔离的memory_store
        social_user_preferences: dict = None,  # ✅ 新增：社交模式用户偏好（用于动态提示词）
        social_soul_file_path: str = None,  # ✅ 新增：社交模式 soul.md 文件路径
        social_user_file_path: str = None,  # ✅ 新增：社交模式 USER.md 文件路径
        social_soul_context: str = None,  # ✅ 新增：社交模式 soul.md 内容（助理灵魂档案）
        social_user_context: str = None  # ✅ 新增：社交模式 USER.md 内容（用户档案）
    ) -> str:
        """
        Aggregate streaming events from ReActAgent into final response.

        Args:
            content: User query
            session_id: Agent session ID
            chat_id: Chat ID for progress tracking
            channel: Channel name (weixin/qq/dingtalk/wecom)
            memory_context: ⚠️ 保留兼容但不再使用（记忆由react_agent通过social_memory_store注入）
            social_user_id: Social platform user ID (for social mode memory isolation)
            social_memory_store: 社交模式用户隔离的memory_store（由agent_bridge传入）
            social_user_preferences: 社交模式用户偏好配置（用于动态提示词）
            social_soul_file_path: 社交模式 soul.md 文件路径（由agent_bridge传入）
            social_user_file_path: 社交模式 USER.md 文件路径（由agent_bridge传入）
            social_soul_context: 社交模式 soul.md 内容（助理灵魂档案，由agent_bridge传入）
            social_user_context: 社交模式 USER.md 内容（用户档案，由agent_bridge传入）

        Returns:
            Aggregated final response in Markdown format
        """
        events_buffer = []
        streaming_text_parts = []
        tool_calls = []
        stream_segments = []  # ✅ 流式输出分段
        current_buffer = []  # ✅ 当前缓冲区

        try:
            # ✅ 记忆上下文由 react_agent.py 通过 social_memory_store 注入到系统提示词
            # 不再在 query 中拼接记忆（避免双重注入）

            # Call agent and collect events
            async for event in self.agent.analyze(
                user_query=content,  # ✅ 直接使用原始查询（记忆由react_agent通过social_memory_store管理）
                session_id=session_id,
                manual_mode=self.mode,
                user_identifier=social_user_id if self.mode == "social" else None,  # ✅ 传递用户标识
                social_memory_store=social_memory_store if self.mode == "social" else None,  # ✅ 传递用户隔离的memory_store
                social_user_preferences=social_user_preferences if self.mode == "social" else None,  # ✅ 传递用户偏好
                social_soul_file_path=social_soul_file_path if self.mode == "social" else None,  # ✅ 传递 soul.md 文件路径
                social_user_file_path=social_user_file_path if self.mode == "social" else None,  # ✅ 传递 USER.md 文件路径
                social_soul_context=social_soul_context if self.mode == "social" else None,  # ✅ 传递 soul.md 内容
                social_user_context=social_user_context if self.mode == "social" else None  # ✅ 传递 USER.md 内容
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
                    # Extract final answer (loop.py returns "answer" field)
                    final_data = event.get("data", {})
                    if isinstance(final_data, dict):
                        final_answer = final_data.get("answer", "")
                        if final_answer:
                            return final_answer

                elif event_type == "error":
                    # Handle error events
                    error_data = event.get("data", {})
                    error_msg = error_data.get("error", "Unknown error")
                    logger.warning("Agent error event", error=error_msg)
                    return f"处理查询时出错: {error_msg}"

                elif event_type == "fatal_error":
                    # Handle fatal error events
                    error_data = event.get("data", {})
                    if isinstance(error_data, dict):
                        error_msg = error_data.get("error", "未知错误")
                        logger.error("Agent fatal error event", error=error_msg)
                        return f"⚠️ 系统遇到错误：{error_msg}\n\n请稍后重试或联系技术支持。"

                    return "⚠️ 系统遇到错误，请稍后重试。"

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
        from app.services.image_cache import get_image_cache

        media_files = []

        logger.debug("extracting_media_files_start",
                    content_length=len(content),
                    content_preview=content[:200])

        # 1. 提取图片URL（/api/image/{image_id}）
        # 支持 Markdown 图片语法：![描述](/api/image/xxx) 和普通链接：[描述](/api/image/xxx)
        image_pattern = r'!?\[.*?\]\(/api/image/([a-zA-Z0-9_-]+)\)'
        matches = list(re.finditer(image_pattern, content))
        logger.debug("image_pattern_matches", count=len(matches))

        for match in matches:
            image_id = match.group(1)
            # 使用 ImageCache 获取正确的缓存目录（绝对路径）
            cache = get_image_cache()
            image_path = f"{cache.cache_dir}/{image_id}.png"
            logger.debug("checking_image_file",
                        image_id=image_id,
                        image_path=image_path,
                        exists=Path(image_path).exists())
            if Path(image_path).exists():
                media_files.append(image_path)
                logger.info("image_extracted", image_id=image_id, path=image_path)
            else:
                logger.warning("image_file_not_found",
                             image_id=image_id,
                             expected_path=image_path,
                             cache_dir=cache.cache_dir)

        # 2. 提取本地文档路径
        # 匹配常见文档格式：.docx, .xlsx, .pptx, .pdf, .md（支持 Office 文档和 Markdown）
        doc_pattern = r'([a-zA-Z0-9_/\-\.]+\.(docx|xlsx|pptx|pdf|md))'
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

        content = re.sub(r'\([a-zA-Z0-9_/\-\.]+\.(docx|xlsx|pptx|pdf|md)\)', replace_doc_path, content)

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

    async def _check_and_consolidate_memory(
        self,
        session_id: str,
        social_user_id: str
    ) -> bool:
        """
        检查并执行记忆整合

        触发条件：
        1. Session 历史 token 数超过 80% 上下文窗口
        2. 距离上次整合超过 10 条消息

        Returns:
            是否执行了整合
        """
        from app.utils.token_budget import token_budget_manager

        # 1. 获取 session 历史
        session_data = self.agent._session_store.get(session_id)
        if not session_data:
            return False

        memory_manager = session_data.get("memory")
        if not memory_manager:
            return False

        messages = memory_manager.session.get_messages_for_llm()

        # 2. 计算 token 数
        total_tokens = 0
        for msg in messages:
            total_tokens += token_budget_manager.count_tokens(msg.get("content", ""))

        # 3. 获取 session 映射信息
        mapping = await self.session_mapper.get_mapping_info(social_user_id)
        if not mapping:
            return False

        last_offset = mapping.get("last_consolidated_offset", 0)
        new_message_count = len(messages) - last_offset

        # 4. 触发条件检查
        max_tokens = int(token_budget_manager.max_context_tokens * 0.8)
        should_consolidate = (
            total_tokens > max_tokens or  # Token 超限
            new_message_count >= 20  # 新增 20 条以上消息（从10调整为20，约5-8轮对话）
        )

        if should_consolidate and new_message_count > 0:
            logger.info(
                "memory_consolidation_triggered",
                session_id=session_id,
                social_user_id=social_user_id,
                total_tokens=total_tokens,
                max_tokens=max_tokens,
                new_message_count=new_message_count,
                last_offset=last_offset
            )

            # 5. 执行整合
            await self._consolidate_session_memory(
                session_id=session_id,
                social_user_id=social_user_id,
                messages=messages,
                start_offset=last_offset
            )

            return True

        return False

    async def _consolidate_session_memory(
        self,
        session_id: str,
        social_user_id: str,
        messages: List[Dict[str, Any]],
        start_offset: int
    ) -> None:
        """
        执行 session 记忆整合（使用 ReAct Agent 循环方式）

        与非社交模式统一：通过 remember_fact/replace_memory/remove_memory 工具
        逐步更新记忆，避免单次 LLM 调用失败导致记忆被清空。

        Args:
            session_id: Session ID
            social_user_id: 社交平台用户ID
            messages: 完整消息列表
            start_offset: 起始偏移量
        """
        from app.social.memory_store import ImprovedMemoryStore
        from app.tools.social.remember_fact.tool import RememberFactTool
        from app.tools.social.replace_memory.tool import ReplaceMemoryTool
        from app.tools.social.remove_memory.tool import RemoveMemoryTool
        from pathlib import Path
        from datetime import datetime

        try:
            # 1. 获取现有记忆内容和文件路径
            social_workspace = Path("/home/xckj/suyuan/backend_data_registry/social/memory")
            memory_store = ImprovedMemoryStore(user_id=social_user_id, workspace=social_workspace)

            existing_memory = memory_store.read_long_term()
            memory_file_path = str(memory_store.memory_file.resolve()) if memory_store.memory_file.exists() else ""

            # 2. 提取要合并的消息（从 start_offset 开始）
            messages_to_consolidate = messages[start_offset:] if start_offset > 0 else messages

            if not messages_to_consolidate:
                logger.debug("no_messages_to_consolidate", session_id=session_id, start_offset=start_offset)
                return

            # 3. 添加时间戳（如果没有）
            for msg in messages_to_consolidate:
                if "timestamp" not in msg:
                    msg["timestamp"] = datetime.now().isoformat()

            # 4. 构建整合提示词
            consolidation_prompt = self._build_social_consolidation_prompt(
                messages=messages_to_consolidate,
                existing_memory=existing_memory,
                memory_file_path=memory_file_path
            )

            # 5. 设置记忆工具上下文（社交模式用户隔离）
            safe_user_id = social_user_id.replace(":", "_")
            RememberFactTool.set_memory_context("social", safe_user_id)
            ReplaceMemoryTool.set_memory_context("social", safe_user_id)
            RemoveMemoryTool.set_memory_context("social", safe_user_id)

            # 6. 创建记忆整合 Agent 并执行
            from app.agent.memory_consolidator_factory import create_memory_consolidator_agent
            consolidator_agent = create_memory_consolidator_agent()

            async for event in consolidator_agent.analyze(
                user_query=consolidation_prompt,
                session_id=f"{session_id}_consolidation",
                manual_mode="memory_consolidator"
            ):
                if event.get("type") == "complete":
                    # 更新 session 映射偏移量
                    await self.session_mapper.update_consolidation_offset(
                        social_user_id=social_user_id,
                        new_offset=len(messages),
                        total_count=len(messages)
                    )

                    logger.info(
                        "memory_consolidation_completed",
                        session_id=session_id,
                        social_user_id=social_user_id,
                        old_offset=start_offset,
                        new_offset=len(messages),
                        method="react_agent"
                    )
                    break
                elif event.get("type") == "error":
                    logger.warning(
                        "memory_consolidation_failed",
                        session_id=session_id,
                        social_user_id=social_user_id,
                        error=event.get("data", {}).get("error")
                    )
                    break

        except Exception as e:
            logger.exception(
                "memory_consolidation_error",
                session_id=session_id,
                social_user_id=social_user_id,
                error=str(e)
            )
        finally:
            # 7. 清除记忆工具上下文
            try:
                RememberFactTool.clear_memory_context()
                ReplaceMemoryTool.clear_memory_context()
                RemoveMemoryTool.clear_memory_context()
            except Exception as e:
                logger.warning("failed_to_clear_memory_context", error=str(e))

    def _build_social_consolidation_prompt(
        self,
        messages: List[Dict[str, Any]],
        existing_memory: str = "",
        memory_file_path: str = ""
    ) -> str:
        """
        构建社交模式记忆整合提示词

        Args:
            messages: 消息列表
            existing_memory: 现有记忆内容
            memory_file_path: 记忆文件路径

        Returns:
            整合提示词
        """
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages[-10:]  # 只使用最近10条
        ])

        # 计算记忆文件字符数
        current_size = len(existing_memory) if existing_memory else 0
        max_size = 3000
        size_info = f"（{current_size}/{max_size}字符，使用率{current_size/max_size*100:.1f}%）"

        prompt_parts = [
            "请分析以下对话内容，提取重要信息并更新长期记忆。",
            "",
            "## 模式",
            "social",
            ""
        ]

        # 添加现有记忆内容
        if existing_memory and existing_memory.strip():
            prompt_parts.extend([
                "## 现有记忆",
                f"**当前记忆大小**：{size_info}",
                "",
                "```",
                existing_memory,
                "```",
                "",
                "**⚠️ 重要限制**：",
                f"- 记忆文件上限：{max_size}字符",
                f"- 当前使用：{current_size}字符（{current_size/max_size*100:.1f}%）",
                "- 当接近上限（>80%）时，优先使用 remove_memory 删除旧内容",
                "- 当已满（100%）时，必须先删除才能添加新内容",
                ""
            ])
        else:
            prompt_parts.extend([
                "## 现有记忆",
                "**当前记忆大小**：0/3000字符（0.0%）",
                "",
                "记忆文件为空，可以开始添加记忆。",
                ""
            ])

        # 添加记忆文件路径
        if memory_file_path:
            prompt_parts.extend([
                "## 记忆文件路径",
                memory_file_path,
                ""
            ])

        # 添加对话内容和任务
        prompt_parts.extend([
            "## 对话内容",
            conversation_text,
            "",
            "**任务**：",
            "1. 阅读现有记忆，了解已记住的内容",
            "2. 分析对话内容，识别需要记住的新信息",
            "3. 使用工具更新记忆：",
            "   - remember_fact: 添加新记忆",
            "   - replace_memory: 替换现有记忆",
            "   - remove_memory: 删除过时记忆",
            "",
            "**⚠️ 记忆管理策略**（基于字符限制）：",
            f"- 当记忆使用率 < 80%：可以正常添加新记忆",
            f"- 当记忆使用率 >= 80%：优先删除临时、过时或低优先级的记忆",
            f"- 当记忆使用率 = 100%：必须先删除才能添加",
            "",
            "**注意事项**：",
            "- 避免重复记忆（先检查现有记忆）",
            "- 更新偏好设置时使用replace_memory",
            "- 删除临时或错误记忆时使用remove_memory",
            "- 优先保留高价值信息（用户偏好 > 领域知识 > 历史结论）",
            "- 记忆文件路径已在上方提供，工具会自动使用"
        ])

        return "\n".join(prompt_parts)

    async def _on_heartbeat_execute(self, tasks: list, user_id: str) -> dict:
        """
        心跳执行回调：执行HEARTBEAT.md中的任务

        Args:
            tasks: 任务列表
            user_id: 用户ID

        Returns:
            执行结果
        """
        from datetime import datetime

        logger.info("heartbeat_execute_callback", task_count=len(tasks), user_id=user_id)

        if not tasks:
            return {"should_notify": False, "summary": "无任务执行"}

        # 构建任务描述
        task_description = "\n".join([
            f"- {task.get('name', '未知任务')}: {task.get('description', '')}"
            for task in tasks
        ])

        # 调用 Agent 执行任务
        try:
            # 使用特殊的 session_id
            heartbeat_session_id = f"heartbeat_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # 构建查询
            query = f"""请执行以下定时任务：

{task_description}

请逐个执行这些任务，并返回执行结果。"""

            # 调用 Agent
            events = []
            async for event in self.agent.analyze(
                user_query=query,
                session_id=heartbeat_session_id,
                manual_mode=self.mode
            ):
                events.append(event)

                # 提取最终答案
                if event.get("type") == "complete":
                    final_data = event.get("data", {})
                    final_answer = final_data.get("final_answer", "")

                    return {
                        "should_notify": True,
                        "summary": final_answer or f"执行了 {len(tasks)} 个任务"
                    }

            return {"should_notify": False, "summary": f"处理了 {len(tasks)} 个任务"}

        except Exception as e:
            logger.error("heartbeat_execution_failed", error=str(e), exc_info=True, user_id=user_id)
            return {"should_notify": False, "summary": f"任务执行失败: {str(e)}"}

    async def _on_heartbeat_notify(self, response: dict, user_id: str) -> None:
        """
        心跳通知回调：主动推送结果

        Args:
            response: 执行结果
            user_id: 用户ID
        """
        logger.info("heartbeat_notify_callback", summary=response.get("summary"), user_id=user_id)

        # 解析 user_id: {channel}:{bot_account}:{sender_id}
        parts = user_id.split(":")
        if len(parts) < 3:
            logger.warning("invalid_user_id_format", user_id=user_id)
            return

        channel, bot_account, sender_id = parts[0], parts[1], parts[2]
        chat_id = sender_id  # 微信等渠道 chat_id = sender_id

        summary = response.get("summary", "")
        if not summary:
            logger.debug("empty_summary_no_notification_sent", user_id=user_id)
            return

        # 发送通知
        try:
            outbound_msg = OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=f"【定时任务通知】\n\n{summary}",
                reply_to=sender_id
            )
            await self.message_bus.publish_outbound(outbound_msg)
            logger.info("heartbeat_notification_sent", user_id=user_id, channel=channel)
        except Exception as e:
            logger.error("heartbeat_notification_failed", error=str(e), exc_info=True, user_id=user_id)

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
