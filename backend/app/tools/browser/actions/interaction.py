"""Interaction Action Handler (SYNC version)

Handler for act operation (click, type, scroll, press, hover, drag, select, fill, scrollIntoView)

Supported operations (v3.0):
- click: Click element (supports double_click, button, modifiers)
- type: Type text into element
- press: Press keyboard key (Enter, Tab, Escape, etc.)
- hover: Hover over element
- drag: Drag element to another element
- select: Select dropdown options
- fill: Fill form with multiple fields
- scrollIntoView: Scroll element into view
- scroll: Scroll page (up/down/top/bottom) - legacy
"""
import structlog
import base64

from ..config import config
from ....services.image_cache import ImageCache
from ..refs.ref_resolver import get_global_resolver

logger = structlog.get_logger()

# 图片缓存实例
_image_cache = None

def _get_image_cache():
    """获取图片缓存实例（延迟初始化）"""
    global _image_cache
    if _image_cache is None:
        _image_cache = ImageCache()
    return _image_cache


def handle_act(
    manager,
    ref: str = None,
    selector: str = None,
    text: str = None,
    click: bool = False,
    scroll: str = None,
    press: str = None,
    hover: bool = False,
    drag_to_ref: str = None,
    select_values: list = None,
    fill_fields: list = None,
    scroll_into_view: bool = False,
    double_click: bool = False,
    button: str = None,
    modifiers: list = None,
    session_id: str = "default",
    **kwargs
) -> dict:
    """Perform interaction action (SYNC version)

    Args:
        manager: BrowserManager instance
        ref: Element reference ID (e.g., "e1", "e12") - preferred method
        selector: CSS selector for element (legacy, use ref instead)
        text: Text to type into element
        click: Click element
        scroll: Scroll direction (up/down/top/bottom) - legacy
        press: Key to press (Enter, Tab, Escape, etc.)
        hover: Hover over element
        drag_to_ref: Drag element to another element (ref of target)
        select_values: List of values to select in dropdown
        fill_fields: List of form fields to fill [{"ref": "e1", "type": "text", "value": "..."}]
        scroll_into_view: Scroll element into view
        double_click: Double click instead of single click
        button: Mouse button ("left", "right", "middle")
        modifiers: Keyboard modifiers ("Alt", "Control", "Shift", "Meta")
        session_id: Session identifier

    Returns:
        {
            "action": str,
            "ref": str or "N/A",
            "result": str
        }
    """
    page = manager.get_active_page(session_id)

    action_performed = None
    result_message = ""
    element_descriptor = None  # For error messages

    # Fill form action (batch operation)
    if fill_fields:
        action_performed = "fill"
        result_message = _handle_fill(page, fill_fields, ref, selector, session_id)

    # Select dropdown action
    elif select_values is not None:
        action_performed = "select"
        locator = _get_locator(page, ref, selector)
        element_descriptor = ref or selector

        try:
            # Convert single string to list
            values = select_values if isinstance(select_values, list) else [select_values]
            locator.select_option(values, timeout=config.DEFAULT_TIMEOUT)
            result_message = f"Selected options {values} in {element_descriptor}"
        except Exception as e:
            raise RuntimeError(f"Failed to select options in {element_descriptor}: {str(e)}")

        logger.info(
            "browser_action_select",
            ref=ref,
            selector=selector,
            values=values,
            session_id=session_id
        )

    # Drag action
    elif drag_to_ref:
        action_performed = "drag"
        start_descriptor = ref or selector
        end_descriptor = drag_to_ref

        try:
            start_locator = _get_locator(page, ref, selector)
            end_locator = _get_locator(page, drag_to_ref, None)
            start_locator.drag_to(end_locator, timeout=config.DEFAULT_TIMEOUT)
            result_message = f"Dragged from {start_descriptor} to {end_descriptor}"
        except Exception as e:
            raise RuntimeError(f"Failed to drag from {start_descriptor} to {end_descriptor}: {str(e)}")

        logger.info(
            "browser_action_drag",
            start=start_descriptor,
            end=end_descriptor,
            session_id=session_id
        )

    # Hover action
    elif hover:
        action_performed = "hover"

        try:
            locator = _get_locator(page, ref, selector)
            element_descriptor = ref or selector
            locator.hover(timeout=config.DEFAULT_TIMEOUT)
            result_message = f"Hovered over {element_descriptor}"
        except Exception as e:
            raise RuntimeError(f"Failed to hover over {element_descriptor}: {str(e)}")

        logger.info(
            "browser_action_hover",
            ref=ref,
            selector=selector,
            session_id=session_id
        )

    # Press key action
    elif press:
        action_performed = "press"

        try:
            # Press key on page (or element if ref/selector provided)
            if ref or selector:
                locator = _get_locator(page, ref, selector)
                element_descriptor = ref or selector
                locator.press(press, timeout=config.DEFAULT_TIMEOUT)
                result_message = f"Pressed key '{press}' on {element_descriptor}"
            else:
                page.keyboard.press(press)
                result_message = f"Pressed key '{press}'"
        except Exception as e:
            target_desc = element_descriptor if element_descriptor else "page"
            raise RuntimeError(f"Failed to press key '{press}' on {target_desc}: {str(e)}")

        logger.info(
            "browser_action_press",
            key=press,
            ref=ref,
            selector=selector,
            session_id=session_id
        )

    # Scroll into view action
    elif scroll_into_view:
        action_performed = "scrollIntoView"

        try:
            locator = _get_locator(page, ref, selector)
            element_descriptor = ref or selector
            locator.scroll_into_view_if_needed(timeout=config.DEFAULT_TIMEOUT)
            result_message = f"Scrolled {element_descriptor} into view"
        except Exception as e:
            raise RuntimeError(f"Failed to scroll {element_descriptor} into view: {str(e)}")

        logger.info(
            "browser_action_scroll_into_view",
            ref=ref,
            selector=selector,
            session_id=session_id
        )
        action_performed = "scroll"

        if scroll == "up":
            page.evaluate("window.scrollBy(0, -500)")
            result_message = "Scrolled up 500px"
        elif scroll == "down":
            page.evaluate("window.scrollBy(0, 500)")
            result_message = "Scrolled down 500px"
        elif scroll == "top":
            page.evaluate("window.scrollTo(0, 0)")
            result_message = "Scrolled to top"
        elif scroll == "bottom":
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            result_message = "Scrolled to bottom"

        logger.info("browser_action_scroll", direction=scroll, session_id=session_id)

    # Type action
    elif text:
        action_performed = "type"

        try:
            locator = _get_locator(page, ref, selector)
            element_descriptor = ref or selector

            if ref:
                locator.fill(text, timeout=config.DEFAULT_TIMEOUT)
                result_message = f"Typed text into ref={ref}"
            else:
                locator.fill(text, timeout=config.DEFAULT_TIMEOUT)
                result_message = f"Typed text into {selector}"

        except Exception as e:
            raise RuntimeError(f"Failed to type into {element_descriptor}: {str(e)}")

        logger.info(
            "browser_action_type",
            ref=ref,
            selector=selector,
            text_length=len(text),
            session_id=session_id
        )

    # Click action
    elif click:
        action_performed = "click"

        try:
            locator = _get_locator(page, ref, selector)
            element_descriptor = ref or selector

            # Build click options
            click_options = {"timeout": config.DEFAULT_TIMEOUT}

            if double_click:
                locator.dblclick(**click_options)
                result_message = f"Double-clicked {element_descriptor}"
            else:
                # Add button and modifiers if provided
                if button:
                    click_options["button"] = button
                if modifiers:
                    click_options["modifiers"] = modifiers

                locator.click(**click_options)
                click_detail = f" with {button} button" if button else ""
                if modifiers:
                    click_detail += f" with modifiers {modifiers}"
                result_message = f"Clicked {element_descriptor}{click_detail}"

        except Exception as e:
            error_msg = str(e)

            if "intercepts pointer events" in error_msg or "Timeout" in error_msg:
                # 检测页面障碍
                obstacles = _detect_obstacles(page)

                logger.info(
                    "click_blocked_attempting_js_fallback",
                    ref=ref,
                    selector=selector,
                    obstacles=obstacles,
                    session_id=session_id
                )

                # 🔥 自动使用JavaScript重试
                js_result = _try_js_click(page, selector, ref)

                if js_result["success"]:
                    # JavaScript点击成功
                    result_message = f"Clicked {element_descriptor} (using JavaScript fallback)"
                    logger.info(
                        "click_js_fallback_success",
                        ref=ref,
                        selector=selector,
                        session_id=session_id
                    )
                else:
                    # JavaScript也失败了，返回详细错误
                    screenshot_info = _take_screenshot_for_analysis(page)

                    logger.info(
                        "click_js_fallback_failed",
                        ref=ref,
                        selector=selector,
                        obstacles=obstacles,
                        js_error=js_result.get("error"),
                        session_id=session_id,
                        has_screenshot=screenshot_info is not None
                    )

                    # 构建错误信息
                    error_detail = {
                        "obstacle_type": "element_blocked",
                        "ref": ref,
                        "selector": selector,
                        "obstacles": obstacles,
                        "js_error": js_result.get("error"),
                        "suggestions": _get_suggestions(obstacles)
                    }

                    error_message = (
                        f"Failed to click {element_descriptor}: Element is blocked by overlay.\n" +
                        f"JavaScript fallback also failed: {js_result.get('error', 'Unknown error')}\n" +
                        f"Obstacles detected: {obstacles}\n" +
                        f"Suggestions: {error_detail['suggestions']}"
                    )

                    # 如果截图成功，添加截图信息
                    if screenshot_info:
                        error_message += (
                            f"\n\n📸 **Screenshot saved for analysis**\n" +
                            f"Local path: {screenshot_info['local_path']}\n" +
                            f"URL: {screenshot_info['url']}"
                        )

                    raise RuntimeError(error_message)
            else:
                raise RuntimeError(f"Failed to click {element_descriptor}: {error_msg}")

        logger.info("browser_action_click", ref=ref, selector=selector, session_id=session_id)

    else:
        raise ValueError("One of text, click, or scroll is required for act action")

    return {
        "action": action_performed,
        "ref": ref or "N/A",
        "result": result_message
    }


