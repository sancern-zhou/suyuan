"""FastAPI dependencies for the conversation catalog."""

from .repository import ConversationCatalogRepository
from .service import ConversationCatalogService
from app.agent.resources.service import get_session_resource_manifest_service


_service = ConversationCatalogService(
    ConversationCatalogRepository(),
    resource_manifest_service=get_session_resource_manifest_service(),
)


def get_conversation_catalog() -> ConversationCatalogService:
    return _service
