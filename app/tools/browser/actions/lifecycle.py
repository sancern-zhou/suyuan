"""
Lifecycle Action Handlers (SYNC version)

Handlers for browser lifecycle operations: start, stop, status.
"""
import uuid
import structlog

logger = structlog.get_logger()


def handle_start(manager, session_id: str = "default", **kwargs) -> dict:
    """Start browser and create session (SYNC version)

    Returns:
        {
            "status": "running",
            "session_id": str,
            "browser_type": str
        }
    """
    # Generate session ID if not provided
    if not session_id or session_id == "default":
        session_id = kwargs.get("session_id", f"session_{uuid.uuid4().hex[:8]}")

    # Ensure browser is started
    manager.get_browser()

    # Create page for session (warm up)
    manager.get_page(session_id)

    logger.info("browser_action_start", session_id=session_id)

    return {
        "status": "running",
        "session_id": session_id,
        "browser_type": "chromium"
    }


def handle_stop(manager, session_id: str = None, **kwargs) -> dict:
    """Stop browser or specific session (SYNC version)

    Args:
        session_id: Session ID to close (None = close all)

    Returns:
        {
            "status": "stopped",
            "sessions_closed": int
        }
    """
    if session_id:
        # Close specific session
        manager.close_session(session_id)
        logger.info("browser_action_stop_session", session_id=session_id)
        return {
            "status": "stopped",
            "sessions_closed": 1,
            "session_id": session_id
        }
    else:
        # Close all sessions and browser
        status_before = manager.get_status()
        session_count = status_before["total_contexts"]

        manager.close_all()

        logger.info("browser_action_stop_all", sessions_closed=session_count)

        return {
            "status": "stopped",
            "sessions_closed": session_count
        }


def handle_status(manager, **kwargs) -> dict:
    """Get browser status (SYNC version)

    Returns:
        {
            "status": str,
            "browser_started": bool,
            "total_contexts": int,
            "total_pages": int,
            "sessions": list
        }
    """
    status_info = manager.get_status()

    # Determine overall status
    if status_info["browser_started"]:
        overall_status = "running"
    else:
        overall_status = "stopped"

    logger.info("browser_action_status", status=overall_status)

    return {
        "status": overall_status,
        **status_info
    }
