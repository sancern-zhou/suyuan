"""Social platform integration layer."""

from app.social.events import InboundMessage, OutboundMessage
from app.social.message_bus import MessageBus
from app.social.session_mapper import SessionMapper

__all__ = [
    "InboundMessage",
    "OutboundMessage",
    "MessageBus",
    "SessionMapper",
    "AgentBridge",
]


def __getattr__(name: str):
    """Load AgentBridge only for channel workers that explicitly use it."""
    if name == "AgentBridge":
        from app.social.agent_bridge import AgentBridge

        return AgentBridge
    raise AttributeError(name)
