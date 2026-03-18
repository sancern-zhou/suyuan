"""
Snapshot Action Handler (SYNC version)

Handler for snapshot operation (text extraction)
"""
import structlog

from ..config import config

logger = structlog.get_logger()


def handle_snapshot(manager, session_id: str = "default", **kwargs) -> dict:
    """Get page snapshot (text-only, LLM-friendly) (SYNC version)

    Args:
        manager: BrowserManager instance
        session_id: Session identifier
        max_length: Max content length (overrides config)

    Returns:
        {
            "content": str,  # Page text content
            "title": str,
            "url": str,
            "length": int
        }
    """
    page = manager.get_page(session_id)

    # Get max length
    max_length = kwargs.get("max_length", config.MAX_CONTENT_LENGTH)

    # Extract content
    snapshot_data = page.evaluate(f"""(maxLen) => {{
        return {{
            title: document.title,
            url: window.location.href,
            content: document.body.innerText.substring(0, maxLen),
            meta: {{
                charset: document.characterSet,
                lang: document.documentElement.lang
            }}
        }};
    }}""", max_length)

    content_length = len(snapshot_data["content"])

    logger.info(
        "browser_action_snapshot",
        session_id=session_id,
        title=snapshot_data["title"],
        content_length=content_length
    )

    return {
        "content": snapshot_data["content"],
        "title": snapshot_data["title"],
        "url": snapshot_data["url"],
        "length": content_length,
        "meta": snapshot_data["meta"]
    }
