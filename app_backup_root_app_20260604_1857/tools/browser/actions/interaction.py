"""
Interaction Action Handler

Handler for act operation (click, type, scroll)
"""
import structlog

from ..config import config

logger = structlog.get_logger()


async def handle_act(
    manager,
    selector: str = None,
    text: str = None,
    click: bool = False,
    scroll: str = None,
    session_id: str = "default",
    **kwargs
) -> dict:
    """Perform interaction action (click, type, scroll)

    Args:
        selector: CSS selector for element
        text: Text to type
        click: Click element
        scroll: Scroll direction (up/down/top/bottom)
        session_id: Session identifier

    Returns:
        {
            "action": str,
            "selector": str,
            "result": str
        }
    """
    page = await manager.get_page(session_id)

    action_performed = None
    result_message = ""

    # Scroll action
    if scroll:
        action_performed = "scroll"

        if scroll == "up":
            await page.evaluate("window.scrollBy(0, -500)")
            result_message = "Scrolled up 500px"
        elif scroll == "down":
            await page.evaluate("window.scrollBy(0, 500)")
            result_message = "Scrolled down 500px"
        elif scroll == "top":
            await page.evaluate("window.scrollTo(0, 0)")
            result_message = "Scrolled to top"
        elif scroll == "bottom":
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            result_message = "Scrolled to bottom"

        logger.info("browser_action_scroll", direction=scroll, session_id=session_id)

    # Type action
    elif text:
        if not selector:
            raise ValueError("selector is required for type action")

        action_performed = "type"

        try:
            await page.fill(selector, text, timeout=config.DEFAULT_TIMEOUT)
            result_message = f"Typed text into {selector}"
        except Exception as e:
            raise RuntimeError(f"Failed to type into {selector}: {str(e)}")

        logger.info(
            "browser_action_type",
            selector=selector,
            text_length=len(text),
            session_id=session_id
        )

    # Click action
    elif click:
        if not selector:
            raise ValueError("selector is required for click action")

        action_performed = "click"

        try:
            await page.click(selector, timeout=config.DEFAULT_TIMEOUT)
            result_message = f"Clicked {selector}"
        except Exception as e:
            raise RuntimeError(f"Failed to click {selector}: {str(e)}")

        logger.info("browser_action_click", selector=selector, session_id=session_id)

    else:
        raise ValueError("One of text, click, or scroll is required for act action")

    return {
        "action": action_performed,
        "selector": selector or "N/A",
        "result": result_message
    }
