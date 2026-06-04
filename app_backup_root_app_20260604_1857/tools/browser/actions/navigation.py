"""
Navigation Action Handler (SYNC version)

Handler for navigate operation (alias for open)
"""
import structlog

logger = structlog.get_logger()


def handle_navigate(manager, url: str, session_id: str = "default", **kwargs) -> dict:
    """Navigate to URL (alias for open action) (SYNC version)

    Args:
        url: URL to navigate to
        session_id: Session identifier

    Returns:
        {
            "title": str,
            "url": str,
            "content": str,  # Page text (LLM-readable)
            "links": list
        }
    """
    # Import open handler
    from .tab_management import handle_open
    from ..config import config

    # Navigate to URL
    result = handle_open(manager, url=url, session_id=session_id, **kwargs)

    # Get page for content extraction
    page = manager.get_page(session_id)

    # Extract LLM-readable content
    content_data = page.evaluate(f"""() => {{
        return {{
            title: document.title,
            url: window.location.href,
            content: document.body.innerText.substring(0, {config.MAX_CONTENT_LENGTH}),
            links: Array.from(document.querySelectorAll('a'))
                .slice(0, {config.MAX_LINKS})
                .map(a => ({{
                    text: a.textContent.trim(),
                    href: a.href
                }}))
                .filter(link => link.text && link.href)
        }};
    }}""")

    logger.info(
        "browser_action_navigate",
        url=url,
        title=content_data["title"],
        content_length=len(content_data["content"])
    )

    return {
        "title": content_data["title"],
        "url": content_data["url"],
        "content": content_data["content"],
        "links": content_data["links"]
    }