def _try_js_click(page, selector: str = None, ref: str = None) -> dict:
    """Try to click element using JavaScript as fallback

    Args:
        page: Playwright Page instance
        selector: CSS selector
        ref: Element reference ID

    Returns:
        {
            "success": bool,
            "error": str or None
        }
    """
    try:
        if selector:
            # Convert Playwright selector to standard JavaScript
            js_code = _convert_selector_to_js(selector)

            # Execute the JavaScript click
            result = page.evaluate(js_code)

            # Extract error from result if present
            success = result is not None and result.get("success", False)
            error = None
            if result and not success:
                error = result.get("error", "Unknown error")

            return {"success": success, "error": error}
        elif ref:
            # For ref-based clicks, we need to resolve the ref first
            # Get the locator and extract the selector
            from ..refs.ref_resolver import get_global_resolver
            resolver = get_global_resolver()
            try:
                locator = resolver.resolve(page, ref)
                # Try to click using the locator's element
                element = locator.element_handle()
                if element:
                    element.click()
                    return {"success": True, "error": None}
            except:
                pass
            # Fallback: try to get selector from ref data
            return {"success": False, "error": "Ref-based JS click not implemented, use selector"}
        else:
            return {"success": False, "error": "No selector or ref provided"}

    except Exception as e:
        logger.warning("js_click_fallback_failed", error=str(e), selector=selector, ref=ref)
        return {"success": False, "error": str(e)}


