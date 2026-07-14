"""FastAPI dependencies for the conversation catalog."""

from .repository import ConversationCatalogRepository
from .service import ConversationCatalogService


_service = ConversationCatalogService(ConversationCatalogRepository())


def get_conversation_catalog() -> ConversationCatalogService:
    return _service
