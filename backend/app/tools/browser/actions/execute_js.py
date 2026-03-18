"""Execute JavaScript Action Handler

Allows executing arbitrary JavaScript code in the browser context.
Useful for:
- Bypassing element blocking issues
- Direct DOM manipulation
- Custom page interactions
- Debugging and testing

v2.2: Fixed double arrow function issue - detect if user code already contains () =>
"""
import structlog
import re

logger = structlog.get_logger()


def _has_arrow_function(code: str) -> bool:
    """Check if user code already starts with an arrow function

    Args:
        code: User's JavaScript code

    Returns:
        True if code starts with arrow function syntax
    """
    # Remove leading whitespace
    stripped = code.lstrip()

    # Check for arrow function patterns
    patterns = [
        r'^\(\s*\)\s*=>\s*{',      # () => {
        r'^\w+\s*=>\s*{',          # param => {
        r'^\([^)]+\)\s*=>\s*{',   # (param) => {
    ]

    for pattern in patterns:
        if re.match(pattern, stripped):
            return True

    return False


def handle_execute_js(
    manager,
    code: str,
    session_id: str = "default",
    **kwargs
) -> dict:
    """Execute JavaScript code in the browser context

    Args:
        manager: BrowserManager instance
        code: JavaScript code to execute
        session_id: Session identifier
        **kwargs: Additional parameters, including:
            - refs: Optional refs object to pass to JavaScript code

    Returns:
        {
            "code": str,           # Executed code
            "result": any,          # Return value from JavaScript
            "type": str,           # Result type (undefined/null/boolean/number/string/object)
            "refs_provided": bool  # Whether refs were passed to the code
        }
    """
    page = manager.get_active_page(session_id)

    try:
        # Check if refs parameter is provided
        refs = kwargs.get('refs')

        if refs is not None:
            # Execute JavaScript with refs parameter
            # The user code should expect (refs) as parameter
            # Check if user code already has arrow function
            if _has_arrow_function(code):
                # User code already has arrow function, pass directly with parameter
                # Replace () => with (refs) =>
                modified_code = re.sub(r'^\(\s*\)\s*=>', '(refs) =>', code.lstrip())
                result = page.evaluate(modified_code, refs)
                refs_provided = True
                logger.info(
                    "browser_execute_js_with_refs_direct",
                    code_length=len(code),
                    refs_count=len(refs) if isinstance(refs, (dict, list)) else 1,
                    session_id=session_id
                )
            else:
                # Wrap user code with arrow function
                result = page.evaluate(f"(refs) => {{ {code} }}", refs)
                refs_provided = True
                logger.info(
                    "browser_execute_js_with_refs_wrapped",
                    code_length=len(code),
                    refs_count=len(refs) if isinstance(refs, (dict, list)) else 1,
                    session_id=session_id
                )
        else:
            # Execute JavaScript without parameters
            if _has_arrow_function(code):
                # User code already has arrow function, evaluate directly
                result = page.evaluate(code)
                refs_provided = False
                logger.info(
                    "browser_execute_js_direct",
                    code_length=len(code),
                    session_id=session_id
                )
            else:
                # Wrap user code with arrow function
                result = page.evaluate(f"() => {{ {code} }}")
                refs_provided = False
                logger.info(
                    "browser_execute_js_wrapped",
                    code_length=len(code),
                    session_id=session_id
                )

        # Determine result type
        result_type = type(result).__name__
        if result is None:
            result_type = "null"
        elif isinstance(result, bool):
            result_type = "boolean"
        elif isinstance(result, (int, float)):
            result_type = "number"
        elif isinstance(result, str):
            result_type = "string"
        elif isinstance(result, list):
            result_type = "array"
        elif isinstance(result, dict):
            result_type = "object"

        logger.info(
            "browser_execute_js_success",
            code_length=len(code),
            result_type=result_type,
            refs_provided=refs_provided,
            session_id=session_id
        )

        return {
            "code": code,
            "result": result,
            "type": result_type,
            "refs_provided": refs_provided
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(
            "browser_execute_js_failed",
            code=code[:100],
            error=error_msg,
            refs_provided=refs is not None,
            session_id=session_id
        )

        # Return error information
        return {
            "code": code,
            "result": None,
            "type": "error",
            "error": error_msg,
            "refs_provided": refs is not None
        }
