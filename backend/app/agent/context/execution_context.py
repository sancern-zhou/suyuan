"""
Execution Context for Tool Invocation

This module provides a context object that is injected into every tool execution,
enabling tools to access data, memory, and session information without requiring
explicit parameter passing through the LLM.

Key Benefits:
- Tools can load data from session-scoped paths instead of receiving full payloads
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
        async def execute(self, context: ExecutionContext, station_name: str, file_path: str):
            # Load data from the session file
            vocs_data = context.get_data(file_path, expected_schema="vocs")

            # Process and save results
            result = compute_pmf(vocs_data)
            result_path = context.save_data(result, schema="pmf_result")

            return {"success": True, "file_path": result_path}
    """

    def __init__(
        self,
        session_id: str,
        iteration: int,
        data_manager: DataContextManager,
        task_list: Optional[Any] = None,
    ) -> None:
        """
        Initialize execution context.

        Args:
            session_id: Current session identifier
            iteration: Current iteration number in ReAct loop
            data_manager: Data context manager instance
            task_list: Task list instance for task management tools
        """
        self.session_id = session_id
        self.iteration = iteration
        self.data_manager = data_manager
        self.task_list = task_list
        self.current_file_path: Optional[str] = None
        self.available_file_paths: List[str] = []
        # Durable session inputs (uploads etc.) authorized for sandbox staging.
        # Separate from available_file_paths, which doubles as output declarations.
        self.authorized_input_paths: List[str] = []

        logger.debug(
            "execution_context_created",
            session_id=session_id,
            iteration=iteration,
            has_task_list=task_list is not None,
        )

    def get_data(
        self,
        file_path: str,
        expected_schema: Optional[str] = None
    ) -> Any:
        """
        Load data from an immutable session file.

        Args:
            file_path: Canonical absolute session data path
            expected_schema: Expected schema for validation (e.g., "vocs")

        Returns:
            Loaded data (typically List[Pydantic model])

        Raises:
            KeyError: Data file not found
            ValueError: Schema mismatch

        Example:
            vocs_data = context.get_data("/configured/data/root/sessions/agent_session_123/data/vocs--abc.json", expected_schema="vocs")
        """
        logger.info(
            "context_loading_data",
            file_path=file_path,
            expected_schema=expected_schema,
            session_id=self.session_id
        )

        return self.data_manager.get_data(
            file_path=file_path,
            expected_schema=expected_schema
        )

    def get_raw_data(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Load raw data without deserializing to Pydantic models.

        This method returns data in its original dictionary format, which is useful
        for analysis results (PMF, OBM) that are already in standard dictionary format.

        Args:
            file_path: Canonical absolute session data path

        Returns:
            List of dictionaries (raw data)

        Raises:
            KeyError: Session file not found or not authorized

        Example:
            # Get PMF result as raw dictionary
            pmf_result = context.get_raw_data("/absolute/session/path/pmf_result.json")
            # Returns [{'sources': [...], 'timeseries': [...], ...}]
        """
        logger.info(
            "context_loading_raw_data",
            file_path=file_path,
            session_id=self.session_id
        )

        return self.data_manager.get_raw_data(file_path)

    def get_data_payload(self, file_path: str) -> Any:
        """Load an authorized session file without record-shape coercion."""
        logger.info(
            "context_loading_data_payload",
            file_path=file_path,
            session_id=self.session_id,
        )
        return self.data_manager.get_data_payload(file_path)

    def save_data(
        self,
        data: Any,
        schema: str,
        field_stats: Optional[List[Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Save data and return its canonical absolute file path.

        Args:
            data: Data to save (should be List[Pydantic model] for validation)
            schema: Data schema identifier (e.g., "vocs", "pmf_result")
            field_stats: Optional field statistics for validation
            metadata: Optional metadata to attach

        Returns:
            Canonical absolute path of the saved session data file.

        Example:
            result_path = context.save_data(
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

        file_path = self.data_manager.save_data(
            data=data,
            schema=schema,
            field_stats=field_stats,
            metadata=metadata
        )

        if not file_path:
            raise ValueError(f"Data manager returned an empty file path for schema: {schema}")

        self.current_file_path = file_path
        if file_path not in self.available_file_paths:
            self.available_file_paths.append(file_path)

        logger.info(
            "context_data_file_updated",
            file_path=file_path,
            available_count=len(self.available_file_paths),
            session_id=self.session_id
        )

        return file_path

    def get_handle(self, file_path: str) -> TypedDataHandle:
        """
        Get data handle without loading full data.

        This is useful for inspecting metadata, checking schema compatibility,
        or validating data quality before loading.

        Args:
            file_path: Canonical absolute session data path

        Returns:
            TypedDataHandle with metadata

        Example:
            handle = context.get_handle("/configured/data/root/sessions/agent_session_123/data/vocs--abc.json")
            if handle.record_count < 30:
                return {"success": False, "error": "Insufficient samples"}
        """
        return self.data_manager.get_handle(file_path)

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

    def list_data(self, schema: Optional[str] = None) -> List[str]:
        """
        List all available data file paths in current session.

        Args:
            schema: Optional schema filter (e.g., "vocs")

        Returns:
            List of canonical absolute data file paths

        Example:
            all_vocs = context.list_data(schema="vocs")
        """
        return self.data_manager.list_data(schema=schema)

    def exists(self, file_path: str) -> bool:
        """
        Check whether a session data file exists.

        Args:
            file_path: Canonical absolute session data path

        Returns:
            True if data exists
        """
        return self.data_manager.exists(file_path)

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
        copied.current_file_path = updates.get("current_file_path", self.current_file_path)
        copied.available_file_paths = list(updates.get("available_file_paths", self.available_file_paths))
        copied.authorized_input_paths = list(updates.get("authorized_input_paths", self.authorized_input_paths))

        return copied
