"""Console Action Handler (SYNC version)

Handler for console log capture operations.
"""
import structlog

from ..services.console_capture import ConsoleCapture

logger = structlog.get_logger()

# Global console capture instance
_console_capture = ConsoleCapture()


def get_console_capture() -> ConsoleCapture:
    """Get or create global console capture instance"""
    return _console_capture


def handle_console(
    manager,
    action: str = "get",
    clear: bool = False,
    session_id: str = "default",
    **kwargs
) -> dict:
    """Handle console log operations

    Args:
        manager: BrowserManager instance
        action: Operation (get/enable/disable/clear)
        clear: Clear logs after retrieval (for get action)
        session_id: Session identifier

    Returns:
        {
            "enabled": bool,
            "logs": list,
            "count": int,
            "type_counts": dict
        }
    """
    capture = get_console_capture()
    page = manager.get_active_page(session_id)

    if action == "enable":
        # Enable console capture
        enabled = capture.enable_capture(page)
        return {
            "enabled": enabled,
            "message": "Console capture enabled" if enabled else "Already enabled"
        }

    elif action == "disable":
        # Disable console capture
        disabled = capture.disable_capture(page)
        return {
            "disabled": disabled,
            "message": "Console capture disabled" if disabled else "Not enabled"
        }

    elif action == "clear":
        # Clear logs
        cleared = capture.clear_logs(page)
        return {
            "cleared": cleared,
            "message": "Logs cleared" if cleared else "No logs to clear"
        }

    elif action == "get":
        # Get logs (auto-enable if not already)
        if not capture.is_enabled(page):
            capture.enable_capture(page)

        result = capture.get_logs(page, clear=clear)
        result["enabled"] = True
        return result

    else:
        raise ValueError(f"Unknown console action: {action}. Valid: enable, disable, clear, get")
