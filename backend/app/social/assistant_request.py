"""Turn-local authority, adapted from nanobot's goal_permission (see notices)."""

from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class AssistantRequest:
    session_id: str
    request_id: str
    user_message: str


@dataclass
class _RequestScope:
    request: AssistantRequest
    active: bool = True


_request: ContextVar[_RequestScope | None] = ContextVar("assistant_request", default=None)


def begin_assistant_request(
    session_id: str, user_message: str, request_id: str | None = None
) -> Token:
    """Called only by authenticated human-message ingress, never by tool arguments."""
    if not session_id or not isinstance(user_message, str) or not user_message.strip():
        return _request.set(None)
    return _request.set(
        _RequestScope(AssistantRequest(session_id, request_id or uuid4().hex, user_message))
    )


def end_assistant_request(token: Token) -> None:
    scope = _request.get()
    if scope:
        # Child asyncio tasks inherit ContextVars; revoke their shared scope too.
        scope.active = False
    _request.reset(token)


def require_assistant_request(session_id: str) -> AssistantRequest:
    scope = _request.get()
    if scope is None or not scope.active or scope.request.session_id != session_id:
        raise PermissionError("事项变更需要当前用户交办；后台事件不能代替用户授权")
    return scope.request
