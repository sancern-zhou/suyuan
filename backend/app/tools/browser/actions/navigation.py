"""Navigation Action Handler (SYNC version)

Handler for navigate operation (alias for open)
"""
import structlog

from ..config import config

logger = structlog.get_logger()


def handle_navigate(manager, url: str, session_id: str = "default", **kwargs) -> dict:
    """Navigate to URL (SYNC version)

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
        raise ValueError("url is required for navigate action")

    page = manager.get_active_page(session_id)
    page.goto(url, timeout=config.NAVIGATION_TIMEOUT, wait_until="domcontentloaded")
    title = page.title()

    logger.info("browser_navigated", session_id=session_id, url=url, title=title)

    return {
        "url": url,
        "title": title
    }
