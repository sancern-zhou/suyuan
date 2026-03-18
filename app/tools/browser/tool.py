"""
Browser Tool - Main Implementation (SYNC API version)

Browser automation tool for the ReAct Agent.
Follows Office Assistant Tool pattern (simplified format, no UDF v2.0).

Uses Playwright SYNC API with thread pool execution for Windows compatibility.
"""
from typing import Dict, Any
import asyncio
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from .browser_manager import BrowserManager

logger = structlog.get_logger()


class BrowserTool(LLMTool):
    """Browser automation tool (Office Assistant pattern)

    Text-first design: Returns LLM-readable content, not complex UDF v2.0 format.

    Uses Playwright SYNC API to avoid Windows asyncio subprocess issues.

    Supported Actions (12 core operations):
    - Lifecycle: start, stop, status
    - Tab Management: tabs, open, focus, close
    - Navigation: navigate (alias for open)
    - Content: snapshot (text), screenshot (image), extract (data)
    - Interaction: act (click, type, scroll)
    """

    def __init__(self):
        super().__init__(
            name="browser",
            description="""Browser automation tool for web-based operations

Supported actions (12 core operations):
- **Lifecycle**: start, stop, status
- **Tab Management**: tabs, open, focus, close
- **Navigation**: navigate (alias for open)
- **Content**: snapshot (text), screenshot (image), extract (data)
- **Interaction**: act (click, type, scroll)

Text-first design: All operations return LLM-readable content.

Examples:
- browser(action="start")
- browser(action="navigate", url="https://python.org")
- browser(action="snapshot")
- browser(action="screenshot")
- browser(action="act", selector="#search", text="Python")
- browser(action="extract", selector="table", extract_type="table")
- browser(action="stop")

Note: Screenshots include text descriptions for LLM understanding.
""",
            category=ToolCategory.QUERY,  # Office assistant tool
            version="1.1.0",  # Updated for sync API
            requires_context=False  # Simplified pattern
        )
        self.manager = BrowserManager()

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Execute browser action (async wrapper for sync operations)

        Args:
            action: Browser action (start/stop/status/tabs/open/navigate/etc.)
            **kwargs: Action-specific parameters

        Returns:
            {
                "success": bool,
                "data": dict,  # Action-specific data
                "summary": str
            }
        """
        try:
            # Run sync operation in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,  # Use default thread pool
                self._sync_execute,
                action,
                **kwargs
            )

            return {
                "success": True,
                "data": result,
                "summary": self._generate_summary(action, result)
            }

        except Exception as e:
            logger.error("browser_action_failed", action=action, error=str(e), exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "summary": f"Browser action '{action}' failed: {str(e)[:50]}"
            }

    def _sync_execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Synchronous execution wrapper (runs in thread pool)

        Args:
            action: Browser action
            **kwargs: Action-specific parameters

        Returns:
            Action result dictionary
        """
        # Route to action handler
        handler = self._get_action_handler(action)
        result = handler(self.manager, **kwargs)
        return result

    def _get_action_handler(self, action: str):
        """Get action handler function

        Args:
            action: Action name

        Returns:
            Handler function

        Raises:
            ValueError: If action is unknown
        """
        # Import handlers (lazy import to avoid circular dependencies)
        from .actions.lifecycle import handle_start, handle_stop, handle_status
        from .actions.tab_management import handle_tabs, handle_open, handle_focus, handle_close
        from .actions.navigation import handle_navigate
        from .actions.snapshot import handle_snapshot
        from .actions.screenshot import handle_screenshot
        from .actions.extract import handle_extract
        from .actions.interaction import handle_act

        handlers = {
            # Lifecycle
            "start": handle_start,
            "stop": handle_stop,
            "status": handle_status,

            # Tab management
            "tabs": handle_tabs,
            "open": handle_open,
            "navigate": handle_navigate,
            "focus": handle_focus,
            "close": handle_close,

            # Content
            "snapshot": handle_snapshot,
            "screenshot": handle_screenshot,
            "extract": handle_extract,

            # Interaction
            "act": handle_act,
        }

        if action not in handlers:
            raise ValueError(
                f"Unknown action: {action}. "
                f"Valid actions: {', '.join(sorted(handlers.keys()))}"
            )

        return handlers[action]

    def _generate_summary(self, action: str, result: Dict[str, Any]) -> str:
        """Generate human-readable summary

        Args:
            action: Action name
            result: Action result data

        Returns:
            Summary string
        """
        summaries = {
            "start": f"Browser started (session: {result.get('session_id', 'N/A')})",
            "stop": f"Browser stopped ({result.get('sessions_closed', 0)} sessions closed)",
            "status": f"Browser status: {result.get('status', 'unknown')}",
            "tabs": f"Open tabs: {result.get('count', 0)}",
            "open": f"Navigated to {result.get('url', 'unknown')}",
            "navigate": f"Navigated to {result.get('url', 'unknown')}",
            "focus": f"Focused tab: {result.get('tab_id', 'unknown')}",
            "close": f"Closed tab: {result.get('tab_id', 'unknown')}",
            "snapshot": f"Captured text snapshot ({result.get('length', 0)} chars)",
            "screenshot": f"Captured screenshot: {result.get('description', '')[:50]}...",
            "extract": f"Extracted {result.get('type', 'data')}: {result.get('count', 0)} items",
            "act": f"Performed action: {result.get('action', 'unknown')}"
        }

        return summaries.get(action, f"Action '{action}' completed")

    def is_available(self) -> bool:
        """Check if browser tool is available

        Returns:
            True if playwright is installed
        """
        try:
            import playwright
            return True
        except ImportError:
            logger.warning("playwright_not_installed")
            return False

    def get_function_schema(self) -> Dict[str, Any]:
        """Get Function Calling Schema

        Returns:
            OpenAI function calling format schema
        """
        return {
            "name": "browser",
            "description": """Browser automation tool for web-based operations

Supported actions (12 core operations):
- **Lifecycle**: start, stop, status
- **Tab Management**: tabs, open, focus, close
- **Navigation**: navigate (alias for open)
- **Content**: snapshot (text), screenshot (image), extract (data)
- **Interaction**: act (click, type, scroll)

Text-first design: All operations return LLM-readable content.

Examples:
- browser(action="start")
- browser(action="navigate", url="https://python.org")
- browser(action="snapshot")
- browser(action="screenshot")
- browser(action="act", selector="#search", text="Python")
- browser(action="extract", selector="table", extract_type="table")
- browser(action="stop")

Note: Screenshots include text descriptions for LLM understanding.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "start", "stop", "status",
                            "tabs", "open", "focus", "close", "navigate",
                            "snapshot", "screenshot", "extract", "act"
                        ],
                        "description": "Browser action to perform"
                    },
                    "url": {
                        "type": "string",
                        "description": "URL for navigate/open actions"
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for act/extract actions"
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type (for act action)"
                    },
                    "click": {
                        "type": "boolean",
                        "description": "Click element (for act action)"
                    },
                    "scroll": {
                        "type": "string",
                        "enum": ["up", "down", "top", "bottom"],
                        "description": "Scroll direction (for act action)"
                    },
                    "extract_type": {
                        "type": "string",
                        "enum": ["table", "list", "form", "links", "images"],
                        "description": "Data type to extract"
                    },
                    "tab_id": {
                        "type": "string",
                        "description": "Tab ID for focus/close actions"
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Max content length (default: 10000)"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in milliseconds (default: 30000)"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID for multi-user isolation (optional)"
                    }
                },
                "required": ["action"]
            }
        }
