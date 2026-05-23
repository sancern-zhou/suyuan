"""
Input adapter compatibility shim.

The runtime now relies on native Anthropic tool schemas as the parameter
contract. This module intentionally does not rewrite, infer, normalize, or
validate tool arguments. It remains only to keep old imports stable while the
execution path passes tool_use input through unchanged.
"""

from typing import Any, Dict, Optional, Tuple

import structlog

logger = structlog.get_logger()


class InputValidationError(Exception):
    """Compatibility exception for older callers."""

    def __init__(
        self,
        message: str,
        tool_name: str,
        error_type: str = "VALIDATION_FAILED",
        missing_fields: Optional[list[str]] = None,
        invalid_fields: Optional[Dict[str, str]] = None,
        expected_schema: Optional[Dict[str, Any]] = None,
        suggested_call: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.tool_name = tool_name
        self.error_type = error_type
        self.missing_fields = missing_fields or []
        self.invalid_fields = invalid_fields or {}
        self.expected_schema = expected_schema or {}
        self.suggested_call = suggested_call or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.message,
            "error_type": self.error_type,
            "tool_name": self.tool_name,
            "missing_fields": self.missing_fields,
            "invalid_fields": self.invalid_fields,
            "expected_schema": self.expected_schema,
            "suggested_call": self.suggested_call,
        }


# No tools should be routed through parameter adaptation.
TOOL_RULES: Dict[str, Dict[str, Any]] = {}


class InputAdapterEngine:
    """Pass-through adapter kept for backwards-compatible imports."""

    def __init__(self, tool_rules: Optional[Dict[str, Dict[str, Any]]] = None):
        self.tool_rules = {}
        logger.info("input_adapter_disabled")

    def normalize(
        self,
        tool_name: str,
        raw_args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        logger.debug("input_adapter_passthrough", tool_name=tool_name)
        return raw_args, {
            "status": "disabled",
            "tool_name": tool_name,
            "corrections": [],
            "inferences": [],
            "validations": [],
        }


def normalize_tool_args(
    tool_name: str,
    raw_args: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return tool arguments unchanged."""
    return InputAdapterEngine().normalize(tool_name, raw_args, context)
