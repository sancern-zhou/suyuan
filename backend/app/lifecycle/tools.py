"""LLM tool lifecycle extracted from app/main.py.

Dependency note:
- Tool initialization is independent of the database.
- Agent instances are refreshed after the global tool registry has been checked.
- Scheduled tasks and social channels create Agents, so this should run before
  those services are started.
"""

import structlog

from app.services.lifecycle_manager import initialize_llm_tools

logger = structlog.get_logger()


async def initialize_tools_and_agents() -> None:
    """Initialize LLM tools and refresh global Agent instances."""
    try:
        initialize_llm_tools()
        logger.info("llm_tools_initialized")

        try:
            from app.routers.agent import (
                data_viz_agent_instance,
                meteorology_expert_agent_instance,
                multi_expert_agent_instance,
            )

            logger.info("refreshing_global_agent_tools")

            multi_expert_agent_instance.refresh_tools()
            meteorology_expert_agent_instance.refresh_tools()
            data_viz_agent_instance.refresh_tools()

            logger.info(
                "global_agents_refreshed",
                multi_expert_tools=len(multi_expert_agent_instance.get_available_tools()),
                meteorology_tools=len(meteorology_expert_agent_instance.get_available_tools()),
                data_viz_tools=len(data_viz_agent_instance.get_available_tools()),
            )
        except Exception as e:
            logger.warning("agent_refresh_failed", error=str(e))

    except Exception as e:
        logger.error("llm_tools_initialization_failed", error=str(e), exc_info=True)
        logger.warning("continuing_without_llm_tools")

