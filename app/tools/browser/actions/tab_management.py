"""
Tab Management Action Handlers (SYNC version)

Handlers for tab management operations: tabs, open, focus, close
"""
import structlog
from typing import Dict, List

from ..config import config

logger = structlog.get_logger()


def handle_tabs(manager, session_id: str = "default", **kwargs) -> dict:
    """List all open tabs (SYNC version)

    Args:
        session_id: Session identifier

    Returns:
        {
            "count": int,
            "tabs": [
                {"id": str, "url": str, "title": str}
            ]
        }
    """
    status_info = manager.get_status()

    # Get tabs for this session
    session_tabs = []
    for sid, page in list(manager._pages.items()):
        if sid == session_id or sid.startswith(f"{session_id}_"):
            try:
                title = page.title()
                url = page.url
                session_tabs.append({
                    "id": sid,
                    "url": url,
                    "title": title
                })
            except Exception as e:
                logger.warning("tab_info_failed", session_id=sid, error=str(e))

    logger.info("browser_action_tabs", session_id=session_id, count=len(session_tabs))

    return {
        "count": len(session_tabs),
        "tabs": session_tabs
    }


def handle_open(manager, url: str, session_id: str = "default", **kwargs) -> dict:
    """Open new tab and navigate to URL (SYNC version)

    Args:
        url: URL to navigate to
        session_id: Session identifier

    Returns:
        {
            "tab_id": str,
            "url": str,
            "title": str
        }
    """
    # Validate URL
    if not url:
        raise ValueError("URL is required for open action")

    # Check URL whitelist
    if config.URL_WHITELIST:
        if not any(url.startswith(allowed) for allowed in config.URL_WHITELIST):
            raise ValueError(f"URL not in whitelist: {url}")

    # Check URL scheme
    if not any(url.startswith(scheme + "://") for scheme in config.ALLOWED_SCHEMES):
        raise ValueError(f"URL scheme not allowed: {url}")

    # Get page (creates new page if needed)
    page = manager.get_page(session_id)

    # Navigate
    timeout = kwargs.get("timeout", config.NAVIGATION_TIMEOUT)
    page.goto(url, timeout=timeout)

    # Get page info
    title = page.title()

    logger.info(
        "browser_action_open",
        session_id=session_id,
        url=url,
        title=title
    )

    return {
        "tab_id": session_id,
        "url": page.url,
        "title": title
    }


def handle_focus(manager, tab_id: str, session_id: str = "default", **kwargs) -> dict:
    """Focus specific tab (SYNC version)

    Args:
        tab_id: Tab ID to focus
        session_id: Current session identifier

    Returns:
        {
            "tab_id": str,
            "url": str,
            "title": str
        }
    """
    if not tab_id:
        raise ValueError("tab_id is required for focus action")

    # Check if tab exists
    if tab_id not in manager._pages:
        raise ValueError(f"Tab not found: {tab_id}")

    page = manager._pages[tab_id]

    # Bring page to front
    page.bring_to_front()

    # Get page info
    title = page.title()

    logger.info("browser_action_focus", tab_id=tab_id, title=title)

    return {
        "tab_id": tab_id,
        "url": page.url,
        "title": title
    }


def handle_close(manager, tab_id: str = None, session_id: str = "default", **kwargs) -> dict:
    """Close tab (SYNC version)

    Args:
        tab_id: Tab ID to close (None = close current session tab)
        session_id: Session identifier

    Returns:
        {
            "tab_id": str,
            "closed": bool
        }
    """
    # Default to session tab
    if not tab_id:
        tab_id = session_id

    # Check if tab exists
    if tab_id not in manager._pages:
        raise ValueError(f"Tab not found: {tab_id}")

    page = manager._pages[tab_id]

    # Close page
    page.close()

    # Remove from pages dict
    del manager._pages[tab_id]

    logger.info("browser_action_close", tab_id=tab_id)

    return {
        "tab_id": tab_id,
        "closed": True
    }
