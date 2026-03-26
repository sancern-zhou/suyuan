"""Command-line interface for social platform integration.

使用方式：

方式1：集成到主应用（推荐）
----------------------------
社交平台服务已集成到主FastAPI应用中，无需单独启动：

    cd backend
    python -m uvicorn app.main:app --reload

主应用启动时会自动启动社交平台服务（根据config/social_config.yaml配置）。

方式2：独立CLI服务（开发调试用）
----------------------------
也可以作为独立服务运行：

    cd backend
    python -m app.social.cli

注意：独立CLI模式与主应用模式不能同时运行，会冲突。

配置文件：config/social_config.yaml
"""

import asyncio
import sys
from pathlib import Path

import structlog

from config.settings import settings
from app.social.config import SocialConfig
from app.social.message_bus import MessageBus
from app.social.session_mapper import SessionMapper
from app.social.agent_bridge import AgentBridge
from app.channels.manager import ChannelManager
from app.agent.react_agent import create_react_agent

logger = structlog.get_logger(__name__)


async def main():
    """Main entry point for social platform integration."""
    # Configure logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logger.info("Starting social platform integration")

    # Load configuration
    logger.info("Loading configuration")
    social_config = SocialConfig.load_from_yaml(settings.social_config_path)

    if not any([social_config.qq.enabled, social_config.weixin.enabled,
                social_config.dingtalk.enabled, social_config.wecom.enabled]):
        logger.warning("No social platforms enabled. Please enable at least one platform in config/social_config.yaml")
        return

    # Initialize components
    logger.info("Initializing message bus")
    message_bus = MessageBus()

    logger.info("Initializing session mapper")
    session_mapper = SessionMapper(
        data_dir=settings.data_registry_dir
    )
    await session_mapper.load()

    logger.info("Initializing ReActAgent")
    agent = await create_react_agent()

    logger.info("Initializing agent bridge")
    agent_bridge = AgentBridge(
        message_bus=message_bus,
        agent=agent,
        session_mapper=session_mapper,
        mode="social"  # ⚠️ Social模式：移动端呼吸式Agent
    )

    logger.info("Initializing channel manager")
    channel_manager = ChannelManager(social_config, message_bus)

    # Start agent bridge
    logger.info("Starting agent bridge")
    await agent_bridge.start()

    # Start channels (this will block)
    try:
        logger.info("Starting all channels")
        await channel_manager.start_all()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error("Error in channel manager", error=str(e), exc_info=True)
    finally:
        # Cleanup
        logger.info("Stopping social platform integration")
        await agent_bridge.stop()
        await channel_manager.stop_all()
        await session_mapper.save()

        # Cleanup expired sessions
        cleaned = await session_mapper.cleanup_expired(ttl_hours=24)
        logger.info("Cleaned expired sessions", count=cleaned)

    logger.info("Social platform integration stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Fatal error", error=str(e), exc_info=True)
        sys.exit(1)
