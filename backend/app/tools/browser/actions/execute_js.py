"""Execute JavaScript Action Handler

Allows executing arbitrary JavaScript code in the browser context.
Useful for:
- Bypassing element blocking issues
- Direct DOM manipulation
- Custom page interactions
- Debugging and testing

v2.3: Fixed 'return var' syntax error - removed 'return' keyword to allow declarations
"""
import structlog
import re

from ..services.frame_target import resolve_frame

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


def _is_statement_script(code: str) -> bool:
    stripped = code.strip()
    return bool(re.match(r"^(var|let|const|for|if|while|switch|try|return|class|function)\b", stripped))


def _expression_code(code: str) -> str:
    return code.strip().rstrip(";")


def handle_execute_js(
    manager,
    code: str,
    session_id: str = "default",
    frame_url: str = None,
    frame_name: str = None,
    frame_index: int = None,
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
    context = resolve_frame(page, frame_url=frame_url, frame_name=frame_name, frame_index=frame_index)

    try:
        # Check if refs parameter is provided
        refs = kwargs.get('refs')

        if refs is not None:
            if _has_arrow_function(code):
                modified_code = re.sub(r'^\(\s*\)\s*=>', '(refs) =>', code.lstrip())
                result = context.evaluate(modified_code, refs)
                refs_provided = True
                logger.info(
                    "browser_execute_js_with_refs_direct",
                    code_length=len(code),
                    refs_count=len(refs) if isinstance(refs, (dict, list)) else 1,
                    session_id=session_id
                )
            elif _is_statement_script(code):
                result = context.evaluate(f"(refs) => {{\n{code}\n}}", refs)
                refs_provided = True
                logger.info(
                    "browser_execute_js_with_refs_script",
                    code_length=len(code),
                    refs_count=len(refs) if isinstance(refs, (dict, list)) else 1,
                    session_id=session_id
                )
            else:
                result = context.evaluate(f"(refs) => ({_expression_code(code)})", refs)
                refs_provided = True
                logger.info(
                    "browser_execute_js_with_refs_expression",
                    code_length=len(code),
                    refs_count=len(refs) if isinstance(refs, (dict, list)) else 1,
                    session_id=session_id
                )
        else:
            if _has_arrow_function(code):
                result = context.evaluate(code)
                refs_provided = False
                logger.info(
                    "browser_execute_js_direct",
                    code_length=len(code),
                    session_id=session_id
                )
            elif _is_statement_script(code):
                result = context.evaluate(f"() => {{\n{code}\n}}")
                refs_provided = False
                logger.info(
                    "browser_execute_js_script",
                    code_length=len(code),
                    session_id=session_id
                )
            else:
                result = context.evaluate(f"() => ({_expression_code(code)})")
                refs_provided = False
                logger.info(
                    "browser_execute_js_expression",
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
