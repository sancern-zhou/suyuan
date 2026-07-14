"""社交 Agent 桥接模块，负责连接消息总线与 ReActAgent。"""

import asyncio
import json
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import structlog

from app.agent.react_agent import ReActAgent
from app.services.media_object_store import get_media_object_store
from app.social.events import InboundMessage, OutboundMessage
from app.social.message_bus import MessageBus
from app.social.session_mapper import SessionMapper
from app.social.heartbeat_service import HeartbeatService
from app.social.memory_store import MemoryStore
from app.social.task_status_store import TaskStatusStore
from app.social.user_preferences import UserPreferences
from app.agent.runtime.steering import steering_registry
from app.agent.session import Session
from app.agent.session.conversation_persistence import ConversationPersistenceService
from app.agent.session.session_resolver import (
    append_session_transcript_for_mode,
    load_session_for_mode,
)
from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.schemas import ConversationSource
from app.social.binding_service import get_social_binding_service

logger = structlog.get_logger(__name__)


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Parse a whole-response JSON object, including simple fenced JSON replies."""
    stripped = text.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()

    try:
        parsed = json.loads(stripped)
    except Exception:
        return None

    return parsed if isinstance(parsed, dict) else None


def _is_heartbeat_silent_response(summary: str) -> bool:
    stripped = summary.strip()
    if not stripped:
        return True
    if stripped == "HEARTBEAT_OK":
        return True

    parsed = _extract_json_object(stripped)
    if not parsed:
        return False

    return parsed.get("heartbeat_silent") is True or parsed.get("should_notify") is False


def _heartbeat_should_notify(summary: str, use_social_context: bool) -> bool:
    return bool(summary.strip()) and use_social_context and not _is_heartbeat_silent_response(summary)


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
        mode: str = "social",  
        enable_heartbeat: bool = True,  
        enable_memory: bool = True,
        binding_service=None,
        catalog=None,
    ):
        """初始化 AgentBridge 及社交模式需要的心跳、记忆和子 Agent 管理器。"""
        self.message_bus = message_bus
        self.agent = agent
        self.session_mapper = session_mapper
        self.mode = mode
        self.enable_heartbeat = enable_heartbeat
        self.enable_memory = enable_memory
        self.binding_service = binding_service or get_social_binding_service()
        self.catalog = catalog or get_conversation_catalog()

        self._running = False
        self._consume_task: Optional[asyncio.Task] = None
        self._message_tasks: set[asyncio.Task] = set()
        self._active_social_sessions: set[str] = set()

        
        # 初始化用户心跳管理器
        from app.social.user_heartbeat_manager import UserHeartbeatManager
        from app.social.user_heartbeat_singleton import set_user_heartbeat_manager

        self.user_heartbeat_manager: Optional[UserHeartbeatManager] = None
        if enable_heartbeat and mode == "social":
            self.user_heartbeat_manager = UserHeartbeatManager(
                on_execute_callback=self._on_heartbeat_execute,
                on_notify_callback=self._on_heartbeat_notify,
                user_id_resolver=self._resolve_heartbeat_user_id,
            )
            
            set_user_heartbeat_manager(self.user_heartbeat_manager)
            logger.info("user_heartbeat_manager_initialized")

        
        # 初始化用户隔离记忆管理器
        from app.social.user_memory_manager import UserMemoryManager

        self.user_memory_manager: Optional[UserMemoryManager] = None
        if enable_memory and mode == "social":
            self.user_memory_manager = UserMemoryManager()
            logger.info("user_memory_manager_initialized")

        
        # 初始化社交子 Agent 管理器
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
            
            set_subagent_manager(self.subagent_manager)
            logger.info("subagent_manager_initialized")

            from app.social.cli_task_manager import CliTaskManager
            from app.social.cli_task_singleton import set_cli_task_manager
            from app.social.cli_task_store import CliTaskStore

            self.cli_task_manager = CliTaskManager(
                task_store=CliTaskStore(),
                message_bus=message_bus,
            )
            set_cli_task_manager(self.cli_task_manager)
            logger.info("cli_task_manager_initialized")
        else:
            self.cli_task_manager = None

        
        self._channel_map: Dict[str, "BaseChannel"] = {}

    async def start(self) -> None:
        """Start consuming inbound messages and processing them."""
        if self._running:
            logger.warning("AgentBridge already running")
            return

        self._running = True
        self._consume_task = asyncio.create_task(self._consume_loop())

        # ✅ 启动子Agent管理器
        if self.subagent_manager:
            await self.subagent_manager.start()

        if self.cli_task_manager:
            await self.cli_task_manager.start()

        # ✅ 后端重启后恢复已有用户的社交定时任务心跳循环
        if self.user_heartbeat_manager and self.mode == "social":
            try:
                restored_count = await self.user_heartbeat_manager.restore_existing_heartbeats()
                logger.info("user_heartbeat_restore_completed", restored_count=restored_count)
            except Exception as e:
                logger.error("user_heartbeat_restore_failed", error=str(e), exc_info=True)

        # ✅ 执行迁移：为现有用户创建 USER.md（如果不存在）
        if self.mode == "social":
            try:
                from app.social.migrations.create_user_md_files import migrate_user_md_files
                migrate_user_md_files()
            except Exception as e:
                logger.error("user_md_migration_failed", error=str(e), exc_info=True)

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

        for task in list(self._message_tasks):
            task.cancel()
        if self._message_tasks:
            await asyncio.gather(*self._message_tasks, return_exceptions=True)
            self._message_tasks.clear()

        
        if self.user_heartbeat_manager:
            await self.user_heartbeat_manager.shutdown()

        
        if self.subagent_manager:
            await self.subagent_manager.shutdown()

        if self.cli_task_manager:
            await self.cli_task_manager.shutdown()

        logger.info("AgentBridge stopped")

    def register_channel(self, channel: "BaseChannel") -> None:
        """注册社交渠道，用于解析机器人账号和发送消息。"""
        from app.channels.base import BaseChannel

        if not isinstance(channel, BaseChannel):
            logger.warning("invalid_channel_type", type=type(channel))
            return

        self._channel_map[channel.name] = channel
        logger.info("channel_registered", channel_name=channel.name)

    async def _get_bot_account(self, channel_name: str) -> str:
        """根据渠道名称获取机器人账号。"""
        channel = self._channel_map.get(channel_name)
        if channel:
            return channel.bot_account
        return "default"

    def _resolve_heartbeat_user_id(self, user_id: str) -> str:
        """Map persisted heartbeat user ids to currently registered channels."""
        parts = user_id.rsplit(":", 2)
        if len(parts) < 3:
            return user_id

        channel_name, bot_account, sender_id = parts
        if channel_name in self._channel_map:
            current_bot_account = self._channel_map[channel_name].bot_account
            if current_bot_account != bot_account:
                return f"{channel_name}:{current_bot_account}:{sender_id}"
            return user_id

        sender_matches: list[tuple[str, str]] = []
        bot_matches: list[tuple[str, str]] = []
        for name, channel in self._channel_map.items():
            channel_bot_account = channel.bot_account
            context_tokens = getattr(channel, "_context_tokens", None)
            has_sender_context = isinstance(context_tokens, dict) and sender_id in context_tokens
            if has_sender_context:
                sender_matches.append((name, channel_bot_account))
            if channel_bot_account == bot_account:
                bot_matches.append((name, channel_bot_account))

        if len(sender_matches) == 1:
            new_channel, new_bot_account = sender_matches[0]
            return f"{new_channel}:{new_bot_account}:{sender_id}"

        if len(bot_matches) == 1:
            new_channel, new_bot_account = bot_matches[0]
            return f"{new_channel}:{new_bot_account}:{sender_id}"

        logger.warning(
            "heartbeat_user_id_channel_unresolved",
            user_id=user_id,
            channel=channel_name,
            sender_id=sender_id,
            available_channels=list(self._channel_map.keys()),
            sender_match_count=len(sender_matches),
            bot_match_count=len(bot_matches),
        )
        return user_id

    @staticmethod
    def _is_image_media(media_path: str) -> bool:
        mime_type, _ = mimetypes.guess_type(media_path)
        if mime_type and mime_type.startswith("image/"):
            return True
        return Path(media_path).suffix.lower() in {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".bmp",
            ".tif",
            ".tiff",
        }

    def _build_agent_attachments(self, media: Optional[List[str]]) -> List[Dict[str, Any]]:
        """Convert social channel media references into agent attachments."""
        attachments: List[Dict[str, Any]] = []
        for item in media or []:
            if not item:
                continue
            media_type = "image" if self._is_image_media(item) else "file"
            attachment: Dict[str, Any] = {
                "type": media_type,
                "name": Path(item).name or "attachment",
            }
            if item.startswith(("http://", "https://")):
                attachment["url"] = item
            else:
                attachment["local_path"] = item
                mime_type, _ = mimetypes.guess_type(item)
                if media_type == "image":
                    try:
                        object_url = get_media_object_store().upload_and_presign(
                            item,
                            content_type=mime_type,
                        )
                        if object_url:
                            attachment["url"] = object_url
                    except Exception as exc:
                        logger.warning(
                            "media_object_store_upload_failed",
                            path=item,
                            error=str(exc),
                        )
                    try:
                        from app.services.signed_media import get_signed_media_service

                        signed_url = get_signed_media_service().create_url(item)
                        if signed_url and not attachment.get("url"):
                            attachment["url"] = signed_url
                    except Exception as exc:
                        logger.warning(
                            "signed_media_url_generation_failed",
                            path=item,
                            error=str(exc),
                        )
            mime_type, _ = mimetypes.guess_type(item)
            if mime_type:
                attachment["mime_type"] = mime_type
            attachments.append(attachment)
        return attachments

    @staticmethod
    def _strip_media_source_markers(content: str) -> str:
        """Remove local/remote media source paths that are supplied as attachments."""
        cleaned = re.sub(
            r"(?im)^\[(?:Image|Audio|Video|File):\s*source:\s*[^\]]+\]\s*$",
            "",
            content or "",
        )
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

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
                task = asyncio.create_task(self._route_message(msg))
                self._message_tasks.add(task)
                task.add_done_callback(self._message_tasks.discard)
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

    async def _route_message(self, msg: InboundMessage) -> None:
        bot_account = await self._get_bot_account(msg.channel)
        social_user_id = f"{msg.channel}:{bot_account}:{msg.sender_id}"
        is_weixin = msg.channel == "weixin" or msg.channel.startswith("weixin:")

        if self.mode == "social" and is_weixin:
            binding = await self.binding_service.resolve_sender(
                channel=msg.channel,
                bot_account=bot_account,
                sender_id=msg.sender_id,
            )
            if binding is None:
                await self.message_bus.publish_outbound(OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="请先登录 Web 端，在微信账号管理中完成扫码绑定。",
                    reply_to=msg.sender_id,
                ))
                return

            session_id = await self.session_mapper.get_session(social_user_id)
            catalog_user = CurrentUser(
                id=binding.platform_user_id,
                username=binding.platform_username,
                display_name=binding.platform_display_name,
            )
            if session_id:
                try:
                    row = await self.catalog.require_read(session_id, catalog_user)
                    if row.source != ConversationSource.SOCIAL:
                        session_id = None
                except Exception:
                    session_id = None

            if session_id is None:
                session_id = self.session_mapper.new_session_id(self.mode)
                registered = False
                try:
                    await self.catalog.register_identity(
                        session_id=session_id,
                        owner_user_id=binding.platform_user_id,
                        owner_username=binding.platform_username,
                        owner_display_name=binding.platform_display_name,
                        source=ConversationSource.SOCIAL,
                        mode=self.mode,
                        title=(msg.content or "微信会话")[:256],
                        read_only_on_web=True,
                    )
                    registered = True
                    await self.session_mapper.save_mapping(social_user_id, session_id)
                except Exception:
                    if registered:
                        await self.catalog.delete(session_id)
                    logger.exception(
                        "social_session_registration_failed",
                        social_user_id=social_user_id,
                    )
                    await self.message_bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="会话初始化失败，请稍后重试。",
                        reply_to=msg.sender_id,
                    ))
                    return

        elif self.mode == "social":
            from app.social.user_registry import BIND_CODE_PATTERN, get_social_user_registry

            registry = get_social_user_registry()
            if BIND_CODE_PATTERN.match(msg.content or ""):
                bound_user = await registry.bind_by_code(
                    message_text=msg.content,
                    channel=msg.channel,
                    bot_account=bot_account,
                    sender_id=msg.sender_id,
                )
                if bound_user:
                    await self.message_bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=f"绑定成功，{bound_user.name}。现在可以正常使用了。",
                            reply_to=msg.sender_id,
                        )
                    )
                    logger.info(
                        "social_user_bound",
                        social_user_id=bound_user.social_user_id,
                        user_id=bound_user.id,
                    )
                else:
                    await self.message_bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content="绑定码无效、已使用，或当前微信已经绑定过用户。",
                            reply_to=msg.sender_id,
                        )
                    )
                    logger.warning(
                        "social_user_bind_failed",
                        channel=msg.channel,
                        sender_id=msg.sender_id,
                        content_preview=msg.content[:40],
                    )
                return

            social_user = await registry.touch_social_user(social_user_id)
            if social_user and social_user.status == "disabled":
                await self.message_bus.publish_outbound(
                    OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="当前用户已被禁用，请联系管理员。",
                        reply_to=msg.sender_id,
                    )
                )
                return

        else:
            session_id = await self.session_mapper.get_or_create_session(
                social_user_id, mode=self.mode
            )

        if self.mode == "social" and not is_weixin:
            session_id = await self.session_mapper.get_or_create_session(
                social_user_id, mode=self.mode
            )

        if self.mode == "social" and session_id in self._active_social_sessions:
            agent_attachments = self._build_agent_attachments(msg.media)
            agent_content = (
                self._strip_media_source_markers(msg.content)
                if agent_attachments
                else msg.content
            )
            accepted = await steering_registry.add_input(
                session_id,
                agent_content,
                attachments=agent_attachments,
            )
            if not accepted:
                await asyncio.sleep(0.2)
                accepted = await steering_registry.add_input(
                    session_id,
                    agent_content,
                    attachments=agent_attachments,
                )
            if accepted:
                logger.info(
                    "social_message_steered_to_active_run",
                    channel=msg.channel,
                    sender_id=msg.sender_id,
                    session_id=session_id,
                    content_preview=agent_content[:80],
                    attachment_count=len(agent_attachments),
                )
                return

        await self._process_message(
            msg,
            bot_account=bot_account,
            social_user_id=social_user_id,
            session_id=session_id,
        )

    async def _process_message(
        self,
        msg: InboundMessage,
        bot_account: Optional[str] = None,
        social_user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
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

            
            bot_account = bot_account or await self._get_bot_account(msg.channel)
            social_user_id = social_user_id or f"{msg.channel}:{bot_account}:{msg.sender_id}"

            
            session_id = session_id or await self.session_mapper.get_or_create_session(social_user_id, mode=self.mode)
            if self.mode == "social":
                self._active_social_sessions.add(session_id)

            logger.info("Session obtained",
                       channel=msg.channel,
                       sender_id=msg.sender_id,
                       bot_account=bot_account,
                       session_id=session_id,
                       chat_id=msg.chat_id,
                       mode=self.mode)


            from app.social.message_bus_singleton import set_current_context
            set_current_context(
                channel=msg.channel,
                chat_id=msg.chat_id,
                bot_account=bot_account,
            )
            logger.debug("current_context_set", chat_id=msg.chat_id, channel=msg.channel, bot_account=bot_account)

            
            if self.user_heartbeat_manager and self.mode == "social":
                heartbeat = await self.user_heartbeat_manager.get_user_heartbeat(social_user_id)
                logger.debug("user_heartbeat_started", user_id=social_user_id)

            
            
            # ✅ 使用复用函数加载社交上下文（避免代码重复）
            social_memory_store = None
            social_user_prefs = None
            social_soul_file_path = None
            social_user_file_path = None
            social_heartbeat_file_path = None
            social_soul_context = None
            social_user_context = None

            if self.mode == "social":
                social_context = await self._load_social_agent_context(social_user_id)
                social_memory_store = social_context["social_memory_store"]
                social_user_prefs = social_context["social_user_preferences"]
                social_soul_file_path = social_context["social_soul_file_path"]
                social_user_file_path = social_context["social_user_file_path"]
                social_heartbeat_file_path = social_context["social_heartbeat_file_path"]
                social_soul_context = social_context["social_soul_context"]
                social_user_context = social_context["social_user_context"]

            agent_attachments = self._build_agent_attachments(msg.media) if self.mode == "social" else []
            agent_content = (
                self._strip_media_source_markers(msg.content)
                if agent_attachments
                else msg.content
            )

            # ✅ 加载 Session 对象，用于持久化对话历史
            session = await load_session_for_mode(session_id, mode=self.mode)
            if not session:
                session = Session(session_id=session_id, query=agent_content)

            response_text, reasoning_content = await self._aggregate_agent_events(
                content=agent_content,
                session_id=session_id,
                chat_id=msg.chat_id,
                channel=msg.channel,
                attachments=agent_attachments,
                social_user_id=social_user_id if self.mode == "social" else None,
                social_memory_store=social_memory_store,
                social_user_preferences=social_user_prefs,
                social_soul_file_path=social_soul_file_path,
                social_user_file_path=social_user_file_path,
                social_heartbeat_file_path=social_heartbeat_file_path,
                social_soul_context=social_soul_context,
                social_user_context=social_user_context,
                session=session  # ✅ 传递 session 对象
            )

            logger.info("Agent analysis completed",
                       session_id=session_id,
                       response_length=len(response_text) if response_text else 0,
                       reasoning_length=len(reasoning_content) if reasoning_content else 0)

            
            if self.user_memory_manager and self.mode == "social":
                
                from datetime import datetime
                messages = [
                    {"role": "user", "content": msg.content, "timestamp": datetime.now().isoformat()},
                    {"role": "assistant", "content": response_text, "timestamp": datetime.now().isoformat()}
                ]


                # 达到阈值后整理长期记忆
                await self._check_and_consolidate_memory(session_id, social_user_id)


            media_files = self._extract_media_files(response_text)


            cleaned_answer = self._clean_media_references(response_text)

            # ✅ 检查用户是否启用了思考内容显示（默认开启）
            show_reasoning = True  # 默认开启
            if social_user_prefs:
                show_reasoning = social_user_prefs.get("show_reasoning", True)

            # ✅ 如果启用了思考内容显示且有思考内容，则前置到最终回复前
            final_content = cleaned_answer
            if show_reasoning and reasoning_content:
                final_content = reasoning_content + cleaned_answer

            # Publish outbound response
            outbound_msg = OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=final_content,
                reply_to=msg.sender_id,
                media=media_files,
                metadata={}
            )

            await self.message_bus.publish_outbound(outbound_msg)

            logger.info("Response sent",
                       channel=msg.channel,
                       chat_id=msg.chat_id,
                       session_id=session_id,
                       has_reasoning=bool(reasoning_content),
                       show_reasoning=show_reasoning)

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
        finally:
            if self.mode == "social" and session_id:
                self._active_social_sessions.discard(session_id)

    async def _aggregate_agent_events(
        self,
        content: str,
        session_id: str,
        chat_id: str,
        channel: str = None,
        memory_context: str = "",
        social_user_id: str = None,
        social_memory_store = None,
        social_user_preferences: dict = None,
        social_soul_file_path: str = None,
        social_user_file_path: str = None,
        social_heartbeat_file_path: str = None,
        social_soul_context: str = None,
        social_user_context: str = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        session: Optional[Session] = None,
    ) -> tuple[str, str]:
        """聚合 Agent 事件并生成最终回复。

        Returns:
            tuple: (response_text, reasoning_content)
                   - response_text: 最终回复内容
                   - reasoning_content: 思考内容（如果有，否则为空）
        """
        events_buffer = []
        streaming_text_parts = []
        tool_calls = []
        reasoning_parts = []
        sent_text_contents = set()

        conversation_history = []
        collected_data_ids = []
        collected_visuals = []
        seen_visual_ids = set()

        persistence = ConversationPersistenceService()

        user_message = {
            "type": "user",
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        conversation_history.append(user_message)
        logger.debug("user_message_added_to_history",
                    session_id=session_id,
                    content_preview=content[:100])

        async def persist_turn(
            *,
            terminal_message: Optional[Dict[str, Any]] = None,
            office_documents: Optional[List[Dict[str, Any]]] = None,
            log_event: str = "social_session_transcript_persisted",
            **log_fields: Any,
        ) -> None:
            if not session:
                return
            if terminal_message is None:
                persistence.append_complete(
                    session,
                    display_history=conversation_history,
                    collected_data_ids=collected_data_ids,
                    collected_visuals=collected_visuals,
                    office_documents=office_documents,
                )
            else:
                persistence.append_terminal(
                    session,
                    display_history=conversation_history,
                    terminal_message=terminal_message,
                    collected_data_ids=collected_data_ids,
                    collected_visuals=collected_visuals,
                    office_documents=office_documents,
                )
            await append_session_transcript_for_mode(session, mode=self.mode)

            if session_id not in self.agent._session_store:
                self.agent._session_store[session_id] = {}
            self.agent._session_store[session_id]["collected_data_ids"] = list(
                dict.fromkeys(collected_data_ids)
            )
            self.agent._session_store[session_id]["collected_visuals"] = collected_visuals
            self.agent._session_store[session_id]["display_history_persisted"] = True

            logger.info(
                log_event,
                session_id=session_id,
                conversation_history_length=len(conversation_history),
                collected_data_ids_count=len(collected_data_ids),
                collected_visuals_count=len(collected_visuals),
                **log_fields,
            )

        try:
            
            

            # Call agent and collect events
            async for event in self.agent.analyze(
                user_query=content,
                session_id=session_id,
                manual_mode=self.mode,
                user_identifier=social_user_id if self.mode == "social" else None,
                social_memory_store=social_memory_store if self.mode == "social" else None,
                social_user_preferences=social_user_preferences if self.mode == "social" else None,
                social_soul_file_path=social_soul_file_path if self.mode == "social" else None,
                social_user_file_path=social_user_file_path if self.mode == "social" else None,
                social_heartbeat_file_path=social_heartbeat_file_path if self.mode == "social" else None,
                social_soul_context=social_soul_context if self.mode == "social" else None,
                social_user_context=social_user_context if self.mode == "social" else None,
                attachments=attachments if self.mode == "social" else None,
            ):
                events_buffer.append(event)

                # Process different event types
                event_type = event.get("type", "")

                if event_type in ["thought", "tool_use", "tool_result"]:
                    event_data = event.get("data", {})
                    frontend_message = {
                        "type": event_type,
                        "data": event_data,
                        "timestamp": event_data.get("timestamp") if "timestamp" in event_data else None
                    }

                    if event_type == "thought":
                        frontend_message["content"] = event_data.get("text_content", "思考中...")
                    elif event_type == "tool_use":
                        tool_name = event_data.get("tool_name", "")
                        frontend_message["content"] = f"调用工具: {tool_name}" if tool_name else "执行行动"
                    elif event_type == "tool_result":
                        result_data = event_data.get("result", {})
                        if isinstance(result_data, dict):
                            frontend_message["content"] = (
                                result_data.get("summary_text")
                                or (result_data.get("summary", "")[:500] if result_data.get("summary") else "")
                                or "获得结果"
                            )
                        else:
                            frontend_message["content"] = str(result_data)

                    conversation_history.append(frontend_message)
                    logger.debug("conversation_history_appended",
                                event_type=event_type,
                                history_length=len(conversation_history))

                # 收集数据ID
                if event_type == "tool_result" and "data" in event:
                    data = event.get("data", {})
                    if "data_id" in data:
                        collected_data_ids.append(data["data_id"])
                    if "data_ids" in data:
                        collected_data_ids.extend(data["data_ids"])

                # 收集可视化（基于ID去重）
                if "visuals" in event.get("data", {}):
                    visuals = event["data"]["visuals"]
                    if isinstance(visuals, list):
                        for visual in visuals:
                            visual_id = visual.get("id")
                            if visual_id and visual_id not in seen_visual_ids:
                                collected_visuals.append(visual)
                                seen_visual_ids.add(visual_id)

                if event_type == "streaming_text":
                    # Accumulate streaming text
                    data = event.get("data", {})

                    # Handle different data formats
                    if isinstance(data, dict):
                        # New format: {"chunk": "...", "is_complete": false}
                        chunk = data.get("chunk", "")
                        is_complete = data.get("is_complete", False)

                        if isinstance(chunk, str):
                            streaming_text_parts.append(chunk)
                        else:
                            streaming_text_parts.append(str(chunk))

                        # 社交端最终回复由 complete/final outbound 统一发送；
                        # 这里仅缓冲文本用于异常 fallback，避免中间流和最终回复重复。
                        if self.mode == "social" and is_complete:
                            pass

                    elif isinstance(data, str):
                        # Legacy format: data is directly a string
                        streaming_text_parts.append(data)
                    else:
                        # Fallback: convert to string
                        streaming_text_parts.append(str(data))

                elif event_type == "agent_action":
                    # Track tool calls for progress reporting
                    action = event.get("data", {})
                    tool_name = action.get("tool", "")
                    tool_calls.append(tool_name)

                elif event_type == "thought":
                    # ✅ 提取 LLM 的普通文本（用户关心的自然语言说明）
                    thought_data = event.get("data", {})
                    text_content = thought_data.get("text_content", "")

                    # ❌ 忽略 thought 字段（技术描述如"准备调用工具"，用户不关心）

                    if text_content and thought_data.get("will_use_tool"):
                        reasoning_parts.append(text_content)

                        # ✅ 仅工具调用前的 text_content 作为进展发送，避免最终回答重复显示
                        # ✅ 去重：如果还没发送过，才发送
                        if text_content not in sent_text_contents and self.mode == "social":
                            await self._send_thinking_chunk(
                                channel=channel,
                                chat_id=chat_id,
                                thinking_content=text_content
                            )
                            sent_text_contents.add(text_content)  # 标记为已发送

                elif event_type == "thinking_content":
                    # ✅ 新增：监听真实的 LLM thinking 内容
                    thinking_data = event.get("data", {})
                    real_thinking = thinking_data.get("content", "")

                    if real_thinking:
                        # ✅ 实时流式发送到微信端（不过滤，这是真实思考）
                        if self.mode == "social":
                            await self._send_thinking_chunk(
                                channel=channel,
                                chat_id=chat_id,
                                thinking_content=real_thinking
                            )

                        # 同时收集到 reasoning_parts（用于向后兼容）
                        reasoning_parts.append(real_thinking)

                elif event_type == "agent_finish":
                    # ✅ 新增：agent_finish 事件也可能包含思考内容
                    thought_data = event.get("data", {})
                    thought_content = thought_data.get("thought", "")
                    if thought_content and thought_content not in reasoning_parts:
                        reasoning_parts.append(str(thought_content))

                elif event_type == "complete":
                    # Extract final answer (loop.py returns "answer" field)
                    final_data = event.get("data", {})
                    if isinstance(final_data, dict):
                        response_text = final_data.get("answer", "")
                        if response_text:
                            reasoning_content = self._format_reasoning_content(reasoning_parts)

                            final_message = {
                                "type": "final",
                                "content": response_text,
                                "data": final_data,
                                "timestamp": final_data.get("timestamp", datetime.now().isoformat())
                            }
                            conversation_history.append(final_message)

                            if "visuals" in final_data and isinstance(final_data["visuals"], list):
                                final_message["visuals"] = final_data["visuals"]

                            if session:
                                office_documents = self.agent._session_store.get(
                                    session_id, {}
                                ).get("office_documents", [])

                                await persist_turn(
                                    office_documents=office_documents,
                                    log_event="social_session_transcript_persisted",
                                )

                            return response_text, reasoning_content

                elif event_type == "error":
                    # Handle error events
                    error_data = event.get("data", {})
                    error_msg = error_data.get("error", "Unknown error")
                    logger.warning("Agent error event", error=error_msg)

                    if session:
                        terminal_message = {
                            "type": "error",
                            "content": f"处理查询时出错: {error_msg}",
                            "data": error_data,
                            "timestamp": datetime.now().isoformat(),
                        }
                        await persist_turn(
                            terminal_message=terminal_message,
                            log_event="social_session_transcript_persisted_on_error",
                            error_type="error",
                        )

                    return f"处理查询时出错: {error_msg}", ""

                elif event_type in ["incomplete", "fatal_error", "interrupted"]:
                    # Handle terminal events
                    error_data = event.get("data", {})

                    if event_type == "interrupted":
                        terminal_content = error_data.get("reason", "用户已暂停本轮分析")
                    elif event_type == "incomplete":
                        terminal_content = error_data.get(
                            "reason",
                            "分析任务较复杂，在限定步骤内未完成，是否继续？",
                        )
                    else:
                        terminal_content = error_data.get("error") or error_data.get("message") or "分析失败"

                    if session:
                        terminal_message = {
                            "type": event_type,
                            "content": terminal_content,
                            "data": error_data,
                            "timestamp": error_data.get("timestamp") or datetime.now().isoformat(),
                        }
                        await persist_turn(
                            terminal_message=terminal_message,
                            log_event="social_session_transcript_persisted_on_terminal",
                            terminal_type=event_type,
                        )

                    if event_type == "fatal_error":
                        error_msg = error_data.get("error", "未知错误") if isinstance(error_data, dict) else str(error_data)
                        return f"系统遇到致命错误: {error_msg}\n\n请稍后重试或联系技术支持。", ""

                    return terminal_content, ""

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

                reasoning_content = self._format_reasoning_content(reasoning_parts)
                return full_text, reasoning_content

            # Fallback: extract content from last event
            if events_buffer:
                last_event = events_buffer[-1]
                data = last_event.get("data", {})
                if isinstance(data, str):
                    reasoning_content = self._format_reasoning_content(reasoning_parts)
                    return data, reasoning_content
                elif isinstance(data, dict):
                    reasoning_content = self._format_reasoning_content(reasoning_parts)
                    return data.get("content", str(data)), reasoning_content

            return "抱歉，未能生成回复。", ""

        except Exception as e:
            logger.error("Error aggregating agent events",
                        session_id=session_id,
                        error=str(e),
                        exc_info=True)

            if session:
                terminal_message = {
                    "type": "fatal_error",
                    "content": str(e),
                    "timestamp": datetime.now().isoformat(),
                }

                try:
                    await persist_turn(
                        terminal_message=terminal_message,
                        log_event="social_session_transcript_persisted_on_exception",
                        error=str(e),
                    )
                except Exception as persist_err:
                    logger.error("failed_to_persist_session_on_exception",
                               session_id=session_id,
                               persist_error=str(persist_err))

            return f"处理请求时出错: {str(e)}", ""

    def _filter_technical_details(self, thought: str) -> str:
        """过滤掉工具调用等技术细节，只保留真实思考内容。

        Args:
            thought: 原始思考内容

        Returns:
            过滤后的思考内容（如果全是技术细节则返回空字符串）
        """
        if not thought:
            return ""

        # 技术关键词列表（需要过滤）
        technical_patterns = [
            r"^准备调用工具[:：]",
            r"^调用工具[:：]",
            r"^执行工具[:：]",
            r"^使用.*工具",
            r"^工具调用[:：]",
            r"^tool call[:：]",
            r"^Tool call[:：]",
            r"^正在调用",
            r"^将要调用",
        ]

        lines = thought.strip().split("\n")
        filtered_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检查是否是技术细节
            is_technical = False
            for pattern in technical_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    is_technical = True
                    break

            if not is_technical:
                filtered_lines.append(line)

        result = "\n".join(filtered_lines).strip()
        return result

    async def _send_thinking_chunk(
        self,
        channel: str,
        chat_id: str,
        thinking_content: str
    ) -> None:
        """实时流式发送思考内容到微信端。

        Args:
            channel: 微信通道ID（如 weixin:auto_mo427atx）
            chat_id: 微信聊天ID
            thinking_content: 思考内容片段
        """
        from app.social.events import OutboundMessage

        # 格式化思考内容（不带"思考过程"标签）
        formatted_thinking = f"{thinking_content}\n\n"

        # 创建流式消息（标记为中间片段）
        thinking_msg = OutboundMessage(
            channel=channel,  # 使用具体的微信通道ID
            chat_id=chat_id,
            content=formatted_thinking,
            reply_to="",
            media=[],
            metadata={
                "_stream_id": "thinking_stream",
                "_stream_end": False  # 标记为中间片段
            }
        )

        # 发布到消息总线
        await self.message_bus.publish_outbound(thinking_msg)

        logger.debug("Thinking chunk sent",
                    chat_id=chat_id,
                    content_preview=thinking_content[:50])

    def _format_reasoning_content(self, reasoning_parts: list[str]) -> str:
        """格式化思考内容（参考 Hermes 的格式）。

        注意：思考内容已经通过实时流式发送到微信端（通过 thinking_content 事件），
        最终回复中不再包含格式化的思考内容，避免重复显示。

        Args:
            reasoning_parts: 思考内容片段列表

        Returns:
            始终返回空字符串（思考内容已实时发送）
        """
        # 思考内容已通过 _send_thinking_chunk 实时流式发送
        # 最终回复中不再包含，避免重复显示
        return ""

    def _extract_media_files(self, content: str) -> list[str]:
        """从回复内容中提取媒体文件路径。"""
        import re
        from pathlib import Path
        from app.services.image_cache import get_image_cache

        media_files = []

        logger.debug("extracting_media_files_start",
                    content_length=len(content),
                    content_preview=content[:200])

        
        
        image_pattern = r'!?\[.*?\]\(/api/image/([a-zA-Z0-9_-]+)\)'
        matches = list(re.finditer(image_pattern, content))
        logger.debug("image_pattern_matches", count=len(matches))

        for match in matches:
            image_id = match.group(1)
            
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

        
        
        doc_pattern = r'([a-zA-Z0-9_/\-\.]+\.(docx|xlsx|pptx|pdf|md))'
        for match in re.finditer(doc_pattern, content):
            doc_path = match.group(1)
            if Path(doc_path).exists():
                media_files.append(doc_path)
                logger.debug("document_extracted", path=doc_path)

        logger.info("media_files_extracted", count=len(media_files), files=media_files)
        return media_files

    def _clean_media_references(self, content: str) -> str:
        """清理社交平台不适合直接展示的媒体引用。"""
        import re

        
        def replace_image_markdown(match):
            alt_text = match.group(1)  
            return f"\n[图片: {alt_text}]\n"

        content = re.sub(r'!\[([^\]]+)\]\([^\)]+\)', replace_image_markdown, content)

        
        content = re.sub(r'\(/api/image/[a-zA-Z0-9_-]+\)', '', content)

        
        def replace_doc_path(match):
            filename = Path(match.group(1)).name
            return f"\n[文件: {filename}]\n"

        content = re.sub(r'\([a-zA-Z0-9_/\-\.]+\.(docx|xlsx|pptx|pdf|md)\)', replace_doc_path, content)

        
        content = re.sub(r'\n{3,}', '\n\n', content)

        return content.strip()

    async def _send_stream_chunk(
        self,
        channel: str,
        chat_id: str,
        content: str,
        segment_id: int,
        resuming: bool = False
    ) -> None:
        """发送流式回复片段到微信端。"""
        from app.social.events import OutboundMessage

        logger.debug(
            "stream_chunk",
            chat_id=chat_id,
            segment_id=segment_id,
            length=len(content),
            resuming=resuming
        )

        # 创建流式消息
        stream_msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=content,
            reply_to="",
            media=[],
            metadata={
                "_stream_id": "response_stream",
                "_stream_end": False,  # 标记为中间片段
                "_segment_id": segment_id,
                "_resuming": resuming
            }
        )

        # 发布到消息总线
        await self.message_bus.publish_outbound(stream_msg)

    async def _load_social_agent_context(self, user_id: str) -> dict:
        """
        加载社交模式 Agent 所需的用户上下文

        ✅ 复用函数：避免 _process_message 和 _on_heartbeat_execute 逻辑重复

        Args:
            user_id: 用户ID（格式：{channel}:{bot_account}:{sender_id}）

        Returns:
            包含社交上下文的字典
        """
        from app.social.user_preferences import UserPreferences

        context = {
            "social_memory_store": None,
            "social_user_preferences": None,
            "social_soul_file_path": None,
            "social_user_file_path": None,
            "social_heartbeat_file_path": None,
            "social_soul_context": None,
            "social_user_context": None
        }

        try:
            # 1. 加载用户记忆存储
            if self.user_memory_manager:
                context["social_memory_store"] = await self.user_memory_manager.get_user_memory(user_id)
                logger.debug("user_memory_loaded", user_id=user_id)

            try:
                from app.social.user_registry import get_social_user_registry

                social_user = await get_social_user_registry().get_by_social_user_id(user_id)
                if social_user:
                    structured_user_context = [
                        "## 结构化用户档案",
                        f"- 用户姓名：{social_user.name}",
                        f"- 用户状态：{social_user.status}",
                    ]
                    if social_user.email:
                        structured_user_context.append(f"- 邮箱：{social_user.email}")

                    existing_user_context = context.get("social_user_context") or ""
                    context["social_user_context"] = "\n".join(
                        [*structured_user_context, "", existing_user_context]
                    ).strip()
                    context["social_user_profile"] = social_user.model_dump()
            except Exception as e:
                logger.warning("failed_to_load_structured_social_user", user_id=user_id, error=str(e))

            # 2. 加载用户偏好和文件路径
            preferences_manager = UserPreferences(user_id)
            user_preferences = preferences_manager.get_preferences()

            if user_preferences:
                context["social_user_preferences"] = user_preferences
                context["social_soul_file_path"] = str(preferences_manager.soul_file.resolve()) if preferences_manager.soul_file else None
                context["social_user_file_path"] = str(preferences_manager.user_file.resolve()) if preferences_manager.user_file else None
                context["social_heartbeat_file_path"] = str(preferences_manager.heartbeat_file.resolve()) if preferences_manager.heartbeat_file else None

                # 加载 soul.md 和 USER.md 内容
                context["social_soul_context"] = preferences_manager.load_soul_md()
                user_md_context = preferences_manager.load_user_md()
                if context["social_user_context"] and user_md_context:
                    context["social_user_context"] = (
                        context["social_user_context"] + "\n\n" + user_md_context
                    )
                elif user_md_context:
                    context["social_user_context"] = user_md_context

                has_soul = len(context["social_soul_context"].strip()) > 0 if context["social_soul_context"] else False

                logger.info(
                    "social_agent_context_loaded",
                    user_id=user_id,
                    has_soul=has_soul,
                    soul_file_path=context["social_soul_file_path"],
                    user_file_path=context["social_user_file_path"],
                    heartbeat_file_path=context["social_heartbeat_file_path"]
                )
        except Exception as e:
            logger.warning(
                "failed_to_load_social_agent_context",
                user_id=user_id,
                error=str(e),
                exc_info=True
            )

        return context

    async def _check_and_consolidate_memory(
        self,
        session_id: str,
        social_user_id: str
    ) -> bool:
        """检查是否需要触发社交用户记忆整理。"""
        from app.utils.token_budget import token_budget_manager

        
        session_data = self.agent._session_store.get(session_id)
        if not session_data:
            return False

        memory_manager = session_data.get("memory")
        if not memory_manager:
            return False

        messages = memory_manager.session.get_messages_for_llm()

        
        total_tokens = 0
        for msg in messages:
            total_tokens += token_budget_manager.count_tokens(msg.get("content", ""))

        
        mapping = await self.session_mapper.get_mapping_info(social_user_id)
        if not mapping:
            return False

        last_offset = mapping.get("last_consolidated_offset", 0)
        new_message_count = len(messages) - last_offset

        
        max_tokens = int(token_budget_manager.max_context_tokens * 0.8)
        should_consolidate = (
            total_tokens > max_tokens or  
            new_message_count >= 20  
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
        """整理当前会话并更新社交用户长期记忆。"""
        from app.social.memory_store import ImprovedMemoryStore
        from app.tools.social.remember_fact.tool import RememberFactTool
        from app.tools.social.replace_memory.tool import ReplaceMemoryTool
        from app.tools.social.remove_memory.tool import RemoveMemoryTool
        from pathlib import Path
        from datetime import datetime

        try:
            # ✅ 使用统一路径配置
            from app.utils.path_config import get_social_memory_dir
            social_workspace = get_social_memory_dir()
            memory_store = ImprovedMemoryStore(user_id=social_user_id, workspace=social_workspace)

            existing_memory = memory_store.read_long_term()
            memory_file_path = str(memory_store.memory_file.resolve()) if memory_store.memory_file.exists() else ""

            
            messages_to_consolidate = messages[start_offset:] if start_offset > 0 else messages

            if not messages_to_consolidate:
                logger.debug("no_messages_to_consolidate", session_id=session_id, start_offset=start_offset)
                return

            
            for msg in messages_to_consolidate:
                if "timestamp" not in msg:
                    msg["timestamp"] = datetime.now().isoformat()

            daily_note_entry = self._build_daily_note_entry(messages_to_consolidate)
            memory_store.append_daily_note(daily_note_entry)

            dream_candidate_entry = self._build_dream_candidate_entry(messages_to_consolidate)
            memory_store.append_dream_candidate(dream_candidate_entry)
            recent_dreams = memory_store.read_recent_dreams()

            
            consolidation_prompt = self._build_social_consolidation_prompt(
                messages=messages_to_consolidate,
                existing_memory=existing_memory,
                memory_file_path=memory_file_path,
                recent_dreams=recent_dreams
            )

            
            safe_user_id = social_user_id.replace(":", "_")
            RememberFactTool.set_memory_context("social", safe_user_id)
            ReplaceMemoryTool.set_memory_context("social", safe_user_id)
            RemoveMemoryTool.set_memory_context("social", safe_user_id)

            
            from app.agent.memory_consolidator_factory import create_memory_consolidator_agent
            consolidator_agent = create_memory_consolidator_agent()

            async for event in consolidator_agent.analyze(
                user_query=consolidation_prompt,
                session_id=f"{session_id}_consolidation",
                manual_mode="memory_consolidator"
            ):
                if event.get("type") == "complete":
                    
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
            
            try:
                RememberFactTool.clear_memory_context()
                ReplaceMemoryTool.clear_memory_context()
                RemoveMemoryTool.clear_memory_context()
            except Exception as e:
                logger.warning("failed_to_clear_memory_context", error=str(e))

    def _build_social_consolidation_prompt(
        self,
        messages: List[Dict[str, Any]],
        existing_memory: str,
        memory_file_path: str,
        recent_dreams: str = ""
    ) -> str:
        """Build the prompt used by the social memory consolidator."""
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages[-10:]
        ])

        current_size = len(existing_memory) if existing_memory else 0
        max_size = 3000
        usage = current_size / max_size * 100 if max_size else 0
        size_info = f"{current_size}/{max_size} chars ({usage:.1f}%)"

        prompt_parts = [
            "You are a social-mode memory consolidation agent.",
            "Your job is to update long-term memory using only durable facts from the recent conversation.",
            "",
            "## Mode",
            "social",
            "",
            "## Existing Memory",
            f"Current size: {size_info}",
            "```",
            existing_memory.strip() if existing_memory and existing_memory.strip() else "(empty)",
            "```",
            "",
            "## Memory File",
            memory_file_path or "(unknown)",
            "",
            "## Recent Dream Candidates",
            "These are candidate memories from memory/.dreams/. They are not confirmed facts yet.",
            "```",
            recent_dreams.strip() if recent_dreams and recent_dreams.strip() else "(empty)",
            "```",
            "",
            "## Recent Conversation",
            "Use this only as evidence for the dream candidates. Do not promote one-off details directly from raw conversation.",
            conversation_text,
            "",
            "## Instructions",
            "1. The recent conversation has already been written to memory/YYYY-MM-DD.md as a daily note.",
            "2. Candidate memories have been written to memory/.dreams/YYYY-MM-DD.md as a dreaming layer.",
            "3. Promote only durable candidates from Recent Dream Candidates to MEMORY.md.",
            "4. Do not save one-off chit-chat, temporary status, or sensitive data unless the user explicitly asks.",
            "5. Use remember_fact, replace_memory, or remove_memory to update MEMORY.md.",
            "6. Keep memory concise. If usage is above 80%, prefer replacing or removing stale content before adding new facts.",
            "7. Preserve the existing markdown structure when possible."
        ]

        return "\n".join(prompt_parts)

    def _build_daily_note_entry(self, messages: List[Dict[str, Any]]) -> str:
        """Build a compact OpenClaw-style daily note entry from recent messages."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"## {timestamp}", ""]

        for msg in messages:
            role = msg.get("role", "unknown")
            content = str(msg.get("content", "")).strip()
            if not content:
                continue

            if len(content) > 800:
                content = content[:800].rstrip() + "..."

            role_name = "用户" if role == "user" else "助手" if role == "assistant" else role
            lines.append(f"**{role_name}**: {content}")
            lines.append("")

        lines.append("---")
        return "\n".join(lines)

    def _build_dream_candidate_entry(self, messages: List[Dict[str, Any]]) -> str:
        """Build a conservative dreaming candidate entry for later promotion."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"## {timestamp}",
            "",
            "状态: candidate",
            "说明: 以下内容是待观察候选，不是已确认长期事实；只有稳定、重复或用户明确要求记住的内容才可晋升 MEMORY.md。",
            "",
            "### Evidence",
        ]

        for msg in messages[-10:]:
            role = msg.get("role", "unknown")
            content = str(msg.get("content", "")).strip()
            if not content:
                continue

            if len(content) > 500:
                content = content[:500].rstrip() + "..."

            role_name = "用户" if role == "user" else "助手" if role == "assistant" else role
            lines.append(f"- {role_name}: {content}")

        lines.extend([
            "",
            "### Promotion Criteria",
            "- 用户明确说“记住”或纠正了长期偏好",
            "- 多次出现的稳定偏好、长期需求或项目背景",
            "- 可复用的领域知识或经过验证的长期结论",
            "- 排除一次性任务、临时状态、工具过程和时效性数据",
            "",
            "---",
        ])

        return "\n".join(lines)
    async def _on_heartbeat_execute(self, tasks: list, user_id: str) -> dict:
        """
        Execute heartbeat tasks through the agent.

        ✅ 修复：使用复用函数加载完整的社交上下文，确保任务执行时能访问用户专属资源
        """
        from datetime import datetime

        logger.info("heartbeat_execute_callback", task_count=len(tasks), user_id=user_id)

        if not tasks:
            return {"should_notify": False, "summary": "No tasks to execute"}

        manual_modes = {
            str(task.get("manual_mode") or "social").strip() or "social"
            for task in tasks
        }
        if len(manual_modes) > 1:
            logger.error("mixed_heartbeat_manual_modes", user_id=user_id, manual_modes=sorted(manual_modes))
            return {
                "should_notify": True,
                "summary": f"Heartbeat tasks for {user_id} mix manual modes: {', '.join(sorted(manual_modes))}",
            }
        manual_mode = manual_modes.pop()
        use_social_context = manual_mode == "social"

        social_context = await self._load_social_agent_context(user_id) if use_social_context else {
            "social_memory_store": None,
            "social_user_preferences": None,
            "social_heartbeat_file_path": None,
            "social_soul_file_path": None,
            "social_user_file_path": None,
            "social_soul_context": None,
            "social_user_context": None,
        }

        # 从 user_id 恢复本次心跳执行的 social 上下文。
        # user_id 格式：{channel}:{bot_account}:{chat_id}，channel 本身可能包含 ':'。
        from app.social.message_bus_singleton import set_current_context, reset_current_context
        parts = user_id.rsplit(":", 2)
        if len(parts) != 3:
            logger.error("invalid_heartbeat_user_id_format", user_id=user_id)
            return {"should_notify": True, "summary": f"Invalid heartbeat user_id: {user_id}"}

        channel, bot_account, chat_id = parts
        context_tokens = set_current_context(
            channel=channel,
            chat_id=chat_id,
            bot_account=bot_account,
        )
        logger.info("heartbeat_context_set", channel=channel, chat_id=chat_id, bot_account=bot_account)

        task_description = "\n".join([
            f"- {task.get('name', 'task')} [{task.get('manual_mode') or manual_mode}]: {task.get('description', '')}"
            for task in tasks
        ])

        try:
            heartbeat_session_id = f"heartbeat_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            query = f"""Please execute these scheduled tasks now:

{task_description}

⚠️ IMPORTANT:
- These are already-scheduled tasks that are due NOW
- Execute the task descriptions directly
- DO NOT use schedule_task tool to create new tasks
- DO NOT reschedule these tasks
- Just perform the actions described in each task
- If no user-visible notification is needed, your final answer MUST be exactly: HEARTBEAT_OK
- If a task says to be silent, return exactly HEARTBEAT_OK and do not explain why it was silent
- Only return a normal summary when the user should receive a WeChat notification

Example: If task says "Send a test message", then send the message directly, don't create a schedule."""

            result_parts = []
            # ✅ 传递完整的社交上下文
            async for event in self.agent.analyze(
                user_query=query,
                session_id=heartbeat_session_id,
                manual_mode=manual_mode,
                user_identifier=user_id,
                social_memory_store=social_context["social_memory_store"],
                social_user_preferences=social_context["social_user_preferences"],
                social_heartbeat_file_path=social_context["social_heartbeat_file_path"],
                social_soul_file_path=social_context["social_soul_file_path"],
                social_user_file_path=social_context["social_user_file_path"],
                social_soul_context=social_context["social_soul_context"],
                social_user_context=social_context["social_user_context"]
            ):
                if event.get("type") == "complete":
                    data = event.get("data", {})
                    if isinstance(data, dict):
                        result_parts.append(
                            data.get("answer")
                            or data.get("response")
                            or ""
                        )

            summary = "\n".join(part for part in result_parts if part).strip()
            should_notify = _heartbeat_should_notify(summary, use_social_context)
            response = {
                "should_notify": should_notify,
                "summary": summary or "Tasks completed",
                "executed_at": datetime.now().isoformat()
            }
            if should_notify and use_social_context:
                try:
                    from app.social.heartbeat_context import persist_heartbeat_context_event

                    await persist_heartbeat_context_event(
                        session_mapper=self.session_mapper,
                        user_id=user_id,
                        response=response,
                        heartbeat_session_id=heartbeat_session_id,
                        tasks=tasks,
                    )
                except Exception as persist_error:
                    logger.warning(
                        "heartbeat_context_event_persist_failed",
                        user_id=user_id,
                        heartbeat_session_id=heartbeat_session_id,
                        error=str(persist_error),
                    )
            return {
                **response,
            }

        except Exception as e:
            logger.error("heartbeat_execute_failed", user_id=user_id, error=str(e), exc_info=True)
            return {"should_notify": True, "summary": f"Task execution failed: {e}"}
        finally:
            reset_current_context(context_tokens)
    async def _on_heartbeat_notify(self, response: dict, user_id: str) -> None:
        """
        发送心跳任务通知。

        ✅ 修复：使用 rsplit(":", 2) 正确解析 user_id（因为 channel 本身可能包含 ':'）
        """
        logger.info("heartbeat_notify_callback", summary=response.get("summary"), user_id=user_id)


        # ✅ 修复：user_id 格式：{channel}:{bot_account}:{sender_id}
        # channel 本身可能包含 ':'（如 weixin:auto_mo427atx），所以用 rsplit(":", 2)
        parts = user_id.rsplit(":", 2)
        if len(parts) < 3:
            logger.warning("invalid_user_id_format", user_id=user_id)
            return

        channel, bot_account, sender_id = parts
        chat_id = sender_id  

        summary = response.get("summary", "")
        if not summary:
            logger.debug("empty_summary_no_notification_sent", user_id=user_id)
            return

        
        # 发送心跳任务通知
        try:
            outbound_msg = OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=f"定时任务通知\n\n{summary}",
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
