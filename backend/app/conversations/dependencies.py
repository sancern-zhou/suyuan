"""FastAPI dependencies for the conversation catalog."""

from .repository import ConversationCatalogRepository
from .service import ConversationCatalogService
from app.agent.resources.resource_service import SessionResourceService


_service = ConversationCatalogService(
    ConversationCatalogRepository(),
    resource_service=SessionResourceService.database(),
)


def get_conversation_catalog() -> ConversationCatalogService:
    return _service
