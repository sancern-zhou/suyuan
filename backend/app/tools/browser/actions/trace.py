"""Trace Action Handler (SYNC version)

Handler for trace debugging operations.
"""
import structlog

from ..services.trace_manager import TraceManager

logger = structlog.get_logger()

# Global trace manager instance
_trace_manager = None


def get_trace_manager() -> TraceManager:
    """Get or create global trace manager instance"""
    global _trace_manager
    if _trace_manager is None:
        _trace_manager = TraceManager()
    return _trace_manager


def handle_trace(
    manager,
    action: str = "start",
    name: str = "trace",
    title: str = "Trace",
    session_id: str = "default",
    **kwargs
) -> dict:
    """Handle trace operations

    Args:
        manager: BrowserManager instance
        action: Operation (start/stop/chunk/list)
        name: Trace name
        title: Trace/chunk title
        session_id: Session identifier

    Returns:
        For start:
        {
            "action": "start",
            "trace_path": str,
            "name": str
        }

        For stop:
        {
            "action": "stop",
            "trace_path": str
        }

        For chunk:
        {
            "action": "chunk",
            "started": bool
        }

        For list:
        {
            "action": "list",
            "traces": list,
            "count": int
        }
    """
    trace_mgr = get_trace_manager()

    if action == "start":
        # Start trace recording
        context = manager._contexts.get(session_id)

        if not context:
            raise ValueError(f"No context found for session: {session_id}")

        trace_path = trace_mgr.start_trace(context, name, title)

        return {
            "action": "start",
            "trace_path": trace_path,
            "name": name
        }

    elif action == "stop":
        # Stop trace recording
        context = manager._contexts.get(session_id)

        if not context:
            raise ValueError(f"No context found for session: {session_id}")

        trace_path = trace_mgr.stop_trace(context)

        if trace_path:
            return {
                "action": "stop",
                "trace_path": trace_path
            }
        else:
            return {
                "action": "stop",
                "message": "No active trace to stop"
            }

    elif action == "chunk":
        # Start new trace chunk
        context = manager._contexts.get(session_id)

        if not context:
            raise ValueError(f"No context found for session: {session_id}")

        started = trace_mgr.start_chunk(context, title)

        return {
            "action": "chunk",
            "started": started,
            "title": title
        }

    elif action == "list":
        # List all traces
        traces = trace_mgr.list_traces()

        return {
            "action": "list",
            "traces": traces,
            "count": len(traces)
        }

    else:
        raise ValueError(f"Unknown trace action: {action}. Valid: start, stop, chunk, list")
