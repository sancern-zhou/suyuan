"""Web ingress for the same social runtime used by other clients."""

from contextlib import contextmanager
from hashlib import sha256

from app.social.assistant_request import begin_assistant_request, end_assistant_request


def web_assistant_recipient(owner):
    if not owner or owner == "system":
        raise PermissionError("无法确认当前用户")
    return "web:account:" + sha256(owner.encode()).hexdigest()


def social_runtime_mode(mode):
    # The assistant UI ID remains a compatibility alias, not a second runtime.
    return "social" if mode in {"assistant", "social"} else mode


def web_social_context(user):
    from app.agent.memory.memory_store import ImprovedMemoryStore
    from app.social.user_preferences import UserPreferences

    # Filesystem-safe and collision-resistant; never trust a client user_id.
    memory_id = "web:" + sha256(f"{user.auth_source}\0{user.id}".encode()).hexdigest()
    manager = UserPreferences(memory_id)
    return {
        "user_identifier": memory_id,
        "social_memory_store": ImprovedMemoryStore(user_id=memory_id, mode="social"),
        "social_user_preferences": manager.get_preferences() or {},
        "social_soul_file_path": str(manager.soul_file.resolve()),
        "social_user_file_path": str(manager.user_file.resolve()),
        "social_heartbeat_file_path": str(manager.heartbeat_file.resolve()),
        "social_soul_context": manager.load_soul_md(),
        "social_user_context": manager.load_user_md(),
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
