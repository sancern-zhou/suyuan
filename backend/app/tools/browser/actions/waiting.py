"""
Waiting conditions handler for browser automation.

Implements 7 types of wait conditions:
- time_ms: Wait for fixed time
- text: Wait for text to appear
- text_gone: Wait for text to disappear
- selector: Wait for element visibility
- url: Wait for URL change
- load_state: Wait for page load state
- fn: Wait for JavaScript function (requires config.WAIT_FN_ENABLED=True)
"""

from typing import Optional, List
from ..config import config


def handle_wait(manager, session_id: str = "default", time_ms: Optional[int] = None,
                text: Optional[str] = None, text_gone: Optional[str] = None,
                selector: Optional[str] = None, url: Optional[str] = None,
                load_state: Optional[str] = None, fn: Optional[str] = None,
                timeout: Optional[int] = None, **kwargs) -> dict:
    """
    Wait condition handler - supports multiple conditions executed sequentially.

    Args:
        manager: BrowserSessionManager instance
        session_id: Session identifier
        time_ms: Wait time in milliseconds
        text: Text to wait for appearance
        text_gone: Text to wait for disappearance
        selector: CSS selector to wait for visibility
        url: URL pattern to wait for (supports * wildcard)
        load_state: Page load state ("load", "domcontentloaded", "networkidle")
        fn: JavaScript function body to wait for
        timeout: Maximum wait time in milliseconds (default: 20000)

    Returns:
        dict with keys:
            - conditions_applied: List of condition descriptions
            - result: Summary message

    Raises:
        RuntimeError: If wait operation fails or times out
        ValueError: If invalid parameters are provided
    """
    page = manager.get_active_page(session_id)
    timeout_ms = _normalize_timeout(timeout)
    conditions_applied = []

    try:
        # Execute each wait condition in order
        if time_ms is not None:
            wait_time = max(0, int(time_ms))
            page.wait_for_timeout(wait_time)
            conditions_applied.append(f"timeMs({wait_time}ms)")

        if text:
            page.get_by_text(text).first.wait_for(state="visible", timeout=timeout_ms)
            conditions_applied.append(f"text('{text}')")

        if text_gone:
            page.get_by_text(text_gone).first.wait_for(state="hidden", timeout=timeout_ms)
            conditions_applied.append(f"textGone('{text_gone}')")

        if selector:
            page.locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
            conditions_applied.append(f"selector('{selector}')")

        if url:
            page.wait_for_url(url, timeout=timeout_ms)
            conditions_applied.append(f"url('{url}')")

        if load_state:
            valid_states = ["load", "domcontentloaded", "networkidle"]
            if load_state not in valid_states:
                raise ValueError(
                    f"Invalid loadState: '{load_state}'. "
                    f"Must be one of: {', '.join(valid_states)}"
                )
            page.wait_for_load_state(load_state, timeout=timeout_ms)
            conditions_applied.append(f"loadState('{load_state}')")

        if fn:
            if not config.WAIT_FN_ENABLED:
                raise RuntimeError(
                    "wait fn is disabled by config. "
                    "Set config.WAIT_FN_ENABLED=True to enable JavaScript function waits."
                )
            page.wait_for_function(fn, timeout=timeout_ms)
            fn_preview = fn[:50] + "..." if len(fn) > 50 else fn
            conditions_applied.append(f"fn('{fn_preview}')")

        # At least one condition must be specified
        if not conditions_applied:
            raise ValueError(
                "At least one wait condition must be specified: "
                "time_ms, text, text_gone, selector, url, load_state, or fn"
            )

        return {
            "success": True,
            "conditions_applied": conditions_applied,
            "result": f"Waited for: {', '.join(conditions_applied)}",
            "timeout_ms": timeout_ms
        }

    except Exception as e:
        error_msg = str(e)
        conditions_str = ', '.join(conditions_applied) if conditions_applied else "none"

        if "Timeout" in error_msg:
            # Provide helpful recovery suggestion
            suggestion = (
                f"Wait timeout after {timeout_ms}ms. "
                f"Conditions applied: {conditions_str}. "
                f"Try increasing wait_timeout or check if the condition is correct. "
                f"⚠️ RECOMMENDED: Execute browser(action='snapshot', format='ai') to see actual page structure "
                f"and use text-based selectors like button:has-text('...')"
            )
            raise RuntimeError(suggestion)
        elif "strict mode violation" in error_msg:
            raise RuntimeError(
                f"Multiple elements matched. Use more specific selector. "
                f"Conditions: {conditions_str}"
            )
        else:
            raise RuntimeError(f"Wait operation failed: {error_msg}")


def _normalize_timeout(timeout: Optional[int]) -> int:
    """
    Normalize timeout value with bounds checking.

    Args:
        timeout: Timeout in milliseconds

    Returns:
        Normalized timeout (min: 500ms, max: 120000ms, default: 20000ms)
    """
    if timeout is None:
        return config.WAIT_DEFAULT_TIMEOUT

    timeout = int(timeout)
    if timeout < config.WAIT_MIN_TIMEOUT:
        return config.WAIT_MIN_TIMEOUT
    elif timeout > config.WAIT_MAX_TIMEOUT:
        return config.WAIT_MAX_TIMEOUT
    return timeout


def get_wait_summary(result: dict) -> str:
    """
    Generate a human-readable summary of wait operation.

    Args:
        result: Result dictionary from handle_wait

    Returns:
        Summary string
    """
    conditions = result.get("conditions_applied", [])
    if not conditions:
        return "Wait operation completed"

    timeout = result.get("timeout_ms", config.WAIT_DEFAULT_TIMEOUT)
    return f"Waited for {len(conditions)} condition(s) (timeout: {timeout}ms): {', '.join(conditions)}"