def _convert_selector_to_js(selector: str) -> str:
    """Convert Playwright selector to JavaScript code for finding and clicking element

    Args:
        selector: Playwright CSS selector (may contain :has-text() etc.)

    Returns:
        JavaScript code string that finds and clicks the element
    """
    # Handle Playwright's :has-text() pseudo-class
    if ':has-text(' in selector:
        # Extract the tag and text from selector like "a:has-text('实时预览')"
        import re
        match = re.match(r'^([a-zA-Z]+):has-text\(["\'](.+?)["\']\)', selector)
        if match:
            tag = match.group(1)
            text = match.group(2)
            # Return JavaScript that finds element by tag and text content
            return f"""() => {{
                const elements = document.querySelectorAll('{tag}');
                for (let el of elements) {{
                    if (el.textContent && el.textContent.includes('{text}')) {{
                        el.click();
                        return {{success: true}};
                    }}
                }}
                return {{success: false, error: "Element not found"}};
            }}"""

    # Handle text= selectors (Playwright text selector)
    if selector.startswith('text='):
        text = selector[5:].strip('"\'')
        return f"""() => {{
            const elements = document.querySelectorAll('*');
            for (let el of elements) {{
                if (el.textContent && el.textContent.trim() === '{text}') {{
                    el.click();
                    return {{success: true}};
                }}
            }}
            return {{success: false, error: "Element not found"}};
        }}"""

    # Standard CSS selector - use querySelector directly
    # Need to escape selector for JavaScript template literal
    escaped_selector = selector.replace('`', '\\`').replace('\\', '\\\\')
    return f"""() => {{
        const element = document.querySelector(`{escaped_selector}`);
        if (!element) return {{success: false, error: "Element not found"}};
        element.click();
        return {{success: true}};
    }}"""


