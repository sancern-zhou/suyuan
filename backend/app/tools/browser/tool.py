"""
Browser Tool - Main Implementation (SYNC API version)

Browser automation tool for the ReAct Agent.
Follows Office Assistant Tool pattern (simplified format, no UDF v2.0).

Uses Playwright SYNC API with thread pool execution for Windows compatibility.
IMPORTANT: Requires WindowsProactorEventLoopPolicy to be set before uvicorn starts.
Use start_windows.py to launch the server on Windows.
"""
from typing import Dict, Any
import asyncio
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from .browser_manager import BrowserManager
from .session_thread_executor import get_session_executor

logger = structlog.get_logger()


class BrowserTool(LLMTool):
    """Browser automation tool (Office Assistant pattern)

    Text-first design: Returns LLM-readable content, not complex UDF v2.0 format.

    Uses Playwright SYNC API to avoid Windows asyncio subprocess issues.

    Supported Actions (22 operations in v2.2):
    - Lifecycle: start, stop, status
    - Tab Management: tabs, open, focus, close
    - Navigation: navigate (alias for open)
    - Content: snapshot (ai/aria formats), screenshot (image), extract (data)
    - Interaction: act (click, type, scroll), execute_js (JavaScript code execution) ⭐ NEW
    - Waiting: wait (7 condition types: timeMs, text, textGone, selector, url, loadState, fn)
    - Debug: console (log capture), pdf (export), trace (debugging)
    - File: download, upload, list_files
    - Dialog: dialog (accept/dismiss)
    """

    def __init__(self):
        super().__init__(
            name="browser",
            description="""Browser automation tool for web-based operations (v3.0)

CRITICAL: Always use snapshot() to get element info before using act()!

Supported actions (22 operations):
- **Lifecycle**: start, stop, status
- **Tab Management**: tabs, open, focus, close
- **Navigation**: navigate (alias for open)
- **Content**: snapshot (page text + element info), screenshot (image), extract (structured data)
- **Interaction**: act (10+ operations: click, type, scroll, press, hover, drag, select, fill, scrollIntoView)
- **JavaScript**: execute_js (JavaScript code execution)
- **Waiting**: wait (7 condition types: timeMs, text, textGone, selector, url, loadState, fn)
- **Debug**: console (capture browser logs), pdf (export page), trace (debugging)
- **File**: download (file download), upload (file upload), list_files
- **Dialog**: dialog (handle alerts/confirms)

ACT OPERATIONS (v3.0 NEW):
- click: Click element (supports double_click, button="left/right/middle", modifiers=["Alt","Control","Shift","Meta"])
- type: Type text into element (ref="e1", text="username")
- press: Press keyboard key (press="Enter" or "Tab" or "Escape" or "Backspace" or "ArrowUp" etc.)
- hover: Hover over element (hover=True)
- drag: Drag element to another element (ref="e1", drag_to_ref="e2")
- select: Select dropdown options (ref="e1", select_values=["Option1", "Option2"])
- fill: Fill form with multiple fields (fill_fields=[{"ref":"e1","type":"text","value":"..."}, ...])
- scrollIntoView: Scroll element into view (scroll_into_view=True)
- scroll: Scroll page (scroll="up/down/top/bottom") - legacy

WAIT CONDITIONS:
- time_ms: Wait for fixed time (e.g., time_ms=5000)
- text: Wait for text to appear (e.g., text="Loading complete", timeout=10000)
- text_gone: Wait for text to disappear (e.g., text_gone="Loading...", timeout=10000)
- selector: Wait for element visibility (e.g., selector=".result-panel", timeout=5000)
- url: Wait for URL change (e.g., url="*dashboard*", timeout=10000)
- load_state: Wait for page load state (e.g., load_state="domcontentloaded")
- fn: Wait for JavaScript function (e.g., fn="() => document.title.includes('Done')")
- timeout: Maximum wait time in milliseconds (default: 20000)

SNAPSHOT FORMATS:
- format="ai": LLM-optimized format with role-based refs (default, recommended)
- format="aria": ARIA attribute-based format
- compact="true": Remove unnamed structural elements (default: True, reduces token usage by 30-50%)

SELECTOR STRATEGY (priority order):
1. Text content: button:has-text("Login") - MOST RELIABLE
2. Unique attributes: #submit-btn, [name="username"], [placeholder="Password"]
3. Unique classes: .login-btn (avoid generic .el-button)
4. Attribute combos: button[class*="login"], [type="password"][placeholder*="密码"]
5. Tag + attribute: input[type="email"], button[type="submit"]

NEVER use:
- Generic classes: .el-button, .btn (matches multiple elements!)
- Tag names alone: button, input (too broad!)

Standard workflow:
1. browser(action="start")
2. browser(action="navigate", url="https://example.com")
3. browser(action="wait", selector=".login-btn", timeout=5000)
4. browser(action="snapshot", format="ai")
5. browser(action="act", ref="e1", click=True)
6. browser(action="wait", text_gone="Logging in...", timeout=10000)
7. browser(action="stop")

ACT OPERATION EXAMPLES (v3.0):
- Click: browser(action="act", ref="e1", click=True)
- Double-click: browser(action="act", ref="e1", click=True, double_click=True)
- Right-click: browser(action="act", ref="e1", click=True, button="right")
- Type: browser(action="act", ref="e1", text="hello")
- Press Enter: browser(action="act", ref="e1", press="Enter") or browser(action="act", press="Enter")
- Hover: browser(action="act", ref="e1", hover=True)
- Drag: browser(action="act", ref="e1", drag_to_ref="e2")
- Select dropdown: browser(action="act", ref="e1", select_values=["Option1", "Option2"])
- Fill form: browser(action="act", fill_fields=[{"ref":"e1","type":"text","value":"user"}, {"ref":"e2","type":"password","value":"pass"}])
- Scroll into view: browser(action="act", ref="e1", scroll_into_view=True)

EXECUTE JS (JavaScript execution):
Use execute_js when:
- Element is blocked by overlay (timeout/intercepts pointer events)
- Need to bypass normal click restrictions
- Direct DOM manipulation required

Examples:
- Click blocked element: code='document.querySelector("a:has-text(\\"实时预览\\")").click()'
- Remove blocking dialogs: code='document.querySelectorAll(".el-dialog").forEach(d=>d.remove())'
- Get page info: code='document.title'
- Scroll to bottom: code='window.scrollTo(0, document.body.scrollHeight)'

IMPORTANT: If act(action="click") fails with timeout/blocking error, IMMEDIATELY try execute_js instead of retrying with different selectors!

If operation times out: selector is not unique. Use more specific attributes or text content.
""",
            category=ToolCategory.QUERY,  # Office assistant tool
            version="3.2.0",  # v3.2: text format removed, use ai format (default: compact=True)
            requires_context=False  # Simplified pattern
        )
        self.manager = BrowserManager()

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Execute browser action (async wrapper for sync operations)

        使用专用线程执行器确保每个 session 的所有操作在同一线程执行，
        解决 Playwright 对象的线程亲和性问题。

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
        logger.info("[BROWSER_TOOL] execute called", action=action, kwargs=list(kwargs.keys()))

        try:
            # 获取 session_id（用于线程绑定）
            session_id = kwargs.get("session_id", "default")

            # 获取专用线程执行器
            executor = get_session_executor()

            logger.info(
                "[BROWSER_TOOL] submitting to session executor",
                session_id=session_id,
                assigned_thread=executor.get_session_thread(session_id),
                active_sessions=executor.active_sessions
            )

            # 提交任务到专用线程执行器
            result = await asyncio.get_event_loop().run_in_executor(
                None,  # executor 内部管理线程池
                lambda: executor.submit(session_id, self._sync_execute, action, **kwargs)
            )

            logger.info(
                "[BROWSER_TOOL] execution completed",
                result_type=type(result).__name__,
                thread_id=executor.get_session_thread(session_id)
            )

            return {
                "success": True,
                "data": result,
                "summary": self._generate_summary(action, result)
            }

        except Exception as e:
            logger.error(
                "[BROWSER_TOOL] execute failed",
                action=action,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
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
        import sys
        import threading
        import asyncio

        # CRITICAL: Set ProactorEventLoopPolicy for Windows BEFORE any async operations
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        thread_id = threading.get_ident()
        logger.info(
            "[BROWSER_TOOL] _sync_execute started",
            action=action,
            thread_id=thread_id,
            platform=sys.platform,
            kwargs_keys=list(kwargs.keys())
        )

        try:
            # Route to action handler
            logger.info("[BROWSER_TOOL] getting action handler", action=action)
            handler = self._get_action_handler(action)
            logger.info("[BROWSER_TOOL] handler obtained", handler_name=handler.__name__)

            logger.info("[BROWSER_TOOL] calling handler", action=action)
            result = handler(self.manager, **kwargs)
            logger.info("[BROWSER_TOOL] handler completed", result_type=type(result).__name__)

            # 增强返回结果：添加当前页面信息
            result = self._enhance_result_with_page_info(result, action, kwargs)

            return result
        except Exception as e:
            logger.error(
                "[BROWSER_TOOL] _sync_execute failed",
                action=action,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            raise

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
        # New handlers for v2.0
        from .actions.console import handle_console
        from .actions.pdf import handle_pdf
        from .actions.file_ops import handle_download, handle_upload, handle_list_files
        from .actions.trace import handle_trace
        from .actions.dialog import handle_dialog
        # New handlers for v2.1
        from .actions.waiting import handle_wait
        # New handlers for v2.2
        from .actions.execute_js import handle_execute_js

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
            "execute_js": handle_execute_js,  # v2.2 NEW

            # Debug features (v2.0)
            "console": handle_console,
            "pdf": handle_pdf,

            # File operations (v2.0)
            "download": handle_download,
            "upload": handle_upload,
            "list_files": handle_list_files,

            # Trace debugging (v2.0)
            "trace": handle_trace,

            # Dialog handling (v2.0)
            "dialog": handle_dialog,

            # Wait conditions (v2.1)
            "wait": handle_wait,
        }

        if action not in handlers:
            raise ValueError(
                f"Unknown action: {action}. "
                f"Valid actions: {', '.join(sorted(handlers.keys()))}"
            )

        return handlers[action]

    def _enhance_result_with_page_info(self, result: Dict[str, Any], action: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance result with current page information

        Args:
            result: Original action result
            action: Action name
            kwargs: Action parameters

        Returns:
            Enhanced result with page_info
        """
        # Skip for actions that don't have a page context
        skip_actions = {"start", "stop", "status"}
        if action in skip_actions:
            return result

        try:
            session_id = kwargs.get("session_id", "default")
            context = self.manager._contexts.get(session_id)

            if not context:
                return result

            pages = context.pages
            if not pages:
                return result

            # Get the active page (same logic as get_active_page)
            active_page = pages[-1]

            try:
                page_info = {
                    "current_url": active_page.url,
                    "page_title": active_page.title(),
                    "total_tabs": len(pages)
                }

                # Add to result
                result["page_info"] = page_info

            except Exception as e:
                # Page might be closed or navigating
                logger.warning("[BROWSER_TOOL] Failed to get page info", error=str(e))

        except Exception as e:
            logger.warning("[BROWSER_TOOL] Failed to enhance result with page info", error=str(e))

        return result

    def _generate_summary(self, action: str, result: Dict[str, Any]) -> str:
        """Generate human-readable summary

        Args:
            action: Action name
            result: Action result data

        Returns:
            Summary string (may include markdown image for screenshot)
        """
        base_summary = ""
        page_info = result.get("page_info", {})

        summaries = {
            "start": f"Browser started (session: {result.get('session_id', 'N/A')})",
            "stop": f"Browser stopped ({result.get('sessions_closed', 0)} sessions closed)",
            "status": f"Browser status: {result.get('status', 'unknown')}",
            "tabs": f"Open tabs: {result.get('count', 0)}",
            "open": f"Navigated to {result.get('url', 'unknown')}",
            "navigate": f"Navigated to {result.get('url', 'unknown')}",
            "focus": f"Focused tab: {result.get('tab_id', 'unknown')}",
            "close": f"Closed tab: {result.get('tab_id', 'unknown')}",
            "extract": f"Extracted {result.get('type', 'data')}: {result.get('count', 0)} items",
            "act": f"Performed action: {result.get('action', 'unknown')}",
            "execute_js": f"Executed JavaScript: {result.get('type', 'unknown')}",
            "wait": f"Waited for: {result.get('conditions_applied', [])}"
        }

        # Snapshot: include element count (ai/aria formats only)
        if action == "snapshot":
            stats = result.get('stats', {})
            total_refs = stats.get('total_refs', 0)
            interactive_refs = stats.get('interactive_refs', 0)
            format_name = result.get('format', 'ai')
            compact = result.get('compact', False)
            compact_str = " (compact)" if compact else ""
            base_summary = f"Captured {format_name}{compact_str} snapshot: {total_refs} total elements, {interactive_refs} interactive elements"

        # Screenshot: include markdown image link for LLM output
        elif action == "screenshot":
            markdown_image = result.get('markdown_image')
            if markdown_image:
                base_summary = f"Captured screenshot: {markdown_image}\n\n{result.get('description', '')[:100]}..."
            else:
                base_summary = f"Captured screenshot: {result.get('image_id', 'N/A')} - {result.get('title', '')[:30]}"
        else:
            base_summary = summaries.get(action, f"Action '{action}' completed")

        # Append page info if available
        if page_info:
            current_url = page_info.get("current_url", "")
            page_title = page_info.get("page_title", "")
            total_tabs = page_info.get("total_tabs", 1)

            # Truncate URL if too long
            if len(current_url) > 50:
                current_url = current_url[:47] + "..."

            # Truncate title if too long
            if len(page_title) > 30:
                page_title = page_title[:27] + "..."

            page_info_str = f"\n\n**Current Page**: {page_title}\n**URL**: {current_url}"
            if total_tabs > 1:
                page_info_str += f"\n**Total Tabs**: {total_tabs}"

            return base_summary + page_info_str

        return base_summary

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
            "description": """Browser automation tool for web-based operations (v3.0)

CRITICAL: Always use snapshot() to get element info before using act()!

Supported actions (22 operations):
- **Lifecycle**: start, stop, status
- **Tab Management**: tabs, open, focus, close
- **Navigation**: navigate (alias for open)
- **Content**: snapshot (page text + element info), screenshot (image), extract (structured data)
- **Interaction**: act (10+ operations: click, type, scroll, press, hover, drag, select, fill, scrollIntoView)
- **JavaScript**: execute_js (JavaScript code execution)
- **Waiting**: wait (7 condition types: timeMs, text, textGone, selector, url, loadState, fn)

ACT OPERATIONS (v3.0):
- click: Click element (supports double_click, button="left/right/middle", modifiers)
- type: Type text into element (ref="e1", text="hello")
- press: Press keyboard key (press="Enter" or "Tab" or "Escape" or "Backspace" or "ArrowUp" etc.)
- hover: Hover over element (hover=True)
- drag: Drag element to another element (ref="e1", drag_to_ref="e2")
- select: Select dropdown options (ref="e1", select_values=["Option1"])
- fill: Fill form with multiple fields (fill_fields=[{"ref":"e1","type":"text","value":"..."}])
- scrollIntoView: Scroll element into view (scroll_into_view=True)
- scroll: Scroll page (scroll="up/down/top/bottom") - legacy

WAIT CONDITIONS:
- time_ms: Wait for fixed time (e.g., time_ms=5000)
- text: Wait for text to appear (e.g., text="Loading complete", timeout=10000)
- text_gone: Wait for text to disappear (e.g., text_gone="Loading...", timeout=10000)
- selector: Wait for element visibility (e.g., selector=".result-panel", timeout=5000)
- url: Wait for URL change (e.g., url="*dashboard*", timeout=10000)
- load_state: Wait for page load state (e.g., load_state="domcontentloaded")
- fn: Wait for JavaScript function (e.g., fn="() => document.title.includes('Done')")
- timeout: Maximum wait time in milliseconds (default: 20000)

SELECTOR STRATEGY (priority order):
1. Text content: button:has-text("Login") - MOST RELIABLE
2. Unique attributes: #submit-btn, [name="username"], [placeholder="Password"]
3. Unique classes: .login-btn (avoid generic .el-button)
4. Attribute combos: button[class*="login"], [type="password"][placeholder*="密码"]
5. Tag + attribute: input[type="email"], button[type="submit"]

NEVER use:
- Generic classes: .el-button, .btn (matches multiple elements!)
- Tag names alone: button, input (too broad!)

Standard workflow:
1. browser(action="start")
2. browser(action="navigate", url="https://example.com")
3. browser(action="wait", selector=".login-btn", timeout=5000)
4. browser(action="snapshot", format="ai")
5. browser(action="act", ref="e1", click=True)
6. browser(action="wait", text_gone="Logging in...", timeout=10000)
7. browser(action="stop")

EXECUTE JS (JavaScript execution):
Use execute_js when:
- Element is blocked by overlay (timeout/intercepts pointer events)
- Need to bypass normal click restrictions
- Direct DOM manipulation required

Examples:
- Click blocked element: code='document.querySelector("a:has-text(\\"实时预览\\")").click()'
- Remove blocking dialogs: code='document.querySelectorAll(".el-dialog").forEach(d=>d.remove())'
- Get page info: code='document.title'
- Scroll to bottom: code='window.scrollTo(0, document.body.scrollHeight)'

IMPORTANT: If act(action="click") fails with timeout/blocking error, IMMEDIATELY try execute_js instead of retrying with different selectors!

If operation times out: selector is not unique. Use more specific attributes or text content.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "start", "stop", "status",
                            "tabs", "open", "focus", "close", "navigate",
                            "snapshot", "screenshot", "extract", "act", "execute_js",
                            "console", "pdf", "download", "upload", "list_files",
                            "trace", "dialog", "wait"
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
                    "press": {
                        "type": "string",
                        "description": "Key to press (for act action): Enter, Tab, Escape, Backspace, ArrowUp, ArrowDown, etc."
                    },
                    "hover": {
                        "type": "boolean",
                        "description": "Hover over element (for act action)"
                    },
                    "drag_to_ref": {
                        "type": "string",
                        "description": "Target element ref to drag to (for act action)"
                    },
                    "select_values": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of values to select in dropdown (for act action)"
                    },
                    "fill_fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ref": {"type": "string", "description": "Element reference ID"},
                                "type": {"type": "string", "description": "Field type: text, checkbox, radio, select"},
                                "value": {"description": "Field value"}
                            },
                            "required": ["ref", "type", "value"]
                        },
                        "description": "List of form fields to fill (for act action)"
                    },
                    "scroll_into_view": {
                        "type": "boolean",
                        "description": "Scroll element into view (for act action)"
                    },
                    "double_click": {
                        "type": "boolean",
                        "description": "Double click instead of single click (for act action)"
                    },
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "description": "Mouse button for click (for act action, default: left)"
                    },
                    "modifiers": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["Alt", "Control", "Meta", "Shift"]},
                        "description": "Keyboard modifiers for click (for act action)"
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
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in milliseconds (default: 30000)"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID for multi-user isolation (optional)"
                    },
                    "code": {
                        "type": "string",
                        "description": "JavaScript code to execute (for execute_js action)"
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full page screenshot (default: false, only viewport)"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["ai", "aria"],
                        "default": "ai",
                        "description": "Snapshot format (for snapshot action): ai=LLM-optimized with refs (default), aria=ARIA-based. Note: text format removed, use ai instead."
                    },
                    "max_refs": {
                        "type": "integer",
                        "description": "Maximum number of refs for ai/aria snapshot formats (default: 100)"
                    },
                    "interactive_only": {
                        "type": "boolean",
                        "description": "Only include interactive elements in snapshot (default: false)"
                    },
                    "compact": {
                        "type": "boolean",
                        "description": "Remove unnamed structural elements (generic, group, etc.) in ai format (default: true, reduces token usage by 30-50%)"
                    },
                    "console_action": {
                        "type": "string",
                        "enum": ["get", "enable", "disable", "clear"],
                        "description": "Console operation (for console action)"
                    },
                    "pdf_action": {
                        "type": "string",
                        "enum": ["export", "export_element", "list"],
                        "description": "PDF operation (for pdf action)"
                    },
                    "file_path": {
                        "type": "string",
                        "description": "File path for upload action"
                    },
                    "trace_action": {
                        "type": "string",
                        "enum": ["start", "stop", "chunk", "list"],
                        "description": "Trace operation (for trace action)"
                    },
                    "dialog_action": {
                        "type": "string",
                        "enum": ["accept", "dismiss"],
                        "description": "Dialog operation (for dialog action)"
                    },
                    "time_ms": {
                        "type": "integer",
                        "description": "Wait time in milliseconds (for wait action)"
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to wait for appearance (for wait action)"
                    },
                    "text_gone": {
                        "type": "string",
                        "description": "Text to wait for disappearance (for wait action)"
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector to wait for element visibility (for wait action)"
                    },
                    "url": {
                        "type": "string",
                        "description": "URL pattern to wait for (supports * wildcard, for wait action)"
                    },
                    "load_state": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                        "description": "Page load state to wait for (for wait action)"
                    },
                    "fn": {
                        "type": "string",
                        "description": "JavaScript function body to wait for (for wait action, requires config.WAIT_FN_ENABLED=True)"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum wait time in milliseconds for wait conditions (default: 20000, min: 500, max: 120000)"
                    }
                },
                "required": ["action"]
            }
        }
