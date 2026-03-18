"""Tab Management Action Handlers (SYNC version)

Handlers for tabs, open, focus, close operations
"""
import structlog

from ..config import config

logger = structlog.get_logger()


def handle_tabs(manager, session_id: str = "default", **kwargs) -> dict:
    """List open tabs (SYNC version)

    Args:
        manager: BrowserManager instance
        session_id: Session identifier

    Returns:
        {
            "tabs": list,
            "count": int
        }
    """
    sessions = manager.list_sessions()

    logger.info("browser_tabs_listed", session_id=session_id, count=len(sessions))

    return {
        "tabs": sessions,
        "count": len(sessions)
    }


def handle_open(manager, url: str, session_id: str = "default", **kwargs) -> dict:
    """Open URL in browser (SYNC version)

    Args:
        manager: BrowserManager instance
        url: URL to navigate to
        session_id: Session identifier

    Returns:
        {
            "url": str,
            "title": str
        }
    """
    if not url:
        raise ValueError("url is required for open action")

    page = manager.get_active_page(session_id)
    page.goto(url, timeout=config.NAVIGATION_TIMEOUT, wait_until="domcontentloaded")
    title = page.title()

    logger.info("browser_opened_url", session_id=session_id, url=url, title=title)

    return {
        "url": url,
        "title": title
    }


def handle_focus(manager, tab_id: str = "default", **kwargs) -> dict:
    """Focus on a specific tab (SYNC version)

    Args:
        manager: BrowserManager instance
        tab_id: Tab/session identifier

    Returns:
        {
            "tab_id": str,
            "focused": bool
        }
    """
    # Check if tab exists
    sessions = manager.list_sessions()
    exists = tab_id in sessions

    if exists:
        # Get page to ensure it's active
        manager.get_active_page(tab_id)
        logger.info("browser_tab_focused", tab_id=tab_id)

    return {
        "tab_id": tab_id,
        "focused": exists
    }


def handle_close(manager, tab_id: str = "default", **kwargs) -> dict:
    """Close a tab (SYNC version)

    Args:
        manager: BrowserManager instance
        tab_id: Tab/session identifier

    Returns:
        {
            "tab_id": str,
            "closed": bool
        }
    """
    closed = manager.close_session(tab_id)

    if closed:
        logger.info("browser_tab_closed", tab_id=tab_id)
    else:
        logger.warning("browser_tab_not_found", tab_id=tab_id)

    return {
        "tab_id": tab_id,
        "closed": closed
    }
