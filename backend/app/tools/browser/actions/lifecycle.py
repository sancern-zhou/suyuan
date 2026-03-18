"""Lifecycle Action Handlers (SYNC version)

Handlers for start, stop, status operations
"""
import structlog

logger = structlog.get_logger()


def handle_start(manager, session_id: str = "default", **kwargs) -> dict:
    """Handle browser start (SYNC version)

    Args:
        manager: BrowserManager instance
        session_id: Session identifier

    Returns:
        {
            "status": str,
            "session_id": str
        }
    """
    import threading

    logger.info(
        "[LIFECYCLE] handle_start called",
        session_id=session_id,
        thread_id=threading.get_ident(),
        manager_type=type(manager).__name__
    )

    try:
        # Trigger browser start by getting a page
        logger.info("[LIFECYCLE] calling get_page")
        page = manager.get_active_page(session_id)
        logger.info("[LIFECYCLE] get_page returned", page_type=type(page).__name__)

        logger.info("[LIFECYCLE] getting status")
        status = manager.get_status()
        logger.info("[LIFECYCLE] status obtained", status=status)

        logger.info(
            "browser_started",
            session_id=session_id,
            active_sessions=status["active_sessions"]
        )

        return {
            "status": status["status"],
            "session_id": session_id,
            "active_sessions": status["active_sessions"]
        }
    except Exception as e:
        logger.error(
            "[LIFECYCLE] handle_start failed",
            session_id=session_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise


def handle_stop(manager, **kwargs) -> dict:
    """Handle browser stop (SYNC version)

    Args:
        manager: BrowserManager instance

    Returns:
        {
            "status": str,
            "sessions_closed": int
        }
    """
    sessions_closed = manager.stop_browser()

    logger.info("browser_stopped", sessions_closed=sessions_closed)

    return {
        "status": "stopped",
        "sessions_closed": sessions_closed
    }


def handle_status(manager, **kwargs) -> dict:
    """Handle browser status query (SYNC version)

    Args:
        manager: BrowserManager instance

    Returns:
        {
            "status": str,
            "active_sessions": int,
            "active_pages": int
        }
    """
    return manager.get_status()
