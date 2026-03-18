"""
Screenshot Action Handler (SYNC version)

Handler for screenshot operation (image capture with text description)
"""
import structlog

from ..config import config

logger = structlog.get_logger()


def handle_screenshot(manager, session_id: str = "default", **kwargs) -> dict:
    """Capture screenshot with text description (SYNC version)

    Args:
        session_id: Session identifier
        full_page: Capture full page (default: False)

    Returns:
        {
            "image_url": str,
            "description": str  # LLM-readable description
        }
    """
    from app.services.image_cache import ImageCache

    page = manager.get_page(session_id)

    # Capture screenshot
    full_page = kwargs.get("full_page", False)  # Default to viewport-only
    screenshot_bytes = page.screenshot(
        full_page=full_page,
        type=config.SCREENSHOT_FORMAT
    )

    # Save to image cache
    image_id = ImageCache.save(screenshot_bytes, format=config.SCREENSHOT_FORMAT)

    # Generate text description (for LLM)
    description = page.evaluate("""() => {
        const title = document.title;
        const url = window.location.href;
        const bodyText = document.body.innerText.substring(0, 300);

        return `Page Title: ${title}
URL: ${url}

Page Description: This screenshot shows the webpage "${title}" at ${url}.
${bodyText}`;
    }""")

    logger.info(
        "browser_action_screenshot",
        session_id=session_id,
        image_id=image_id,
        description_length=len(description)
    )

    return {
        "image_url": f"/api/image/{image_id}",
        "description": description.strip(),
        "format": config.SCREENSHOT_FORMAT
    }
