"""Authenticated personal context for the shared assistant runtime."""

from contextlib import contextmanager
from hashlib import sha256

from app.social.assistant_request import begin_assistant_request, end_assistant_request


def web_assistant_recipient(owner):
    if not owner or owner == "system":
        raise PermissionError("无法确认当前用户")
    return "web:account:" + sha256(owner.encode()).hexdigest()


def web_assistant_context(user):
    # Filesystem-safe and collision-resistant; never trust a client user_id.
    memory_id = "web:" + sha256(f"{user.auth_source}\0{user.id}".encode()).hexdigest()
    return assistant_personal_context(memory_id)


def assistant_personal_context(memory_id):
    """Bind a server-resolved identity to its personal documents and memory."""
    from app.agent.memory.memory_store import ImprovedMemoryStore
    from app.social.user_preferences import UserPreferences

    manager = UserPreferences(memory_id)
    return {
        "user_identifier": memory_id,
        "assistant_memory_store": ImprovedMemoryStore(user_id=memory_id, mode="assistant"),
        "assistant_user_preferences": manager.get_preferences() or {},
        "assistant_soul_file_path": str(manager.soul_file.resolve()),
        "assistant_user_file_path": str(manager.user_file.resolve()),
        "assistant_heartbeat_file_path": str(manager.heartbeat_file.resolve()),
        "assistant_soul_context": manager.load_soul_md(),
        "assistant_user_context": manager.load_user_md(),
    }


@contextmanager
def web_assistant_request(session_id, user, message, request_id):
    token = begin_assistant_request(
        session_id, message, request_id, delivery_user_id=web_assistant_recipient(user.id)
    )
    try:
        yield
    finally:
        end_assistant_request(token)