def _get_locator(page, ref: str = None, selector: str = None):
    """Get locator for element

    Priority:
    1. Use ref if provided (new method)
    2. Fall back to selector if provided (legacy method)

    Args:
        page: Playwright Page instance
        ref: Element reference ID
        selector: CSS selector

    Returns:
        Playwright Locator

    Raises:
        ValueError: If neither ref nor selector is provided
    """
    if ref:
        # Use ref-based resolution (preferred)
        resolver = get_global_resolver()
        return resolver.resolve(page, ref)
    elif selector:
        # Legacy selector-based fallback
        return page.locator(selector)
    else:
        raise ValueError("Either ref or selector is required for act action")


def _detect_obstacles(page) -> dict:
    """检测页面上的障碍物（对话框、覆盖层等）

    Returns:
        {
            "dialogs": int,      # 对话框数量
            "overlays": int,     # 覆盖层数量
            "has_cert_warning": bool,  # 是否有证书警告
            "page_text_sample": str    # 页面文本样本
        }
    """
    try:
        obstacles = page.evaluate("""() => {
            return {
                dialogs: document.querySelectorAll('.el-dialog, .ant-modal, .modal, [role="dialog"]').length,
                overlays: document.querySelectorAll('.v-modal, .el-overlay, .el-overlay-message-box, .ant-modal-mask, .modal-backdrop').length,
                has_close_button: document.querySelectorAll('.el-dialog__headerbtn, .el-dialog__close, .ant-modal-close, [aria-label="Close"]').length,
                body_text: document.body.innerText.substring(0, 500)
            };
        }""")

        # 检测是否是证书相关警告
        page_text = obstacles.get("body_text", "")
        has_cert_warning = any(keyword in page_text for keyword in ["根证书", "证书", "安全", "certificate"])

        return {
            "dialogs": obstacles.get("dialogs", 0),
            "overlays": obstacles.get("overlays", 0),
            "close_buttons": obstacles.get("has_close_button", 0),
            "has_cert_warning": has_cert_warning,
            "page_text_sample": page_text[:200] if page_text else ""
        }
    except Exception as e:
        logger.warning("obstacle_detection_failed", error=str(e))
        return {
            "dialogs": 0,
            "overlays": 0,
            "close_buttons": 0,
            "has_cert_warning": False,
            "detection_error": str(e)
        }


def _get_suggestions(obstacles: dict) -> list:
    """根据障碍类型提供建议的解决方案"""
    suggestions = []

    if obstacles.get("dialogs", 0) > 0:
        if obstacles.get("close_buttons", 0) > 0:
            suggestions.append("点击对话框关闭按钮: browser[action=act, selector='.el-dialog__headerbtn', click=true]")
        suggestions.append("移除对话框: browser[action=execute_js, code='document.querySelectorAll(\".el-dialog\").forEach(d=>d.remove())']")

    if obstacles.get("has_cert_warning"):
        suggestions.append("检测到根证书提示，这可能需要安装证书或关闭对话框")

    if not suggestions:
        suggestions.append("使用JavaScript直接点击元素: browser[action=execute_js, code='document.querySelector(\"<selector>\").click()']")
        suggestions.append("使用文本选择器: browser[action=act, selector='text=<按钮文本>', click=true]")

    return suggestions


