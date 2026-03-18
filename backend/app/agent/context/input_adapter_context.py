"""
Input Adapter Context Proxy

为 InputAdapterEngine 提供所需的上下文接口，桥接 HybridMemoryManager、
ExecutionContext 与适配器中的推断逻辑。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()


class InputAdapterContext:
    """
    Adapter 上下文代理

    暴露 InputAdapter 需要的方法：
    - session_memory: 直接返回 HybridMemoryManager.session
    - get_query_params(): 最近一次工具调用的参数
    - get_latest_data_id(): 最近的 data_id
    - get_latest_data(): 最近 data_id 对应的数据
    """

    def __init__(self, memory_manager, execution_context=None) -> None:
        self.memory_manager = memory_manager
        self.execution_context = execution_context

    # ----- 基础属性 -----
    @property
    def session_memory(self):
        return getattr(self.memory_manager, "session", None)

    # ----- Adapter Hooks -----
    def get_query_params(self) -> Dict[str, Any]:
        """返回最近一次工具调用参数（若存在）。"""
        try:
            iterations = self.memory_manager.get_iterations()
            for iteration in reversed(iterations):
                action = iteration.get("action", {})
                if action.get("type") == "TOOL_CALL":
                    args = action.get("args")
                    if isinstance(args, dict) and args:
                        return args
        except Exception as exc:  # pragma: no cover - 防御
            logger.debug("input_adapter_context_query_params_failed", error=str(exc))

        return {}

    def get_latest_data_id(self) -> Optional[str]:
        """返回最近一次保存的数据引用ID。"""
        if self.execution_context and getattr(self.execution_context, "current_data_id", None):
            return self.execution_context.current_data_id

        session = self.session_memory
        if session and session.data_files:
            try:
                return next(reversed(session.data_files.keys()))
            except Exception:  # pragma: no cover - 防御
                pass
        return None

    def get_latest_data(self):
        """加载最近的 data_id 对应的数据内容（若存在）。"""
        session = self.session_memory
        if not session:
            return None

        data_id = self.get_latest_data_id()
        if not data_id:
            return None

        try:
            return session.load_data_from_file(data_id)
        except Exception as exc:  # pragma: no cover - 防御
            logger.debug("input_adapter_context_load_data_failed", error=str(exc))
            return None

