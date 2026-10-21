"""Tool result envelope contract shared by every executor surface.

A tool reports failure through its result envelope (``status="failed"`` /
``success=False``), not by raising. Executors must derive ``is_error`` from
both the execution status *and* this envelope contract so returned-failure
results are never recorded as successes in conversation history, UI styling
or downstream statistics.
"""
from typing import Any, Mapping, Optional


FAILED_RESULT_STATUS = "failed"


def result_envelope_indicates_error(result: Optional[Any]) -> bool:
    """Whether a tool's returned payload declares failure.

    Accepts any payload; only mapping envelopes are inspected. Treat
    ``success is False`` or ``status == "failed"`` as failure — the two
    spellings are used interchangeably by tools in this codebase.
    """
    if not isinstance(result, Mapping):
        return False
    if result.get("success") is False:
        return True
    return result.get("status") == FAILED_RESULT_STATUS
