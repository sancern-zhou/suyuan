"""
Execution Context for Tool Invocation

This module provides a context object that is injected into every tool execution,
enabling tools to access data, memory, and session information without requiring
explicit parameter passing through the LLM.

Key Benefits:
- Tools can load data by reference (data_id) instead of receiving full payloads
- Type-safe data access with schema validation
- Session isolation and iteration tracking
- Unified data lifecycle management
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import structlog

if TYPE_CHECKING:
    from app.agent.context.data_context_manager import DataContextManager
    from app.agent.context.typed_data_handle import TypedDataHandle

logger = structlog.get_logger()


class ExecutionContext:
    """
    Tool execution context providing data access and session information.

    This context is automatically injected into all tool execute() methods,
    allowing tools to:
    - Load data by reference without seeing full payloads
    - Save computed results for downstream tools
    - Access session and iteration metadata

    Example:
        async def execute(self, context: ExecutionContext, station_name: str, data_id: str):
            # Load data by reference
            vocs_data = context.get_data(data_id, expected_schema="vocs")

            # Process and save results
            result = compute_pmf(vocs_data)
            result_id = context.save_data(result, schema="pmf_result")

            return {"success": True, "data_id": result_id}
    """

    def __init__(
        self,
        session_id: str,
        iteration: int,
        data_manager: DataContextManager,
        task_list: Optional[Any] = None,
        todo_list: Optional[Any] = None,
    ) -> None:
        """
        Initialize execution context.

        Args:
            session_id: Current session identifier
            iteration: Current iteration number in ReAct loop
            data_manager: Data context manager instance
            task_list: Task list instance for task management tools (legacy)
            todo_list: Todo list instance for new TodoWrite tool
        """
        self.session_id = session_id
        self.iteration = iteration
        self.data_manager = data_manager
        self.task_list = task_list or todo_list  # Support both old and new
        # 跟踪最近一次保存的data_id
        self.current_data_id: Optional[str] = None
        # 跟踪所有可用的data_id列表
        self.available_data_ids: List[str] = []

        logger.debug(
            "execution_context_created",
            session_id=session_id,
            iteration=iteration,
            has_task_list=task_list is not None,
            has_todo_list=todo_list is not None
        )

    def get_data(
        self,
        data_id: str,
        expected_schema: Optional[str] = None
    ) -> Any:
        """
        Load data by reference ID.

        Args:
            data_id: Data identifier (e.g., "vocs:v1:abc123")
            expected_schema: Expected schema for validation (e.g., "vocs")

        Returns:
            Loaded data (typically List[Pydantic model])

        Raises:
            KeyError: Data ID not found
            ValueError: Schema mismatch

        Example:
            vocs_data = context.get_data("vocs:v1:abc123", expected_schema="vocs")
        """
        logger.info(
            "context_loading_data",
            data_id=data_id,
            expected_schema=expected_schema,
            session_id=self.session_id
        )

        return self.data_manager.get_data(
            data_id=data_id,
            expected_schema=expected_schema
        )

    def get_raw_data(self, data_id: str) -> List[Dict[str, Any]]:
        """
        Load raw data without deserializing to Pydantic models.

        This method returns data in its original dictionary format, which is useful
        for analysis results (PMF, OBM) that are already in standard dictionary format.

        Args:
            data_id: Data identifier (e.g., "pmf_result:v1:abc123")

        Returns:
            List of dictionaries (raw data)

        Raises:
            KeyError: Data ID not found

        Example:
            # Get PMF result as raw dictionary
            pmf_result = context.get_raw_data("pmf_result:v1:abc123")
            # Returns [{'sources': [...], 'timeseries': [...], ...}]
        """
        logger.info(
            "context_loading_raw_data",
            data_id=data_id,
            session_id=self.session_id
        )

        return self.data_manager.get_raw_data(data_id)

    def save_data(
        self,
        data: Any,
        schema: str,
        field_stats: Optional[List[Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Save data and return a reference ID.

        Args:
            data: Data to save (should be List[Pydantic model] for validation)
            schema: Data schema identifier (e.g., "vocs", "pmf_result")
            field_stats: Optional field statistics for validation
            metadata: Optional metadata to attach

        Returns:
            Data reference ID (e.g., "vocs:v1:abc123")

        Example:
            result_id = context.save_data(
                data=pmf_results,
                schema="pmf_result",
                metadata={"station": "Shenzhen", "pollutant": "VOCs"}
            )
        """
        logger.info(
            "context_saving_data",
            schema=schema,
            session_id=self.session_id
        )

        # ✅ save_data() 返回字典 {"data_id": str, "file_path": str}
        saved_ref = self.data_manager.save_data(
            data=data,
            schema=schema,
            field_stats=field_stats,
            metadata=metadata
        )

        # ✅ 提取字符串 ID
        if isinstance(saved_ref, dict):
            data_id = saved_ref.get("data_id")
        else:
            data_id = saved_ref

        # ✅ 直接使用字符串ID进行跟踪
        self.current_data_id = data_id
        if data_id not in self.available_data_ids:
            self.available_data_ids.append(data_id)

        logger.info(
            "context_data_id_updated",
            data_id=data_id,
            available_count=len(self.available_data_ids),
            session_id=self.session_id
        )

        return data_id

    def get_handle(self, data_id: str) -> TypedDataHandle:
        """
        Get data handle without loading full data.

        This is useful for inspecting metadata, checking schema compatibility,
        or validating data quality before loading.

        Args:
            data_id: Data identifier

        Returns:
            TypedDataHandle with metadata

        Example:
            handle = context.get_handle("vocs:v1:abc123")
            if handle.record_count < 30:
                return {"success": False, "error": "Insufficient samples"}
        """
        return self.data_manager.get_handle(data_id)

    def get_task_list(self) -> Optional[Any]:
        """
        Get task list instance for task management.

        Returns:
            TaskList instance if available, None otherwise

        Example:
            task_list = context.get_task_list()
            if task_list:
                tasks = task_list.get_tasks(context.session_id)
        """
        return self.task_list  # ✅ 返回None而不是抛异常，支持"无任务"场景

    def get_todo_list(self) -> Optional[Any]:
        """
        Get todo list instance for TodoWrite tool.

        Returns:
            TodoList instance if available, None otherwise

        Example:
            todo_list = context.get_todo_list()
            if todo_list:
                items = todo_list.get_items()
        """
        return self.task_list  # TodoList uses the same slot as TaskList

    def list_data(self, schema: Optional[str] = None) -> List[str]:
        """
        List all available data IDs in current session.

        Args:
            schema: Optional schema filter (e.g., "vocs")

        Returns:
            List of data IDs

        Example:
            all_vocs = context.list_data(schema="vocs")
        """
        return self.data_manager.list_data(schema=schema)

    def exists(self, data_id: str) -> bool:
        """
        Check if data ID exists.

        Args:
            data_id: Data identifier

        Returns:
            True if data exists
        """
        return self.data_manager.exists(data_id)

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get context metadata for debugging/logging."""
        return {
            "session_id": self.session_id,
            "iteration": self.iteration,
        }

    def __repr__(self) -> str:
        return (
            f"<ExecutionContext session={self.session_id} "
            f"iteration={self.iteration}>"
        )

    def copy(self, **updates) -> "ExecutionContext":
        """
        Create a copy of the execution context with optional updates.

        This is useful for tools that need to modify the context temporarily
        without affecting the original context.

        Args:
            **updates: Optional fields to update in the copied context

        Returns:
            A new ExecutionContext instance

        Example:
            # Create a copy with a different iteration
            new_context = context.copy(iteration=5)
        """
        # Create a new instance with the same attributes
        copied = ExecutionContext(
            session_id=updates.get("session_id", self.session_id),
            iteration=updates.get("iteration", self.iteration),
            data_manager=updates.get("data_manager", self.data_manager),
            task_list=updates.get("task_list", self.task_list),
        )

        # Copy over the tracking attributes
        copied.current_data_id = updates.get("current_data_id", self.current_data_id)
        copied.available_data_ids = list(updates.get("available_data_ids", self.available_data_ids))

        return copied
