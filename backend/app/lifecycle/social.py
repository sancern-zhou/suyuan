"""Social platform lifecycle extracted from app/main.py.

Dependency note:
- Social startup creates an AgentBridge and channel manager.
- It should run after tool initialization, because the bridge uses ReAct Agent.
- Shutdown cancels background tasks before stopping channel/bridge instances.
"""

import asyncio

from fastapi import FastAPI
import structlog

from config.settings import settings

logger = structlog.get_logger()


async def start_social_platform_service(app: FastAPI) -> None:
    """Start configured social platform channels and Agent bridge."""
    try:
        from app.agent.react_agent import create_react_agent
        from app.channels.manager import ChannelManager
        from app.social.agent_bridge import AgentBridge
        from app.social.config import SocialConfig
        from app.social.message_bus import MessageBus
        from app.social.session_mapper import SessionMapper

        social_config = SocialConfig.load_from_yaml(settings.social_config_path)

        if not any([social_config.qq.enabled, social_config.weixin.enabled]):
            logger.info("social_platform_disabled", reason="no_platforms_enabled")
            return

        message_bus = MessageBus()

        from app.social.message_bus_singleton import set_message_bus

        set_message_bus(message_bus)
        logger.info("global_message_bus_set")

        session_mapper = SessionMapper()
        await session_mapper.load()

        agent = create_react_agent()
        agent_bridge = AgentBridge(
            agent=agent,
            message_bus=message_bus,
            session_mapper=session_mapper,
            mode="social",
        )

        message_bus.agent_bridge = agent_bridge
        logger.info("message_bus_agent_bridge_set")

        channel_manager = ChannelManager(
            config=social_config,
            bus=message_bus,
            agent_bridge=agent_bridge,
        )

        # Register configured channels before AgentBridge restores heartbeat
        # loops. Restart-time heartbeats need the channel map to translate old
        # persisted user ids and to resolve bot_account values.
        for name, channel in channel_manager.channels.items():
            agent_bridge.register_channel(channel)
            logger.info("channel_registered_to_agent_bridge_before_start", channel_name=name)

        async def run_agent_bridge():
            try:
                logger.info("agent_bridge_starting")
                await agent_bridge.start()
                logger.info("agent_bridge_started")
            except Exception as e:
                logger.error("agent_bridge_failed", error=str(e), exc_info=True)

        async def run_channel_manager():
            try:
                logger.info("channel_manager_starting")
                await channel_manager.start_all()
                logger.info("channel_manager_started")
            except Exception as e:
                logger.error("channel_manager_failed", error=str(e), exc_info=True)

        try:
            app.state.agent_bridge_task = asyncio.create_task(run_agent_bridge())
            logger.info("agent_bridge_task_created", task_id=id(app.state.agent_bridge_task))
        except Exception as e:
            logger.error("agent_bridge_task_creation_failed", error=str(e), exc_info=True)

        try:
            app.state.channel_manager_task = asyncio.create_task(run_channel_manager())
            logger.info("channel_manager_task_created", task_id=id(app.state.channel_manager_task))
        except Exception as e:
            logger.error("channel_manager_task_creation_failed", error=str(e), exc_info=True)

        app.state.social_config = social_config
        app.state.message_bus = message_bus
        app.state.session_mapper = session_mapper
        app.state.agent_bridge = agent_bridge
        app.state.channel_manager = channel_manager

        enabled_platforms = [
            name
            for name, config in [
                ("qq", social_config.qq),
                ("weixin", social_config.weixin),
            ]
            if config.enabled
        ]

        logger.info(
            "social_platform_service_started",
            enabled_platforms=enabled_platforms,
            agent_bridge_running=True,
            channel_manager_running=True,
        )
    except Exception as e:
        logger.error("social_platform_service_failed", error=str(e), exc_info=True)
        logger.warning("continuing_without_social_platforms")


async def stop_social_platform_service(app: FastAPI) -> None:
    """Stop social platform background tasks and persist session mapper state."""
    try:
        if hasattr(app.state, "channel_manager_task") and app.state.channel_manager_task:
            app.state.channel_manager_task.cancel()
            try:
                await app.state.channel_manager_task
            except asyncio.CancelledError:
                pass
            logger.info("channel_manager_task_cancelled")

        if hasattr(app.state, "agent_bridge_task") and app.state.agent_bridge_task:
            app.state.agent_bridge_task.cancel()
            try:
                await app.state.agent_bridge_task
            except asyncio.CancelledError:
                pass
            logger.info("agent_bridge_task_cancelled")

        if hasattr(app.state, "channel_manager") and app.state.channel_manager:
            await app.state.channel_manager.stop_all()
            logger.info("channel_manager_stopped")

        if hasattr(app.state, "agent_bridge") and app.state.agent_bridge:
            await app.state.agent_bridge.stop()
            logger.info("agent_bridge_stopped")

        if hasattr(app.state, "session_mapper") and app.state.session_mapper:
            await app.state.session_mapper.save()
            cleaned = await app.state.session_mapper.cleanup_expired(ttl_hours=24)
            logger.info("session_mapper_saved_and_cleaned", cleaned_count=cleaned)

        logger.info("social_platform_service_stopped")
    except Exception as e:
        logger.warning("social_platform_service_stop_failed", error=str(e))
