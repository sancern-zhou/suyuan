"""
ReAct loop compatibility facade.

The execution engine lives in ``app.agent.runtime``.  This module keeps the
historical ``ReActLoop`` entry point used by callers while avoiding a second,
stale loop implementation in ``core``.
"""

import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional

import structlog

from ..context.context_builder import SimplifiedContextBuilder
from ..memory.hybrid_manager import HybridMemoryManager
from ..runtime import AgentRuntime, AgentRuntimeConfig
from ...utils.agent_logger import AgentLogger
from .schema_injection import SchemaInjector

logger = structlog.get_logger()


class ReActLoop:
    """
    Compatibility wrapper for the decomposed ReAct runtime.

    ``react_agent.py`` and public imports still construct ``ReActLoop``.  The
    actual loop, tool coordination, transcript writes, and finalization are
    delegated to ``AgentRuntime``.
    """

    def __init__(
        self,
        memory_manager: HybridMemoryManager,
        llm_planner,
        tool_executor,
        max_iterations: int = 120,
        stream_enabled: bool = True,
        enable_agent_logging: bool = True,
        log_dir: str = "./logs/agent_runs",
        enable_reasoning: bool = False,
        is_interruption: bool = False,
        knowledge_base_ids: Optional[list] = None,
        cancel_event: Optional[asyncio.Event] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        auto_profile: Optional[str] = None,
    ):
        self.memory = memory_manager
        self.planner = llm_planner
        self.executor = tool_executor
        self.max_iterations = max_iterations
        self.stream_enabled = stream_enabled
        self.is_interruption = is_interruption
        self.knowledge_base_ids = knowledge_base_ids
        self.cancel_event = cancel_event
        self.attachments = attachments
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.auto_profile = auto_profile

        self.enable_agent_logging = enable_agent_logging
        self.agent_logger = (
            AgentLogger(log_dir=log_dir, enable_file_logging=enable_agent_logging)
            if enable_agent_logging
            else None
        )

        llm_client = llm_planner.llm_service if hasattr(llm_planner, "llm_service") else None
        self.context_builder = SimplifiedContextBuilder(
            llm_client=llm_client,
            memory_manager=memory_manager,
            tool_registry=tool_executor.tool_registry if hasattr(tool_executor, "tool_registry") else None,
        )

        self.enable_reasoning = enable_reasoning
        self.current_mode = "expert"
        self.schema_injector = SchemaInjector(consecutive_error_threshold=2)

        logger.info(
            "react_loop_initialized",
            session_id=memory_manager.session_id,
            max_iterations=max_iterations,
            agent_logging=enable_agent_logging,
            enable_reasoning=enable_reasoning,
            knowledge_base_ids=knowledge_base_ids,
            runtime="decomposed",
        )

    async def run(
        self,
        user_query: str,
        enhance_with_history: bool = True,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
        manual_mode: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        self.current_mode = manual_mode or "expert"

        logger.info(
            "react_loop_mode_selected",
            mode=self.current_mode,
            manual_override=manual_mode is not None,
        )

        runtime = AgentRuntime(AgentRuntimeConfig(
            memory_manager=self.memory,
            planner=self.planner,
            tool_executor=self.executor,
            context_builder=self.context_builder,
            max_iterations=self.max_iterations,
            enhance_with_history=enhance_with_history,
            enable_reasoning=self.enable_reasoning,
            is_interruption=self.is_interruption,
            knowledge_base_ids=self.knowledge_base_ids,
            agent_logger=self.agent_logger,
            schema_injector=self.schema_injector,
            cancel_event=self.cancel_event,
            attachments=self.attachments,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            auto_profile=self.auto_profile,
            runtime_mode=self.current_mode,
            user_identifier=getattr(self.executor, "user_identifier", None),
            board_context=self.context_builder.board_context if self.current_mode == "board" else None,
        ))

        async for event in runtime.run(
            user_query=user_query,
            initial_messages=initial_messages,
            mode=self.current_mode,
        ):
            event["mode"] = self.current_mode
            yield event

    def get_memory_stats(self) -> Dict[str, Any]:
        session = self.memory.session
        return {
            "working_iterations": len(getattr(self.memory, "recent_iterations", [])),
            "compressed_iterations": len(getattr(session, "compressed_iterations", [])),
            "data_files": len(getattr(session, "data_files", [])),
            "session_id": self.memory.session_id,
        }

    def get_agent_log_summary(self) -> Optional[Dict[str, Any]]:
        if self.agent_logger:
            return self.agent_logger.get_run_summary()
        return None

    def get_enhanced_stats(self) -> Dict[str, Any]:
        stats = self.get_memory_stats()
        if self.agent_logger:
            stats["current_run"] = self.agent_logger.get_run_summary()
        return stats

    def __repr__(self) -> str:
        return f"<ReActLoop session={self.memory.session_id} max_iter={self.max_iterations}>"