def _take_screenshot_for_analysis(page) -> dict:
    """在操作失败时截图，供 LLM 视觉分析

    Returns:
        {
            "local_path": str,     # 本地文件路径（供 analyze_image 使用）
            "url": str,           # HTTP访问URL（供前端渲染）
            "image_id": str,
            "size_kb": float
        }
        或 None（如果截图失败）
    """
    try:
        screenshot_bytes = page.screenshot(
            full_page=False,
            type="png"
        )

        # 保存到图片缓存
        base64_data = base64.b64encode(screenshot_bytes).decode('utf-8')
        save_result = _get_image_cache().save(base64_data)

        logger.info(
            "screenshot_saved_for_analysis",
            image_id=save_result["image_id"],
            size_kb=save_result["size_kb"]
        )

        return {
            "local_path": save_result["local_path"],
            "url": save_result["url"],
            "image_id": save_result["image_id"],
            "size_kb": save_result["size_kb"]
        }
    except Exception as e:
        logger.warning("screenshot_failed", error=str(e))
        return None


def _handle_fill(page, fields: list, default_ref: str = None, default_selector: str = None, session_id: str = "default") -> str:
    """Handle fill form action (batch operation)

    Args:
        page: Playwright Page instance
        fields: List of form fields to fill
            Each field should have: {"ref": str, "type": str, "value": any}
        default_ref: Default ref if field doesn't specify one
        default_selector: Default selector if field doesn't specify ref
        session_id: Session identifier

    Returns:
        Result message string
    """
    filled_count = 0
    errors = []

    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            errors.append(f"Field {i}: not a dict")
            continue

        field_ref = field.get("ref", default_ref)
        field_type = field.get("type", "text")
        field_value = field.get("value", "")

        # Convert value to string for non-checkbox/radio fields
        if field_type not in ("checkbox", "radio"):
            if isinstance(field_value, bool):
                field_value = "true" if field_value else "false"
            elif field_value is None:
                field_value = ""
            else:
                field_value = str(field_value)

        try:
            if field_ref:
                locator = _get_locator(page, field_ref, None)
            elif default_selector:
                # For fill without ref, we need unique selectors per field
                # This is a simplified approach - in real usage, each field should have ref
                locator = page.locator(default_selector).nth(i)
            else:
                errors.append(f"Field {i}: no ref or selector provided")
                continue

            element_descriptor = field_ref or f"field {i}"

            # Handle checkbox/radio
            if field_type in ("checkbox", "radio"):
                checked = field_value in (True, 1, "1", "true")
                locator.set_checked(checked, timeout=config.DEFAULT_TIMEOUT)
                logger.info(
                    "browser_action_fill_checkbox",
                    ref=field_ref,
                    checked=checked,
                    session_id=session_id
                )

            # Handle select dropdown
            elif field_type == "select":
                if isinstance(field_value, str):
                    values = [field_value]
                elif isinstance(field_value, list):
                    values = field_value
                else:
                    values = [str(field_value)]
                locator.select_option(values, timeout=config.DEFAULT_TIMEOUT)
                logger.info(
                    "browser_action_fill_select",
                    ref=field_ref,
                    values=values,
                    session_id=session_id
                )

            # Handle text input (default)
            else:
                locator.fill(field_value, timeout=config.DEFAULT_TIMEOUT)
                logger.info(
                    "browser_action_fill_text",
                    ref=field_ref,
                    value_length=len(field_value),
                    session_id=session_id
                )

            filled_count += 1

        except Exception as e:
            error_msg = f"Field {element_descriptor}: {str(e)}"
            errors.append(error_msg)
            logger.warning("browser_action_fill_field_failed", field=field, error=str(e))

    # Build result message
    result_parts = [f"Filled {filled_count} form fields"]
    if errors:
        result_parts.append(f"with {len(errors)} errors: {'; '.join(errors[:3])}")
        if len(errors) > 3:
            result_parts.append(f"...and {len(errors) - 3} more errors")

    return ". ".join(result_parts)
