"""Dialog Action Handler (SYNC version)

Handler for JavaScript dialog operations (alert, confirm, prompt).
"""
import structlog

logger = structlog.get_logger()


def handle_dialog(
    manager,
    action: str = "accept",
    prompt_text: str = "",
    session_id: str = "default",
    **kwargs
) -> dict:
    """Handle dialog operations

    Note: Playwright handles dialogs automatically by default.
    This handler provides explicit control for special cases.

    Args:
        manager: BrowserManager instance
        action: Operation (accept/dismiss)
        prompt_text: Text to enter for prompt dialogs
        session_id: Session identifier

    Returns:
        {
            "action": str,
            "handled": bool,
            "message": str
        }
    """
    page = manager.get_active_page(session_id)

    if action == "accept":
        # Set up dialog handler to accept next dialog
        def accept_dialog(dialog):
            dialog.accept(prompt_text)
            logger.info(
                "[DIALOG] Dialog accepted",
                prompt_text=prompt_text if prompt_text else None
            )

        page.on("dialog", accept_dialog)

        return {
            "action": "accept",
            "handled": True,
            "message": "Next dialog will be accepted" + (f" with text: {prompt_text}" if prompt_text else "")
        }

    elif action == "dismiss":
        # Set up dialog handler to dismiss next dialog
        def dismiss_dialog(dialog):
            dialog.dismiss()
            logger.info("[DIALOG] Dialog dismissed")

        page.on("dialog", dismiss_dialog)

        return {
            "action": "dismiss",
            "handled": True,
            "message": "Next dialog will be dismissed"
        }

    else:
        raise ValueError(f"Unknown dialog action: {action}. Valid: accept, dismiss")
